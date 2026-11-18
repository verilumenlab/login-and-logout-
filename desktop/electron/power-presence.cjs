/**
 * Durable power-presence queue + signed-in session flag for WorkPulse Employee.
 * Survives dirty shutdown better than renderer localStorage alone.
 *
 * Also runs a main-process idle watcher so breaks still start when:
 * - the window is hidden / in the tray (Chromium throttles renderer timers)
 * - Windows display timeout is "Never" (no lock/sleep events)
 */
const fs = require('node:fs');
const path = require('node:path');
const { app, powerMonitor, BrowserWindow } = require('electron');
const { randomUUID } = require('node:crypto');

const QUEUE_FILE = 'power-presence-queue.json';
const SESSION_FILE = 'power-presence-session.json';
const WATERMARK_FILE = 'power-presence-watermark.json';
const BREAK_QUEUE_FILE = 'break-break-queue.json';
const MAX_QUEUE = 500;

/** Match desktop/src/attendance/breakTracker.ts */
const IDLE_BREAK_START_SECONDS = 10 * 60;
const IDLE_BREAK_END_SECONDS = 60;
const IDLE_POLL_MS = 15_000;

let idleBreakActive = false;
let idleTimer = null;

function dataPath(name) {
  return path.join(app.getPath('userData'), name);
}

function readJson(file, fallback) {
  try {
    if (!fs.existsSync(file)) return fallback;
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value, null, 0));
}

function loadQueue() {
  const q = readJson(dataPath(QUEUE_FILE), []);
  return Array.isArray(q) ? q : [];
}

function saveQueue(queue) {
  writeJson(dataPath(QUEUE_FILE), queue.slice(-MAX_QUEUE));
}

function loadBreakQueue() {
  const q = readJson(dataPath(BREAK_QUEUE_FILE), []);
  return Array.isArray(q) ? q : [];
}

function saveBreakQueue(queue) {
  writeJson(dataPath(BREAK_QUEUE_FILE), queue.slice(-MAX_QUEUE));
}

function getSession() {
  return readJson(dataPath(SESSION_FILE), {
    signedIn: false,
    deviceId: null,
    userId: null,
    workLoggedIn: false,
  });
}

function setSession(session) {
  const prev = getSession();
  const next = {
    signedIn: Boolean(session?.signedIn),
    deviceId: session?.deviceId || null,
    userId: session?.userId || null,
    workLoggedIn:
      session?.workLoggedIn === undefined ? Boolean(prev.workLoggedIn) : Boolean(session.workLoggedIn),
    updatedAt: new Date().toISOString(),
  };
  writeJson(dataPath(SESSION_FILE), next);
  if (!next.signedIn || !next.workLoggedIn) {
    idleBreakActive = false;
  }
  ensureIdleWatcher();
}

function getWatermark() {
  return readJson(dataPath(WATERMARK_FILE), { lastProcessedAt: null });
}

function setWatermark(iso) {
  writeJson(dataPath(WATERMARK_FILE), { lastProcessedAt: iso, updatedAt: new Date().toISOString() });
}

function enqueuePowerEvent(eventType, occurredAt, extra = {}) {
  const session = getSession();
  if (!session.signedIn || !session.deviceId) {
    return null;
  }
  const occurred_at = occurredAt || new Date().toISOString();
  const deviceId = session.deviceId;
  const tag = String(deviceId).replace(/[^A-Za-z0-9]/g, '').slice(-12) || 'device';
  const { client_event_id: customId, ...rest } = extra || {};
  const ev = {
    client_event_id:
      customId ||
      `pwr:${tag}:${eventType}:${Date.parse(occurred_at) || Date.now()}:${randomUUID().slice(0, 8)}`,
    event_type: eventType,
    occurred_at,
    device_id: deviceId,
    ssid: null,
    bssid: null,
    ...rest,
  };
  const queue = loadQueue();
  if (queue.some((e) => e.client_event_id === ev.client_event_id)) return ev;
  // Collapse rapid duplicate same-type events within 2s
  const last = queue[queue.length - 1];
  if (
    last &&
    last.event_type === ev.event_type &&
    Math.abs(Date.parse(last.occurred_at) - Date.parse(ev.occurred_at)) < 2000
  ) {
    return last;
  }
  queue.push(ev);
  saveQueue(queue);
  broadcast('power-presence:queued', ev);
  return ev;
}

/**
 * Durable break signals for when the renderer is gone (app quit) or timers are throttled.
 */
function enqueueBreakSignal(signal, occurredAt, extra = {}) {
  const session = getSession();
  if (!session.signedIn || !session.deviceId) return null;
  const occurred_at = occurredAt || new Date().toISOString();
  const item = {
    signal,
    occurred_at,
    device_id: session.deviceId,
    ...extra,
  };
  const queue = loadBreakQueue();
  const last = queue[queue.length - 1];
  if (
    last &&
    last.signal === item.signal &&
    Math.abs(Date.parse(last.occurred_at) - Date.parse(item.occurred_at)) < 2000
  ) {
    return last;
  }
  queue.push(item);
  saveBreakQueue(queue);
  broadcast('break-away:queued', item);
  return item;
}

function drainBreakQueue() {
  const queue = loadBreakQueue();
  saveBreakQueue([]);
  return queue;
}

function drainQueue() {
  const queue = loadQueue();
  saveQueue([]);
  return queue;
}

function peekQueue() {
  return loadQueue();
}

function broadcast(channel, payload) {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, payload);
    }
  }
}

function emitBreakAway(signal, occurredAt) {
  const payload = {
    signal,
    occurred_at: occurredAt || new Date().toISOString(),
  };
  broadcast('break-away:queued', payload);
  return payload;
}

function getSystemIdleSeconds() {
  try {
    // Electron returns idle time in seconds
    return Math.max(0, Math.floor(Number(powerMonitor.getSystemIdleTime()) || 0));
  } catch {
    return 0;
  }
}

function tickIdleBreakWatch() {
  const session = getSession();
  if (!session.signedIn || !session.workLoggedIn || !session.deviceId) {
    idleBreakActive = false;
    return;
  }
  const idle = getSystemIdleSeconds();
  if (!idleBreakActive && idle >= IDLE_BREAK_START_SECONDS) {
    idleBreakActive = true;
    const started = new Date(Date.now() - idle * 1000).toISOString();
    emitBreakAway('IDLE_START', started);
  } else if (idleBreakActive && idle < IDLE_BREAK_END_SECONDS) {
    idleBreakActive = false;
    emitBreakAway('IDLE_END', new Date().toISOString());
  }
}

function ensureIdleWatcher() {
  if (idleTimer) return;
  idleTimer = setInterval(() => {
    try {
      tickIdleBreakWatch();
    } catch (err) {
      console.warn('[idle-watch]', err);
    }
  }, IDLE_POLL_MS);
  if (typeof idleTimer.unref === 'function') idleTimer.unref();
}

/** Record that the employee closed/quit the app while still on the clock. */
function recordAppCloseBreak() {
  const session = getSession();
  if (!session.workLoggedIn || !session.deviceId) return null;
  idleBreakActive = false;
  return enqueueBreakSignal('APP_CLOSE', new Date().toISOString());
}

function registerPowerMonitor() {
  const onLogout = (kind) => {
    const type = kind === 'suspend' ? 'SYSTEM_SUSPEND' : 'SYSTEM_SHUTDOWN';
    const at = new Date().toISOString();
    enqueuePowerEvent(type, at);
    if (kind === 'suspend') emitBreakAway('SUSPEND', at);
  };
  const onLogin = (kind) => {
    const type = kind === 'resume' ? 'SYSTEM_RESUME' : 'SYSTEM_STARTUP';
    const at = new Date().toISOString();
    enqueuePowerEvent(type, at);
    if (kind === 'resume') emitBreakAway('RESUME', at);
  };

  powerMonitor.on('suspend', () => onLogout('suspend'));
  powerMonitor.on('resume', () => onLogin('resume'));
  powerMonitor.on('shutdown', () => onLogout('shutdown'));
  // Lock/unlock are not presence logout — they drive automatic breaks.
  powerMonitor.on('lock-screen', () => emitBreakAway('LOCK', new Date().toISOString()));
  powerMonitor.on('unlock-screen', () => emitBreakAway('UNLOCK', new Date().toISOString()));
  ensureIdleWatcher();
}

module.exports = {
  getSession,
  setSession,
  getWatermark,
  setWatermark,
  enqueuePowerEvent,
  drainQueue,
  peekQueue,
  drainBreakQueue,
  enqueueBreakSignal,
  recordAppCloseBreak,
  registerPowerMonitor,
  loadQueue,
  saveQueue,
  getSystemIdleSeconds,
  emitBreakAway,
  IDLE_BREAK_START_SECONDS,
  IDLE_BREAK_END_SECONDS,
};
