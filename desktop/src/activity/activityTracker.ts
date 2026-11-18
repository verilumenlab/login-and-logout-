/**
 * Foreground app usage → /activity/sync (admin laptop-usage board).
 * Captures application name + window title only. No screenshots or keylogging.
 */

import { getActiveWindow, getSystemIdleSeconds } from '../api/ipc';
import { HttpError, NetworkError, syncActivityLogs, type ActivityLogItem } from '../api/backend';

const QUEUE_KEY = '__activity_queue_v1';
const QUEUE_OWNER_KEY = '__activity_queue_owner';
const SESSION_KEY = '__device_session_id';
const MAX_QUEUE = 400;
const MAX_BATCH = 40;
const SAMPLE_MS = 20_000;

type OpenSlice = {
  application_name: string;
  window_title: string | null;
  process_id: number;
  start_time: string;
  device_event_id: string;
};

let openSlice: OpenSlice | null = null;
let sampleTimer: ReturnType<typeof setInterval> | null = null;

function loadQueue(): ActivityLogItem[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as ActivityLogItem[];
  } catch {
    return [];
  }
}

function saveQueue(queue: ActivityLogItem[]): void {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
}

function enqueue(item: ActivityLogItem): void {
  const queue = loadQueue();
  if (queue.some((e) => e.device_event_id === item.device_event_id)) return;
  queue.push(item);
  saveQueue(queue);
}

export function bindActivityQueueToUser(userId: string): void {
  if (localStorage.getItem(QUEUE_OWNER_KEY) !== userId) {
    localStorage.removeItem(QUEUE_KEY);
    localStorage.setItem(QUEUE_OWNER_KEY, userId);
    openSlice = null;
  }
}

export function setDeviceSessionId(id: string | null): void {
  if (id) localStorage.setItem(SESSION_KEY, id);
  else localStorage.removeItem(SESSION_KEY);
}

export function getDeviceSessionId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

export function pendingActivityCount(): number {
  return loadQueue().length;
}

function shortTag(deviceId: string): string {
  return deviceId.replace(/[^A-Za-z0-9]/g, '').slice(-12) || 'device';
}

function closeOpenSlice(endIso: string, idleSeconds: number): void {
  if (!openSlice) return;
  const startMs = Date.parse(openSlice.start_time) || Date.now();
  const endMs = Date.parse(endIso) || Date.now();
  const duration = Math.max(1, Math.floor((endMs - startMs) / 1000));
  enqueue({
    device_event_id: openSlice.device_event_id,
    application_name: openSlice.application_name,
    window_title: openSlice.window_title,
    process_id: openSlice.process_id || null,
    start_time: openSlice.start_time,
    end_time: new Date(endMs).toISOString(),
    duration_seconds: duration,
    idle_seconds: Math.max(0, idleSeconds),
    keystrokes_count: 0,
    mouse_clicks_count: 0,
  });
  openSlice = null;
}

/** Sample foreground window; close/open slices when the app changes. */
export async function sampleForegroundActivity(deviceId: string): Promise<void> {
  const idle = await getSystemIdleSeconds();
  const win = await getActiveWindow();
  const nowIso = new Date().toISOString();
  const app = (win.application_name || 'Unknown').slice(0, 255);
  const title = (win.window_title || '').slice(0, 500) || null;
  const pid = win.process_id || 0;

  if (
    openSlice &&
    openSlice.application_name === app &&
    openSlice.window_title === title
  ) {
    // Same app — keep slice open; a heartbeat row is written on change or flush.
    return;
  }

  if (openSlice) {
    closeOpenSlice(nowIso, idle);
  }

  openSlice = {
    application_name: app,
    window_title: title,
    process_id: pid,
    start_time: nowIso,
    device_event_id: `act:${shortTag(deviceId)}:${Date.now()}`,
  };
}

/** Force-close current slice so the admin board gets a fresh last_seen. */
export async function checkpointForegroundActivity(deviceId: string): Promise<void> {
  const idle = await getSystemIdleSeconds();
  const nowIso = new Date().toISOString();
  if (!openSlice) {
    await sampleForegroundActivity(deviceId);
  }
  const prev = openSlice
    ? {
        application_name: openSlice.application_name,
        window_title: openSlice.window_title,
        process_id: openSlice.process_id,
      }
    : null;
  if (openSlice) {
    closeOpenSlice(nowIso, idle);
  }
  // Re-open same app so continuous use still tracks between checkpoints.
  if (prev) {
    openSlice = {
      application_name: prev.application_name,
      window_title: prev.window_title,
      process_id: prev.process_id,
      start_time: nowIso,
      device_event_id: `act:${shortTag(deviceId)}:${Date.now()}`,
    };
  }
}

export async function flushActivityQueue(): Promise<number> {
  const sessionId = getDeviceSessionId();
  if (!sessionId) return 0;
  const queue = loadQueue();
  if (!queue.length) return 0;
  const batch = queue.slice(0, MAX_BATCH);
  try {
    await syncActivityLogs(sessionId, batch);
    saveQueue(queue.slice(batch.length));
    return batch.length;
  } catch (err) {
    if (err instanceof NetworkError) throw err;
    if (err instanceof HttpError && err.status >= 500) throw err;
    if (err instanceof HttpError && err.status >= 400 && err.status < 500) {
      console.warn('[activity] dropping rejected batch:', err.message);
      saveQueue(queue.slice(batch.length));
      return batch.length;
    }
    throw err;
  }
}

export function startActivitySampler(deviceId: string, enabled: () => boolean): () => void {
  if (sampleTimer) {
    clearInterval(sampleTimer);
    sampleTimer = null;
  }
  const tick = () => {
    if (!enabled()) return;
    void (async () => {
      try {
        await checkpointForegroundActivity(deviceId);
        await flushActivityQueue();
      } catch (err) {
        if (!(err instanceof NetworkError)) {
          console.warn('[activity] sample failed:', err);
        }
      }
    })();
  };
  tick();
  sampleTimer = setInterval(tick, SAMPLE_MS);
  return () => {
    if (sampleTimer) clearInterval(sampleTimer);
    sampleTimer = null;
  };
}
