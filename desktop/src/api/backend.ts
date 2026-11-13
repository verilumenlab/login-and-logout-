/**
 * Backend API Client with Offline Resilience & Optimistic Updates
 */

import {
  UserSession,
  LeaveBalance,
  LeaveRequest,
  ActivityTelemetry,
  AttendanceEvent,
  DeviceInfo,
} from '../types';
import {
  getSecureToken,
  saveSecureToken,
  deleteSecureToken,
  enqueueOfflineItem,
} from './ipc';

let customServerUrl = localStorage.getItem('__backend_server_url') || 'http://localhost:8000/api/v1';

export function setBackendServerUrl(url: string): void {
  customServerUrl = url.replace(/\/$/, '');
  localStorage.setItem('__backend_server_url', customServerUrl);
}

export function getBackendServerUrl(): string {
  return customServerUrl;
}

export async function pingBackend(): Promise<{ online: boolean; latencyMs: number }> {
  const start = performance.now();
  try {
    const res = await fetch(`${customServerUrl}/health`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(3000),
    });
    const latencyMs = Math.round(performance.now() - start);
    return { online: res.ok, latencyMs };
  } catch {
    return { online: false, latencyMs: -1 };
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  fallbackHandler?: () => T
): Promise<T> {
  let token = await getSecureToken('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  try {
    let res = await fetch(`${customServerUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`, {
      ...options,
      headers,
      signal: AbortSignal.timeout(6000),
    });

    // Automatic token refresh on 401
    if (res.status === 401) {
      const refreshToken = await getSecureToken('refresh_token');
      if (refreshToken) {
        try {
          const refreshRes = await fetch(`${customServerUrl}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          if (refreshRes.ok) {
            const tokenData = await refreshRes.json();
            await saveSecureToken('access_token', tokenData.access_token);
            if (tokenData.refresh_token) {
              await saveSecureToken('refresh_token', tokenData.refresh_token);
            }
            token = tokenData.access_token;
            headers['Authorization'] = `Bearer ${token}`;
            res = await fetch(`${customServerUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`, {
              ...options,
              headers,
              signal: AbortSignal.timeout(6000),
            });
          }
        } catch {
          // Token refresh failed, continue to error handler
        }
      }
    }

    if (!res.ok) {
      const errText = await res.text();
      let detail = errText;
      try {
        const parsed = JSON.parse(errText);
        detail = parsed.detail || errText;
      } catch {
        // use raw
      }
      throw new Error(detail || `HTTP ${res.status}`);
    }

    return (await res.json()) as T;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    if (fallbackHandler) {
      console.warn(`[Backend] Call to ${endpoint} failed (${msg}). Applying offline handler.`);
      return fallbackHandler();
    }
    throw new Error(msg);
  }
}

/**
 * Dedicated Employee-Only Desktop Authentication (Prompt 18)
 */
export async function loginUser(
  email: string,
  password: string,
  deviceId?: string,
  deviceInfo?: Partial<DeviceInfo>
): Promise<UserSession> {
  const hardwareId = deviceId || localStorage.getItem('__dev_id') || 'DEV-WORKSTATION-01';

  const payload = {
    email: email.trim(),
    password,
    device_identifier: hardwareId,
    device_name: deviceInfo?.machine_name || 'Employee Workstation',
    platform: deviceInfo?.os_type || 'windows',
    os_name: deviceInfo?.os_type === 'macos' ? 'macOS' : 'Windows',
    os_version: deviceInfo?.os_version || '11',
    mac_address: deviceInfo?.mac_address || null,
    agent_version: deviceInfo?.agent_version || '0.1.0',
    client_type: 'desktop',
  };

  const res = await fetch(`${customServerUrl}/auth/desktop-login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Client-Type': 'desktop',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorText = await res.text();
    let detail = 'Authentication failed';
    try {
      const parsed = JSON.parse(errorText);
      detail = parsed.detail || detail;
    } catch {
      // raw
    }
    throw new Error(detail);
  }

  const data = await res.json();
  const { access_token, refresh_token, user, device_id, device_session_id, employee_id } = data;

  // Enforce role check on client as well (Prompt 18: Never rely on frontend role checks alone, enforce both)
  const roleName = (user?.role || '').toUpperCase();
  if (roleName !== 'EMPLOYEE' && roleName !== 'EMPLOYEE ROLE') {
    throw new Error('This desktop application is available exclusively to Employee accounts. Please use the web application.');
  }

  // Persist tokens securely into OS Credential Manager
  await saveSecureToken('access_token', access_token);
  await saveSecureToken('refresh_token', refresh_token);
  if (device_session_id) {
    await saveSecureToken('device_session_id', device_session_id);
  }

  const userSession: UserSession = {
    user_id: user.id || 'usr_enterprise_01',
    email: user.email || email.trim(),
    first_name: user.first_name || email.split('@')[0].split('.')[0] || 'Employee',
    last_name: user.last_name || email.split('@')[0].split('.')[1] || 'User',
    role: 'EMPLOYEE',
    organization_id: user.organization_id || 'org_default',
    employee_code: user.employee_code || 'EMP-001',
    job_title: user.job_title || 'Workstation Specialist',
    department_name: user.department_name || 'Engineering',
  };

  localStorage.setItem('__user_session', JSON.stringify(userSession));
  localStorage.setItem('__device_id', device_id || '');
  localStorage.setItem('__device_session_id', device_session_id || '');
  localStorage.setItem('__employee_id', employee_id || '');

  return userSession;
}

export async function logoutUser(): Promise<void> {
  try {
    await request('/auth/logout', { method: 'POST' });
  } catch {
    // Ignore network failures on logout
  }
  await deleteSecureToken('access_token');
  await deleteSecureToken('refresh_token');
  localStorage.removeItem('__user_session');
}

export function getStoredUserSession(): UserSession | null {
  try {
    const raw = localStorage.getItem('__user_session');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/**
 * Attendance Operations with Offline Queueing
 */
export async function submitAttendanceEvent(
  eventType: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END',
  note?: string,
  locationData?: {
    latitude?: number;
    longitude?: number;
    accuracy_meters?: number;
    permission_status?: string;
    ssid?: string;
    bssid?: string;
  }
): Promise<AttendanceEvent> {
  const event: AttendanceEvent = {
    id: `att_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    timestamp: new Date().toISOString(),
    event_type: eventType,
    note,
    synced: false,
  };

  const endpoint =
    eventType === 'CLOCK_IN'
      ? '/attendance/clock-in'
      : eventType === 'CLOCK_OUT'
      ? '/attendance/clock-out'
      : eventType === 'BREAK_START'
      ? '/attendance/break/start'
      : '/attendance/break/end';

  const sessionToken = localStorage.getItem('__device_session_id');

  try {
    await request(endpoint, {
      method: 'POST',
      body: JSON.stringify({
        notes: note,
        client_event_id: event.id,
        occurred_at: event.timestamp,
        source: 'DESKTOP',
        device_session_id: sessionToken || undefined,
        ...(locationData || {}),
      }),
    });
    event.synced = true;
  } catch {
    // Queue offline for later synchronization
    enqueueOfflineItem('ATTENDANCE', { ...event, locationData } as unknown as Record<string, unknown>);
  }

  return event;
}

/**
 * Computer Activity Sync with Offline Queueing
 */
export async function syncActivityLogs(logs: ActivityTelemetry[]): Promise<{ count: number; synced: boolean }> {
  try {
    await request('/activity/sync', {
      method: 'POST',
      body: JSON.stringify({ logs }),
    });
    return { count: logs.length, synced: true };
  } catch {
    for (const log of logs) {
      enqueueOfflineItem('ACTIVITY', log as unknown as Record<string, unknown>);
    }
    return { count: logs.length, synced: false };
  }
}

/**
 * Leave Management
 */
export async function getLeaveBalances(): Promise<LeaveBalance[]> {
  return request<LeaveBalance[]>(
    '/leaves/balances',
    { method: 'GET' },
    () => [
      { leave_type: 'Annual Leave', total_allowed: 18, used: 6, available: 12 },
      { leave_type: 'Sick Leave', total_allowed: 12, used: 3, available: 9 },
      { leave_type: 'Casual Leave', total_allowed: 8, used: 2, available: 6 },
      { leave_type: 'Compensatory Off', total_allowed: 3, used: 0, available: 3 },
    ]
  );
}

export async function getLeaveRequests(): Promise<LeaveRequest[]> {
  return request<LeaveRequest[]>(
    '/leaves/requests',
    { method: 'GET' },
    () => {
      const stored = localStorage.getItem('__mock_leaves');
      if (stored) return JSON.parse(stored);
      const defaults: LeaveRequest[] = [
        {
          id: 'lv_001',
          leave_type: 'Annual Leave',
          start_date: '2026-11-20',
          end_date: '2026-11-22',
          total_days: 3,
          is_half_day: false,
          reason: 'Family event and travel',
          status: 'PENDING',
          applied_at: '2026-11-10T09:30:00Z',
        },
        {
          id: 'lv_002',
          leave_type: 'Sick Leave',
          start_date: '2026-10-14',
          end_date: '2026-10-14',
          total_days: 1,
          is_half_day: false,
          reason: 'Severe migraine recovery',
          status: 'APPROVED',
          applied_at: '2026-10-14T07:15:00Z',
          reviewer_notes: 'Approved by Engineering Manager',
        },
      ];
      localStorage.setItem('__mock_leaves', JSON.stringify(defaults));
      return defaults;
    }
  );
}

export async function submitLeaveRequest(data: {
  leave_type: string;
  start_date: string;
  end_date: string;
  total_days: number;
  is_half_day: boolean;
  half_day_period?: 'FIRST_HALF' | 'SECOND_HALF';
  reason: string;
  document_name?: string;
}): Promise<LeaveRequest> {
  const newReq: LeaveRequest = {
    id: `lv_${Date.now()}`,
    ...data,
    status: 'PENDING',
    applied_at: new Date().toISOString(),
  };

  try {
    const res = await request<LeaveRequest>('/leaves/apply', {
      method: 'POST',
      body: JSON.stringify(newReq),
    });
    return res;
  } catch {
    // Offline resilience: save locally and queue
    enqueueOfflineItem('LEAVE', newReq as unknown as Record<string, unknown>);
    const existing = await getLeaveRequests();
    localStorage.setItem('__mock_leaves', JSON.stringify([newReq, ...existing]));
    return newReq;
  }
}

export async function cancelLeaveRequest(id: string): Promise<void> {
  try {
    await request(`/leaves/requests/${id}/cancel`, { method: 'POST' });
  } catch {
    // Offline update
    const existing = await getLeaveRequests();
    const updated = existing.map((r) => (r.id === id ? { ...r, status: 'CANCELLED' as const } : r));
    localStorage.setItem('__mock_leaves', JSON.stringify(updated));
  }
}

/**
 * Device Heartbeat
 */
export async function sendDeviceHeartbeat(deviceInfo: DeviceInfo): Promise<void> {
  try {
    await request('/devices/heartbeat', {
      method: 'POST',
      body: JSON.stringify({
        device_id: deviceInfo.device_id,
        battery: deviceInfo.battery_percent,
        ip: deviceInfo.ip_address,
        os: deviceInfo.os_version,
      }),
    });
  } catch {
    // heartbeats don't strictly need offline persistence
  }
}

