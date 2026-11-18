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
 * Infer logout from timeline:
 * 1) after 6:00 PM sleep/shutdown (no wake)
 * 2) office/Wi-Fi disconnect with no later Wi-Fi connect / app sign-in
 */
export function inferLogoutEvent(events: PresenceEvent[], workDate: string): PresenceEvent | null {
  const cutoff = eveningCutoffMs(workDate);
  const ordered = [...events].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at));
  let last: PresenceEvent | null = null;

  for (const ev of ordered) {
    const t = new Date(ev.occurred_at).getTime();
    if (!Number.isFinite(t)) continue;

    // Only a counted office login clears a prior leave (home APP_LOGIN must not revive hours).
    if (ev.event_type === 'WIFI_CONNECTED' && ev.attendance_action === 'CLOCK_IN') {
      last = null;
      continue;
    }
    if (ev.event_type === 'APP_LOGIN' && ev.attendance_action === 'CLOCK_IN') {
      last = null;
      continue;
    }
    if (ev.event_type === 'WIFI_DISCONNECTED' || ev.event_type === 'APP_LOGOUT') {
      last = ev;
      continue;
    }
    if (ev.event_type === 'SYSTEM_SHUTDOWN') {
      last = ev;
      continue;
    }
    if (ev.event_type === 'SYSTEM_SUSPEND' && t >= cutoff) {
      last = ev;
      continue;
    }
  }
  return last;
}

/** @deprecated use inferLogoutEvent */
export function finalEveningPowerOff(events: PresenceEvent[], workDate: string): PresenceEvent | null {
  return inferLogoutEvent(events, workDate);
}

/** Corrected logout ISO + worked minutes for one attendance history day. */
export function correctedHistoryDay(day: PresenceDay): {
  last_logout: string | null | undefined;
  worked_minutes: number;
  powerOffEvent: PresenceEvent | null;
  logout_reason: string | null;
  logout_note: string | null;
} {
  const powerOffEvent = inferLogoutEvent(day.events || [], day.work_date);
  if (!day.first_login) {
    return {
      last_logout: day.last_logout,
      worked_minutes: 0,
      powerOffEvent,
      logout_reason: day.logout_reason || null,
      logout_note: day.logout_note || null,
    };
  }

  const start = new Date(day.first_login).getTime();
  const endCap = dayEndMs(day.work_date);

  if (day.is_logged_in && !powerOffEvent) {
    const mins = Math.max(0, (Math.min(Date.now(), endCap) - start) / 60000);
    return {
      last_logout: day.last_logout,
      worked_minutes: mins,
      powerOffEvent,
      logout_reason: day.logout_reason || null,
      logout_note: day.logout_note || null,
    };
  }

  const endIso = powerOffEvent?.occurred_at || day.last_logout || null;
  if (!endIso) {
    return {
      last_logout: day.last_logout,
      worked_minutes: day.worked_minutes || 0,
      powerOffEvent,
      logout_reason: day.logout_reason || null,
      logout_note: day.logout_note || null,
    };
  }

  const end = Math.min(new Date(endIso).getTime(), endCap);
  const mins = Math.max(0, (end - start) / 60000);
  const reasonFromEvent =
    powerOffEvent?.event_type === 'WIFI_DISCONNECTED'
      ? 'office_wifi'
      : powerOffEvent?.event_type === 'SYSTEM_SUSPEND'
        ? 'sleep'
        : powerOffEvent?.event_type === 'SYSTEM_SHUTDOWN'
          ? 'shutdown'
          : powerOffEvent?.event_type === 'APP_LOGOUT'
            ? 'app_logout'
            : null;
  return {
    last_logout: powerOffEvent?.occurred_at || day.last_logout,
    worked_minutes: mins,
    powerOffEvent,
    logout_reason: day.logout_reason || reasonFromEvent,
    logout_note: day.logout_note || null,
  };
}

export function isPowerOffCountedAsLogout(ev: PresenceEvent, day: PresenceDay): boolean {
  if (ev.attendance_action === 'CLOCK_OUT') return true;
  const power = inferLogoutEvent(day.events || [], day.work_date);
  return Boolean(power && power.occurred_at === ev.occurred_at && power.event_type === ev.event_type);
}
