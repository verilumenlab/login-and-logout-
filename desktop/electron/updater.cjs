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
const runtimeConfig = require('./runtime-config.cjs');
const sessionReset = require('./session-reset.cjs');

let checkTimer = null;
let retryTimer = null;
let lastInfo = null;
let forceUpdate = false;
let currentDeviceId = null;
let updateChannel = runtimeConfig.RELEASE_CHANNEL || 'production';
let eventsWired = false;
let ipcRegistered = false;

async function installUpdateAndRequireRelogin() {
  const toVersion = lastInfo?.version || null;
  await sessionReset.prepareReloginBeforeUpdate({
    fromVersion: readPkgVersion(),
    toVersion,
  });
  autoUpdater.quitAndInstall(false, true);
}

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
  const packagedDefault = runtimeConfig.API_BASE_URL || 'https://workpulse-api-pm0x.onrender.com/api/v1';
  return (
    process.env.WORKPULSE_API_BASE_URL ||
    process.env.VITE_API_BASE_URL ||
    (app.isPackaged ? packagedDefault : 'http://localhost:8000/api/v1')
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
  // Feed itself is public; still attach token when present for reporting continuity.
  autoUpdater.requestHeaders = await authHeaders();
  autoUpdater.setFeedURL({
    provider: 'generic',
    url: feedBase(),
  });
}

function scheduleRetry(ms = 45000) {
  if (retryTimer) clearTimeout(retryTimer);
  retryTimer = setTimeout(() => {
    checkForUpdates({ silent: true });
  }, ms);
}

function wireEvents() {
  if (eventsWired) return;
  eventsWired = true;

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
      mandatory: true,
    });
    report('installing', { to_version: info.version }).catch(() => undefined);
    // Close app, install new build, then require email sign-in on next launch.
    setTimeout(() => {
      installUpdateAndRequireRelogin().catch((err) => {
        console.warn('[updater] quitAndInstall failed:', err);
      });
    }, 2000);
  });

  autoUpdater.on('error', (err) => {
    console.warn('[updater] error (non-fatal):', err?.message || err);
    broadcast('wp:update-status', {
      state: 'error',
      message: String(err?.message || err || 'Update check failed'),
    });
    report('failed', { error: String(err?.message || err) }).catch(() => undefined);
    scheduleRetry(60000);
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
    scheduleRetry(60000);
    return { ok: false, error: String(err?.message || err) };
  }
}

async function refreshPolicy() {
  try {
    const headers = await authHeaders();
    // Policy needs auth; feed check does not. Keep default interval if offline/unsigned.
    if (!headers.Authorization) return false;
    const res = await fetch(`${apiBase()}/updates/policy?channel=${encodeURIComponent(updateChannel)}`, {
      headers,
    });
    if (!res.ok) return false;
    const policy = await res.json();
    forceUpdate = Boolean(policy.force_update);
    autoUpdater.autoDownload = policy.auto_download !== false;
    const minutes = Number(policy.check_interval_minutes) || 60;
    if (checkTimer) clearInterval(checkTimer);
    checkTimer = setInterval(() => {
      checkForUpdates({ silent: true });
    }, Math.max(15, minutes) * 60 * 1000);
    return true;
  } catch (err) {
    console.warn('[updater] policy fetch failed:', err?.message || err);
    return false;
  }
}

function setSessionContext({ deviceId, channel } = {}) {
  if (deviceId) currentDeviceId = deviceId;
  if (channel) updateChannel = channel;
}

function registerUpdaterIpc() {
  if (ipcRegistered) return;
  ipcRegistered = true;

  ipcMain.handle('wp:checkForUpdates', async () => checkForUpdates({ silent: false }));
  ipcMain.handle('wp:installUpdateNow', async () => {
    try {
      await report('installing', { to_version: lastInfo?.version });
      await installUpdateAndRequireRelogin();
      return { ok: true };
    } catch (err) {
      await report('failed', { error: String(err?.message || err) });
      return { ok: false, error: String(err?.message || err) };
    }
  });
  ipcMain.handle('wp:getAppVersion', async () => readPkgVersion());
  ipcMain.handle('wp:setUpdateContext', async (_e, ctx) => {
    setSessionContext(ctx || {});
    // After employee signs in: refresh policy and check immediately (was the main miss).
    await refreshPolicy();
    await checkForUpdates({ silent: true });
    return { ok: true };
  });
}

function startUpdater({ deviceId, channel } = {}) {
  setSessionContext({ deviceId, channel });
  wireEvents();
  registerUpdaterIpc();
  // Feed is public — check soon after launch, then again after typical login time.
  setTimeout(() => {
    checkForUpdates({ silent: true });
  }, 5000);
  setTimeout(() => {
    refreshPolicy().then(() => checkForUpdates({ silent: true }));
  }, 20000);
  if (checkTimer) clearInterval(checkTimer);
  checkTimer = setInterval(() => {
    checkForUpdates({ silent: true });
  }, 60 * 60 * 1000);
}

module.exports = {
  startUpdater,
  checkForUpdates,
  setSessionContext,
  readPkgVersion,
};
