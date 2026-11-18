const { app, BrowserWindow, ipcMain, shell, Tray, Menu, nativeImage } = require('electron');
const path = require('node:path');
const native = require('./native.cjs');
const powerPresence = require('./power-presence.cjs');
const updater = require('./updater.cjs');

const isDev = !app.isPackaged;
let mainWindow = null;
let tray = null;
let isQuitting = false;

function appIconPath() {
  const fs = require('node:fs');
  const candidates = [
    // Packaged install: next to the .exe (NSIS shortcut uses {app}\\app.ico)
    path.join(path.dirname(process.execPath || ''), 'app.ico'),
    // Packaged: resources/app.ico (extraResources)
    path.join(process.resourcesPath || '', 'app.ico'),
    path.join(process.resourcesPath || '', 'icon.ico'),
    path.join(process.resourcesPath || '', 'build', 'icon.ico'),
    // Dev
    path.join(__dirname, '..', 'build', 'icon.ico'),
    path.join(__dirname, '..', 'build', 'icon.png'),
  ];
  for (const p of candidates) {
    try {
      if (p && fs.existsSync(p)) return p;
    } catch {
      // ignore
    }
  }
  return undefined;
}

function uiIndexPath() {
  // Packaged: app.asar/dist/index.html (via app.getAppPath()).
  // Dev packaged-path fallback: electron/../dist/index.html.
  return path.join(app.getAppPath(), 'dist', 'index.html');
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function createTray() {
  if (tray) return;
  const iconFile = appIconPath();
  let image = iconFile ? nativeImage.createFromPath(iconFile) : nativeImage.createEmpty();
  if (image.isEmpty()) {
    // 16x16 placeholder so Tray still constructs on Windows
    image = nativeImage.createFromDataURL(
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAYAAAAfSC3RAAAAHElEQVQoz2NgGAWjYBSMglEwCkbBKBgFo4D6AQB8AAH/YYvH1gAAAABJRU5ErkJggg=='
    );
  }
  tray = new Tray(image);
  tray.setToolTip('WorkPulse Employee — tracking stays on while in tray');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Open WorkPulse', click: () => showMainWindow() },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          isQuitting = true;
          try {
            powerPresence.recordAppCloseBreak();
          } catch (err) {
            console.warn('[tray] recordAppCloseBreak failed:', err);
          }
          app.quit();
        },
      },
    ])
  );
  tray.on('double-click', () => showMainWindow());
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 440,
    height: 760,
    minWidth: 380,
    minHeight: 640,
    title: 'WorkPulse Employee',
    icon: appIconPath(),
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  const win = mainWindow;
  const reveal = () => {
    if (!win.isDestroyed() && !win.isVisible()) win.show();
  };
  win.once('ready-to-show', reveal);
  // If HTML/assets fail to load, still show a window instead of staying invisible.
  setTimeout(reveal, 4000);

  // Closing the X hides to tray — idle/break tracking must keep running.
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      win.hide();
      return;
    }
    try {
      powerPresence.recordAppCloseBreak();
    } catch (err) {
      console.warn('[quit] recordAppCloseBreak failed:', err);
    }
  });

  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error('[ui] did-fail-load', { code, desc, url });
    reveal();
    const message = encodeURIComponent(
      `WorkPulse could not load its UI (${desc || code}). Reinstall the latest setup, or contact support.`
    );
    win.loadURL(`data:text/html,<h3 style="font-family:sans-serif;padding:24px">WorkPulse failed to open</h3><p style="font-family:sans-serif;padding:0 24px;color:#334155">${message}</p>`);
  });

  if (isDev) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL || 'http://localhost:1420');
  } else {
    const indexHtml = uiIndexPath();
    win.loadFile(indexHtml).catch((err) => {
      console.error('[ui] loadFile failed:', indexHtml, err);
      reveal();
    });
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

async function catchUpPowerBootEvents() {
  const session = powerPresence.getSession();
  if (!session.signedIn || !session.deviceId) return;

  const watermark = powerPresence.getWatermark();
  const since =
    watermark.lastProcessedAt ||
    new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();

  let events = [];
  try {
    events = await native.getPowerBootEvents(since);
  } catch (err) {
    console.warn('[power] event-log catch-up failed:', err);
    return;
  }

  let latest = since;
  for (const ev of events) {
    if (ev.occurred_at <= since) continue;
    powerPresence.enqueuePowerEvent(ev.event_type, ev.occurred_at, {
      client_event_id: `bootlog:${session.deviceId.slice(-12)}:${ev.record_id}:${ev.windows_event_id}`,
    });
    if (ev.occurred_at > latest) latest = ev.occurred_at;
  }
  if (latest > since) powerPresence.setWatermark(latest);
}

function registerIpc() {
  ipcMain.handle('wp:saveSecureToken', async (_e, key, value) => {
    await native.saveSecureToken(key, value);
  });
  ipcMain.handle('wp:getSecureToken', async (_e, key) => native.getSecureToken(key));
  ipcMain.handle('wp:deleteSecureToken', async (_e, key) => {
    await native.deleteSecureToken(key);
  });
  ipcMain.handle('wp:getDeviceInfo', async () => native.getDeviceInfo());
  ipcMain.handle('wp:getConnectedWifi', async () => native.getConnectedWifi());
  ipcMain.handle('wp:getWifiEvents', async (_e, since) => native.getWifiEvents(since));

  ipcMain.handle('wp:setPresenceSession', async (_e, session) => {
    powerPresence.setSession(session || {});
    if (session?.signedIn) {
      await catchUpPowerBootEvents();
      updater.setSessionContext({
        deviceId: session.deviceId || null,
        channel: process.env.VITE_RELEASE_CHANNEL || 'production',
      });
    }
  });
  ipcMain.handle('wp:drainPowerEvents', async () => powerPresence.drainQueue());
  ipcMain.handle('wp:peekPowerEvents', async () => powerPresence.peekQueue());
  ipcMain.handle('wp:drainBreakAwayQueue', async () => powerPresence.drainBreakQueue());
  ipcMain.handle('wp:getSystemIdleSeconds', async () => powerPresence.getSystemIdleSeconds());
  ipcMain.handle('wp:getActiveWindow', async () => native.getActiveWindow());
  ipcMain.handle('wp:showNotification', async (_e, payload) => {
    const title = String(payload?.title || 'WorkPulse');
    const body = String(payload?.body || '');
    try {
      const { Notification } = require('electron');
      if (!Notification.isSupported()) return { ok: false, reason: 'unsupported' };
      const note = new Notification({ title, body, silent: false });
      note.show();
      return { ok: true };
    } catch (err) {
      console.warn('[notify]', err);
      return { ok: false, reason: String(err) };
    }
  });
}

app.whenReady().then(async () => {
  registerIpc();
  powerPresence.registerPowerMonitor();
  updater.startUpdater({
    channel: process.env.VITE_RELEASE_CHANNEL || 'production',
  });
  createWindow();
  createTray();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
    else showMainWindow();
  });
});

app.on('before-quit', () => {
  isQuitting = true;
  try {
    powerPresence.recordAppCloseBreak();
  } catch {
    // ignore
  }
});

app.on('window-all-closed', () => {
  // Stay alive in the tray on Windows so idle breaks still record.
  if (process.platform === 'darwin') return;
  if (isQuitting) app.quit();
});
