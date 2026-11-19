const { app, BrowserWindow, ipcMain, shell, Tray, Menu, nativeImage, Notification } = require('electron');
const path = require('node:path');
const native = require('./native.cjs');
const powerPresence = require('./power-presence.cjs');
const updater = require('./updater.cjs');
const sessionReset = require('./session-reset.cjs');

const isDev = !app.isPackaged;
let mainWindow = null;
let tray = null;
let isQuitting = false;
let hidToTrayNoticeShown = false;
/** After an update, force the login window open (do not start hidden). */
let forceShowForRelogin = false;

// One process only — reopening the shortcut brings back the background instance.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    showMainWindow();
  });
}

function appIconPath() {
  const fs = require('node:fs');
  const candidates = [
    path.join(path.dirname(process.execPath || ''), 'app.ico'),
    path.join(process.resourcesPath || '', 'app.ico'),
    path.join(process.resourcesPath || '', 'icon.ico'),
    path.join(process.resourcesPath || '', 'build', 'icon.ico'),
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
  return path.join(app.getAppPath(), 'dist', 'index.html');
}

function notifyBackground() {
  try {
    if (!Notification.isSupported()) return;
    const note = new Notification({
      title: 'WorkPulse is running in the background',
      body: 'Login, breaks, and laptop activity keep tracking. Open from the system tray icon. Use Quit in the tray to stop.',
      silent: true,
    });
    note.show();
  } catch (err) {
    console.warn('[tray] notify failed:', err);
  }
}

function hideToTray(win) {
  if (!win || win.isDestroyed()) return;
  win.hide();
  try {
    win.setSkipTaskbar(true);
  } catch {
    // ignore
  }
  if (!hidToTrayNoticeShown) {
    hidToTrayNoticeShown = true;
    notifyBackground();
  }
  if (tray) {
    tray.setToolTip('WorkPulse Employee — running in background');
  }
}

function showMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    createWindow();
    return;
  }
  try {
    mainWindow.setSkipTaskbar(false);
  } catch {
    // ignore
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
  if (tray) {
    tray.setToolTip('WorkPulse Employee — tracking active');
  }
}

function createTray() {
  if (tray) return;
  const iconFile = appIconPath();
  let image = iconFile ? nativeImage.createFromPath(iconFile) : nativeImage.createEmpty();
  if (image.isEmpty()) {
    image = nativeImage.createFromDataURL(
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA4AAAAOCAYAAAAfSC3RAAAAHElEQVQoz2NgGAWjYBSMglEwCkbBKBgFo4D6AQB8AAH/YYvH1gAAAABJRU5ErkJggg=='
    );
  }
  tray = new Tray(image);
  tray.setToolTip('WorkPulse Employee — tracking active');
  const rebuildMenu = () => {
    tray.setContextMenu(
      Menu.buildFromTemplate([
        { label: 'WorkPulse is running in the background', enabled: false },
        { type: 'separator' },
        { label: 'Open WorkPulse', click: () => showMainWindow() },
        { type: 'separator' },
        {
          label: 'Quit (stop tracking)',
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
  };
  rebuildMenu();
  tray.on('double-click', () => showMainWindow());
  tray.on('click', () => showMainWindow());
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
      // Keep presence / break / activity timers alive while hidden in the tray.
      backgroundThrottling: false,
    },
  });

  const win = mainWindow;
  const reveal = () => {
    if (!win.isDestroyed() && !win.isVisible()) {
      win.show();
      try {
        win.setSkipTaskbar(false);
      } catch {
        // ignore
      }
    }
  };
  win.once('ready-to-show', reveal);
  setTimeout(reveal, 4000);

  // X / Alt+F4 → background (tray), not quit.
  win.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      hideToTray(win);
      return;
    }
    try {
      powerPresence.recordAppCloseBreak();
    } catch (err) {
      console.warn('[quit] recordAppCloseBreak failed:', err);
    }
  });

  // Minimize also goes to tray so employees do not leave a taskbar entry only.
  win.on('minimize', (event) => {
    if (isQuitting) return;
    event.preventDefault();
    hideToTray(win);
  });

  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error('[ui] did-fail-load', { code, desc, url });
    reveal();
    const message = encodeURIComponent(
      `WorkPulse could not load its UI (${desc || code}). Reinstall the latest setup, or contact support.`
    );
    win.loadURL(
      `data:text/html,<h3 style="font-family:sans-serif;padding:24px">WorkPulse failed to open</h3><p style="font-family:sans-serif;padding:0 24px;color:#334155">${message}</p>`
    );
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

function enableStartWithWindows() {
  if (isDev) return;
  try {
    app.setLoginItemSettings({
      openAtLogin: true,
      openAsHidden: true,
      path: process.execPath,
      args: ['--hidden'],
    });
  } catch (err) {
    console.warn('[startup] setLoginItemSettings failed:', err);
  }
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
      if (!Notification.isSupported()) return { ok: false, reason: 'unsupported' };
      const note = new Notification({ title, body, silent: false });
      note.show();
      return { ok: true };
    } catch (err) {
      console.warn('[notify]', err);
      return { ok: false, reason: String(err) };
    }
  });
  ipcMain.handle('wp:consumePostUpdateRelogin', async () => sessionReset.consumeReloginRequirement());
}

if (gotLock) {
  app.whenReady().then(async () => {
    registerIpc();
    powerPresence.registerPowerMonitor();
    enableStartWithWindows();

    const reauth = await sessionReset.enforceReloginOnVersionChange(updater.readPkgVersion());
    forceShowForRelogin = Boolean(reauth?.required);

    updater.startUpdater({
      channel: process.env.VITE_RELEASE_CHANNEL || 'production',
    });
    createWindow();
    createTray();

    // After update: always show login. Otherwise honor --hidden startup.
    if (forceShowForRelogin) {
      showMainWindow();
    } else if (process.argv.includes('--hidden')) {
      if (mainWindow && !mainWindow.isDestroyed()) {
        hideToTray(mainWindow);
      }
    }

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
    // Stay alive in the tray on Windows so tracking continues in the background.
    if (process.platform === 'darwin') return;
    if (isQuitting) app.quit();
  });
}
