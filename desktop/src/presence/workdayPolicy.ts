/**
 * Office day policy mirrored from backend office_policy:
 * 09:30–18:30 (9h), late login until 10:30, confirm at 7h & 9h, 10 min timeout → logout.
 */

export const OFFICE_START_MINUTES = 9 * 60 + 30; // 09:30
export const OFFICE_END_MINUTES = 18 * 60 + 30; // 18:30
export const LATE_LOGIN_GRACE_MINUTES = 60; // until 10:30
export const EXPECTED_WORK_MINUTES = 9 * 60;
export const CHECK_EARLY_MINUTES = 7 * 60;
export const CHECK_FULL_MINUTES = 9 * 60;
export const RESPONSE_TIMEOUT_MS = 10 * 60 * 1000;

export type WorkdayCheckpoint = '7h' | '9h';

export type WorkdayLogoutReason =
  | 'still_in_office_no'
  | 'no_response_7h'
  | 'no_response_9h'
  | 'eod_idle';

const WORK_START_KEY_PREFIX = '__work_start_';
const CONFIRMED_KEY_PREFIX = '__work_confirmed_';
const PROMPT_KEY_PREFIX = '__work_prompt_';

function localDateKey(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function workStartKey(date = localDateKey()): string {
  return `${WORK_START_KEY_PREFIX}${date}`;
}

function confirmedKey(checkpoint: WorkdayCheckpoint, date = localDateKey()): string {
  return `${CONFIRMED_KEY_PREFIX}${checkpoint}_${date}`;
}

function promptKey(checkpoint: WorkdayCheckpoint, date = localDateKey()): string {
  return `${PROMPT_KEY_PREFIX}${checkpoint}_${date}`;
}

/** Persist / refine today's first-login timestamp (prefer earliest). */
export function syncWorkStart(iso: string | Date): void {
  const next = typeof iso === 'string' ? iso : iso.toISOString();
  const key = workStartKey();
  const prev = localStorage.getItem(key);
  if (!prev || new Date(next).getTime() < new Date(prev).getTime()) {
    localStorage.setItem(key, next);
  }
}

export function clearWorkdaySession(): void {
  const date = localDateKey();
  localStorage.removeItem(workStartKey(date));
  localStorage.removeItem(confirmedKey('7h', date));
  localStorage.removeItem(confirmedKey('9h', date));
  localStorage.removeItem(promptKey('7h', date));
  localStorage.removeItem(promptKey('9h', date));
}

export function getWorkStartMs(): number | null {
  const raw = localStorage.getItem(workStartKey());
  if (!raw) return null;
  const ms = new Date(raw).getTime();
  return Number.isFinite(ms) ? ms : null;
}

export function workedMinutesNow(now = Date.now()): number {
  const start = getWorkStartMs();
  if (start == null) return 0;
  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart);
  dayEnd.setDate(dayEnd.getDate() + 1);
  const clippedStart = Math.max(start, dayStart.getTime());
  const clippedEnd = Math.min(now, dayEnd.getTime());
  return Math.max(0, Math.floor((clippedEnd - clippedStart) / 60000));
}

export function isCheckpointConfirmed(checkpoint: WorkdayCheckpoint): boolean {
  return localStorage.getItem(confirmedKey(checkpoint)) === '1';
}

export function markCheckpointConfirmed(checkpoint: WorkdayCheckpoint): void {
  localStorage.setItem(confirmedKey(checkpoint), '1');
  localStorage.removeItem(promptKey(checkpoint));
}

export function markPromptOpened(checkpoint: WorkdayCheckpoint): void {
  if (!localStorage.getItem(promptKey(checkpoint))) {
    localStorage.setItem(promptKey(checkpoint), String(Date.now()));
  }
}

export function getPromptOpenedAt(checkpoint: WorkdayCheckpoint): number | null {
  const raw = localStorage.getItem(promptKey(checkpoint));
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** Next checkpoint that needs a response, or null. */
export function nextDueCheckpoint(workedMinutes: number): WorkdayCheckpoint | null {
  if (workedMinutes >= CHECK_FULL_MINUTES && !isCheckpointConfirmed('9h')) return '9h';
  if (workedMinutes >= CHECK_EARLY_MINUTES && !isCheckpointConfirmed('7h')) return '7h';
  return null;
}

export function checkpointLabel(checkpoint: WorkdayCheckpoint): string {
  return checkpoint === '9h' ? '9 hours (full office day)' : '7 hours';
}

export function logoutReasonForTimeout(checkpoint: WorkdayCheckpoint): WorkdayLogoutReason {
  return checkpoint === '9h' ? 'no_response_9h' : 'no_response_7h';
}

export function logoutReasonLabel(reason: WorkdayLogoutReason): string {
  switch (reason) {
    case 'no_response_7h':
      return 'Auto-logout: no response after 7h office check';
    case 'no_response_9h':
      return 'Auto-logout: no response after 9h office check';
    case 'still_in_office_no':
      return 'Logged out: confirmed not in office';
    case 'eod_idle':
      return 'Auto-logout at 6:30 PM — laptop idle';
    default:
      return 'Auto-logout';
  }
}
