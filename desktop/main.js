'use strict';

/**
 * Scadenzario — processo principale Electron.
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

const DEV = process.env.SCADENZARIO_DEV === '1';
// Schema dei collegamenti delle notifiche. Distinto in sviluppo per la stessa
// ragione dell'identità: non rubare all'app installata i propri collegamenti.
const PROTOCOL = app.isPackaged ? 'scadenzario' : 'scadenzario-sviluppo';
const PORT = Number(process.env.SCADENZARIO_PORT || 8010);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const POLL_MS = 30_000;

let mainWindow = null;
let tray = null;
let backend = null;
let pollTimer = null;
let quitting = false;
let interfacciaPronta = false;
let rottaInAttesa = null;

/**
 * Ricava la rotta dell'interfaccia da un collegamento `scadenzario://`.
 *
 * Windows non consegna l'attivazione al processo già in esecuzione: lancia
 * l'eseguibile una seconda volta passando il collegamento fra gli argomenti.
 * Quel lancio muore subito contro il lucchetto di istanza singola, ma prima
 * consegna i suoi argomenti a chi il lucchetto ce l'ha — ed è lì che questa
 * funzione li legge.
 */
function rottaDaArgomenti(argomenti) {
  const collegamento = argomenti.find((a) => a.startsWith(`${PROTOCOL}://`));
  if (!collegamento) return null;
  try {
    // scadenzario://scadenze/12  ->  /scadenze/12
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
  const exe = path.join(process.resourcesPath, 'backend', 'scadenzario-backend.exe');
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

function iconPath() {
  const file = path.join(__dirname, 'assets', 'icon.ico');
  return fs.existsSync(file) ? file : undefined;
}

// L'.ico contiene la stessa icona disegnata a più misure (16, 24, 32, ... 256).
// Caricandolo per intero Electron tiene la più grande e lascia che sia Windows
// a rimpicciolirla: nella tray, che è alta 16 punti, la "S" si impasta e non si
// riconosce più. Qui peschiamo dal file la misura giusta, quella disegnata
// apposta per quello spazio.
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

function iconImage(wanted) {
  const file = iconPath();
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
    title: 'Scadenzario',
    autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  });

  // Di norma l'interfaccia è quella compilata e servita dal backend stesso.
  // Per lavorare sul frontend con ricaricamento a caldo:
  //   $env:SCADENZARIO_UI = 'http://localhost:4300'
  mainWindow.loadURL(process.env.SCADENZARIO_UI || BASE_URL);
  mainWindow.once('ready-to-show', () => mainWindow.show());

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

  // La X chiude solo la finestra: l'app resta in tray e continua ad avvisare.
  mainWindow.on('close', (event) => {
    if (!quitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  // I link esterni si aprono nel browser, non dentro l'applicazione.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

function showWindow(route) {
  if (mainWindow === null) {
    createWindow();
  } else {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
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

ipcMain.on('interfaccia-pronta', (event) => {
  if (mainWindow === null || event.sender !== mainWindow.webContents) return;
  interfacciaPronta = true;
  if (rottaInAttesa) {
    mainWindow.webContents.send('navigate', rottaInAttesa);
    rottaInAttesa = null;
  }
});

function createTray() {
  const { scaleFactor } = screen.getPrimaryDisplay();
  tray = new Tray(iconImage(Math.round(16 * scaleFactor)));
  tray.setToolTip('Scadenzario');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Apri Scadenzario', click: () => showWindow() },
      { label: 'Controlla scadenze adesso', click: () => runCycleNow() },
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
    ]),
  );
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
  const collegamento = `${PROTOCOL}://scadenze`;

  return `<toast scenario="reminder" activationType="protocol" launch="${collegamento}">
  <visual>
    <binding template="ToastGeneric">
      <text>${xmlEscape(item.title)}</text>
      <text>${xmlEscape(item.body)}</text>
      ${image}
    </binding>
  </visual>
  <actions>
    <action content="Apri scadenza" activationType="protocol" arguments="${collegamento}"/>
    <action content="" arguments="dismiss" activationType="system"/>
  </actions>
</toast>`;
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
      toast.on('click', () => showWindow('/scadenze'));
      toast.show();

      await fetch(`${BASE_URL}/api/notifications/${item.id}/displayed`, { method: 'POST' });
    }
  } catch (err) {
    console.error('Lettura notifiche fallita:', err);
  }
}

function startPolling() {
  if (pollTimer === null) {
    pollTimer = setInterval(pollNotifications, POLL_MS);
    void pollNotifications();
  }
}

// --------------------------------------------------------- aggiornamenti

function setupUpdater() {
  if (DEV || !app.isPackaged) return;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.on('update-downloaded', () => {
      new Notification({
        title: 'Scadenzario aggiornato',
        body: "La nuova versione verrà applicata alla prossima chiusura dell'applicazione.",
      }).show();
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
