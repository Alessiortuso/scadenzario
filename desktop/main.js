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

const { app, BrowserWindow, Tray, Menu, Notification, shell, nativeImage } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const DEV = process.env.SCADENZARIO_DEV === '1';
const PORT = Number(process.env.SCADENZARIO_PORT || 8010);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const POLL_MS = 30_000;

let mainWindow = null;
let tray = null;
let backend = null;
let pollTimer = null;
let quitting = false;

// Una sola istanza: al secondo avvio si riporta in primo piano quella esistente.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => showWindow());
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
  if (route) {
    mainWindow.webContents.send('navigate', route);
  }
}

function createTray() {
  const icon = iconPath();
  tray = new Tray(icon ? nativeImage.createFromPath(icon) : nativeImage.createEmpty());
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
        urgency: item.severity === 'danger' || item.severity === 'critical' ? 'critical' : 'normal',
      });
      toast.on('click', () => showWindow(`/scadenze/${item.deadline_id}`));
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
  app.setAppUserModelId('it.scadenzario.desktop');
  startBackend();
  createTray();
  await waitForBackend();
  createWindow();
  startPolling();
  setupUpdater();
});

app.on('window-all-closed', () => {
  // Volutamente niente quit: l'app vive nella tray.
});

app.on('before-quit', () => {
  quitting = true;
  if (pollTimer !== null) clearInterval(pollTimer);
  stopBackend();
});
