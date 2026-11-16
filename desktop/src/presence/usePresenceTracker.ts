import { useCallback, useEffect, useRef, useState } from 'react';

import {
  BreakAwayPayload,
  getConnectedWifiInfo,
  onBreakAwayQueued,
  onPowerEventQueued,
  setPresenceSession,
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

/**
 * Runs automatic login/logout tracking while an employee is signed in.
 * Also consumes laptop power events and drives automatic break tracking
 * (idle / lock / sleep).
 */
export function usePresenceTracker(
  device: DeviceInfo | null,
  active: boolean,
  onSessionExpired: (reason?: 'expired' | 'blocked') => void,
  session: UserSession | null = null
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

      setStatus((prev) => ({
        isOnline,
        pendingEvents: pendingEventCount(),
        lastSyncAt: lastSyncTime(),
        wifi,
        isLoggedIn: isLoggedIn ?? prev.isLoggedIn,
      }));
      refreshBreakStatus();
      // Always bump so Dashboard / Leave / Login history auto-refresh.
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
  }, [device, onSessionExpired, refreshBreakStatus]);

  // Tell Electron main whether a signed-in employee session exists (for powerMonitor attribution).
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

  // Live power events while the window is open.
  useEffect(() => {
    if (!active || !device) return;
    const unsubscribe = onPowerEventQueued((event: PresenceEventIn) => {
      enqueuePresenceEvent(event);
      void tick();
    });
    return unsubscribe;
  }, [active, device, tick]);

  // Lock / unlock / sleep break signals
  useEffect(() => {
    if (!active || !device) return;
    const unsubscribe = onBreakAwayQueued((payload: BreakAwayPayload) => {
      handleBreakAwaySignal(payload, device.device_id);
      refreshBreakStatus();
      void tick();
    });
    return unsubscribe;
  }, [active, device, tick, refreshBreakStatus]);

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

  /** Records the app sign-out and tries to deliver it before the tokens are cleared. */
  const recordAppLogout = useCallback(async () => {
    if (!device) return;
    endAutoBreak(device.device_id);
    await setPresenceSession({ signedIn: false, deviceId: device.device_id, userId: null });
    const wifi = await getConnectedWifiInfo();
    await collectWifiEvents(device.device_id, device.os_type);
    queueAppEvent('APP_LOGOUT', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    try {
      await flushBreakQueue();
      await flushQueue();
    } catch {
      // Left in the queue; it is sent after the next sign-in.
    }
  }, [device]);

  /** Manual work login (clock-in) while staying signed into the app. */
  const recordWorkLogin = useCallback(async () => {
    if (!device) return;
    const wifi = await getConnectedWifiInfo();
    queueAppEvent('APP_LOGIN', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    await flushQueue();
    setVersion((v) => v + 1);
    await tick();
  }, [device, tick]);

  /** Manual work logout (clock-out) while staying signed into the app. */
  const recordWorkLogout = useCallback(async () => {
    if (!device) return;
    endAutoBreak(device.device_id);
    const wifi = await getConnectedWifiInfo();
    queueAppEvent('APP_LOGOUT', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    try {
      await flushBreakQueue();
      await flushQueue();
    } catch {
      // queued for later
    }
    setVersion((v) => v + 1);
    await tick();
  }, [device, tick]);

  return {
    status,
    breakStatus,
    dataVersion: version,
    refresh: tick,
    recordAppLogout,
    recordWorkLogin,
    recordWorkLogout,
  };
}
