/**
 * Comprehensive Type-Safe API Client for Enterprise Attendance Platform (Phase 10)
 * Connects Web Dashboards (Admin, HR, Manager, Employee) directly to FastAPI Backend.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

// ==========================================
// Models & Interfaces
// ==========================================

export interface HealthStatus {
  status: string;
  environment: string;
  version: string;
  timestamp: string;
}

export interface DetailedHealthStatus extends HealthStatus {
  uptime_seconds: number;
  database: {
    status: string;
    latency_ms?: number;
    database?: string;
    error?: string;
  };
  redis: {
    status: string;
    latency_ms?: number;
    message?: string;
    error?: string;
  };
  celery: {
    status: string;
    broker_status: string;
    active_workers?: number;
    error?: string;
  };
  email?: {
    status: string;
    provider?: string;
    from_email?: string;
    delivers_to_inbox?: boolean;
    note?: string | null;
  };
}

export interface Department {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  parent_id?: string | null;
  is_active: boolean;
  employee_count: number;
  created_at: string;
  updated_at: string;
}

export interface DepartmentCreate {
  name: string;
  code: string;
  parent_id?: string | null;
  is_active?: boolean;
}

export interface DepartmentUpdate {
  name?: string;
  code?: string;
  parent_id?: string | null;
  is_active?: boolean;
}

export interface EmployeeManagerInfo {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  email?: string | null;
  job_title?: string | null;
}

export interface Employee {
  id: string;
  user_id: string;
  organization_id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone?: string | null;
  job_title?: string | null;
  department_id?: string | null;
  department?: {
    id: string;
    name: string;
    code: string;
  } | null;
  work_schedule_id?: string | null;
  work_schedule?: {
    id: string;
    name: string;
    shift_start_time: string;
    shift_end_time: string;
  } | null;
  hire_date: string;
  termination_date?: string | null;
  /** Only present right after create / password reset. */
  temporary_password?: string | null;
  credentials_email_sent?: boolean | null;
  credentials_email_error?: string | null;
  /** Admin-only: last password assigned by an administrator. */
  admin_visible_password?: string | null;
  admin_password_updated_at?: string | null;
  has_admin_password?: boolean;
  employment_status: 'ACTIVE' | 'ON_LEAVE' | 'PROBATION' | 'TERMINATED';
  is_active: boolean;
  role_name?: string | null;
  manager?: EmployeeManagerInfo | null;
  hr_rep?: EmployeeManagerInfo | null;
  metadata_json?: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeePagination {
  items: Employee[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface EmployeeCreate {
  first_name: string;
  last_name: string;
  email: string;
  employee_code: string;
  phone?: string;
  job_title?: string;
  department_id?: string;
  manager_id?: string;
  hr_rep_id?: string;
  work_schedule_id?: string;
  hire_date: string;
  employment_status?: string;
  initial_password?: string;
  role_name?: string;
}

export interface EmployeeUpdate {
  first_name?: string;
  last_name?: string;
  employee_code?: string;
  phone?: string;
  job_title?: string;
  department_id?: string;
  manager_id?: string;
  hr_rep_id?: string;
  work_schedule_id?: string;
  hire_date?: string;
  termination_date?: string;
  employment_status?: string;
  is_active?: boolean;
  role_name?: string;
}

/** Roles that can be assigned from the portal. Administrator is offered to administrators only. */
export const ASSIGNABLE_ROLES: { value: string; label: string; hint: string; adminOnly?: boolean }[] = [
  { value: 'Employee', label: 'Employee', hint: 'Desktop app only: clock in/out and apply for leave' },
  { value: 'Department Manager', label: 'Manager', hint: 'Web portal: team attendance and leave approvals' },
  { value: 'HR Manager', label: 'HR', hint: 'Web portal: employees, leave policy, reports' },
  { value: 'Administrator', label: 'Administrator', hint: 'Web portal: full control', adminOnly: true },
];

export function roleLabel(roleName?: string | null): string {
  return ASSIGNABLE_ROLES.find((r) => r.value === roleName)?.label || roleName || 'Employee';
}

export interface EmployeeImportResult {
  success_count: number;
  error_count: number;
  imported_employees: Employee[];
  errors: {
    row: number;
    employee_code?: string;
    email?: string;
    errors: string[];
  }[];
}

export interface OfficeGeofence {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_meters: number;
  is_active: boolean;
}

export interface OfficeNetwork {
  id: string;
  name: string;
  ssid?: string | null;
  bssid_mac?: string | null;
  ip_address?: string | null;
  subnet_cidr?: string | null;
  is_active: boolean;
}

export interface Office {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  address: string;
  timezone: string;
  is_active: boolean;
  geofences?: OfficeGeofence[];
  networks?: OfficeNetwork[];
  created_at: string;
  updated_at: string;
}

export interface OfficeListResponse {
  items: Office[];
  total: number;
  page: number;
  page_size: number;
}

export interface Device {
  id: string;
  device_identifier: string;
  device_name: string;
  os_name: string;
  os_version: string;
  platform: string;
  mac_address?: string | null;
  agent_version: string;
  is_trusted: boolean;
  is_blocked: boolean;
  registered_at: string;
  last_seen_at?: string | null;
  last_ip_address?: string | null;
  employee_id?: string | null;
  employee_name?: string | null;
  employee_code?: string | null;
  employee_email?: string | null;
}

export interface ReleaseFile {
  id: string;
  kind: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
}

export interface ApplicationRelease {
  id: string;
  channel_name: string;
  version: string;
  build_number?: string | null;
  release_notes?: string | null;
  status: string;
  os_name: string;
  package_size: number;
  sha256: string;
  sha512?: string | null;
  uploaded_at: string;
  published_at?: string | null;
  created_at: string;
  files: ReleaseFile[];
}

export interface ReleaseSummary {
  current_published_version?: string | null;
  current_published_id?: string | null;
  latest_uploaded_version?: string | null;
  latest_uploaded_id?: string | null;
  new_release_available: boolean;
  channel: string;
  registered_devices: number;
  devices_needing_update: number;
  successful_updates: number;
  failed_updates: number;
}

export interface DeviceUpdateStatus {
  device_id: string;
  device_name: string;
  device_identifier: string;
  employee_id?: string | null;
  agent_version: string;
  installed_version?: string | null;
  needs_update: boolean;
  last_update_status?: string | null;
  last_check_at?: string | null;
  last_seen_at?: string | null;
}

export interface ReleaseActionResult {
  id: string;
  status: string;
  message: string;
}

export interface UpdateEvent {
  id: string;
  event_type: string;
  message?: string | null;
  release_id?: string | null;
  device_id?: string | null;
  details_json?: Record<string, unknown> | null;
  created_at: string;
}

export interface AttendanceDay {
  id: string;
  employee_id: string;
  employee_name?: string;
  employee_code?: string;
  work_date: string;
  status: 'PRESENT' | 'ABSENT' | 'HALF_DAY' | 'LATE' | 'ON_LEAVE' | 'HOLIDAY' | 'WEEKEND';
  shift_start?: string | null;
  shift_end?: string | null;
  total_work_minutes: number;
  total_break_minutes: number;
  total_idle_minutes: number;
  is_overtime: boolean;
  late_minutes: number;
  early_departure_minutes: number;
  is_wfh: boolean;
  is_missing_checkout: boolean;
  metadata_json?: Record<string, any> | null;
}

export interface AttendanceStatusResponse {
  is_clocked_in: boolean;
  is_on_break: boolean;
  today_day?: AttendanceDay | null;
  active_break?: any | null;
  total_work_minutes: number;
}

export interface LeaveBalance {
  id: string;
  leave_type_id: string;
  leave_type_name: string;
  leave_type_code: string;
  year: number;
  allocated_days: number;
  used_days: number;
  pending_days: number;
  carryover_days: number;
  available_days: number;
}

export interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name?: string;
  employee_code?: string;
  department_name?: string;
  leave_type_name?: string;
  start_date: string;
  end_date: string;
  total_days: number;
  is_half_day: boolean;
  half_day_period?: string | null;
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
  manager_approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  hr_approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  created_at: string;
  withdrawn_at?: string | null;
  approvals?: LeaveApprovalStep[];
  documents?: any[];
}

export interface LeaveApprovalStep {
  id: string;
  approver_name?: string | null;
  stage: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  comments?: string | null;
  decided_at?: string | null;
}

export interface AuditLog {
  id: string;
  user_email?: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  ip_address?: string | null;
  diff_json?: Record<string, any> | null;
  created_at: string;
}

export interface ReportJob {
  id: string;
  report_type: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  started_at?: string | null;
  completed_at?: string | null;
  error_message?: string | null;
  parameters_json?: Record<string, any> | null;
  schedule_id?: string | null;
  idempotency_key?: string | null;
  created_at: string;
  files: {
    id: string;
    file_name: string;
    storage_path: string;
    file_size_bytes: number;
    mime_type: string;
    created_at: string;
  }[];
}

export interface EmailOutbox {
  id: string;
  recipient_email: string;
  recipient_name?: string | null;
  sender_email?: string | null;
  sender_name?: string | null;
  subject: string;
  status: 'PENDING' | 'SENT' | 'FAILED';
  retry_count: number;
  error_message?: string | null;
  sent_at?: string | null;
  created_at: string;
}

export interface MissingLoginAlert {
  id: string;
  organization_id: string;
  employee_id: string;
  work_date: string;
  employee_name: string;
  employee_email: string;
  employee_code: string;
  department_name?: string | null;
  scheduled_shift?: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'SENT';
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  review_note?: string | null;
  emails_sent_count: number;
  created_at: string;
  updated_at: string;
}

// ==========================================
// ApiClient Class
// ==========================================

export interface ReportSchedule {
  id: string;
  organization_id: string;
  schedule_type: 'DAILY' | 'WEEKLY' | 'MONTHLY';
  cron_expression: string;
  timezone: string;
  is_active: boolean;
  send_email: boolean;
  recipient_emails: string[];
  include_individual_reports: boolean;
  include_manager_reports: boolean;
  include_consolidated_report: boolean;
  last_run_at?: string;
  next_run_at?: string;
  last_status?: string;
  last_error?: string;
  created_at: string;
  updated_at: string;
  recent_jobs?: ReportJob[];
}

export interface AuthUser {
  id: string;
  email: string;
  organization_id: string;
  role: string;
  permissions: string[];
  is_active: boolean;
  is_superuser?: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: AuthUser;
}

export type TeamPresenceStatus = 'LOGGED_IN' | 'LOGGED_OUT' | 'ON_LEAVE' | 'NOT_LOGGED_IN';

export interface TeamPresenceRow {
  employee_id: string;
  employee_code: string;
  full_name: string;
  department_name: string | null;
  status: TeamPresenceStatus;
  first_login: string | null;
  last_logout: string | null;
  worked_minutes: number;
  first_wifi_connected_at: string | null;
  wifi_networks: string[];
  last_signal_at: string | null;
  leave_type_name: string | null;
  logout_note?: string | null;
  logout_reason?: string | null;
  break_count?: number;
  total_break_minutes?: number;
  workday_status?: string | null;
  confirmation_status?: string | null;
  completed_nine_hours?: boolean;
  early_logout?: boolean;
  auto_logout?: boolean;
}

export interface TeamPresenceResponse {
  work_date: string;
  scope: 'ORGANIZATION' | 'TEAM';
  counts: { total: number; logged_in: number; logged_out: number; on_leave: number; not_logged_in: number };
  pending_leave_requests: number;
  rows: TeamPresenceRow[];
}

export interface PresenceEvent {
  event_type:
    | 'APP_LOGIN'
    | 'APP_LOGOUT'
    | 'WIFI_CONNECTED'
    | 'WIFI_DISCONNECTED'
    | 'BREAK_START'
    | 'BREAK_END'
    | string;
  occurred_at: string;
  ssid: string | null;
  attendance_action: 'CLOCK_IN' | 'CLOCK_OUT' | 'NONE' | string;
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
  events: PresenceEvent[];
  logout_note?: string | null;
  logout_reason?: string | null;
}

export interface PresenceHistory {
  start_date: string;
  end_date: string;
  days: PresenceDay[];
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

const ACCESS_TOKEN_KEY = 'auth_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

export class ApiClient {
  private baseUrl: string;
  private token: string | null = null;
  private refreshInFlight: Promise<boolean> | null = null;
  private sessionExpiredHandler: (() => void) | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /** Called once when the session can no longer be refreshed (the user must sign in again). */
  onSessionExpired(handler: (() => void) | null) {
    this.sessionExpiredHandler = handler;
  }

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem(ACCESS_TOKEN_KEY, token);
      } else {
        localStorage.removeItem(ACCESS_TOKEN_KEY);
      }
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      return localStorage.getItem(ACCESS_TOKEN_KEY);
    }
    return null;
  }

  private setRefreshToken(token: string | null) {
    if (typeof window === 'undefined') return;
    if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token);
    else localStorage.removeItem(REFRESH_TOKEN_KEY);
  }

  private getRefreshToken(): string | null {
    return typeof window !== 'undefined' ? localStorage.getItem(REFRESH_TOKEN_KEY) : null;
  }

  clearSession() {
    this.setToken(null);
    this.setRefreshToken(null);
  }

  private refreshAccessToken(): Promise<boolean> {
    if (!this.refreshInFlight) {
      this.refreshInFlight = (async () => {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) return false;
        try {
          const res = await fetch(`${this.baseUrl}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          if (!res.ok) return false;
          const data = await res.json();
          this.setToken(data.access_token);
          if (data.refresh_token) this.setRefreshToken(data.refresh_token);
          return true;
        } catch {
          return false;
        }
      })().finally(() => {
        this.refreshInFlight = null;
      });
    }
    return this.refreshInFlight;
  }

  private send(endpoint: string, options: RequestInit): Promise<Response> {
    const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const misconfigured = this.serverMisconfiguration();
    if (misconfigured) return Promise.reject(new ApiError(misconfigured, 0));
    return fetch(url, { ...options, headers }).catch(() => {
      throw new ApiError(
        `Cannot reach the server at ${this.serverOrigin}. It may be offline, or it does not allow requests from this site.`,
        0
      );
    });
  }

  get serverOrigin(): string {
    try {
      return new URL(this.baseUrl).origin;
    } catch {
      return this.baseUrl;
    }
  }

  /** A deployed site still pointing at localhost was built without NEXT_PUBLIC_API_URL. */
  private serverMisconfiguration(): string | null {
    if (typeof window === 'undefined') return null;
    const local = (host: string) => host === 'localhost' || host === '127.0.0.1';
    try {
      if (!local(window.location.hostname) && local(new URL(this.baseUrl).hostname)) {
        return 'This site is not connected to a server yet. Set NEXT_PUBLIC_API_URL to the backend address and redeploy.';
      }
    } catch {
      return null;
    }
    return null;
  }

  /** True when the backend answers its health check. */
  async isServerReachable(): Promise<boolean> {
    try {
      const res = await this.send('/health', { method: 'GET' });
      return res.ok;
    } catch {
      return false;
    }
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    let response = await this.send(endpoint, options);

    if (response.status === 401 && !endpoint.startsWith('/auth/login') && this.getToken()) {
      if (await this.refreshAccessToken()) {
        response = await this.send(endpoint, options);
      }
      if (response.status === 401) {
        this.clearSession();
        this.sessionExpiredHandler?.();
        throw new ApiError('Your session has expired. Please sign in again.', 401);
      }
    }

    if (!response.ok) {
      const errorBody = await response.text();
      let errorDetail = errorBody;
      try {
        const parsed = JSON.parse(errorBody);
        if (typeof parsed.detail === 'string') errorDetail = parsed.detail;
        else if (Array.isArray(parsed.detail)) {
          errorDetail = parsed.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ');
        }
      } catch {
        // use raw text
      }
      if (response.status === 404 && errorDetail === 'Not Found') {
        errorDetail = 'The server does not support this page yet. Ask your administrator to update and restart the backend.';
      }
      throw new ApiError(errorDetail || `HTTP ${response.status}: ${response.statusText}`, response.status);
    }

    return response.json();
  }

  // --- Auth ---
  async login(email: string, password: string): Promise<LoginResponse> {
    const res = await this.request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: email.trim(), password, client_type: 'web' }),
    });
    this.setToken(res.access_token);
    this.setRefreshToken(res.refresh_token);
    return res;
  }

  async logout(): Promise<void> {
    const refreshToken = this.getRefreshToken();
    try {
      await this.request('/auth/logout', {
        method: 'POST',
        ...(refreshToken ? { body: JSON.stringify({ refresh_token: refreshToken }) } : {}),
      });
    } catch {
      // Signing out locally must always work.
    }
    this.clearSession();
  }

  async getCurrentUser(): Promise<AuthUser> {
    return this.request<AuthUser>('/auth/me');
  }

  async forgotPassword(email: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email: email.trim() }),
    });
  }

  async resetPassword(email: string, tokenOrOtp: string, newPassword: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({
        email: email.trim(),
        token_or_otp: tokenOrOtp.trim(),
        new_password: newPassword,
      }),
    });
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
  }

  // --- Employee presence (login & logout board) ---
  async getTeamPresence(date?: string): Promise<TeamPresenceResponse> {
    return this.request<TeamPresenceResponse>(`/presence/team${date ? `?date=${date}` : ''}`);
  }

  /**
   * Backend audit: correct logout + hours from Attendance history rules
   * (office Wi-Fi disconnect / sleep / shutdown) for the last N days.
   */
  async repairAttendanceHistory(days = 3): Promise<{
    status: string;
    days_checked: number;
    from_date: string;
    to_date: string;
    repaired_count: number;
    repaired: Array<{
      employee_id: string;
      full_name?: string | null;
      work_date: string;
      reason: string;
      login_at?: string | null;
      logout_at: string;
      worked_minutes: number;
      note?: string | null;
    }>;
  }> {
    return this.request(`/presence/repair-history?days=${days}`, { method: 'POST' });
  }

  async getEmployeePresenceHistory(employeeId: string, startDate: string, endDate: string): Promise<PresenceHistory> {
    return this.request<PresenceHistory>(
      `/presence/employee/${employeeId}/history?start_date=${startDate}&end_date=${endDate}`
    );
  }

  /** Download weekly (Mon–Fri) or monthly combined HR attendance CSV. */
  async downloadAttendanceCsv(period: 'weekly' | 'monthly', date: string): Promise<void> {
    const endpoint = `/presence/export.csv?period=${period}&date=${encodeURIComponent(date)}`;
    let response = await this.send(endpoint, { method: 'GET' });
    if (response.status === 401 && this.getToken()) {
      if (await this.refreshAccessToken()) {
        response = await this.send(endpoint, { method: 'GET' });
      }
      if (response.status === 401) {
        this.clearSession();
        this.sessionExpiredHandler?.();
        throw new ApiError('Your session has expired. Please sign in again.', 401);
      }
    }
    if (!response.ok) {
      const errorBody = await response.text();
      let detail = errorBody;
      try {
        const parsed = JSON.parse(errorBody);
        detail = parsed.detail || errorBody;
      } catch {
        /* keep text */
      }
      throw new ApiError(typeof detail === 'string' ? detail : 'Export failed', response.status);
    }
    const disposition = response.headers.get('Content-Disposition') || '';
    const match = /filename="([^"]+)"/i.exec(disposition);
    const fallback =
      period === 'weekly'
        ? `Weekly_Attendance_${date}.csv`
        : `Monthly_Attendance_${date}.csv`;
    const filename = match?.[1] || fallback;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // --- Health ---
  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/health');
  }

  async getDetailedHealth(): Promise<DetailedHealthStatus> {
    return this.request<DetailedHealthStatus>('/health/detailed');
  }

  // --- Departments ---
  async listDepartments(): Promise<Department[]> {
    return this.request<Department[]>('/departments/');
  }

  async createDepartment(data: DepartmentCreate): Promise<Department> {
    return this.request<Department>('/departments/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateDepartment(id: string, data: DepartmentUpdate): Promise<Department> {
    return this.request<Department>(`/departments/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteDepartment(id: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/departments/${id}`, {
      method: 'DELETE',
    });
  }

  // --- Employees ---
  async listEmployees(params: {
    search?: string;
    department_id?: string;
    employment_status?: string;
    is_active?: boolean;
    manager_id?: string;
    page?: number;
    page_size?: number;
  } = {}): Promise<EmployeePagination> {
    const searchParams = new URLSearchParams();
    if (params.search) searchParams.append('search', params.search);
    if (params.department_id) searchParams.append('department_id', params.department_id);
    if (params.employment_status) searchParams.append('employment_status', params.employment_status);
    if (params.is_active !== undefined) searchParams.append('is_active', String(params.is_active));
    if (params.manager_id) searchParams.append('manager_id', params.manager_id);
    if (params.page) searchParams.append('page', String(params.page));
    if (params.page_size) searchParams.append('page_size', String(params.page_size));

    const qs = searchParams.toString();
    return this.request<EmployeePagination>(`/employees/${qs ? `?${qs}` : ''}`);
  }

  async getEmployee(id: string): Promise<Employee> {
    return this.request<Employee>(`/employees/${id}`);
  }

  async createEmployee(data: EmployeeCreate): Promise<Employee> {
    return this.request<Employee>('/employees/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateEmployee(id: string, data: EmployeeUpdate): Promise<Employee> {
    return this.request<Employee>(`/employees/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async toggleEmployeeStatus(id: string, isActive: boolean): Promise<{ message: string; is_active: boolean }> {
    return this.request<{ message: string; is_active: boolean }>(`/employees/${id}/status?is_active=${isActive}`, {
      method: 'POST',
    });
  }

  async deleteEmployee(id: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/employees/${id}`, {
      method: 'DELETE',
    });
  }

  async importEmployees(formData: FormData): Promise<EmployeeImportResult> {
    return this.request<EmployeeImportResult>('/employees/import', {
      method: 'POST',
      body: formData,
    });
  }

  // --- Offices ---
  async listOffices(): Promise<Office[]> {
    const res = await this.request<OfficeListResponse | Office[]>('/offices');
    if (Array.isArray(res)) return res;
    return res?.items ?? [];
  }

  async createOffice(data: {
    name: string;
    code: string;
    address: string;
    timezone: string;
    latitude?: number | null;
    longitude?: number | null;
    radius_meters?: number | null;
    networks?: Array<{
      name: string;
      ssid?: string | null;
      ip_address?: string | null;
      bssid_mac?: string | null;
      subnet_cidr?: string | null;
      is_active?: boolean;
    }>;
  }): Promise<Office> {
    return this.request<Office>('/offices', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async addGeofence(officeId: string, data: { name: string; latitude: number; longitude: number; radius_meters: number }): Promise<OfficeGeofence> {
    return this.request<OfficeGeofence>(`/offices/${officeId}/geofences`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async addNetwork(officeId: string, data: {
    name: string;
    ssid?: string | null;
    ip_address?: string | null;
    bssid_mac?: string | null;
    subnet_cidr?: string | null;
    is_active?: boolean;
  }): Promise<OfficeNetwork> {
    return this.request<OfficeNetwork>(`/offices/${officeId}/networks`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async deleteNetwork(officeId: string, networkId: string): Promise<void> {
    await this.request(`/offices/${officeId}/networks/${networkId}`, { method: 'DELETE' });
  }

  async deleteGeofence(officeId: string, geofenceId: string): Promise<void> {
    await this.request(`/offices/${officeId}/geofences/${geofenceId}`, { method: 'DELETE' });
  }

  async deleteOffice(officeId: string): Promise<void> {
    await this.request(`/offices/${officeId}`, { method: 'DELETE' });
  }

  // --- Devices ---
  async listDevices(): Promise<Device[]> {
    return this.request<Device[]>('/devices/');
  }

  async blockDevice(deviceId: string): Promise<Device> {
    return this.request<Device>(`/devices/${deviceId}/block`, { method: 'POST' });
  }

  async unblockDevice(deviceId: string): Promise<Device> {
    return this.request<Device>(`/devices/${deviceId}/unblock`, { method: 'POST' });
  }

  // --- Application Releases (Employee Desktop) ---
  async getReleaseSummary(channel: string = 'production'): Promise<ReleaseSummary> {
    return this.request<ReleaseSummary>(`/releases/summary?channel=${encodeURIComponent(channel)}`);
  }

  async listReleases(params: { channel?: string; status?: string } = {}): Promise<ApplicationRelease[]> {
    const sp = new URLSearchParams();
    if (params.channel) sp.append('channel', params.channel);
    if (params.status) sp.append('status', params.status);
    const qs = sp.toString();
    return this.request<ApplicationRelease[]>(`/releases/${qs ? `?${qs}` : ''}`);
  }

  async getRelease(id: string): Promise<ApplicationRelease> {
    return this.request<ApplicationRelease>(`/releases/${id}`);
  }

  async uploadRelease(formData: FormData): Promise<ApplicationRelease> {
    return this.request<ApplicationRelease>('/releases/upload', {
      method: 'POST',
      body: formData,
    });
  }

  async approveRelease(id: string): Promise<ReleaseActionResult> {
    return this.request<ReleaseActionResult>(`/releases/${id}/approve`, { method: 'POST' });
  }

  async publishRelease(id: string): Promise<ReleaseActionResult> {
    return this.request<ReleaseActionResult>(`/releases/${id}/publish`, { method: 'POST' });
  }

  async pauseRelease(id: string): Promise<ReleaseActionResult> {
    return this.request<ReleaseActionResult>(`/releases/${id}/pause`, { method: 'POST' });
  }

  async cancelRelease(id: string): Promise<ReleaseActionResult> {
    return this.request<ReleaseActionResult>(`/releases/${id}/cancel`, { method: 'POST' });
  }

  async rollbackRelease(id: string): Promise<ReleaseActionResult> {
    return this.request<ReleaseActionResult>(`/releases/${id}/rollback`, { method: 'POST' });
  }

  async getReleaseCompliance(channel: string = 'production'): Promise<DeviceUpdateStatus[]> {
    return this.request<DeviceUpdateStatus[]>(`/releases/compliance?channel=${encodeURIComponent(channel)}`);
  }

  async getReleaseDeviceStatus(releaseId: string): Promise<DeviceUpdateStatus[]> {
    return this.request<DeviceUpdateStatus[]>(`/releases/${releaseId}/devices`);
  }

  async listReleaseEvents(limit: number = 50): Promise<UpdateEvent[]> {
    return this.request<UpdateEvent[]>(`/releases/events?limit=${limit}`);
  }

  /** Download a stored release package (any status — archive / old versions). */
  async downloadReleaseFile(releaseId: string, fileId: string, filename?: string): Promise<void> {
    const endpoint = `/releases/${releaseId}/files/${fileId}/download`;
    let response = await this.send(endpoint, { method: 'GET' });
    if (response.status === 401 && this.getToken()) {
      if (await this.refreshAccessToken()) {
        response = await this.send(endpoint, { method: 'GET' });
      }
      if (response.status === 401) {
        this.clearSession();
        this.sessionExpiredHandler?.();
        throw new ApiError('Your session has expired. Please sign in again.', 401);
      }
    }
    if (!response.ok) {
      let message = `Download failed (${response.status})`;
      try {
        const err = await response.json();
        message = err.detail || err.message || message;
      } catch {
        /* ignore */
      }
      throw new ApiError(message, response.status);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || 'WorkPulse-Employee-Setup.exe';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async resetEmployeePassword(
    employeeId: string,
    temporaryPassword?: string,
    notifyEmail: boolean = true
  ): Promise<{
    status: string;
    message: string;
    temporary_password: string;
    email: string;
  }> {
    return this.request(`/employees/${employeeId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({
        temporary_password: temporaryPassword?.trim() || null,
        notify_email: notifyEmail,
      }),
    });
  }

  // --- Attendance ---
  async getAttendanceStatus(): Promise<AttendanceStatusResponse> {
    return this.request<AttendanceStatusResponse>('/attendance/status');
  }

  async getAttendanceHistory(params: { start_date?: string; end_date?: string } = {}): Promise<AttendanceDay[]> {
    const sp = new URLSearchParams();
    if (params.start_date) sp.append('start_date', params.start_date);
    if (params.end_date) sp.append('end_date', params.end_date);
    const qs = sp.toString();
    return this.request<AttendanceDay[]>(`/attendance/history${qs ? `?${qs}` : ''}`);
  }

  async clockIn(notes?: string): Promise<any> {
    return this.request('/attendance/clock-in', {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  async clockOut(notes?: string): Promise<any> {
    return this.request('/attendance/clock-out', {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  async startBreak(breakType: string = 'LUNCH', notes?: string): Promise<any> {
    return this.request('/attendance/break/start', {
      method: 'POST',
      body: JSON.stringify({ break_type: breakType, notes }),
    });
  }

  async endBreak(notes?: string): Promise<any> {
    return this.request('/attendance/break/end', {
      method: 'POST',
      body: JSON.stringify({ notes }),
    });
  }

  // --- Leaves ---
  async listLeaves(): Promise<LeaveRequest[]> {
    return this.request<LeaveRequest[]>('/leave/');
  }

  async listTeamLeaves(status?: LeaveRequest['status']): Promise<LeaveRequest[]> {
    const query = status ? `?status=${status}` : '';
    return this.request<LeaveRequest[]>(`/leave/team-requests${query}`);
  }

  async getMyBalances(): Promise<LeaveBalance[]> {
    return this.request<LeaveBalance[]>('/leave/balances');
  }

  async applyLeave(data: {
    leave_type_id: string;
    start_date: string;
    end_date: string;
    reason: string;
    is_half_day?: boolean;
    half_day_period?: string;
  }): Promise<LeaveRequest> {
    return this.request<LeaveRequest>('/leave/apply', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async reviewManagerLeave(id: string, action: 'APPROVE' | 'REJECT', comments?: string): Promise<LeaveRequest> {
    return this.request<LeaveRequest>(`/leave/${id}/manager-review`, {
      method: 'POST',
      body: JSON.stringify({ action, comments }),
    });
  }

  async reviewHrLeave(id: string, action: 'APPROVE' | 'REJECT', comments?: string): Promise<LeaveRequest> {
    return this.request<LeaveRequest>(`/leave/${id}/hr-review`, {
      method: 'POST',
      body: JSON.stringify({ action, comments }),
    });
  }

  async withdrawLeave(id: string): Promise<LeaveRequest> {
    return this.request<LeaveRequest>(`/leave/${id}/withdraw`, { method: 'POST' });
  }

  // --- Reports ---
  async listReports(): Promise<ReportJob[]> {
    return this.request<ReportJob[]>('/reports/');
  }

  async generateReport(reportType: string, parameters: Record<string, any> = {}): Promise<ReportJob> {
    return this.request<ReportJob>('/reports/generate', {
      method: 'POST',
      body: JSON.stringify({ report_type: reportType, parameters }),
    });
  }

  async previewReport(reportType: string, startDate: string, endDate: string, departmentId?: string): Promise<any> {
    return this.request('/reports/preview', {
      method: 'POST',
      body: JSON.stringify({
        report_type: reportType,
        start_date: startDate,
        end_date: endDate,
        department_id: departmentId || null,
      }),
    });
  }

  async manualSendReport(reportType: string, startDate: string, endDate: string, recipients: string[]): Promise<any> {
    return this.request('/reports/manual-send', {
      method: 'POST',
      body: JSON.stringify({
        report_type: reportType,
        start_date: startDate,
        end_date: endDate,
        recipients,
      }),
    });
  }

  async getEmployeeLoginHistory(employeeId: string, limit: number = 30): Promise<any[]> {
    return this.request(`/employees/${employeeId}/login-history?limit=${limit}`);
  }

  // --- Audit Logs ---
  async listAuditLogs(limit: number = 100): Promise<AuditLog[]> {
    return this.request<AuditLog[]>(`/audit-logs/?limit=${limit}`);
  }

  // --- Emails / Notifications ---
  async listEmailOutbox(limit: number = 50): Promise<EmailOutbox[]> {
    return this.request<EmailOutbox[]>(`/notifications/outbox?limit=${limit}`);
  }

  async resendEmailOutbox(id: string): Promise<EmailOutbox> {
    return this.request<EmailOutbox>(`/notifications/outbox/${id}/retry`, { method: 'POST' });
  }

  async deleteEmailOutbox(id: string): Promise<{ message: string; id: string }> {
    return this.request<{ message: string; id: string }>(`/notifications/outbox/${id}`, {
      method: 'DELETE',
    });
  }

  async scanMissingLoginAlerts(): Promise<{
    status: string;
    work_date?: string;
    queued_count?: number;
    sent_count?: number;
    queued_employees?: Array<{ employee_name: string; employee_email: string; status: string }>;
    sent_employees?: Array<{
      employee_name: string;
      employee_email: string;
      status: string;
      emails_sent_count?: number;
    }>;
    note?: string;
    reason?: string;
  }> {
    return this.request('/notifications/missing-login-alert', { method: 'POST' });
  }

  async listMissingLoginAlerts(status?: string, limit: number = 100): Promise<MissingLoginAlert[]> {
    const q = new URLSearchParams({ limit: String(limit) });
    if (status) q.set('status', status);
    return this.request<MissingLoginAlert[]>(`/notifications/missing-login-alerts?${q}`);
  }

  async approveMissingLoginAlert(id: string, note?: string): Promise<MissingLoginAlert> {
    return this.request<MissingLoginAlert>(`/notifications/missing-login-alerts/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ note: note || null }),
    });
  }

  async rejectMissingLoginAlert(id: string, note?: string): Promise<MissingLoginAlert> {
    return this.request<MissingLoginAlert>(`/notifications/missing-login-alerts/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ note: note || null }),
    });
  }

  async approveAllMissingLoginAlerts(): Promise<{
    status: string;
    approved_count: number;
    approved_ids: string[];
    errors: string[];
  }> {
    return this.request('/notifications/missing-login-alerts/approve-all', { method: 'POST' });
  }

  // --- Report Schedules (Phase 13) ---
  async listSchedules(): Promise<ReportSchedule[]> {
    return this.request<ReportSchedule[]>('/schedules/');
  }

  async getSchedule(id: string): Promise<ReportSchedule> {
    return this.request<ReportSchedule>(`/schedules/${id}`);
  }

  async updateSchedule(id: string, data: Partial<ReportSchedule>): Promise<ReportSchedule> {
    return this.request<ReportSchedule>(`/schedules/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async manualRunSchedule(id: string, force: boolean = true, referenceDate?: string): Promise<ReportJob> {
    return this.request<ReportJob>(`/schedules/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ force, reference_date: referenceDate }),
    });
  }

  async checkMissedSchedules(): Promise<any> {
    return this.request<any>('/schedules/check-missed', { method: 'POST' });
  }
}

export const apiClient = new ApiClient();
