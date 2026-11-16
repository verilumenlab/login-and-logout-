/**
 * Backend API client for the employee desktop app.
 */

import {
  DeviceInfo,
  LeaveApplyPayload,
  LeaveBalance,
  LeaveRequest,
  LeaveType,
  PresenceEventIn,
  PresenceHistory,
  PresenceMonthSummary,
  PresenceSyncResponse,
  UserSession,
} from '../types';
import { deleteSecureToken, getSecureToken, saveSecureToken } from './ipc';

const DEFAULT_SERVER_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  'https://workpulse-api-pm0x.onrender.com/api/v1';
const SESSION_KEY = '__user_session';

/** Prefer baked production URL; only keep a saved override if it is not localhost. */
function resolveInitialServerUrl(): string {
  const saved = localStorage.getItem('__backend_server_url');
  if (saved && !/localhost|127\.0\.0\.1/i.test(saved)) return saved;
  return DEFAULT_SERVER_URL;
}

let serverUrl = resolveInitialServerUrl();
if (serverUrl === DEFAULT_SERVER_URL) {
  localStorage.setItem('__backend_server_url', DEFAULT_SERVER_URL);
}

/** The server could not be reached (offline, DNS, timeout). Safe to retry later. */
export class NetworkError extends Error {}
/** Tokens are no longer valid; the employee must sign in again. */
export class SessionExpiredError extends Error {}
/** Admin blocked this workstation — force sign-out. */
export class DeviceBlockedError extends Error {}
/** The server answered with an error status. */
export class HttpError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
  }
}

function isDeviceBlockedMessage(message: string): boolean {
  return /device has been blocked|device is blocked|blocked by an administrator/i.test(message);
}

function currentDeviceIdentifier(): string | null {
  try {
    return localStorage.getItem('__device_hardware_id') || localStorage.getItem('__device_id');
  } catch {
    return null;
  }
}

export function rememberDeviceIdentifier(deviceId: string | null | undefined): void {
  if (!deviceId) return;
  try {
    localStorage.setItem('__device_hardware_id', deviceId);
  } catch {
    // ignore storage failures
  }
}

export function setBackendServerUrl(url: string): void {
  serverUrl = url.trim().replace(/\/$/, '');
  localStorage.setItem('__backend_server_url', serverUrl);
}

export function getBackendServerUrl(): string {
  return serverUrl;
}

function url(endpoint: string): string {
  return `${serverUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
}

async function readError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed.detail === 'string') return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ');
    }
  } catch {
    // not JSON
  }
  return text || `HTTP ${res.status}`;
}

async function send(endpoint: string, options: RequestInit, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Client-Type': 'desktop',
    ...(options.headers as Record<string, string>),
  };
  const deviceId = currentDeviceIdentifier();
  if (deviceId) headers['X-Device-Identifier'] = deviceId;
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    return await fetch(url(endpoint), { ...options, headers, signal: AbortSignal.timeout(15000) });
  } catch (err) {
    throw new NetworkError(err instanceof Error ? err.message : String(err));
  }
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = await getSecureToken('refresh_token');
  if (!refreshToken) return null;
  const res = await send('/auth/refresh', { method: 'POST', body: JSON.stringify({ refresh_token: refreshToken }) }, null);
  if (!res.ok) {
    const message = await readError(res);
    if (isDeviceBlockedMessage(message)) {
      throw new DeviceBlockedError(message || 'This device has been blocked by an administrator.');
    }
    return null;
  }
  const data = await res.json();
  await saveSecureToken('access_token', data.access_token);
  if (data.refresh_token) await saveSecureToken('refresh_token', data.refresh_token);
  return data.access_token as string;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  let res = await send(endpoint, options, await getSecureToken('access_token'));
  if (res.status === 401) {
    const message = await readError(res.clone());
    if (isDeviceBlockedMessage(message)) {
      throw new DeviceBlockedError(message || 'This device has been blocked by an administrator.');
    }
    const newToken = await refreshAccessToken();
    if (!newToken) throw new SessionExpiredError('Your session has expired. Please sign in again.');
    res = await send(endpoint, options, newToken);
    if (res.status === 401) {
      const retryMessage = await readError(res);
      if (isDeviceBlockedMessage(retryMessage)) {
        throw new DeviceBlockedError(retryMessage || 'This device has been blocked by an administrator.');
      }
      throw new SessionExpiredError('Your session has expired. Please sign in again.');
    }
  }
  if (!res.ok) {
    const message = await readError(res);
    if ((res.status === 403 || res.status === 401) && isDeviceBlockedMessage(message)) {
      throw new DeviceBlockedError(message || 'This device has been blocked by an administrator.');
    }
    throw new HttpError(message, res.status);
  }
  return (await res.json()) as T;
}

export async function pingBackend(): Promise<boolean> {
  try {
    const res = await fetch(url('/health'), { signal: AbortSignal.timeout(4000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Authentication (employee accounts only)
// ---------------------------------------------------------------------------

interface EmployeeProfileInfo {
  employee_id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  job_title: string | null;
  department_name: string | null;
}

export async function loginUser(email: string, password: string, device: DeviceInfo): Promise<UserSession> {
  const res = await send(
    '/auth/desktop-login',
    {
      method: 'POST',
      body: JSON.stringify({
        email: email.trim(),
        password,
        device_identifier: device.device_id,
        device_name: device.machine_name || 'Employee Laptop',
        platform: device.os_type,
        os_name: device.os_type === 'macos' ? 'macOS' : device.os_type === 'windows' ? 'Windows' : 'Linux',
        os_version: device.os_version || undefined,
        mac_address: device.mac_address || undefined,
        agent_version: device.agent_version,
      }),
    },
    null
  );
  if (!res.ok) {
    const message = await readError(res);
    if (res.status === 403 && isDeviceBlockedMessage(message)) {
      throw new DeviceBlockedError(message);
    }
    throw new Error(message);
  }

  const data = await res.json();
  if (String(data.user?.role || '').toUpperCase() !== 'EMPLOYEE') {
    throw new Error('This app is only for Employee accounts. Admin, HR and Manager accounts use the web portal.');
  }

  await saveSecureToken('access_token', data.access_token);
  await saveSecureToken('refresh_token', data.refresh_token);
  localStorage.setItem('__device_id', data.device_id || '');
  localStorage.setItem('__employee_id', data.employee_id || '');
  rememberDeviceIdentifier(device.device_id);

  let profile: EmployeeProfileInfo | null = null;
  try {
    profile = await request<EmployeeProfileInfo>('/presence/me');
  } catch {
    // Name is cosmetic; continue with the email.
  }

  const session: UserSession = {
    user_id: data.user.id,
    email: data.user.email,
    first_name: profile?.first_name || data.user.email.split('@')[0],
    last_name: profile?.last_name || '',
    role: 'EMPLOYEE',
    organization_id: data.user.organization_id,
    employee_id: data.employee_id,
    employee_code: profile?.employee_code,
    job_title: profile?.job_title || undefined,
    department_name: profile?.department_name || undefined,
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export async function logoutUser(): Promise<void> {
  const refreshToken = await getSecureToken('refresh_token');
  try {
    await request('/auth/logout', {
      method: 'POST',
      body: JSON.stringify(refreshToken ? { refresh_token: refreshToken } : {}),
    });
  } catch {
    // Signing out locally must work offline too.
  }
  await clearLocalSession();
}

export async function clearLocalSession(): Promise<void> {
  await deleteSecureToken('access_token');
  await deleteSecureToken('refresh_token');
  localStorage.removeItem(SESSION_KEY);
}

export function getStoredUserSession(): UserSession | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as UserSession) : null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Presence: login & logout via app + Wi-Fi
// ---------------------------------------------------------------------------

export function syncPresenceEvents(events: PresenceEventIn[]): Promise<PresenceSyncResponse> {
  return request<PresenceSyncResponse>('/presence/events', { method: 'POST', body: JSON.stringify({ events }) });
}

export function getPresenceSummary(month?: string): Promise<PresenceMonthSummary> {
  return request<PresenceMonthSummary>(`/presence/my-summary${month ? `?month=${month}` : ''}`);
}

export function getPresenceHistory(startDate: string, endDate: string): Promise<PresenceHistory> {
  const qs = new URLSearchParams({ start_date: startDate, end_date: endDate });
  return request<PresenceHistory>(`/presence/my-history?${qs.toString()}`);
}

// ---------------------------------------------------------------------------
// Attendance offline sync (auto breaks)
// ---------------------------------------------------------------------------

export type OfflineAttendanceItem = {
  client_event_id: string;
  action: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END';
  occurred_at: string;
  break_type?: string | null;
  source?: string | null;
  is_wfh?: boolean;
  notes?: string | null;
};

export type AttendanceOfflineSyncResponse = {
  received_count: number;
  inserted_count: number;
  duplicate_count: number;
  affected_work_dates: string[];
  message: string;
};

export function syncOfflineAttendance(events: OfflineAttendanceItem[]): Promise<AttendanceOfflineSyncResponse> {
  return request<AttendanceOfflineSyncResponse>('/attendance/sync-offline', {
    method: 'POST',
    body: JSON.stringify({ events }),
  });
}

// ---------------------------------------------------------------------------
// Leave
// ---------------------------------------------------------------------------

export function getLeaveTypes(): Promise<LeaveType[]> {
  return request<LeaveType[]>('/leave/types');
}

export function getLeaveBalances(): Promise<LeaveBalance[]> {
  return request<LeaveBalance[]>('/leave/balances');
}

export function getLeaveRequests(): Promise<LeaveRequest[]> {
  return request<LeaveRequest[]>('/leave/');
}

export function applyForLeave(payload: LeaveApplyPayload): Promise<LeaveRequest> {
  return request<LeaveRequest>('/leave/apply', { method: 'POST', body: JSON.stringify(payload) });
}

export function withdrawLeave(id: string): Promise<LeaveRequest> {
  return request<LeaveRequest>(`/leave/${id}/withdraw`, { method: 'POST' });
}
