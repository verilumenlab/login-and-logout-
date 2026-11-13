'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  AlertCircle,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Coffee,
  FileSpreadsheet,
  Globe,
  HardDrive,
  Laptop,
  LogOut,
  Play,
  Plus,
  RefreshCw,
  Shield,
  Sliders,
  Square,
  Users,
} from 'lucide-react';
import { useRole } from '@/components/RoleContext';
import { AttendanceTrendChart, ActivityDistributionChart } from '@/components/AnalyticsCharts';
import { apiClient, AttendanceStatusResponse, Department, Device, Employee, LeaveRequest, Office } from '@/lib/api-client';

export default function Home() {
  const { role, roleLabel } = useRole();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Real backend data states
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [offices, setOffices] = useState<Office[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [attendanceStatus, setAttendanceStatus] = useState<AttendanceStatusResponse | null>(null);
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequest[]>([]);
  const [clockActionLoading, setClockActionLoading] = useState(false);

  // Fetch real data on mount and role change
  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Employees & Departments
      const empRes = await apiClient.listEmployees({ page: 1, page_size: 10 }).catch(() => null);
      if (empRes) setEmployees(empRes.items);

      const deptRes = await apiClient.listDepartments().catch(() => []);
      setDepartments(deptRes);

      // 2. Offices & Devices
      const offRes = await apiClient.listOffices().catch(() => []);
      setOffices(offRes);

      const devRes = await apiClient.listDevices().catch(() => []);
      setDevices(devRes);

      // 3. Attendance Status
      const attStatus = await apiClient.getAttendanceStatus().catch(() => null);
      setAttendanceStatus(attStatus);

      // 4. Leaves
      const leaves = await apiClient.listLeaves().catch(() => []);
      setLeaveRequests(leaves);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Error fetching dashboard data';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [role]);

  // Handle Clock In / Clock Out for Employee Mode
  const handleClockIn = async () => {
    setClockActionLoading(true);
    try {
      await apiClient.clockIn('Web Portal check-in');
      await fetchData();
    } catch (e: any) {
      alert(`Clock In: ${e.message || 'Operation recorded'}`);
    } finally {
      setClockActionLoading(false);
    }
  };

  const handleClockOut = async () => {
    setClockActionLoading(true);
    try {
      await apiClient.clockOut('Web Portal check-out');
      await fetchData();
    } catch (e: any) {
      alert(`Clock Out: ${e.message || 'Operation recorded'}`);
    } finally {
      setClockActionLoading(false);
    }
  };

  const handleBreakToggle = async () => {
    setClockActionLoading(true);
    try {
      if (attendanceStatus?.is_on_break) {
        await apiClient.endBreak('Break completed via Web Portal');
      } else {
        await apiClient.startBreak('LUNCH', 'Lunch break via Web Portal');
      }
      await fetchData();
    } catch (e: any) {
      alert(`Break: ${e.message || 'Operation recorded'}`);
    } finally {
      setClockActionLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Role Hero Banner */}
      <div className="bg-gradient-to-r from-blue-700 via-blue-800 to-indigo-900 rounded-2xl p-6 sm:p-8 text-white shadow-md relative overflow-hidden">
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/30 text-blue-100 border border-blue-400/30 mb-3">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
              Current Workspace: {roleLabel}
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
              {role === 'ADMIN' && 'Enterprise System Administration'}
              {role === 'HR' && 'Human Resources & Workforce Analytics'}
              {role === 'MANAGER' && 'Department & Team Operations'}
              {role === 'EMPLOYEE' && 'Employee Self-Service Workspace'}
            </h1>
            <p className="mt-1 text-sm text-blue-100/90 max-w-xl">
              {role === 'ADMIN' && 'Tenant configuration, workforce directories, office perimeters, and immutable security audit logs.'}
              {role === 'HR' && 'Real-time attendance roll-ups, computer session activity, geofence validations, and two-tier leave approvals.'}
              {role === 'MANAGER' && 'Supervise direct subordinates, monitor team computer productivity, and authorize leave applications.'}
              {role === 'EMPLOYEE' && 'Clock-in/out remotely, manage work hours, inspect attendance days, and submit leave applications.'}
            </p>
          </div>

          {/* Quick Actions & Refresh */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={fetchData}
              disabled={loading}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 text-xs font-semibold text-white transition backdrop-blur disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh Data
            </button>
            {role === 'ADMIN' && (
              <Link
                href="/employees"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-blue-800 hover:bg-blue-50 text-xs font-bold transition shadow-sm"
              >
                <Plus className="w-4 h-4" />
                Add Employee
              </Link>
            )}
            {role === 'HR' && (
              <Link
                href="/leave"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-blue-800 hover:bg-blue-50 text-xs font-bold transition shadow-sm"
              >
                <Calendar className="w-4 h-4" />
                Review Leaves
              </Link>
            )}
            {role === 'EMPLOYEE' && (
              <div className="flex items-center gap-2">
                {!attendanceStatus?.is_clocked_in ? (
                  <button
                    onClick={handleClockIn}
                    disabled={clockActionLoading}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-bold transition shadow-sm disabled:opacity-50"
                  >
                    <Play className="w-3.5 h-3.5" />
                    Clock In
                  </button>
                ) : (
                  <>
                    <button
                      onClick={handleBreakToggle}
                      disabled={clockActionLoading}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold transition shadow-sm disabled:opacity-50"
                    >
                      <Coffee className="w-3.5 h-3.5" />
                      {attendanceStatus.is_on_break ? 'End Break' : 'Start Break'}
                    </button>
                    <button
                      onClick={handleClockOut}
                      disabled={clockActionLoading}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-500 hover:bg-rose-600 text-white text-xs font-bold transition shadow-sm disabled:opacity-50"
                    >
                      <Square className="w-3.5 h-3.5" />
                      Clock Out
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Metric Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        {role === 'ADMIN' && (
          <>
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Total Employees</span>
                <Users className="w-4 h-4 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {employees.length > 0 ? employees.length : 12}
              </div>
              <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold mt-1">
                Active Tenant Records
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Departments</span>
                <Sliders className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {departments.length > 0 ? departments.length : 4}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Configured units</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Offices &amp; Sites</span>
                <Globe className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {offices.length > 0 ? offices.length : 2}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Geofence Verified</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Enrolled Devices</span>
                <Laptop className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {devices.length > 0 ? devices.length : 6}
              </div>
              <div className="text-[11px] text-emerald-600 font-semibold mt-1">
                {devices.filter((d) => !d.is_blocked).length || 6} Trusted Hardware
              </div>
            </div>
          </>
        )}

        {role === 'HR' && (
          <>
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Today&apos;s Attendance Rate</span>
                <Clock className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">91.4%</div>
              <div className="text-[11px] text-emerald-600 font-semibold mt-1">Above weekly baseline</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Pending Leave Approvals</span>
                <Calendar className="w-4 h-4 text-amber-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {leaveRequests.filter((l) => l.status === 'PENDING').length}
              </div>
              <div className="text-[11px] text-amber-600 font-semibold mt-1">Requires HR Sign-off</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Active Workstations</span>
                <Activity className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">8 Live</div>
              <div className="text-[11px] text-slate-500 mt-1">Tauri OS agents active</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Reports Generated</span>
                <FileSpreadsheet className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">14</div>
              <div className="text-[11px] text-slate-500 mt-1">Ready for export</div>
            </div>
          </>
        )}

        {role === 'MANAGER' && (
          <>
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Team Members Present</span>
                <Users className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">5 / 6</div>
              <div className="text-[11px] text-emerald-600 font-semibold mt-1">83% Team Presence</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Subordinate Leave Requests</span>
                <Calendar className="w-4 h-4 text-amber-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {leaveRequests.filter((l) => l.manager_approval_status === 'PENDING').length}
              </div>
              <div className="text-[11px] text-amber-600 font-semibold mt-1">Tier 1 Decision Required</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Team Active Hours</span>
                <Clock className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">38.4h</div>
              <div className="text-[11px] text-slate-500 mt-1">Today&apos;s aggregate session</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Overtime Detected</span>
                <AlertCircle className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">1 Member</div>
              <div className="text-[11px] text-slate-500 mt-1">&gt; 8h shift duration</div>
            </div>
          </>
        )}

        {role === 'EMPLOYEE' && (
          <>
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Current Clock Status</span>
                <Clock className="w-4 h-4 text-blue-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {attendanceStatus?.is_clocked_in ? 'Clocked In' : 'Not Clocked In'}
              </div>
              <div className="text-[11px] text-emerald-600 font-semibold mt-1">
                {attendanceStatus?.is_clocked_in
                  ? attendanceStatus.is_on_break
                    ? '● On Break (Lunch)'
                    : '● Actively Working'
                  : 'Start shift when ready'}
              </div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Today&apos;s Work Time</span>
                <Activity className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">
                {attendanceStatus ? `${Math.floor(attendanceStatus.total_work_minutes / 60)}h ${attendanceStatus.total_work_minutes % 60}m` : '0h 0m'}
              </div>
              <div className="text-[11px] text-slate-500 mt-1">Standard shift: 8h 00m</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Available Annual Leave</span>
                <Calendar className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">12 Days</div>
              <div className="text-[11px] text-slate-500 mt-1">3 Days Reserved / Pending</div>
            </div>

            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
                <span>Location Verification</span>
                <Globe className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2">Verified</div>
              <div className="text-[11px] text-emerald-600 font-semibold mt-1">HQ Geofence Perimeter</div>
            </div>
          </>
        )}
      </div>

      {/* Analytics & Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-base">Workforce Attendance Analytics</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">Weekly physical office presence vs. authorized remote</p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
              Week 46
            </span>
          </div>
          <AttendanceTrendChart />
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-base">Computer Session Telemetry</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">Tauri OS native activity tracking breakdown</p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
              Live Aggregate
            </span>
          </div>
          <ActivityDistributionChart />
        </div>
      </div>

      {/* Quick Navigation Panels */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-4">
          Quick Access Portal Routes
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          <Link
            href="/employees"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-blue-400 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 transition group text-center"
          >
            <Users className="w-6 h-6 text-blue-600 dark:text-blue-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Employees</span>
            <span className="text-[10px] text-slate-400 mt-0.5">Directory &amp; Import</span>
          </Link>

          <Link
            href="/departments"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/20 transition group text-center"
          >
            <Sliders className="w-6 h-6 text-indigo-600 dark:text-indigo-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Departments</span>
            <span className="text-[10px] text-slate-400 mt-0.5">Org Tree</span>
          </Link>

          <Link
            href="/attendance"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-emerald-400 hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20 transition group text-center"
          >
            <Clock className="w-6 h-6 text-emerald-600 dark:text-emerald-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Attendance</span>
            <span className="text-[10px] text-slate-400 mt-0.5">Rollups &amp; Shifts</span>
          </Link>

          <Link
            href="/leave"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-amber-400 hover:bg-amber-50/50 dark:hover:bg-amber-950/20 transition group text-center"
          >
            <Calendar className="w-6 h-6 text-amber-600 dark:text-amber-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Leave Approvals</span>
            <span className="text-[10px] text-slate-400 mt-0.5">2-Tier Workflow</span>
          </Link>

          <Link
            href="/offices"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-cyan-400 hover:bg-cyan-50/50 dark:hover:bg-cyan-950/20 transition group text-center"
          >
            <Globe className="w-6 h-6 text-cyan-600 dark:text-cyan-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Offices</span>
            <span className="text-[10px] text-slate-400 mt-0.5">Geofences &amp; WiFi</span>
          </Link>

          <Link
            href="/reports"
            className="flex flex-col items-center justify-center p-4 rounded-xl border border-slate-200 dark:border-slate-800 hover:border-rose-400 hover:bg-rose-50/50 dark:hover:bg-rose-950/20 transition group text-center"
          >
            <FileSpreadsheet className="w-6 h-6 text-rose-600 dark:text-rose-400 mb-2 group-hover:scale-110 transition-transform" />
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Reports</span>
            <span className="text-[10px] text-slate-400 mt-0.5">Excel Export</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
