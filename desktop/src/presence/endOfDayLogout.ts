/**
 * End-of-day (6:30 PM local) laptop-use check.
 * - Idle → automatic work logout
 * - Still using → one-time notice; keep checking so logout happens once they go idle
 */

import { getSystemIdleSeconds } from '../api/ipc';

/** Local wall-clock time when the EOD check begins. */
export const EOD_HOUR = 18;
export const EOD_MINUTE = 30;
/** Idle this long after 6:30 → treat as "not using the laptop". */
export const EOD_IDLE_SECONDS = 5 * 60;

const LOGOUT_DONE_KEY = '__eod_auto_logout_date';
const ACTIVE_NOTIFIED_KEY = '__eod_active_notified_date';

export type EndOfDayResult =
  | { action: 'skipped'; reason: 'before_eod' | 'already_logged_out' | 'not_working' }
  | { action: 'auto_logout'; idleSeconds: number }
  | { action: 'still_active'; idleSeconds: number; notified: boolean };

function localDateKey(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function isPastEndOfDay(now = new Date()): boolean {
  const mins = now.getHours() * 60 + now.getMinutes();
  return mins >= EOD_HOUR * 60 + EOD_MINUTE;
}

export function endOfDayLabel(): string {
  const h = EOD_HOUR % 12 || 12;
  const ampm = EOD_HOUR >= 12 ? 'PM' : 'AM';
  const m = String(EOD_MINUTE).padStart(2, '0');
  return `${h}:${m} ${ampm}`;
}

/**
 * Called from the presence poller while the employee is signed in and still on a work session.
 * `isWorkLoggedIn` should be true when attendance is open (Logged in).
 */
export async function evaluateEndOfDayLogout(options: {
  isWorkLoggedIn: boolean;
}): Promise<EndOfDayResult> {
  if (!isPastEndOfDay()) {
    return { action: 'skipped', reason: 'before_eod' };
  }

  const today = localDateKey();
  if (localStorage.getItem(LOGOUT_DONE_KEY) === today) {
    return { action: 'skipped', reason: 'already_logged_out' };
  }
  if (!options.isWorkLoggedIn) {
    return { action: 'skipped', reason: 'not_working' };
  }

  const idleSeconds = await getSystemIdleSeconds();
  if (idleSeconds >= EOD_IDLE_SECONDS) {
    localStorage.setItem(LOGOUT_DONE_KEY, today);
    return { action: 'auto_logout', idleSeconds };
  }

  const alreadyNotified = localStorage.getItem(ACTIVE_NOTIFIED_KEY) === today;
  if (!alreadyNotified) {
    localStorage.setItem(ACTIVE_NOTIFIED_KEY, today);
  }
  return { action: 'still_active', idleSeconds, notified: !alreadyNotified };
}

export function resetEndOfDayStateForTests(): void {
  localStorage.removeItem(LOGOUT_DONE_KEY);
  localStorage.removeItem(ACTIVE_NOTIFIED_KEY);
}
