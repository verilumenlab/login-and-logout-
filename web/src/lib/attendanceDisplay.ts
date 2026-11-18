import type { PresenceDay, PresenceEvent } from '@/lib/api-client';

/** 6:00 PM local on the work date (ms). */
function eveningCutoffMs(workDate: string): number {
  const [y, m, d] = workDate.split('-').map(Number);
  return new Date(y, m - 1, d, 18, 0, 0, 0).getTime();
}

function dayEndMs(workDate: string): number {
  const [y, m, d] = workDate.split('-').map(Number);
  return new Date(y, m - 1, d + 1).getTime();
}

/**
 * Last system sleep/shutdown after 6:00 PM with no later same-evening wake.
 * Hours must stop here (not at 11:59 PM).
 */
export function finalEveningPowerOff(events: PresenceEvent[], workDate: string): PresenceEvent | null {
  const cutoff = eveningCutoffMs(workDate);
  const ordered = [...events].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
  let last: PresenceEvent | null = null;
  for (const ev of ordered) {
    const t = new Date(ev.occurred_at).getTime();
    if (!Number.isFinite(t) || t < cutoff) continue;
    if (ev.event_type === 'SYSTEM_SUSPEND' || ev.event_type === 'SYSTEM_SHUTDOWN') {
      last = ev;
    } else if (ev.event_type === 'SYSTEM_RESUME' || ev.event_type === 'SYSTEM_STARTUP') {
      last = null;
    }
  }
  return last;
}

/** Corrected logout ISO + worked minutes for one attendance history day. */
export function correctedHistoryDay(day: PresenceDay): {
  last_logout: string | null | undefined;
  worked_minutes: number;
  powerOffEvent: PresenceEvent | null;
} {
  const powerOffEvent = finalEveningPowerOff(day.events || [], day.work_date);
  if (!day.first_login) {
    return { last_logout: day.last_logout, worked_minutes: 0, powerOffEvent };
  }

  const start = new Date(day.first_login).getTime();
  const endCap = dayEndMs(day.work_date);
  let endIso = powerOffEvent?.occurred_at || day.last_logout || null;

  if (day.is_logged_in && !powerOffEvent) {
    const mins = Math.max(0, (Math.min(Date.now(), endCap) - start) / 60000);
    return { last_logout: day.last_logout, worked_minutes: mins, powerOffEvent };
  }

  if (!endIso) {
    return { last_logout: day.last_logout, worked_minutes: day.worked_minutes || 0, powerOffEvent };
  }

  const end = Math.min(new Date(endIso).getTime(), endCap);
  const mins = Math.max(0, (end - start) / 60000);
  return {
    last_logout: powerOffEvent?.occurred_at || day.last_logout,
    worked_minutes: mins,
    powerOffEvent,
  };
}

export function isPowerOffCountedAsLogout(ev: PresenceEvent, day: PresenceDay): boolean {
  if (ev.attendance_action === 'CLOCK_OUT') return true;
  const power = finalEveningPowerOff(day.events || [], day.work_date);
  return Boolean(power && power.occurred_at === ev.occurred_at && power.event_type === ev.event_type);
}
