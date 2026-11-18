import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BreakAwayPayload,
  getConnectedWifiInfo,
  onBreakAwayQueued,
  onPowerEventQueued,
  setPresenceSession,
  showDesktopNotification,
} from '../api/ipc';
import { DeviceBlockedError, NetworkError, SessionExpiredError, pingBackend } from '../api/backend';
import {
  bindBreakQueueToUser,
  endAutoBreak,
  evaluateIdleBreak,
  flushBreakQueue,
  getOpenBreak,
  handleBreakAwaySignal,
  openBreakElapsedMinutes,
  openBreakType,
  pendingBreakCount,
} from '../attendance/breakTracker';
import { DeviceInfo, PresenceEventIn, TrackerStatus, UserSession } from '../types';
import { endOfDayLabel, evaluateEndOfDayLogout } from './endOfDayLogout';
import {
  WorkdayLogoutReason,
  WorkdayPromptKind,
  buildLogoutDetail,
  clearWorkdaySession,
  getNineHourExtensionEndsAt,
  getNineHourPromptOpenedAt,
  hasCompletedNineHours,
  isPastSleepLogoutTime,
  logoutNotice,
  markNineHourPromptOpened,
  shouldShowNineHourPrompt,
  syncWorkStart,
  workedMinutesNow,
} from './workdayPolicy';
import {
  collectWifiEvents,
  enqueuePresenceEvent,
  flushQueue,
  ingestPowerEventsFromMain,
  lastSyncTime,
  pendingEventCount,
  queueAppEvent,
} from './tracker';

const POLL_INTERVAL_MS = 15_000;

export type BreakTrackerStatus = {
  isOnBreak: boolean;
  breakSource: string | null;
  breakType: 'LUNCH' | 'PERSONAL' | 'COFFEE' | 'MEETING' | null;
  breakElapsedMinutes: number;
  pendingBreakEvents: number;
};

export type WorkdayCheckRequest = {
  kind: WorkdayPromptKind;
  openedAt: number;
  workedMinutes: number;
};

/**
 * Automatic login/logout tracking, idle breaks, 9h completion prompt, and 6:30 idle stop.
 */
export function usePresenceTracker(
  device: DeviceInfo | null,
  active: boolean,
  onSessionExpired: (reason?: 'expired' | 'blocked') => void,
  session: UserSession | null = null,
  onNotice?: (message: string) => void,
  onWorkdayCheck?: (request: WorkdayCheckRequest | null) => void
) {
  const [status, setStatus] = useState<TrackerStatus>({
    isOnline: true,
    pendingEvents: pendingEventCount(),
    lastSyncAt: lastSyncTime(),
    wifi: null,
    isLoggedIn: null,
  });
  const [breakStatus, setBreakStatus] = useState<BreakTrackerStatus>({
    isOnBreak: Boolean(getOpenBreak()),
    breakSource: getOpenBreak()?.source ?? null,
    breakType: openBreakType(),
    breakElapsedMinutes: openBreakElapsedMinutes(),
    pendingBreakEvents: pendingBreakCount(),
  });
  const [version, setVersion] = useState(0);
  const running = useRef(false);
  const appLoginQueued = useRef(false);
  const loggedInRef = useRef<boolean | null>(null);
  const noticeRef = useRef(onNotice);
  noticeRef.current = onNotice;
  const workdayCheckRef = useRef(onWorkdayCheck);
  workdayCheckRef.current = onWorkdayCheck;

  const refreshBreakStatus = useCallback(() => {
    const open = getOpenBreak();
    setBreakStatus({
      isOnBreak: Boolean(open),
      breakSource: open?.source ?? null,
      breakType: openBreakType(),
      breakElapsedMinutes: openBreakElapsedMinutes(),
      pendingBreakEvents: pendingBreakCount(),
    });
  }, []);

  const performWorkLogout = useCallback(
    async (reason?: WorkdayLogoutReason | null) => {
      if (!device) return false;
      endAutoBreak(device.device_id);
      const wifiNow = await getConnectedWifiInfo();
      const mins = workedMinutesNow();
      const detail = reason ? buildLogoutDetail(reason, mins) : null;
      queueAppEvent('APP_LOGOUT', device.device_id, wifiNow.is_wifi ? wifiNow.ssid : undefined, detail);
      clearWorkdaySession();
      workdayCheckRef.current?.(null);
      try {
        await flushBreakQueue();
        await flushQueue();
        loggedInRef.current = false;
        return true;
      } catch {
        loggedInRef.current = false;
        return false;
      }
    },
    [device]
  );

  const tick = useCallback(async () => {
    if (!device || running.current) return;
    running.current = true;
    try {
      await ingestPowerEventsFromMain();
      await evaluateIdleBreak(device.device_id);

      const wifi = await getConnectedWifiInfo();
      if (!appLoginQueued.current) {
        appLoginQueued.current = true;
        await collectWifiEvents(device.device_id, device.os_type);
        queueAppEvent('APP_LOGIN', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
        syncWorkStart(new Date());
      } else {
        await collectWifiEvents(device.device_id, device.os_type);
      }

      let isLoggedIn: boolean | null = null;
      let isOnline = true;
      if (pendingEventCount() > 0) {
        isLoggedIn = await flushQueue();
        isOnline = pendingEventCount() === 0 || (await pingBackend());
      } else {
        isOnline = await pingBackend();
      }

      if (pendingBreakCount() > 0) {
        try {
          await flushBreakQueue();
        } catch (err) {
          if (!(err instanceof NetworkError)) {
            console.warn('[break] sync failed:', err);
          }
        }
      }

      const workOpen = isLoggedIn ?? loggedInRef.current;
      if (workOpen === true) {
        const worked = workedMinutesNow();

        // After 9h confirm +10 min: when extension ends → auto logout.
        const extensionEnds = getNineHourExtensionEndsAt();
        if (extensionEnds != null && Date.now() >= extensionEnds) {
          await performWorkLogout('nine_hour_extension_ended');
          isLoggedIn = false;
          const msg = 'Auto logged out — your extra 10 minutes after 9 hours have ended.';
          noticeRef.current?.(msg);
          void showDesktopNotification('WorkPulse — Auto logout', msg);
        } else if (shouldShowNineHourPrompt(worked)) {
          const already = getNineHourPromptOpenedAt();
          const openedAt = markNineHourPromptOpened();
          workdayCheckRef.current?.({ kind: 'nine_hour', openedAt, workedMinutes: worked });
          if (!already) {
            void showDesktopNotification(
              'WorkPulse — 9 hours completed',
              'You have completed 9 hours of work. Are you still working in the office? Reply within 10 minutes.'
            );
          }
        }

        // 6:30 PM idle hard stop (wall clock).
        if ((isLoggedIn ?? loggedInRef.current) === true) {
          const eod = await evaluateEndOfDayLogout({ isWorkLoggedIn: true });
          if (eod.action === 'auto_logout') {
            await performWorkLogout('eod_idle');
            isLoggedIn = false;
            const msg = `Auto logged out at ${endOfDayLabel()} — laptop was idle (not in use).`;
            noticeRef.current?.(msg);
            void showDesktopNotification('WorkPulse — Auto logout', msg);
          } else if (eod.action === 'still_active' && eod.notified) {
            const msg = `Still using your laptop after ${endOfDayLabel()}. You stay logged in until idle or you log out.`;
            noticeRef.current?.(msg);
            void showDesktopNotification('WorkPulse — Still working?', msg);
          }
        }
      } else if (workOpen === false) {
        workdayCheckRef.current?.(null);
      }

      const nextLoggedIn = isLoggedIn ?? loggedInRef.current;
      loggedInRef.current = nextLoggedIn;
      setStatus({
        isOnline,
        pendingEvents: pendingEventCount(),
        lastSyncAt: lastSyncTime(),
        wifi,
        isLoggedIn: nextLoggedIn,
      });
      refreshBreakStatus();
      setVersion((v) => v + 1);
    } catch (err) {
      if (err instanceof DeviceBlockedError) {
        onSessionExpired('blocked');
      } else if (err instanceof SessionExpiredError) {
        onSessionExpired('expired');
      } else {
        console.warn('[presence] tracking cycle failed:', err);
      }
    } finally {
      running.current = false;
    }
  }, [device, onSessionExpired, refreshBreakStatus, performWorkLogout]);

  useEffect(() => {
    if (!active || !device || !session) {
      void setPresenceSession({ signedIn: false, deviceId: null, userId: null });
      return;
    }
    bindBreakQueueToUser(session.user_id);
    void setPresenceSession({
      signedIn: true,
      deviceId: device.device_id,
      userId: session.user_id,
    });
  }, [active, device, session]);

  useEffect(() => {
    if (!active || !device) return;
    const unsubscribe = onPowerEventQueued((event: PresenceEventIn) => {
      enqueuePresenceEvent(event);
      if (
        (event.event_type === 'SYSTEM_SUSPEND' || event.event_type === 'SYSTEM_SHUTDOWN') &&
        isPastSleepLogoutTime(event.occurred_at ? new Date(event.occurred_at) : new Date()) &&
        loggedInRef.current === true
      ) {
        const reason = event.event_type === 'SYSTEM_SHUTDOWN' ? 'eod_shutdown' : 'eod_sleep';
        void (async () => {
          await performWorkLogout(reason);
          const msg = logoutNotice(reason);
          noticeRef.current?.(msg);
          void showDesktopNotification('WorkPulse — Auto logout', msg);
          void tick();
        })();
        return;
      }
      void tick();
    });
    return unsubscribe;
  }, [active, device, tick, performWorkLogout]);

  useEffect(() => {
    if (!active || !device) return;
    const unsubscribe = onBreakAwayQueued((payload: BreakAwayPayload) => {
      void (async () => {
        // After 6:00 PM, system sleep = left for the day → logout (hours stop at sleep).
        if (
          payload.signal === 'SUSPEND' &&
          isPastSleepLogoutTime(payload.occurred_at ? new Date(payload.occurred_at) : new Date()) &&
          loggedInRef.current === true
        ) {
          await performWorkLogout('eod_sleep');
          const msg = logoutNotice('eod_sleep');
          noticeRef.current?.(msg);
          void showDesktopNotification('WorkPulse — Auto logout', msg);
          refreshBreakStatus();
          void tick();
          return;
        }
        handleBreakAwaySignal(payload, device.device_id);
        refreshBreakStatus();
        void tick();
      })();
    });
    return unsubscribe;
  }, [active, device, tick, refreshBreakStatus, performWorkLogout]);

  useEffect(() => {
    if (!active || !device) {
      appLoginQueued.current = false;
      return;
    }
    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void tick();
    };
    const onFocus = () => void tick();
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
  }, [active, device, tick]);

  const recordAppLogout = useCallback(async () => {
    if (!device) return;
    endAutoBreak(device.device_id);
    await setPresenceSession({ signedIn: false, deviceId: device.device_id, userId: null });
    const wifi = await getConnectedWifiInfo();
    await collectWifiEvents(device.device_id, device.os_type);
    const mins = workedMinutesNow();
    const reason: WorkdayLogoutReason = hasCompletedNineHours(mins) ? 'nine_hour_manual' : 'early_logout_confirmed';
    queueAppEvent(
      'APP_LOGOUT',
      device.device_id,
      wifi.is_wifi ? wifi.ssid : undefined,
      buildLogoutDetail(reason, mins)
    );
    clearWorkdaySession();
    workdayCheckRef.current?.(null);
    try {
      await flushBreakQueue();
      await flushQueue();
    } catch {
      // queued for next sign-in
    }
  }, [device]);

  const recordWorkLogin = useCallback(async () => {
    if (!device) return;
    const wifi = await getConnectedWifiInfo();
    queueAppEvent('APP_LOGIN', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    syncWorkStart(new Date());
    loggedInRef.current = true;
    setStatus((prev) => ({ ...prev, isLoggedIn: true }));
    setVersion((v) => v + 1);
    try {
      await flushQueue();
    } catch (err) {
      // Keep local logged-in; events stay queued for the next sync cycle.
      console.warn('[presence] work login sync failed:', err);
    }
    // Do not await tick — if a poller cycle is already running, awaiting it
    // never resolves the click handler and the UI stays on "Logging in…".
    void tick();
  }, [device, tick]);

  const recordWorkLogout = useCallback(
    async (reason?: WorkdayLogoutReason | null) => {
      if (!device) return;
      const mins = workedMinutesNow();
      const resolved =
        reason ?? (hasCompletedNineHours(mins) ? 'nine_hour_manual' : 'early_logout_confirmed');
      await performWorkLogout(resolved);
      setVersion((v) => v + 1);
      await tick();
    },
    [device, performWorkLogout, tick]
  );

  return {
    status,
    breakStatus,
    dataVersion: version,
    refresh: tick,
    recordAppLogout,
    recordWorkLogin,
    recordWorkLogout,
    syncWorkStartFromServer: syncWorkStart,
    getWorkedMinutes: workedMinutesNow,
  };
}
