'use strict';

/**
 * Promemoria — processo principale Electron.
 *
 * Responsabilità:
 *  - avviare il backend (in sviluppo: uvicorn dal venv; in produzione: eseguibile impacchettato);
 *  - mostrare la finestra dell'applicazione;
 *  - restare nella tray anche a finestra chiusa, così gli avvisi continuano ad arrivare;
 *  - interrogare periodicamente il backend e mostrare le notifiche native di Windows;
 *  - controllare la presenza di aggiornamenti.
 */

const {
  app,
  BrowserWindow,
  Tray,
  Menu,
  Notification,
  ipcMain,
  screen,
  shell,
  nativeImage,
} = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const DEV = process.env.PROMEMORIA_DEV === '1';
// Schema dei collegamenti delle notifiche. Distinto in sviluppo per la stessa
// ragione dell'identità: non rubare all'app installata i propri collegamenti.
const PROTOCOL = app.isPackaged ? 'promemoria' : 'promemoria-sviluppo';
const PORT = Number(process.env.PROMEMORIA_PORT || 8010);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const POLL_MS = 30_000;

let mainWindow = null;
let tray = null;
let backend = null;
let pollTimer = null;
let quitting = false;
let interfacciaPronta = false;
let rottaInAttesa = null;
//: Aggiornamento scaricato e in attesa di essere applicato.
let aggiornamentoPronto = false;
//: Misura dell'icona della tray su questo schermo: serve a ridisegnarla con e
//: senza bollino senza ricalcolare ogni volta il fattore di scala.
let dimensioneTray = 16;
//: Ultimo stato applicato, per non ripetere lo stesso lavoro ogni mezzo minuto.
let segnalazione = { accesa: false, count: 0 };

//: Schemi riconosciuti nei collegamenti delle notifiche. Quelli `scadenzario://`
//: restano validi: un toast mostrato prima dell'aggiornamento è ancora sullo
//: schermo, e cliccarlo deve portare da qualche parte.
const PROTOCOLLI = [PROTOCOL, 'scadenzario', 'scadenzario-sviluppo'];

/**
 * Ricava la rotta dell'interfaccia da un collegamento `promemoria://`.
 *
 * Windows non consegna l'attivazione al processo già in esecuzione: lancia
 * l'eseguibile una seconda volta passando il collegamento fra gli argomenti.
 * Quel lancio muore subito contro il lucchetto di istanza singola, ma prima
 * consegna i suoi argomenti a chi il lucchetto ce l'ha — ed è lì che questa
 * funzione li legge.
 */
function rottaDaArgomenti(argomenti) {
  const collegamento = argomenti.find((a) => PROTOCOLLI.some((p) => a.startsWith(`${p}://`)));
  if (!collegamento) return null;
  try {
    // promemoria://promemoria/12  ->  /promemoria/12
    const url = new URL(collegamento);
    const rotta = `/${url.hostname}${url.pathname}`.replace(/\/+$/, '');
    return rotta || null;
  } catch {
    return null;
  }
}

// Una sola istanza: al secondo avvio si riporta in primo piano quella esistente.
const istanzaUnica = app.requestSingleInstanceLock();
if (!istanzaUnica) {
  app.quit();
} else {
  app.on('second-instance', (_event, argomenti) => showWindow(rottaDaArgomenti(argomenti)));
}

// ---------------------------------------------------------------- backend

function backendCommand() {
  if (DEV) {
    const python = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
    return {
      command: python,
      args: ['-m', 'uvicorn', 'app.main:app', '--port', String(PORT)],
      cwd: path.join(__dirname, '..', 'backend'),
    };
  }
  const exe = path.join(process.resourcesPath, 'backend', 'promemoria-backend.exe');
  return { command: exe, args: ['--port', String(PORT)], cwd: path.dirname(exe) };
}

function startBackend() {
  const { command, args, cwd } = backendCommand();
  if (!fs.existsSync(command)) {
    console.error('Backend non trovato:', command);
    return;
  }

  backend = spawn(command, args, { cwd, windowsHide: true });
  backend.stdout.on('data', (d) => console.log('[backend]', String(d).trim()));
  backend.stderr.on('data', (d) => console.log('[backend]', String(d).trim()));
  backend.on('exit', (code) => {
    console.log('[backend] terminato con codice', code);
    backend = null;
  });
}

function stopBackend() {
  if (backend && !backend.killed) {
    backend.kill();
    backend = null;
  }
}

/** Attende che il backend risponda prima di caricare l'interfaccia. */
async function waitForBackend(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE_URL}/api/health`);
      if (res.ok) return true;
    } catch {
      /* non ancora pronto */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

// ---------------------------------------------------------------- finestra

function iconPath(avviso = false) {
  const file = path.join(__dirname, 'assets', avviso ? 'icon-avviso.ico' : 'icon.ico');
  return fs.existsSync(file) ? file : undefined;
}

// L'.ico contiene la stessa icona disegnata a più misure (16, 24, 32, ... 256).
// Caricandolo per intero Electron tiene la più grande e lascia che sia Windows
// a rimpicciolirla: nella tray, che è alta 16 punti, la "P" si impasta e non si
// riconosce più. Qui peschiamo dal file la misura giusta, quella disegnata
// apposta per quello spazio — alle misure piccole è la variante senza spunta
// (vedi assets/make_icon.py).
function icoRepresentation(file, wanted) {
  const data = fs.readFileSync(file);
  if (data.length < 6 || data.readUInt16LE(2) !== 1) return null;

  const entries = [];
  for (let i = 0; i < data.readUInt16LE(4); i += 1) {
    const dir = 6 + 16 * i;
    if (dir + 16 > data.length) break;
    entries.push({
      size: data.readUInt8(dir) || 256,
      length: data.readUInt32LE(dir + 8),
      offset: data.readUInt32LE(dir + 12),
    });
  }
  entries.sort((a, b) => a.size - b.size);

  const entry = entries.find((e) => e.size >= wanted) || entries[entries.length - 1];
  if (!entry || entry.offset + entry.length > data.length) return null;

  // Le misure sono salvate come PNG: il buffer si può passare così com'è.
  const bytes = data.subarray(entry.offset, entry.offset + entry.length);
  if (bytes.subarray(0, 4).toString('latin1') !== '\x89PNG') return null;

  const image = nativeImage.createFromBuffer(bytes);
  return image.isEmpty() ? null : image;
}

function iconImage(wanted, avviso = false) {
  const file = iconPath(avviso) || iconPath();
  if (!file) return nativeImage.createEmpty();
  return icoRepresentation(file, wanted) || nativeImage.createFromPath(file);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    show: false,
    icon: iconPath(),
    title: 'Promemoria',
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });

  // Di norma l'interfaccia è quella compilata e servita dal backend stesso.
  // Per lavorare sul frontend con ricaricamento a caldo:
  //   $env:PROMEMORIA_UI = 'http://localhost:4300'
  mainWindow.loadURL(process.env.PROMEMORIA_UI || BASE_URL);
  mainWindow.once('ready-to-show', () => portaInPrimoPiano());

  // Ricaricando la pagina l'ascoltatore va perso e si riparte dall'attesa.
  // Vale solo per un vero cambio di documento: `did-start-loading` sembrava
  // l'evento giusto ma è lo spinner della scheda, e gira a ogni richiesta di
  // rete dell'interfaccia — col polling delle notifiche l'app risultava non
  // pronta quasi sempre, e le rotte restavano in coda senza mai partire.
  mainWindow.webContents.on('did-start-navigation', (details) => {
    if (details.isMainFrame && !details.isSameDocument) {
      interfacciaPronta = false;
    }
  });

  // Tornando sulla finestra il quadro può essere cambiato: si ricontrolla,
  // così il bollino non resta acceso su avvisi già guardati altrove.
  mainWindow.on('focus', () => void aggiornaSegnalazione());

  // La X chiude solo la finestra: l'app resta in tray e continua ad avvisare.
  mainWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  // Tasto destro nei campi di testo: taglia, copia, incolla.
  //
  // Senza questo il menu contestuale non esiste — Electron non ne mette uno di
  // suo — e chi incolla col tasto destro, cioè quasi tutti, conclude che
  // l'applicazione non lo permetta. Sulla schermata di configurazione significa
  // ricopiare a mano una stringa di connessione lunga e piena di caratteri
  // insidiosi, con gli errori di battitura che ne seguono.
  mainWindow.webContents.on('context-menu', (_event, params) => {
    const modificabile = params.isEditable;
    const selezione = params.selectionText.trim().length > 0;
    if (!modificabile && !selezione) return;

    Menu.buildFromTemplate([
      { role: 'cut', label: 'Taglia', enabled: modificabile && selezione },
      { role: 'copy', label: 'Copia', enabled: selezione },
      { role: 'paste', label: 'Incolla', enabled: modificabile },
      { type: 'separator' },
      { role: 'selectAll', label: 'Seleziona tutto' },
    ]).popup({ window: mainWindow });
  });

  // I link esterni si aprono nel browser, non dentro l'applicazione.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

/**
 * Mostra la finestra e le fa arrivare davvero il fuoco della tastiera.
 *
 * `show()` da solo non basta. Windows protegge chi sta lavorando dalle
 * finestre che rubano la tastiera: se in quel momento il primo piano
 * appartiene a un altro processo — l'installer appena finito, Esplora
 * risorse, il programma da cui l'app è stata lanciata — il passaggio del
 * fuoco viene *rifiutato in silenzio*. La finestra compare, si può cliccare,
 * le tendine si aprono col mouse, ma i tasti continuano ad andare altrove: nei
 * campi di testo non si scrive e sembra che l'applicazione sia rotta.
 *
 * Il giro da cima-a-tutto e ritorno passa da una chiamata che Windows concede
 * anche quando nega il primo piano, e trascina con sé l'attivazione. Costa
 * niente e sui computer dove il fuoco arriva da sé non si nota.
 */
function portaInPrimoPiano() {
  if (mainWindow === null) return;
  if (mainWindow.isMinimized()) mainWindow.restore();

  mainWindow.show();
  mainWindow.setAlwaysOnTop(true);
  mainWindow.setAlwaysOnTop(false);
  mainWindow.focus();
}

function showWindow(route) {
  if (mainWindow === null) {
    createWindow();
  } else {
    portaInPrimoPiano();
  }
  if (!route) return;

  // A interfaccia non ancora avviata il messaggio non troverebbe nessuno ad
  // ascoltarlo: si tiene da parte e parte appena il preload si fa vivo.
  if (interfacciaPronta) {
    mainWindow.webContents.send('navigate', route);
  } else {
    rottaInAttesa = route;
  }
}

ipcMain.on('promemoria-guardati', () => void aggiornaSegnalazione());

ipcMain.on('interfaccia-pronta', (event) => {
  if (mainWindow === null || event.sender !== mainWindow.webContents) return;
  interfacciaPronta = true;
  if (rottaInAttesa) {
    mainWindow.webContents.send('navigate', rottaInAttesa);
    rottaInAttesa = null;
  }
});

function menuTray() {
  return Menu.buildFromTemplate([
    { label: 'Apri Promemoria', click: () => showWindow() },
    { label: 'Controlla adesso', click: () => runCycleNow() },
    { type: 'separator' },
    // La versione in chiaro: quando una postazione si comporta diversamente
    // dalle altre, è la prima cosa da sapere e nessuno sa dove guardare.
    { label: `Versione ${app.getVersion()}`, enabled: false },
    ...(aggiornamentoPronto
      ? [{ label: 'Riavvia e aggiorna', click: () => installaAggiornamento() }]
      : []),
    { type: 'separator' },
    {
      label: "Avvia all'avvio di Windows",
      type: 'checkbox',
      checked: app.getLoginItemSettings().openAtLogin,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked, openAsHidden: true }),
    },
    { type: 'separator' },
    {
      label: 'Esci',
      click: () => {
        quitting = true;
        app.quit();
      },
    },
  ]);
}

function createTray() {
  const { scaleFactor } = screen.getPrimaryDisplay();
  dimensioneTray = Math.round(16 * scaleFactor);
  tray = new Tray(iconImage(dimensioneTray));
  tray.setToolTip(`Promemoria ${app.getVersion()}`);
  tray.setContextMenu(menuTray());
  tray.on('double-click', () => showWindow());
}

// ------------------------------------------------------------- notifiche

async function runCycleNow() {
  try {
    await fetch(`${BASE_URL}/api/scheduler/run`, { method: 'POST' });
    await pollNotifications();
  } catch (err) {
    console.error('Ciclo manuale fallito:', err);
  }
}

function xmlEscape(text) {
  const replacements = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' };
  return String(text ?? '').replace(/[&<>"']/g, (c) => replacements[c]);
}

let logoToast;

/**
 * Il logo del toast, come PNG grande scritto una volta sola su disco.
 *
 * Passando l'.ico Windows sceglie da sé quale misura usarne, e sceglie male:
 * prende una delle piccole e la ingrandisce fino a sgranarla. Qui si estrae la
 * misura maggiore e si dà a Windows solo quella, che deve semmai rimpicciolire
 * — operazione che invece gli riesce bene.
 */
function logoToastPath() {
  if (logoToast !== undefined) return logoToast;
  logoToast = null;

  const file = iconPath();
  const image = file ? icoRepresentation(file, 256) : null;
  if (image) {
    const destinazione = path.join(app.getPath('userData'), 'toast-logo.png');
    try {
      fs.writeFileSync(destinazione, image.toPNG());
      logoToast = destinazione;
    } catch (err) {
      console.error('Logo del toast non scritto:', err);
    }
  }
  return logoToast;
}

/**
 * Compone il toast di Windows in XML invece di lasciarlo costruire a Electron.
 *
 * Un toast normale sparisce dopo pochi secondi e finisce nel Centro notifiche:
 * chi in quel momento non sta guardando lo schermo si perde l'avviso. Con
 * `scenario="reminder"` Windows lo tiene in vista finché non lo si tocca —
 * come fanno le sveglie e i promemoria del calendario.
 *
 * Lo scenario pretende almeno un pulsante, altrimenti Windows scarta il toast
 * senza mostrarlo: da qui le due azioni. «Ignora» è quella di sistema (il
 * valore `dismiss` è riservato e il testo lo mette Windows nella sua lingua),
 * e chiude l'avviso senza portare l'app in primo piano.
 *
 * L'attivazione passa dal protocollo invece che da `foreground` perché di un
 * clic su un pulsante Electron non riceve notizia: l'app tornava in primo
 * piano sulla pagina dov'era rimasta, non sulla scadenza. Il collegamento
 * `scadenzario://` invece porta con sé la destinazione, e vale tanto per il
 * corpo del toast quanto per il pulsante.
 */
function reminderToastXml(item) {
  const logo = logoToastPath();
  const image = logo
    ? `<image placement="appLogoOverride" src="file:///${logo.replace(/\\/g, '/')}"/>`
    : '';
  const collegamento = `${PROTOCOL}://promemoria`;

  return `<toast scenario="reminder" activationType="protocol" launch="${collegamento}">
  <visual>
    <binding template="ToastGeneric">
      <text>${xmlEscape(item.title)}</text>
      <text>${xmlEscape(item.body)}</text>
      ${image}
    </binding>
  </visual>
  <actions>
    <action content="Apri promemoria" activationType="protocol" arguments="${collegamento}"/>
    <action content="" arguments="dismiss" activationType="system"/>
  </actions>
</toast>`;
}

/**
 * Accende o spegne la segnalazione sulla barra delle applicazioni.
 *
 * Un toast si può ignorare con un clic, e a quel punto sparisce per sempre:
 * chi stava facendo altro perde l'avviso senza accorgersene. Finché resta
 * qualcosa di imminente che nessuno ha guardato, l'applicazione continua a
 * dirlo — in modo discreto ma presente.
 *
 * Tre segnali diversi perché tre sono i posti in cui l'app può trovarsi:
 *
 *  - il **lampeggio** del pulsante attira l'occhio, ma solo se la finestra
 *    non è già davanti: farlo lampeggiare mentre ci si sta lavorando sarebbe
 *    solo fastidio;
 *  - il **bollino** sul pulsante resta anche dopo che il lampeggio è finito,
 *    ed è quello che sopravvive finché non si guarda davvero;
 *  - l'**icona nella tray** col bollino copre il caso in cui la finestra è
 *    chiusa: lì il pulsante sulla barra non esiste proprio, e senza questa
 *    non resterebbe alcun segno.
 */
function applicaSegnalazione(count, titolo) {
  const accesa = count > 0;
  const cambiata = accesa !== segnalazione.accesa || count !== segnalazione.count;
  segnalazione = { accesa, count };

  if (tray !== null && cambiata) {
    tray.setImage(iconImage(dimensioneTray, accesa));
    tray.setToolTip(
      accesa
        ? `Promemoria — ${count === 1 ? '1 avviso' : `${count} avvisi`} da guardare`
        : 'Promemoria',
    );
  }

  if (mainWindow === null) return;

  const bollino = path.join(__dirname, 'assets', 'badge.png');
  if (accesa && fs.existsSync(bollino)) {
    mainWindow.setOverlayIcon(nativeImage.createFromPath(bollino), titolo || 'Avvisi da guardare');
  } else {
    mainWindow.setOverlayIcon(null, '');
  }

  // Il lampeggio si chiede solo a finestra non in primo piano: Windows lo
  // interrompe da sé appena la finestra viene attivata.
  mainWindow.flashFrame(accesa && !mainWindow.isFocused());
}

/** Chiede al backend se c'è qualcosa di imminente rimasto senza risposta. */
async function aggiornaSegnalazione() {
  try {
    const res = await fetch(`${BASE_URL}/api/notifications/attention`);
    if (!res.ok) return;
    const stato = await res.json();
    applicaSegnalazione(stato.count, stato.title);
  } catch (err) {
    // Backend non ancora pronto o in riavvio: si riprova al giro successivo.
  }
}

/**
 * Chiede al backend gli avvisi consegnati e non ancora mostrati su questa
 * postazione, ne mostra il toast nativo e li marca come mostrati.
 */
async function pollNotifications() {
  if (!Notification.isSupported()) return;

  try {
    const res = await fetch(`${BASE_URL}/api/notifications/to-display`);
    if (!res.ok) return;
    const items = await res.json();

    for (const item of items) {
      const toast = new Notification({
        title: item.title,
        body: item.body,
        icon: iconPath(),
        // `urgency` vale su Linux; su Windows la permanenza la decide il toastXml.
        urgency: item.severity === 'danger' || item.severity === 'critical' ? 'critical' : 'normal',
        toastXml: process.platform === 'win32' ? reminderToastXml(item) : undefined,
      });
      // Fuori da Windows non c'è il toastXml e l'attivazione arriva di qui.
      toast.on('click', () => showWindow('/promemoria'));
      toast.show();

      await fetch(`${BASE_URL}/api/notifications/${item.id}/displayed`, { method: 'POST' });
    }
  } catch (err) {
    console.error('Lettura notifiche fallita:', err);
  }

  await aggiornaSegnalazione();
}

function startPolling() {
  if (pollTimer === null) {
    pollTimer = setInterval(pollNotifications, POLL_MS);
    void pollNotifications();
  }
}

// --------------------------------------------------------- aggiornamenti

/**
 * Applica l'aggiornamento già scaricato, chiudendo davvero l'applicazione.
 *
 * `quitAndInstall` passa dal ciclo di uscita normale, e la X di questa app non
 * chiude ma nasconde: senza alzare `quitting` l'installer resterebbe in attesa
 * di una chiusura che non arriva.
 */
function installaAggiornamento() {
  try {
    quitting = true;
    require('electron-updater').autoUpdater.quitAndInstall();
  } catch (err) {
    console.error('Installazione aggiornamento fallita:', err);
    quitting = false;
  }
}

function setupUpdater() {
  if (DEV || !app.isPackaged) return;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.on('update-downloaded', () => {
      // L'installazione alla chiusura da sola non basta: l'applicazione vive
      // nella tray e su molte postazioni non viene mai chiusa davvero, così la
      // versione nuova resta scaricata e mai applicata per settimane. Con un
      // database condiviso questo si paga: appena una postazione applica una
      // migrazione, quelle rimaste indietro non riescono più a collegarsi.
      aggiornamentoPronto = true;
      if (tray) tray.setContextMenu(menuTray());

      const avviso = new Notification({
        title: 'Aggiornamento di Promemoria pronto',
        body: 'Clicca qui per riavviare e applicarlo adesso, oppure verrà installato alla prossima chiusura.',
      });
      avviso.on('click', () => installaAggiornamento());
      avviso.show();
    });
    autoUpdater.checkForUpdatesAndNotify();
    // Ricontrolla una volta al giorno per le installazioni sempre aperte.
    setInterval(() => autoUpdater.checkForUpdatesAndNotify(), 24 * 60 * 60 * 1000);
  } catch (err) {
    console.error('Aggiornamento non disponibile:', err);
  }
}

// ------------------------------------------------------------ ciclo vita

app.whenReady().then(async () => {
  // La seconda istanza serve solo a consegnare il collegamento a chi è già in
  // esecuzione: senza questa uscita farebbe in tempo ad avviare un backend
  // suo, che poi litiga per la porta, prima che `app.quit()` la fermi.
  if (!istanzaUnica) return;

  // Windows non prende l'icona del pulsante nella barra dalla finestra, ma da
  // quella che ha in cache per questa identità. In sviluppo il processo è
  // electron.exe: se si presentasse con l'identità dell'app installata,
  // Windows assocerebbe a "it.scadenzario.desktop" l'icona di Electron —
  // l'atomo — e la terrebbe poi anche per l'app vera. Da qui un'identità
  // separata quando non siamo impacchettati.
  //
  // L'identità resta "scadenzario" anche ora che l'app si chiama Promemoria:
  // è la stessa dell'`appId` di electron-builder, e cambiarla farebbe
  // installare la nuova versione **accanto** alla vecchia invece che al suo
  // posto, lasciando due applicazioni sulle postazioni. È un identificatore
  // interno: nessuno lo legge.
  app.setAppUserModelId(app.isPackaged ? 'it.scadenzario.desktop' : 'it.scadenzario.desktop.sviluppo');
  registraProtocollo();
  startBackend();
  createTray();
  await waitForBackend();
  createWindow();

  // L'app potrebbe essere stata avviata proprio dal clic su una notifica,
  // se non era già in esecuzione.
  const rotta = rottaDaArgomenti(process.argv);
  if (rotta) showWindow(rotta);

  startPolling();
  setupUpdater();
});

/**
 * Insegna a Windows chi apre i collegamenti `scadenzario://`.
 *
 * Non impacchettati l'eseguibile è electron.exe, che da solo non saprebbe
 * quale progetto aprire: gli si passa anche la cartella, come farebbe `npm
 * run dev`.
 */
function registraProtocollo() {
  if (app.isPackaged) {
    app.setAsDefaultProtocolClient(PROTOCOL);
  } else {
    app.setAsDefaultProtocolClient(PROTOCOL, process.execPath, [path.resolve(process.argv[1])]);
  }
}

app.on('window-all-closed', () => {
  // Volutamente niente quit: l'app vive nella tray.
});

app.on('before-quit', () => {
  quitting = true;
  if (pollTimer !== null) clearInterval(pollTimer);
  stopBackend();
});
