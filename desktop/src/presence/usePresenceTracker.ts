import { useCallback, useEffect, useRef, useState } from 'react';

import { getConnectedWifiInfo } from '../api/ipc';
import { SessionExpiredError, pingBackend } from '../api/backend';
import { DeviceInfo, TrackerStatus } from '../types';
import { collectWifiEvents, flushQueue, lastSyncTime, pendingEventCount, queueAppEvent } from './tracker';

const POLL_INTERVAL_MS = 30_000;

/**
 * Runs automatic login/logout tracking while an employee is signed in.
 * `appLoginPending` queues an APP_LOGIN once (on sign-in or when the app starts with a saved session).
 */
export function usePresenceTracker(
  device: DeviceInfo | null,
  active: boolean,
  onSessionExpired: () => void
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
    const wifi = await getConnectedWifiInfo();
    await collectWifiEvents(device.device_id, device.os_type);
    queueAppEvent('APP_LOGOUT', device.device_id, wifi.is_wifi ? wifi.ssid : undefined);
    try {
      await flushQueue();
    } catch {
      // Left in the queue; it is sent after the next sign-in.
    }
  }, [device]);

  /** Incremented whenever the server confirms new events, so screens can refresh their data. */
  return { status, dataVersion: version, refresh: tick, recordAppLogout };
}
