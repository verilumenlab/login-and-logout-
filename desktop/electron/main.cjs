const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('node:path');
const native = require('./native.cjs');
const powerPresence = require('./power-presence.cjs');
const updater = require('./updater.cjs');

const isDev = !app.isPackaged;

function appIconPath() {
  const fs = require('node:fs');
  const candidates = [
    path.join(__dirname, '..', 'build', 'icon.ico'),
    path.join(__dirname, '..', 'build', 'icon.png'),
    path.join(process.resourcesPath || '', 'build', 'icon.ico'),
    path.join(process.resourcesPath || '', 'icon.ico'),
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

function createWindow() {
  const win = new BrowserWindow({
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

  win.once('ready-to-show', () => win.show());

  if (isDev) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL || 'http://localhost:1420');
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
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
}

app.whenReady().then(async () => {
  registerIpc();
  powerPresence.registerPowerMonitor();
  updater.startUpdater({
    channel: process.env.VITE_RELEASE_CHANNEL || 'production',
  });
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // Do not treat app close as logout (product rule).
  if (process.platform !== 'darwin') app.quit();
});
