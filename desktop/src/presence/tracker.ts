/**
 * Automatic login/logout tracking.
 *
 * Login  = first of (app sign-in, laptop connects to Wi-Fi)
 * Logout = last of (app sign-out, laptop disconnects from Wi-Fi)
 *
 * Every signal is queued locally first and synced to the server in time order, so nothing is lost
 * while the laptop is offline (which is exactly when Wi-Fi disconnects happen).
 */

import { drainPowerEvents, getConnectedWifiInfo, getWifiEvents, isElectronEnvironment } from '../api/ipc';
import { HttpError, NetworkError, syncPresenceEvents } from '../api/backend';
import { PresenceEventIn, PresenceEventType } from '../types';

const QUEUE_KEY = '__presence_queue_v1';
const QUEUE_OWNER_KEY = '__presence_queue_owner';
const WIFI_CURSOR_KEY = '__wifi_log_cursor';
const WIFI_POLL_STATE_KEY = '__wifi_poll_state';
const LAST_SYNC_KEY = '__presence_last_sync';
const MAX_BATCH = 200;
const MAX_QUEUE = 2000;

function loadQueue(): PresenceEventIn[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as PresenceEventIn[];
  } catch {
    return [];
  }
}

function saveQueue(queue: PresenceEventIn[]): void {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
}

/** Keep ISO timestamps within what Pydantic/JS typically accept (ms, not 7+ fraction digits). */
function normalizeOccurredAt(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString();
}

function normalizeEvent(ev: PresenceEventIn): PresenceEventIn {
  return {
    ...ev,
    occurred_at: normalizeOccurredAt(ev.occurred_at),
    ssid: ev.ssid ?? null,
    client_event_id: String(ev.client_event_id || '').slice(0, 100),
  };
}

function enqueue(events: PresenceEventIn[]): void {
  if (events.length === 0) return;
  const queue = loadQueue();
  const known = new Set(queue.map((e) => e.client_event_id));
  for (const raw of events) {
    const ev = normalizeEvent(raw);
    if (!ev.client_event_id) continue;
    if (!known.has(ev.client_event_id)) {
      queue.push(ev);
      known.add(ev.client_event_id);
    }
  }
  saveQueue(queue);
}

/** Unsent events belong to the employee who produced them; never upload them under another account. */
export function bindQueueToUser(userId: string): void {
  if (localStorage.getItem(QUEUE_OWNER_KEY) !== userId) {
    localStorage.removeItem(QUEUE_KEY);
    localStorage.removeItem(WIFI_POLL_STATE_KEY);
    localStorage.setItem(QUEUE_OWNER_KEY, userId);
  }
}

export function pendingEventCount(): number {
  return loadQueue().length;
}

export function lastSyncTime(): string | null {
  return localStorage.getItem(LAST_SYNC_KEY);
}

function shortDeviceTag(deviceId: string): string {
  return deviceId.replace(/[^A-Za-z0-9]/g, '').slice(-12) || 'device';
}

function startOfTodayIso(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

export function queueAppEvent(
  type: Extract<PresenceEventType, 'APP_LOGIN' | 'APP_LOGOUT'>,
  deviceId: string,
  ssid?: string,
  detail?: string | null,
  occurredAt?: Date | string | null
): void {
  const when = occurredAt ? new Date(occurredAt) : new Date();
  const ms = Number.isFinite(when.getTime()) ? when.getTime() : Date.now();
  enqueue([
    {
      client_event_id: `app:${shortDeviceTag(deviceId)}:${type}:${ms}`,
      event_type: type,
      occurred_at: new Date(ms).toISOString(),
      ssid: ssid || null,
      device_id: deviceId,
      detail: detail || null,
    },
  ]);
}

/** Merge durable Electron power-queue events (shutdown/sleep/wake/boot) into the sync queue. */
export async function ingestPowerEventsFromMain(): Promise<number> {
  if (!isElectronEnvironment()) return 0;
  const events = await drainPowerEvents();
  if (!events.length) return 0;
  enqueue(
    events.map((e) => ({
      client_event_id: e.client_event_id,
      event_type: e.event_type,
      occurred_at: e.occurred_at,
      ssid: e.ssid ?? null,
      bssid: e.bssid ?? null,
      device_id: e.device_id ?? null,
    }))
  );
  return events.length;
}

export function enqueuePresenceEvent(event: PresenceEventIn): void {
  enqueue([event]);
}

/**
 * Reads Wi-Fi connect/disconnect events that happened since the last check and queues them.
 * Windows: from the OS WLAN log (includes connections made while the app was closed).
 * Other platforms: by comparing the current connection with the previous poll.
 */
export async function collectWifiEvents(deviceId: string, osType: string): Promise<void> {
  if (!isElectronEnvironment()) return;
  const tag = shortDeviceTag(deviceId);

  if (osType === 'windows') {
    const cursor = localStorage.getItem(WIFI_CURSOR_KEY) || startOfTodayIso();
    const events = await getWifiEvents(cursor);
    enqueue(
      events.map((e) => ({
        client_event_id: `wlan:${tag}:${e.record_id}:${Date.parse(e.occurred_at)}`,
        event_type: e.kind === 'CONNECTED' ? 'WIFI_CONNECTED' : 'WIFI_DISCONNECTED',
        occurred_at: e.occurred_at,
        ssid: e.ssid || null,
        device_id: deviceId,
      }))
    );
    const latest = events.reduce<string | null>((max, e) => (!max || e.occurred_at > max ? e.occurred_at : max), null);
    if (latest) localStorage.setItem(WIFI_CURSOR_KEY, latest);

    // WLAN log only records new associations. If Wi-Fi was already connected
    // (no 8001 today), synthesize a connect from the live interface so the
    // Login & Logout board still shows the SSID — same as non-Windows.
    const current = await getConnectedWifiInfo();
    let previous: { connected: boolean; ssid: string } | null = null;
    try {
      previous = JSON.parse(localStorage.getItem(WIFI_POLL_STATE_KEY) || 'null');
    } catch {
      previous = null;
    }
    const now = new Date();
    const networkChanged = previous?.connected && (!current.is_wifi || current.ssid !== previous.ssid);
    const changes: PresenceEventIn[] = [];
    if (networkChanged && previous) {
      changes.push({
        client_event_id: `poll:${tag}:d:${now.getTime()}`,
        event_type: 'WIFI_DISCONNECTED',
        occurred_at: now.toISOString(),
        ssid: previous.ssid || null,
        device_id: deviceId,
      });
    }
    if (current.is_wifi && (!previous?.connected || networkChanged)) {
      changes.push({
        client_event_id: `poll:${tag}:c:${now.getTime()}`,
        event_type: 'WIFI_CONNECTED',
        occurred_at: new Date(now.getTime() + 1).toISOString(),
        ssid: current.ssid || null,
        bssid: current.bssid || null,
        device_id: deviceId,
      });
    }
    enqueue(changes);
    localStorage.setItem(WIFI_POLL_STATE_KEY, JSON.stringify({ connected: current.is_wifi, ssid: current.ssid }));
    return;
  }

  const current = await getConnectedWifiInfo();
  let previous: { connected: boolean; ssid: string } | null = null;
  try {
    previous = JSON.parse(localStorage.getItem(WIFI_POLL_STATE_KEY) || 'null');
  } catch {
    previous = null;
  }
  const now = new Date();
  const changes: PresenceEventIn[] = [];
  const networkChanged = previous?.connected && (!current.is_wifi || current.ssid !== previous.ssid);
  if (networkChanged && previous) {
    changes.push({
      client_event_id: `poll:${tag}:d:${now.getTime()}`,
      event_type: 'WIFI_DISCONNECTED',
      occurred_at: now.toISOString(),
      ssid: previous.ssid || null,
      device_id: deviceId,
    });
  }
  if (current.is_wifi && (!previous?.connected || networkChanged)) {
    changes.push({
      client_event_id: `poll:${tag}:c:${now.getTime()}`,
      event_type: 'WIFI_CONNECTED',
      occurred_at: new Date(now.getTime() + 1).toISOString(),
      ssid: current.ssid || null,
      bssid: current.bssid || null,
      device_id: deviceId,
    });
  }
  enqueue(changes);
  localStorage.setItem(WIFI_POLL_STATE_KEY, JSON.stringify({ connected: current.is_wifi, ssid: current.ssid }));
}

/**
 * Sends queued events oldest-first. Returns the server's logged-in state, or null if nothing was sent.
 * Network failures keep the queue for the next attempt; SessionExpiredError propagates to the caller.
 */
export async function flushQueue(): Promise<boolean | null> {
  // Re-normalize any older queued rows (e.g. Windows bootlog timestamps with 7+ fraction digits).
  let queue = loadQueue()
    .map(normalizeEvent)
    .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
  saveQueue(queue);
  let isLoggedIn: boolean | null = null;

  while (queue.length > 0) {
    const batch = queue.slice(0, MAX_BATCH);
    try {
      const res = await syncPresenceEvents(batch);
      isLoggedIn = res.is_logged_in;
    } catch (err) {
      if (err instanceof NetworkError) break;
      if (err instanceof HttpError && (err.status === 422 || err.status === 400)) {
        // Malformed events can never succeed; drop them instead of blocking the queue forever.
        console.warn('[presence] Dropping rejected batch:', err.message);
      } else {
        throw err;
      }
    }
    const sent = new Set(batch.map((e) => e.client_event_id));
    queue = loadQueue()
      .map(normalizeEvent)
      .filter((e) => !sent.has(e.client_event_id))
      .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
    saveQueue(queue);
    localStorage.setItem(LAST_SYNC_KEY, new Date().toISOString());
  }
  return isLoggedIn;
}
