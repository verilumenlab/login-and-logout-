import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getConnectedWifiInfo,
  onPowerEventQueued,
  setPresenceSession,
} from '../api/ipc';
import { SessionExpiredError, pingBackend } from '../api/backend';
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

const POLL_INTERVAL_MS = 30_000;

/**
 * Runs automatic login/logout tracking while an employee is signed in.
 * Also consumes laptop power events (shutdown/sleep = logout, wake/boot = login).
 */
export function usePresenceTracker(
  device: DeviceInfo | null,
  active: boolean,
  onSessionExpired: () => void,
  session: UserSession | null = null
) {
  const [status, setStatus] = useState<TrackerStatus>({
    isOnline: true,
    pendingEvents: pendingEventCount(),
    lastSyncAt: lastSyncTime(),
    wifi: null,
    isLoggedIn: null,
  });
  const [version, setVersion] = useState(0);
  const running = useRef(false);
  const appLoginQueued = useRef(false);

  const tick = useCallback(async () => {
    if (!device || running.current) return;
    running.current = true;
    try {
      await ingestPowerEventsFromMain();
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

      setStatus((prev) => ({
        isOnline,
        pendingEvents: pendingEventCount(),
        lastSyncAt: lastSyncTime(),
        wifi,
        isLoggedIn: isLoggedIn ?? prev.isLoggedIn,
      }));
      if (isLoggedIn !== null) setVersion((v) => v + 1);
    } catch (err) {
      if (err instanceof SessionExpiredError) {
        onSessionExpired();
      } else {
        console.warn('[presence] tracking cycle failed:', err);
      }
    } finally {
      running.current = false;
    }
  }, [device, onSessionExpired]);

  // Tell Electron main whether a signed-in employee session exists (for powerMonitor attribution).
  useEffect(() => {
    if (!active || !device || !session) {
      void setPresenceSession({ signedIn: false, deviceId: null, userId: null });
      return;
    }
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

  useEffect(() => {
    if (!active || !device) {
      appLoginQueued.current = false;
      return;
    }
    tick();
    const timer = setInterval(tick, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [active, device, tick]);

  /** Records the app sign-out and tries to deliver it before the tokens are cleared. */
  const recordAppLogout = useCallback(async () => {
    if (!device) return;
    await setPresenceSession({ signedIn: false, deviceId: device.device_id, userId: null });
    const wifi = await getConnectedWifiInfo();
    await collectWifiEvents(device.device_id, device.os_type);
    queueAppEvent('APP_LOGOUT', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    try {
      await flushQueue();
    } catch {
      // Left in the queue; it is sent after the next sign-in.
    }
  }, [device]);

  return { status, dataVersion: version, refresh: tick, recordAppLogout };
}
