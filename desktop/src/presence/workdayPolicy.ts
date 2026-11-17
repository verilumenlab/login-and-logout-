/**
 * Office day policy (mirrors backend office_policy):
 * - Actual login time recorded; 9h required from that login
 * - At 9h: ask still working? Yes → +10 min then auto logout; no reply 10 min → logout
 * - Logout before 9h: confirm continue vs logout; no reply 10 min → logout
 */

export const OFFICE_START_MINUTES = 9 * 60 + 30;
export const OFFICE_END_MINUTES = 18 * 60 + 30;
export const EXPECTED_WORK_MINUTES = 9 * 60;
export const EARLY_BAND_MINUTES = 7 * 60;
export const RESPONSE_TIMEOUT_MS = 10 * 60 * 1000;
export const NINE_HOUR_EXTENSION_MS = 10 * 60 * 1000;

export type WorkdayPromptKind = 'nine_hour' | 'early_logout';

export type WorkdayLogoutReason =
  | 'early_logout_confirmed'
  | 'early_logout_no_response'
  | 'nine_hour_no_response'
  | 'nine_hour_extension_ended'
  | 'nine_hour_manual'
  | 'eod_idle';

const WORK_START_KEY_PREFIX = '__work_start_';
const NINE_CONFIRMED_KEY = '__work_9h_confirmed_';
const NINE_PROMPT_KEY = '__work_9h_prompt_';
const NINE_EXTENSION_ENDS_KEY = '__work_9h_extension_ends_';
const EARLY_PROMPT_KEY = '__work_early_prompt_';

function localDateKey(d = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function workStartKey(date = localDateKey()): string {
  return `${WORK_START_KEY_PREFIX}${date}`;
}

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
  localStorage.removeItem(`${NINE_CONFIRMED_KEY}${date}`);
  localStorage.removeItem(`${NINE_PROMPT_KEY}${date}`);
  localStorage.removeItem(`${NINE_EXTENSION_ENDS_KEY}${date}`);
  localStorage.removeItem(`${EARLY_PROMPT_KEY}${date}`);
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

export function hasCompletedNineHours(workedMinutes = workedMinutesNow()): boolean {
  return workedMinutes >= EXPECTED_WORK_MINUTES;
}

export function isNineHourConfirmed(): boolean {
  return localStorage.getItem(`${NINE_CONFIRMED_KEY}${localDateKey()}`) === '1';
}

export function markNineHourConfirmedWithExtension(): number {
  const date = localDateKey();
  localStorage.setItem(`${NINE_CONFIRMED_KEY}${date}`, '1');
  localStorage.removeItem(`${NINE_PROMPT_KEY}${date}`);
  const endsAt = Date.now() + NINE_HOUR_EXTENSION_MS;
  localStorage.setItem(`${NINE_EXTENSION_ENDS_KEY}${date}`, String(endsAt));
  return endsAt;
}

export function getNineHourExtensionEndsAt(): number | null {
  const raw = localStorage.getItem(`${NINE_EXTENSION_ENDS_KEY}${localDateKey()}`);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function clearNineHourExtension(): void {
  localStorage.removeItem(`${NINE_EXTENSION_ENDS_KEY}${localDateKey()}`);
}

export function markNineHourPromptOpened(): number {
  const key = `${NINE_PROMPT_KEY}${localDateKey()}`;
  if (!localStorage.getItem(key)) {
    localStorage.setItem(key, String(Date.now()));
  }
  return Number(localStorage.getItem(key));
}

export function getNineHourPromptOpenedAt(): number | null {
  const raw = localStorage.getItem(`${NINE_PROMPT_KEY}${localDateKey()}`);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function markEarlyLogoutPromptOpened(): number {
  const key = `${EARLY_PROMPT_KEY}${localDateKey()}`;
  localStorage.setItem(key, String(Date.now()));
  return Date.now();
}

export function getEarlyLogoutPromptOpenedAt(): number | null {
  const raw = localStorage.getItem(`${EARLY_PROMPT_KEY}${localDateKey()}`);
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

export function clearEarlyLogoutPrompt(): void {
  localStorage.removeItem(`${EARLY_PROMPT_KEY}${localDateKey()}`);
}

/** True when a 9h completion prompt should be shown (once until confirmed/timeout). */
export function shouldShowNineHourPrompt(workedMinutes = workedMinutesNow()): boolean {
  return workedMinutes >= EXPECTED_WORK_MINUTES && !isNineHourConfirmed();
}

/** True when logout is being attempted before 9h are complete. */
export function shouldConfirmEarlyLogout(workedMinutes = workedMinutesNow()): boolean {
  return workedMinutes < EXPECTED_WORK_MINUTES;
}

export function earlyHoursLabel(workedMinutes: number): string {
  const h = Math.floor(workedMinutes / 60);
  const m = workedMinutes % 60;
  if (m === 0) return `${h} hour${h === 1 ? '' : 's'}`;
  return `${h}h ${m}m`;
}

export function buildLogoutDetail(reason: WorkdayLogoutReason, workedMinutes: number): string {
  const mins = Math.max(0, Math.floor(workedMinutes));
  switch (reason) {
    case 'early_logout_confirmed':
      return `WORKDAY|EARLY_LOGOUT|CONFIRMED|${mins} — Early logout after ${earlyHoursLabel(mins)} (confirmed)`;
    case 'early_logout_no_response':
      return `WORKDAY|EARLY_LOGOUT|NO_RESPONSE|${mins} — Auto-logout: no response on early logout check (${earlyHoursLabel(mins)})`;
    case 'nine_hour_no_response':
      return `WORKDAY|COMPLETED_9H|NO_RESPONSE|${mins} — Auto-logout: no response after 9-hour check`;
    case 'nine_hour_extension_ended':
      return `WORKDAY|COMPLETED_9H|EXTENSION_ENDED|${mins} — Auto-logout: 10-minute extension after 9 hours ended`;
    case 'nine_hour_manual':
      return `WORKDAY|COMPLETED_9H|CONFIRMED|${mins} — Logged out after completing 9 hours`;
    case 'eod_idle':
      return `WORKDAY|AUTO_LOGOUT|EOD_IDLE|${mins} — Auto-logout at 6:30 PM — laptop idle`;
    default:
      return `WORKDAY|AUTO_LOGOUT|UNKNOWN|${mins}`;
  }
}

export function logoutNotice(reason: WorkdayLogoutReason): string {
  switch (reason) {
    case 'early_logout_confirmed':
      return 'Logged out early — your actual hours were recorded.';
    case 'early_logout_no_response':
      return 'Auto logged out — no response on the early logout confirmation.';
    case 'nine_hour_no_response':
      return 'Auto logged out — no response after completing 9 hours.';
    case 'nine_hour_extension_ended':
      return 'Auto logged out — your extra 10 minutes after 9 hours have ended.';
    case 'nine_hour_manual':
      return 'Logged out after completing 9 hours.';
    case 'eod_idle':
      return 'Auto logged out at 6:30 PM — laptop was idle.';
    default:
      return 'Logged out.';
  }
}
