/**
 * Shared Type Definitions for Enterprise Attendance Desktop Agent
 */

export type ScreenId =
  | 'login'
  | 'dashboard'
  | 'attendance'
  | 'activity'
  | 'leave_apply'
  | 'leave_history'
  | 'device_info'
  | 'settings';

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
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export type AttendanceMode = 'CLOCKED_OUT' | 'CLOCKED_IN' | 'ON_BREAK';

export interface AttendanceEvent {
  id: string;
  timestamp: string;
  event_type: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END';
  note?: string;
  synced: boolean;
}

export interface TodayAttendanceSummary {
  mode: AttendanceMode;
  clockInTime: string | null;
  clockOutTime: string | null;
  totalWorkedSeconds: number;
  totalBreakSeconds: number;
  currentBreakType: string | null;
  currentBreakStartTime: string | null;
  events: AttendanceEvent[];
}

export interface ActiveWindowInfo {
  application_name: string;
  window_title: string;
  process_id: number;
  idle_seconds: number;
  is_tracking: boolean;
}

export interface AppUsageStat {
  application_name: string;
  seconds: number;
  percentage: number;
  category: 'Development' | 'Communication' | 'Documentation' | 'Browsing' | 'Other';
}

export interface ActivityTelemetry {
  timestamp: string;
  application_name: string;
  window_title?: string;
  duration_seconds: number;
  idle_seconds: number;
  keystrokes_count: number;
  mouse_clicks_count: number;
  synced: boolean;
}

export interface LeaveBalance {
  leave_type: string;
  total_allowed: number;
  used: number;
  available: number;
}

export type LeaveStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export interface LeaveRequest {
  id: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  total_days: number;
  is_half_day: boolean;
  half_day_period?: 'FIRST_HALF' | 'SECOND_HALF';
  reason: string;
  status: LeaveStatus;
  applied_at: string;
  reviewer_notes?: string;
  document_name?: string;
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

export interface AppSettings {
  server_url: string;
  autostart_enabled: boolean;
  notifications_enabled: boolean;
  telemetry_sample_interval_secs: number;
  offline_sync_interval_secs: number;
  theme: 'light' | 'dark' | 'system';
}

export interface SyncQueueItem {
  id: string;
  event_type: 'ATTENDANCE' | 'ACTIVITY' | 'LEAVE' | 'HEARTBEAT';
  payload: Record<string, unknown>;
  created_at: string;
  retry_count: number;
}

export interface ConnectionState {
  is_online: boolean;
  last_ping_latency_ms: number | null;
  last_successful_sync: string | null;
  pending_queue_count: number;
}

export type OSSessionEventType =
  | 'OS_LOGON'
  | 'OS_LOGOFF'
  | 'SESSION_LOCK'
  | 'SESSION_UNLOCK'
  | 'SYSTEM_STARTUP'
  | 'SYSTEM_SHUTDOWN'
  | 'SYSTEM_SLEEP'
  | 'SYSTEM_WAKE'
  | 'HEARTBEAT'
  | 'USER_ACTIVITY';

export interface OSSessionEventContract {
  event_id: string;
  employee_id: string;
  device_id: string;
  operating_system: string;
  event_type: OSSessionEventType;
  occurred_at: string;
  sequence_number: number;
  agent_version: string;
  metadata: Record<string, unknown>;
}

export interface EventQueueStatus {
  pending_events_count: number;
  latest_sequence_number: number;
  last_event_type: string | null;
  last_event_time: string | null;
  last_sync_time: string | null;
  queue_file_path: string;
  clock_anomalies_detected: number;
}

export type LocationPermissionState = 'GRANTED' | 'DENIED' | 'UNAVAILABLE' | 'PROMPT';
export type LocationVerificationState =
  | 'VERIFIED'
  | 'OUTSIDE_GEOFENCE'
  | 'UNVERIFIED'
  | 'UNAVAILABLE'
  | 'SPOOF_DETECTED';
export type VerificationMethodType = 'GPS' | 'WIFI_NETWORK' | 'IP_APPROXIMATE' | 'HYBRID' | 'UNAVAILABLE';

export interface LocationCapture {
  latitude: number | null;
  longitude: number | null;
  accuracy_meters: number | null;
  permission_status: LocationPermissionState;
  ssid?: string;
  bssid?: string;
  ip_address?: string;
  verification_status?: LocationVerificationState;
  distance_meters?: number | null;
  is_conclusive?: boolean;
  notes?: string;
}

export interface LocationDisclosureInfo {
  purpose: string;
  gps_tracking_policy: string;
  non_conclusive_rule: string;
  data_retention_days: number;
  employee_rights: string[];
}

