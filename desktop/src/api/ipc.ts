/**
 * Typed IPC bridge to the Tauri 2 native layer, with safe fallbacks when the UI runs in a plain browser.
 */

import { DeviceInfo, NativeWifiEvent, WifiStatus } from '../types';

export function isTauriEnvironment(): boolean {
  return typeof window !== 'undefined' && ('__TAURI_INTERNALS__' in window || '__TAURI__' in window);
}

async function invokeNative<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke } = await import('@tauri-apps/api/core');
  return invoke<T>(command, args);
}

// Browser preview only: tokens live in memory and are never written to disk.
const memoryCredentialVault: Map<string, string> = new Map();

/**
 * Operating system credential storage
 * Windows: Credential Manager, macOS: Keychain
 */
export async function saveSecureToken(key: string, value: string): Promise<void> {
  if (isTauriEnvironment()) {
    try {
      await invokeNative('save_secure_token', { key, value });
      return;
    } catch (e) {
      console.warn('[IPC] Native credential store failed, using memory vault:', e);
    }
  }
  memoryCredentialVault.set(key, value);
}

export async function getSecureToken(key: string): Promise<string | null> {
  if (isTauriEnvironment()) {
    try {
      const val = await invokeNative<string | null>('get_secure_token', { key });
      if (val) return val;
    } catch (e) {
      console.warn('[IPC] Native credential read failed, using memory vault:', e);
    }
  }
  return memoryCredentialVault.get(key) || null;
}

export async function deleteSecureToken(key: string): Promise<void> {
  if (isTauriEnvironment()) {
    try {
      await invokeNative('delete_secure_token', { key });
    } catch (e) {
      console.warn('[IPC] Native credential delete failed:', e);
    }
  }
  memoryCredentialVault.delete(key);
}

export async function getNativeDeviceInfo(): Promise<DeviceInfo> {
  if (isTauriEnvironment()) {
    try {
      return await invokeNative<DeviceInfo>('get_device_info');
    } catch (e) {
      console.warn('[IPC] get_device_info failed:', e);
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
    agent_version: '0.1.0',
  };
}

/** Current Wi-Fi connection of this laptop (not connected / unknown outside the desktop app). */
export async function getConnectedWifiInfo(): Promise<WifiStatus> {
  if (isTauriEnvironment()) {
    try {
      return await invokeNative<WifiStatus>('get_connected_wifi');
    } catch (e) {
      console.warn('[IPC] get_connected_wifi failed:', e);
    }
  }
  return { ssid: '', bssid: '', is_wifi: false, timestamp: new Date().toISOString() };
}

/**
 * Wi-Fi connect/disconnect history recorded by the OS since `since` (RFC 3339).
 * Windows reads the WLAN-AutoConfig log; other platforms return an empty list.
 */
export async function getWifiEvents(since: string | null): Promise<NativeWifiEvent[]> {
  if (!isTauriEnvironment()) return [];
  try {
    return await invokeNative<NativeWifiEvent[]>('get_wifi_events', { since });
  } catch (e) {
    console.warn('[IPC] get_wifi_events failed:', e);
    return [];
  }
}
