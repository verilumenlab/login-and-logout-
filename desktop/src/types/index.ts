/**
 * Shared Type Definitions for the Employee Desktop App
 */

export type ScreenId = 'dashboard' | 'presence' | 'leave';

export interface UserSession {
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  organization_id: string;
  employee_id?: string;
  employee_code?: string;
  job_title?: string;
  department_name?: string;
  device_session_id?: string;
}

export interface DeviceInfo {
  device_id: string;
  machine_name: string;
  os_type: 'windows' | 'macos' | 'linux';
  os_version: string;
  arch: string;
  ip_address: string;
  mac_address: string;
  battery_percent: number | null;
  is_charging: boolean | null;
  enrolled: boolean;
  last_heartbeat: string | null;
  agent_version: string;
}

// ---------------------------------------------------------------------------
// Presence: app login/logout + laptop Wi-Fi connect/disconnect
// ---------------------------------------------------------------------------

export type PresenceEventType =
  | 'APP_LOGIN'
  | 'APP_LOGOUT'
  | 'WIFI_CONNECTED'
  | 'WIFI_DISCONNECTED'
  | 'SYSTEM_SHUTDOWN'
  | 'SYSTEM_SUSPEND'
  | 'SYSTEM_RESUME'
  | 'SYSTEM_STARTUP'
  | 'BREAK_START'
  | 'BREAK_END';
export type AttendanceAction = 'CLOCK_IN' | 'CLOCK_OUT' | 'NONE';

export interface PresenceEventIn {
  client_event_id: string;
  event_type: Exclude<PresenceEventType, 'BREAK_START' | 'BREAK_END'>;
  occurred_at: string;
  ssid?: string | null;
  bssid?: string | null;
  device_id?: string | null;
  detail?: string | null;
}

export interface PresenceEventResult {
  client_event_id: string;
  status: 'RECORDED' | 'DUPLICATE' | 'REJECTED';
  attendance_action: AttendanceAction;
  detail?: string | null;
}

export interface PresenceSyncResponse {
  results: PresenceEventResult[];
  is_logged_in: boolean;
}

export interface PresenceEventOut {
  event_type: PresenceEventType | string;
  occurred_at: string;
  ssid: string | null;
  attendance_action: AttendanceAction | string;
  detail?: string | null;
}

export interface PresenceDay {
  work_date: string;
  first_login: string | null;
  last_logout: string | null;
  is_logged_in: boolean;
  worked_minutes: number;
  break_count?: number;
  total_break_minutes?: number;
  status: string | null;
  first_wifi_connected_at: string | null;
  wifi_networks: string[];
  events: PresenceEventOut[];
}

export interface PresenceHistory {
  start_date: string;
  end_date: string;
  days: PresenceDay[];
}

export interface PresenceMonthSummary {
  month: string;
  working_days: number;
  present_days: number;
  leave_days: number;
  upcoming_leave_days: number;
  absent_days: number;
  total_worked_minutes: number;
  average_daily_minutes: number;
  today: PresenceDay;
}

/** Current Wi-Fi state from `netsh` / `airport`. */
export interface WifiStatus {
  ssid: string;
  bssid: string;
  is_wifi: boolean;
  timestamp: string;
}

/** A connect/disconnect read from the OS Wi-Fi log (Windows WLAN-AutoConfig). */
export interface NativeWifiEvent {
  kind: 'CONNECTED' | 'DISCONNECTED';
  occurred_at: string;
  ssid: string;
  record_id: number;
}

export interface TrackerStatus {
  isOnline: boolean;
  pendingEvents: number;
  lastSyncAt: string | null;
  wifi: WifiStatus | null;
  isLoggedIn: boolean | null;
}

// ---------------------------------------------------------------------------
// Leave (matches backend /leave API)
// ---------------------------------------------------------------------------

export type LeaveStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface LeaveType {
  id: string;
  name: string;
  code: string;
  category: string;
  is_paid: boolean;
  annual_allowance: number;
  requires_attachment: boolean;
  include_weekends: boolean;
}

export interface LeaveBalance {
  id: string;
  leave_type_id: string;
  leave_type_name: string | null;
  leave_type_code: string | null;
  year: number;
  allocated_days: number;
  used_days: number;
  pending_days: number;
  carryover_days: number;
}

export interface LeaveApproval {
  stage: string;
  status: ApprovalStatus;
  approver_name: string | null;
  comments: string | null;
  decided_at: string | null;
}

export interface LeaveRequest {
  id: string;
  leave_type_id: string;
  leave_type_name: string | null;
  start_date: string;
  end_date: string;
  total_days: number;
  is_half_day: boolean;
  half_day_period: string | null;
  reason: string;
  status: LeaveStatus;
  manager_approval_status: ApprovalStatus;
  hr_approval_status: ApprovalStatus;
  created_at: string;
  approvals: LeaveApproval[];
}

export interface LeaveApplyPayload {
  leave_type_id: string;
  start_date: string;
  end_date: string;
  is_half_day: boolean;
  half_day_period?: 'FIRST_HALF' | 'SECOND_HALF' | null;
  reason: string;
}
