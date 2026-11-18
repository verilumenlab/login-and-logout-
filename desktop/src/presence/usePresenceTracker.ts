import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BreakAwayPayload,
  drainBreakAwayQueue,
  getConnectedWifiInfo,
  getSystemIdleSeconds,
  onBreakAwayQueued,
  onPowerEventQueued,
  setPresenceSession,
  showDesktopNotification,
} from '../api/ipc';
import {
  DeviceBlockedError,
  NetworkError,
  SessionExpiredError,
  getAttendanceStatus,
  pingBackend,
} from '../api/backend';
import {
  IDLE_BREAK_END_SECONDS,
  bindBreakQueueToUser,
  closeOrphanServerBreak,
  endAutoBreak,
  evaluateIdleBreak,
  flushBreakQueue,
  getOpenBreak,
  handleBreakAwaySignal,
  openBreakElapsedMinutes,
  openBreakType,
  pendingBreakCount,
} from '../attendance/breakTracker';
import {
  bindActivityQueueToUser,
  setDeviceSessionId,
  startActivitySampler,
} from '../activity/activityTracker';
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
const WORK_LOGIN_KEY = '__work_logged_in_v1';

function readPersistedWorkLogin(): boolean | null {
  const raw = localStorage.getItem(WORK_LOGIN_KEY);
  if (raw === '1') return true;
  if (raw === '0') return false;
  return null;
}

function persistWorkLogin(value: boolean | null): void {
  if (value === true) localStorage.setItem(WORK_LOGIN_KEY, '1');
  else if (value === false) localStorage.setItem(WORK_LOGIN_KEY, '0');
  else localStorage.removeItem(WORK_LOGIN_KEY);
}

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
  const loggedInRef = useRef<boolean | null>(readPersistedWorkLogin());
  const noticeRef = useRef(onNotice);
  noticeRef.current = onNotice;
  const workdayCheckRef = useRef(onWorkdayCheck);
  workdayCheckRef.current = onWorkdayCheck;

  const pushPresenceSession = useCallback(
    async (workLoggedIn: boolean | null) => {
      if (!device || !session) return;
      await setPresenceSession({
        signedIn: true,
        deviceId: device.device_id,
        userId: session.user_id,
        workLoggedIn: workLoggedIn === true,
      });
    },
    [device, session]
  );

  const setWorkLoggedIn = useCallback(
    (value: boolean | null) => {
      loggedInRef.current = value;
      persistWorkLogin(value);
      void pushPresenceSession(value);
    },
    [pushPresenceSession]
  );

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
    async (reason?: WorkdayLogoutReason | null, occurredAt?: Date | string | null) => {
      if (!device) return false;
      endAutoBreak(device.device_id);
      const wifiNow = await getConnectedWifiInfo();
      const mins = workedMinutesNow();
      const detail = reason ? buildLogoutDetail(reason, mins) : null;
      // Use power-event time when provided so a late sync does not extend hours.
      queueAppEvent(
        'APP_LOGOUT',
        device.device_id,
        wifiNow.is_wifi ? wifiNow.ssid : undefined,
        detail,
        occurredAt
      );
      clearWorkdaySession();
      workdayCheckRef.current?.(null);
      try {
        await flushBreakQueue();
        await flushQueue();
        setWorkLoggedIn(false);
        setStatus((prev) => ({ ...prev, isLoggedIn: false }));
        return true;
      } catch (err) {
        setWorkLoggedIn(false);
        setStatus((prev) => ({ ...prev, isLoggedIn: false }));
        if (err instanceof DeviceBlockedError) {
          onSessionExpired('blocked');
        } else if (err instanceof SessionExpiredError) {
          onSessionExpired('expired');
        }
        return false;
      }
    },
    [device, onSessionExpired, setWorkLoggedIn]
  );

  const tick = useCallback(async () => {
    if (!device || running.current) return;
    running.current = true;
    try {
      await ingestPowerEventsFromMain();

      const wifi = await getConnectedWifiInfo();
      if (!appLoginQueued.current) {
        appLoginQueued.current = true;
        await collectWifiEvents(device.device_id, device.os_type);
        // Auto clock-in once per app session, but not after an explicit work logout.
        if (loggedInRef.current !== false) {
          queueAppEvent('APP_LOGIN', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
          syncWorkStart(new Date());
        }
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

      // Prefer server truth from this flush; otherwise keep persisted work-login flag.
      if (isLoggedIn === true || isLoggedIn === false) {
        setWorkLoggedIn(isLoggedIn);
      }
      const workOpen = isLoggedIn ?? loggedInRef.current;

      // Breaks only while work-logged-in — evaluate AFTER login state is known.
      if (workOpen === true) {
        await evaluateIdleBreak(device.device_id);
        try {
          const idle = await getSystemIdleSeconds();
          if (idle < IDLE_BREAK_END_SECONDS && !getOpenBreak() && pendingBreakCount() === 0) {
            const statusNow = await getAttendanceStatus();
            if (statusNow.mode === 'ON_BREAK') {
              closeOrphanServerBreak(device.device_id);
            }
          }
        } catch (err) {
          if (!(err instanceof NetworkError)) {
            console.warn('[break] status reconcile failed:', err);
          }
        }
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
      if (nextLoggedIn === true || nextLoggedIn === false) {
        setWorkLoggedIn(nextLoggedIn);
      }
      setStatus({
        isOnline,
        pendingEvents: pendingEventCount() + pendingBreakCount(),
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
  }, [device, onSessionExpired, refreshBreakStatus, performWorkLogout, setWorkLoggedIn]);

  useEffect(() => {
    if (!active || !device || !session) {
      void setPresenceSession({ signedIn: false, deviceId: null, userId: null, workLoggedIn: false });
      return;
    }
    bindBreakQueueToUser(session.user_id);
    bindActivityQueueToUser(session.user_id);
    if (session.device_session_id) {
      setDeviceSessionId(session.device_session_id);
    } else {
      const saved = localStorage.getItem('__device_session_id');
      if (saved) setDeviceSessionId(saved);
    }
    void (async () => {
      await setPresenceSession({
        signedIn: true,
        deviceId: device.device_id,
        userId: session.user_id,
        workLoggedIn: loggedInRef.current === true,
      });
      // Apply durable idle/app-close break signals saved while the UI was gone.
      const pending = await drainBreakAwayQueue();
      for (const payload of pending) {
        if (loggedInRef.current === true || payload.signal === 'APP_CLOSE') {
          handleBreakAwaySignal(payload, device.device_id);
        }
      }
      if (pending.length) {
        refreshBreakStatus();
        try {
          await flushBreakQueue();
        } catch {
          // retry on next tick
        }
      }
    })();
  }, [active, device, session, refreshBreakStatus]);

  // Admin laptop-usage board: sample foreground app while work-logged-in (incl. tray).
  useEffect(() => {
    if (!active || !device) return;
    return startActivitySampler(device.device_id, () => loggedInRef.current === true);
  }, [active, device]);

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
          await performWorkLogout(reason, event.occurred_at);
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
          await performWorkLogout('eod_sleep', payload.occurred_at);
          const msg = logoutNotice('eod_sleep');
          noticeRef.current?.(msg);
          void showDesktopNotification('WorkPulse — Auto logout', msg);
          refreshBreakStatus();
          void tick();
          return;
        }
        // Lock/sleep breaks only while on the clock — avoids overnight orphan breaks.
        if (loggedInRef.current === true) {
          handleBreakAwaySignal(payload, device.device_id);
          refreshBreakStatus();
        }
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
    setWorkLoggedIn(true);
    setStatus((prev) => ({ ...prev, isLoggedIn: true }));
    setVersion((v) => v + 1);
    try {
      await flushQueue();
    } catch (err) {
      console.warn('[presence] work login sync failed:', err);
      if (err instanceof DeviceBlockedError) {
        onSessionExpired('blocked');
        return;
      }
      if (err instanceof SessionExpiredError) {
        onSessionExpired('expired');
        return;
      }
    }
    // Do not await tick — if a poller cycle is already running, awaiting it
    // never resolves the click handler and the UI stays on "Logging in…".
    void tick();
  }, [device, tick, onSessionExpired, setWorkLoggedIn]);

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
