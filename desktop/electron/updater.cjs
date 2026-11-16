/**
 * WorkPulse Employee — Electron auto-update client (Windows).
 * Uses electron-updater generic provider against the backend release feed.
 * Failures are non-fatal: the app continues if the update server is unavailable.
 */

const { autoUpdater } = require('electron-updater');
const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const native = require('./native.cjs');

let checkTimer = null;
let lastInfo = null;
let forceUpdate = false;
let currentDeviceId = null;
let updateChannel = 'production';

function readPkgVersion() {
  try {
    const pkgPath = path.join(__dirname, '..', 'package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    return String(pkg.version || '0.1.0');
  } catch {
    return '0.1.0';
  }
}

function apiBase() {
  return (
    process.env.WORKPULSE_API_BASE_URL ||
    process.env.VITE_API_BASE_URL ||
    'http://localhost:8000/api/v1'
  ).replace(/\/$/, '');
}

function feedBase() {
  const override =
    process.env.WORKPULSE_UPDATE_FEED_BASE_URL || process.env.VITE_UPDATE_FEED_BASE_URL;
  if (override) return override.replace(/\/$/, '');
  return `${apiBase()}/updates/windows/${updateChannel}`;
}

function broadcast(channel, payload) {
  for (const win of BrowserWindow.getAllWindows()) {
    try {
      win.webContents.send(channel, payload);
    } catch {
      // ignore
    }
  }
}

async function authHeaders() {
  const token = await native.getSecureToken('access_token');
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function report(status, extra = {}) {
  try {
    const headers = {
      'Content-Type': 'application/json',
      ...(await authHeaders()),
    };
    if (!headers.Authorization || !currentDeviceId) return;
    const body = {
      device_id: currentDeviceId,
      channel: updateChannel,
      from_version: readPkgVersion(),
      to_version: lastInfo?.version || extra.to_version || null,
      status,
      error_message: extra.error || null,
      installed_version: status === 'success' ? readPkgVersion() : null,
      ...extra,
    };
    await fetch(`${apiBase()}/updates/report`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.warn('[updater] report failed:', err?.message || err);
  }
}

async function configureUpdater() {
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowDowngrade = false;
  autoUpdater.requestHeaders = await authHeaders();
  autoUpdater.setFeedURL({
    provider: 'generic',
    url: feedBase(),
  });
}

function wireEvents() {
  autoUpdater.on('checking-for-update', () => {
    broadcast('wp:update-status', { state: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    lastInfo = info;
    broadcast('wp:update-status', {
      state: 'available',
      version: info.version,
      releaseNotes: info.releaseNotes || null,
      mandatory: forceUpdate,
    });
    report('downloading', { to_version: info.version }).catch(() => undefined);
  });

  autoUpdater.on('update-not-available', () => {
    broadcast('wp:update-status', { state: 'up-to-date', version: readPkgVersion() });
  });

  autoUpdater.on('download-progress', (progress) => {
    broadcast('wp:update-status', {
      state: 'downloading',
      version: lastInfo?.version,
      percent: progress.percent,
      transferred: progress.transferred,
      total: progress.total,
    });
  });

  autoUpdater.on('update-downloaded', (info) => {
    lastInfo = info;
    broadcast('wp:update-status', {
      state: 'ready',
      version: info.version,
      releaseNotes: info.releaseNotes || null,
      mandatory: forceUpdate,
    });
    report('installing', { to_version: info.version }).catch(() => undefined);
    if (forceUpdate) {
      setTimeout(() => {
        try {
          autoUpdater.quitAndInstall(false, true);
        } catch (err) {
          console.warn('[updater] quitAndInstall failed:', err);
        }
      }, 1500);
    }
  });

  autoUpdater.on('error', (err) => {
    console.warn('[updater] error (non-fatal):', err?.message || err);
    broadcast('wp:update-status', {
      state: 'error',
      message: String(err?.message || err || 'Update check failed'),
    });
    report('failed', { error: String(err?.message || err) }).catch(() => undefined);
  });
}

async function checkForUpdates({ silent = true } = {}) {
  if (!app.isPackaged && process.env.WORKPULSE_FORCE_UPDATER !== '1') {
    // Dev mode: skip network updater unless forced
    broadcast('wp:update-status', { state: 'skipped-dev', version: readPkgVersion() });
    return { ok: true, skipped: true };
  }
  try {
    await configureUpdater();
    const result = await autoUpdater.checkForUpdates();
    return { ok: true, updateInfo: result?.updateInfo || null };
  } catch (err) {
    if (!silent) {
      broadcast('wp:update-status', {
        state: 'error',
        message: String(err?.message || err),
      });
    }
    console.warn('[updater] check failed (app continues):', err?.message || err);
    return { ok: false, error: String(err?.message || err) };
  }
}

async function refreshPolicy() {
  try {
    const headers = await authHeaders();
    if (!headers.Authorization) return;
    const res = await fetch(`${apiBase()}/updates/policy?channel=${encodeURIComponent(updateChannel)}`, {
      headers,
    });
    if (!res.ok) return;
    const policy = await res.json();
    forceUpdate = Boolean(policy.force_update);
    autoUpdater.autoDownload = policy.auto_download !== false;
    const minutes = Number(policy.check_interval_minutes) || 240;
    if (checkTimer) clearInterval(checkTimer);
    checkTimer = setInterval(() => {
      checkForUpdates({ silent: true });
    }, Math.max(15, minutes) * 60 * 1000);
  } catch (err) {
    console.warn('[updater] policy fetch failed:', err?.message || err);
  }
}

function setSessionContext({ deviceId, channel } = {}) {
  if (deviceId) currentDeviceId = deviceId;
  if (channel) updateChannel = channel;
}

function registerUpdaterIpc() {
  ipcMain.handle('wp:checkForUpdates', async () => checkForUpdates({ silent: false }));
  ipcMain.handle('wp:installUpdateNow', async () => {
    try {
      await report('installing', { to_version: lastInfo?.version });
      autoUpdater.quitAndInstall(false, true);
      return { ok: true };
    } catch (err) {
      await report('failed', { error: String(err?.message || err) });
      return { ok: false, error: String(err?.message || err) };
    }
  });
  ipcMain.handle('wp:getAppVersion', async () => readPkgVersion());
  ipcMain.handle('wp:setUpdateContext', async (_e, ctx) => {
    setSessionContext(ctx || {});
    await refreshPolicy();
    return { ok: true };
  });
}

function startUpdater({ deviceId, channel } = {}) {
  setSessionContext({ deviceId, channel });
  wireEvents();
  registerUpdaterIpc();
  // Initial delayed check so login token can be stored first
  setTimeout(() => {
    refreshPolicy().then(() => checkForUpdates({ silent: true }));
  }, 8000);
  checkTimer = setInterval(() => {
    checkForUpdates({ silent: true });
  }, 240 * 60 * 1000);
}

module.exports = {
  startUpdater,
  checkForUpdates,
  setSessionContext,
  readPkgVersion,
};
