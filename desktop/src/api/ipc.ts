/**
 * Typed IPC bridge to the Electron native layer, with safe fallbacks for plain browser preview.
 */

import { DeviceInfo, NativeWifiEvent, PresenceEventIn, WifiStatus } from '../types';

type PresenceSession = {
  signedIn: boolean;
  deviceId?: string | null;
  userId?: string | null;
  workLoggedIn?: boolean;
};

export type UpdateStatusPayload = {
  state: string;
  version?: string;
  releaseNotes?: string | null;
  mandatory?: boolean;
  percent?: number;
  transferred?: number;
  total?: number;
  message?: string;
};

export type BreakAwaySignal =
  | 'LOCK'
  | 'UNLOCK'
  | 'SUSPEND'
  | 'RESUME'
  | 'IDLE_START'
  | 'IDLE_END'
  | 'APP_CLOSE';

export type BreakAwayPayload = {
  signal: BreakAwaySignal;
  occurred_at: string;
  device_id?: string | null;
};

type WorkpulseBridge = {
  platform: 'electron';
  saveSecureToken: (key: string, value: string) => Promise<void>;
  getSecureToken: (key: string) => Promise<string | null>;
  deleteSecureToken: (key: string) => Promise<void>;
  getDeviceInfo: () => Promise<DeviceInfo>;
  getConnectedWifi: () => Promise<WifiStatus>;
  getWifiEvents: (since: string | null) => Promise<NativeWifiEvent[]>;
  setPresenceSession: (session: PresenceSession) => Promise<void>;
  drainPowerEvents: () => Promise<PresenceEventIn[]>;
  peekPowerEvents: () => Promise<PresenceEventIn[]>;
  getSystemIdleSeconds?: () => Promise<number>;
  getActiveWindow?: () => Promise<{
    application_name: string;
    window_title: string | null;
    process_id: number;
  }>;
  showNotification?: (payload: { title: string; body: string }) => Promise<{ ok: boolean; reason?: string }>;
  onPowerEventQueued: (callback: (event: PresenceEventIn) => void) => () => void;
  onBreakAwayQueued?: (callback: (event: BreakAwayPayload) => void) => () => void;
  drainBreakAwayQueue?: () => Promise<BreakAwayPayload[]>;
  checkForUpdates?: () => Promise<unknown>;
  installUpdateNow?: () => Promise<{ ok: boolean; error?: string }>;
  getAppVersion?: () => Promise<string>;
  setUpdateContext?: (ctx: { deviceId?: string | null; channel?: string }) => Promise<unknown>;
  onUpdateStatus?: (callback: (payload: UpdateStatusPayload) => void) => () => void;
};

declare global {
  interface Window {
    workpulse?: WorkpulseBridge;
  }
}

export function isElectronEnvironment(): boolean {
  return typeof window !== 'undefined' && Boolean(window.workpulse);
}

/** @deprecated use isElectronEnvironment */
export function isTauriEnvironment(): boolean {
  return isElectronEnvironment();
}

function bridge(): WorkpulseBridge | null {
  return typeof window !== 'undefined' ? window.workpulse || null : null;
}

const memoryCredentialVault: Map<string, string> = new Map();

export async function saveSecureToken(key: string, value: string): Promise<void> {
  const wp = bridge();
  if (wp) {
    try {
      await wp.saveSecureToken(key, value);
      return;
    } catch (e) {
      console.warn('[IPC] Electron credential store failed, using memory vault:', e);
    }
  }
  memoryCredentialVault.set(key, value);
}

export async function getSecureToken(key: string): Promise<string | null> {
  const wp = bridge();
  if (wp) {
    try {
      const val = await wp.getSecureToken(key);
      if (val) return val;
    } catch (e) {
      console.warn('[IPC] Electron credential read failed, using memory vault:', e);
    }
  }
  return memoryCredentialVault.get(key) || null;
}

export async function deleteSecureToken(key: string): Promise<void> {
  const wp = bridge();
  if (wp) {
    try {
      await wp.deleteSecureToken(key);
    } catch (e) {
      console.warn('[IPC] Electron credential delete failed:', e);
    }
  }
  memoryCredentialVault.delete(key);
}

export async function getNativeDeviceInfo(): Promise<DeviceInfo> {
  const wp = bridge();
  if (wp) {
    try {
      return await wp.getDeviceInfo();
    } catch (e) {
      console.warn('[IPC] getDeviceInfo failed:', e);
    }
  }

  const ua = navigator.userAgent;
  let deviceId = localStorage.getItem('__dev_id');
  if (!deviceId) {
    deviceId = `BROWSER-${Math.random().toString(36).substring(2, 10).toUpperCase()}`;
    localStorage.setItem('__dev_id', deviceId);
  }
  return {
    device_id: deviceId,
    machine_name: 'Browser preview',
    os_type: ua.includes('Mac') ? 'macos' : ua.includes('Win') ? 'windows' : 'linux',
    os_version: '',
    arch: '',
    ip_address: '',
    mac_address: '',
    battery_percent: null,
    is_charging: null,
    enrolled: false,
    last_heartbeat: null,
    agent_version: '0.2.4',
  };
}

export async function getConnectedWifiInfo(): Promise<WifiStatus> {
  const wp = bridge();
  if (wp) {
    try {
      return await wp.getConnectedWifi();
    } catch (e) {
      console.warn('[IPC] getConnectedWifi failed:', e);
    }
  }
  return { ssid: '', bssid: '', is_wifi: false, timestamp: new Date().toISOString() };
}

export async function getWifiEvents(since: string | null): Promise<NativeWifiEvent[]> {
  const wp = bridge();
  if (!wp) return [];
  try {
    return await wp.getWifiEvents(since);
  } catch (e) {
    console.warn('[IPC] getWifiEvents failed:', e);
    return [];
  }
}

export async function setPresenceSession(session: PresenceSession): Promise<void> {
  const wp = bridge();
  if (!wp?.setPresenceSession) return;
  try {
    await wp.setPresenceSession(session);
  } catch (e) {
    console.warn('[IPC] setPresenceSession failed:', e);
  }
}

export async function drainPowerEvents(): Promise<PresenceEventIn[]> {
  const wp = bridge();
  if (!wp?.drainPowerEvents) return [];
  try {
    return (await wp.drainPowerEvents()) || [];
  } catch (e) {
    console.warn('[IPC] drainPowerEvents failed:', e);
    return [];
  }
}

export function onPowerEventQueued(callback: (event: PresenceEventIn) => void): () => void {
  const wp = bridge();
  if (!wp?.onPowerEventQueued) return () => undefined;
  return wp.onPowerEventQueued(callback);
}

export async function getSystemIdleSeconds(): Promise<number> {
  const wp = bridge();
  if (!wp?.getSystemIdleSeconds) return 0;
  try {
    return Math.max(0, Math.floor(Number(await wp.getSystemIdleSeconds()) || 0));
  } catch (e) {
    console.warn('[IPC] getSystemIdleSeconds failed:', e);
    return 0;
  }
}

export async function getActiveWindow(): Promise<{
  application_name: string;
  window_title: string | null;
  process_id: number;
}> {
  const wp = bridge();
  if (!wp?.getActiveWindow) {
    return { application_name: 'Unknown', window_title: null, process_id: 0 };
  }
  try {
    const win = await wp.getActiveWindow();
    return {
      application_name: String(win?.application_name || 'Unknown'),
      window_title: win?.window_title ? String(win.window_title) : null,
      process_id: Number(win?.process_id) || 0,
    };
  } catch (e) {
    console.warn('[IPC] getActiveWindow failed:', e);
    return { application_name: 'Unknown', window_title: null, process_id: 0 };
  }
}

export async function showDesktopNotification(title: string, body: string): Promise<void> {
  const wp = bridge();
  if (wp?.showNotification) {
    try {
      await wp.showNotification({ title, body });
      return;
    } catch (e) {
      console.warn('[IPC] showNotification failed:', e);
    }
  }
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    try {
      new Notification(title, { body });
    } catch {
      // ignore
    }
  }
}

export function onBreakAwayQueued(callback: (event: BreakAwayPayload) => void): () => void {
  const wp = bridge();
  if (!wp?.onBreakAwayQueued) return () => undefined;
  return wp.onBreakAwayQueued(callback);
}

/** Durable break signals saved while the window was closed / app was quitting. */
export async function drainBreakAwayQueue(): Promise<BreakAwayPayload[]> {
  const wp = bridge();
  if (!wp?.drainBreakAwayQueue) return [];
  try {
    return (await wp.drainBreakAwayQueue()) || [];
  } catch (e) {
    console.warn('[IPC] drainBreakAwayQueue failed:', e);
    return [];
  }
}

export function onUpdateStatus(callback: (payload: UpdateStatusPayload) => void): () => void {
  const wp = bridge();
  if (!wp?.onUpdateStatus) return () => undefined;
  return wp.onUpdateStatus(callback);
}

export async function checkForUpdates(): Promise<void> {
  const wp = bridge();
  if (!wp?.checkForUpdates) return;
  try {
    await wp.checkForUpdates();
  } catch (e) {
    console.warn('[IPC] checkForUpdates failed:', e);
  }
}

export async function installUpdateNow(): Promise<boolean> {
  const wp = bridge();
  if (!wp?.installUpdateNow) return false;
  try {
    const res = await wp.installUpdateNow();
    return Boolean(res?.ok);
  } catch (e) {
    console.warn('[IPC] installUpdateNow failed:', e);
    return false;
  }
}

export async function getAppVersion(): Promise<string> {
  const wp = bridge();
  if (wp?.getAppVersion) {
    try {
      return await wp.getAppVersion();
    } catch {
      // fall through
    }
  }
  return '0.1.0';
}

export async function setUpdateContext(ctx: {
  deviceId?: string | null;
  channel?: string;
}): Promise<void> {
  const wp = bridge();
  if (!wp?.setUpdateContext) return;
  try {
    await wp.setUpdateContext(ctx);
  } catch (e) {
    console.warn('[IPC] setUpdateContext failed:', e);
  }
}
