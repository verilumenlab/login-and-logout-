/**
 * Durable power-presence queue + signed-in session flag for WorkPulse Employee.
 * Survives dirty shutdown better than renderer localStorage alone.
 */
const fs = require('node:fs');
const path = require('node:path');
const { app, powerMonitor, BrowserWindow } = require('electron');
const { randomUUID } = require('node:crypto');

const QUEUE_FILE = 'power-presence-queue.json';
const SESSION_FILE = 'power-presence-session.json';
const WATERMARK_FILE = 'power-presence-watermark.json';
const MAX_QUEUE = 500;

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

function getSession() {
  return readJson(dataPath(SESSION_FILE), { signedIn: false, deviceId: null, userId: null });
}

function setSession(session) {
  writeJson(dataPath(SESSION_FILE), {
    signedIn: Boolean(session?.signedIn),
    deviceId: session?.deviceId || null,
    userId: session?.userId || null,
    updatedAt: new Date().toISOString(),
  });
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
  broadcast('break-away:queued', {
    signal,
    occurred_at: occurredAt || new Date().toISOString(),
  });
}

function getSystemIdleSeconds() {
  try {
    // Electron returns idle time in seconds
    return Math.max(0, Math.floor(Number(powerMonitor.getSystemIdleTime()) || 0));
  } catch {
    return 0;
  }
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
}

module.exports = {
  getSession,
  setSession,
  getWatermark,
  setWatermark,
  enqueuePowerEvent,
  drainQueue,
  peekQueue,
  registerPowerMonitor,
  loadQueue,
  saveQueue,
  getSystemIdleSeconds,
  emitBreakAway,
};
