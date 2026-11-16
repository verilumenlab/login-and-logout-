/**
 * Automatic break tracking from idle, lock, and sleep signals.
 * Queues BREAK_START / BREAK_END for /attendance/sync-offline.
 */

import { BreakAwayPayload, getSystemIdleSeconds } from '../api/ipc';
import { HttpError, NetworkError, syncOfflineAttendance } from '../api/backend';

export type BreakSource = 'AUTO_IDLE' | 'AUTO_LOCK' | 'AUTO_SLEEP' | 'MANUAL';
export type BreakType = 'LUNCH' | 'COFFEE' | 'PERSONAL' | 'MEETING';

export type OfflineBreakItem = {
  client_event_id: string;
  action: 'BREAK_START' | 'BREAK_END';
  occurred_at: string;
  break_type?: BreakType;
  source?: BreakSource;
  notes?: string | null;
};

type OpenBreakState = {
  source: BreakSource;
  started_at: string;
  start_client_event_id: string;
};

const QUEUE_KEY = '__break_queue_v1';
const QUEUE_OWNER_KEY = '__break_queue_owner';
const OPEN_BREAK_KEY = '__break_open_v1';
const MAX_QUEUE = 500;
const MAX_BATCH = 100;

/** Idle seconds before an AUTO_IDLE break starts. */
export const IDLE_BREAK_START_SECONDS = 10 * 60;
/** Idle must fall below this to end an AUTO_IDLE break. */
export const IDLE_BREAK_END_SECONDS = 60;
const LUNCH_WINDOW_START_HOUR = 12;
const LUNCH_WINDOW_END_HOUR = 14;

function loadQueue(): OfflineBreakItem[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as OfflineBreakItem[];
  } catch {
    return [];
  }
}

function saveQueue(queue: OfflineBreakItem[]): void {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
}

function enqueue(items: OfflineBreakItem[]): void {
  if (!items.length) return;
  const queue = loadQueue();
  const known = new Set(queue.map((e) => e.client_event_id));
  for (const item of items) {
    if (!known.has(item.client_event_id)) {
      queue.push(item);
      known.add(item.client_event_id);
    }
  }
  saveQueue(queue);
}

export function bindBreakQueueToUser(userId: string): void {
  if (localStorage.getItem(QUEUE_OWNER_KEY) !== userId) {
    localStorage.removeItem(QUEUE_KEY);
    localStorage.removeItem(OPEN_BREAK_KEY);
    localStorage.setItem(QUEUE_OWNER_KEY, userId);
  }
}

export function pendingBreakCount(): number {
  return loadQueue().length;
}

export function getOpenBreak(): OpenBreakState | null {
  try {
    const raw = localStorage.getItem(OPEN_BREAK_KEY);
    return raw ? (JSON.parse(raw) as OpenBreakState) : null;
  } catch {
    return null;
  }
}

function setOpenBreak(state: OpenBreakState | null): void {
  if (!state) localStorage.removeItem(OPEN_BREAK_KEY);
  else localStorage.setItem(OPEN_BREAK_KEY, JSON.stringify(state));
}

function shortTag(deviceId: string): string {
  return deviceId.replace(/[^A-Za-z0-9]/g, '').slice(-12) || 'device';
}

export function tentativeBreakType(occurredAtIso: string): BreakType {
  const d = new Date(occurredAtIso);
  const hour = d.getHours();
  if (hour >= LUNCH_WINDOW_START_HOUR && hour < LUNCH_WINDOW_END_HOUR) return 'LUNCH';
  return 'PERSONAL';
}

export function openBreakType(): BreakType | null {
  const open = getOpenBreak();
  if (!open) return null;
  return tentativeBreakType(open.started_at);
}

export function startAutoBreak(
  source: BreakSource,
  deviceId: string,
  occurredAt: string = new Date().toISOString()
): boolean {
  if (getOpenBreak()) return false;
  const id = `brk:start:${source}:${shortTag(deviceId)}:${Date.parse(occurredAt) || Date.now()}`;
  enqueue([
    {
      client_event_id: id,
      action: 'BREAK_START',
      occurred_at: occurredAt,
      break_type: tentativeBreakType(occurredAt),
      source,
      notes: `auto:${source.toLowerCase()}`,
    },
  ]);
  setOpenBreak({ source, started_at: occurredAt, start_client_event_id: id });
  return true;
}

export function endAutoBreak(
  deviceId: string,
  occurredAt: string = new Date().toISOString()
): boolean {
  const open = getOpenBreak();
  if (!open) return false;
  const id = `brk:end:${open.source}:${shortTag(deviceId)}:${Date.parse(occurredAt) || Date.now()}`;
  enqueue([
    {
      client_event_id: id,
      action: 'BREAK_END',
      occurred_at: occurredAt,
      notes: `auto:end:${open.source.toLowerCase()}`,
    },
  ]);
  setOpenBreak(null);
  return true;
}

export function handleBreakAwaySignal(signal: BreakAwayPayload, deviceId: string): void {
  const at = signal.occurred_at || new Date().toISOString();
  if (signal.signal === 'LOCK') {
    startAutoBreak('AUTO_LOCK', deviceId, at);
  } else if (signal.signal === 'UNLOCK') {
    endAutoBreak(deviceId, at);
  } else if (signal.signal === 'SUSPEND') {
    startAutoBreak('AUTO_SLEEP', deviceId, at);
  } else if (signal.signal === 'RESUME') {
    endAutoBreak(deviceId, at);
  }
}

/** Poll idle and start/end AUTO_IDLE breaks. */
export async function evaluateIdleBreak(deviceId: string): Promise<void> {
  const idle = await getSystemIdleSeconds();
  const open = getOpenBreak();
  if (!open && idle >= IDLE_BREAK_START_SECONDS) {
    // Idle start time is approximately now - idle seconds
    const started = new Date(Date.now() - idle * 1000).toISOString();
    startAutoBreak('AUTO_IDLE', deviceId, started);
    return;
  }
  if (open?.source === 'AUTO_IDLE' && idle < IDLE_BREAK_END_SECONDS) {
    endAutoBreak(deviceId, new Date().toISOString());
  }
}

export async function flushBreakQueue(): Promise<number> {
  const queue = loadQueue();
  if (!queue.length) return 0;

  const batch = queue.slice(0, MAX_BATCH);
  try {
    await syncOfflineAttendance(batch);
    saveQueue(queue.slice(batch.length));
    return batch.length;
  } catch (err) {
    if (err instanceof NetworkError) throw err;
    if (err instanceof HttpError && err.status >= 500) throw err;
    // Drop poison messages that the server permanently rejects
    if (err instanceof HttpError && err.status >= 400 && err.status < 500) {
      console.warn('[break] dropping rejected batch:', err.message);
      saveQueue(queue.slice(batch.length));
      return batch.length;
    }
    throw err;
  }
}

export function openBreakElapsedMinutes(): number {
  const open = getOpenBreak();
  if (!open) return 0;
  return Math.max(0, Math.floor((Date.now() - Date.parse(open.started_at)) / 60000));
}
