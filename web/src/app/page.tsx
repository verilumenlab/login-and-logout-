'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  Calendar,
  Globe,
  Laptop,
  LogIn,
  LogOut,
  Palmtree,
  RefreshCw,
  Sliders,
  UserX,
  Users,
  Wifi,
} from 'lucide-react';
import { useRole } from '@/components/RoleContext';
import { apiClient, LeaveRequest, TeamPresenceResponse } from '@/lib/api-client';
import { formatDuration, formatTime, localDateInput, shiftDate } from '@/lib/format';

interface WeekDay {
  date: string;
  label: string;
  present: number;
  onLeave: number;
  absent: number;
}

interface AdminCounts {
  employees: number;
  departments: number;
  offices: number;
  devices: number;
}

function weekdaysSoFar(): string[] {
  const today = new Date();
  const monday = shiftDate(localDateInput(today), -((today.getDay() + 6) % 7));
  const days: string[] = [];
  for (let i = 0; i < 5; i++) {
    const d = shiftDate(monday, i);
    if (d > localDateInput(today)) break;
    days.push(d);
  }
  return days;
}

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  tone: string;
  href?: string;
}) {
  const body = (
    <div className="h-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 hover:border-slate-300 dark:hover:border-slate-700 transition">
      <div className="flex items-center justify-between text-slate-500 dark:text-slate-400 text-xs font-medium">
        <span>{label}</span>
        <Icon className={`w-4 h-4 ${tone}`} />
      </div>
      <div className="text-2xl font-black text-slate-900 dark:text-slate-100 mt-2 tabular-nums">{value}</div>
      {hint && <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">{hint}</div>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function Home() {
  const { role, user } = useRole();
  const [today, setToday] = useState<TeamPresenceResponse | null>(null);
  const [week, setWeek] = useState<WeekDay[]>([]);
  const [pendingLeaves, setPendingLeaves] = useState<LeaveRequest[]>([]);
  const [adminCounts, setAdminCounts] = useState<AdminCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const days = weekdaysSoFar();
      const [boards, leaves] = await Promise.all([
        Promise.all(days.map((d) => apiClient.getTeamPresence(d))),
        apiClient.listTeamLeaves('PENDING').catch(() => [] as LeaveRequest[]),
      ]);
      const todayBoard = await apiClient.getTeamPresence(localDateInput(new Date()));
      setToday(todayBoard);
      setWeek(
        boards.map((b, i) => ({
          date: days[i],
          label: new Date(`${days[i]}T00:00:00`).toLocaleDateString([], { weekday: 'short' }),
          present: b.counts.logged_in + b.counts.logged_out,
          onLeave: b.counts.on_leave,
          absent: b.counts.not_logged_in,
        }))
      );
      setPendingLeaves(
        leaves.filter((l) =>
          l.status === 'PENDING' &&
          (role === 'MANAGER' ? l.manager_approval_status === 'PENDING' : true)
        )
      );

      if (role === 'ADMIN') {
        const [emps, depts, offices, devices] = await Promise.all([
          apiClient.listEmployees({ page: 1, page_size: 1 }).catch(() => null),
          apiClient.listDepartments().catch(() => []),
          apiClient.listOffices().catch(() => []),
          apiClient.listDevices().catch(() => []),
        ]);
        setAdminCounts({
          employees: emps?.total ?? 0,
          departments: depts.length,
          offices: offices.length,
          devices: devices.length,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the overview');
    } finally {
      setLoading(false);
    }
  }, [role]);

  useEffect(() => {
    load();
  }, [load]);

  const counts = today?.counts;
  const attendanceRate =
    counts && counts.total - counts.on_leave > 0
      ? Math.round(((counts.logged_in + counts.logged_out) / (counts.total - counts.on_leave)) * 100)
      : null;
  const recentLogins = (today?.rows ?? [])
    .filter((r) => r.first_login)
    .sort((a, b) => (a.first_login! < b.first_login! ? -1 : 1))
    .slice(0, 8);
  const notLoggedIn = (today?.rows ?? []).filter((r) => r.status === 'NOT_LOGGED_IN').slice(0, 8);
  const weekMax = Math.max(1, ...week.map((d) => d.present + d.onLeave + d.absent));
  const scopeWord = role === 'MANAGER' ? 'team' : 'organization';

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold">Good {new Date().getHours() < 12 ? 'morning' : 'afternoon'}, {user?.display_name}</h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Today&apos;s login &amp; logout status for your {scopeWord},{' '}
            {new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })}.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-xs font-semibold disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Logged in now"
          value={counts?.logged_in ?? '—'}
          hint={counts ? `of ${counts.total} ${role === 'MANAGER' ? 'team members' : 'employees'}` : undefined}
          icon={LogIn}
          tone="text-emerald-600"
          href="/presence"
        />
        <StatCard label="Logged out" value={counts?.logged_out ?? '—'} icon={LogOut} tone="text-slate-500" href="/presence" />
        <StatCard label="On leave today" value={counts?.on_leave ?? '—'} icon={Palmtree} tone="text-amber-600" href="/presence" />
        <StatCard label="Not logged in" value={counts?.not_logged_in ?? '—'} icon={UserX} tone="text-rose-600" href="/presence" />
        <StatCard
          label="Leave awaiting approval"
          value={pendingLeaves.length}
          hint={attendanceRate !== null ? `Attendance today: ${attendanceRate}%` : undefined}
          icon={Calendar}
          tone="text-indigo-600"
          href="/leave"
        />
      </div>

      {role === 'ADMIN' && adminCounts && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Employee records" value={adminCounts.employees} icon={Users} tone="text-blue-600" href="/employees" />
          <StatCard label="Departments" value={adminCounts.departments} icon={Sliders} tone="text-indigo-600" href="/departments" />
          <StatCard label="Offices" value={adminCounts.offices} icon={Globe} tone="text-emerald-600" href="/offices" />
          <StatCard label="Registered laptops" value={adminCounts.devices} icon={Laptop} tone="text-amber-600" href="/devices" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="font-bold text-sm">This week</h2>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Logged in vs on leave vs not logged in, per day</p>
            </div>
            <div className="flex gap-3 text-[10px] text-slate-500">
              <span className="flex items-center gap-1"><i className="w-2 h-2 rounded-sm bg-emerald-500" /> Present</span>
              <span className="flex items-center gap-1"><i className="w-2 h-2 rounded-sm bg-amber-400" /> Leave</span>
              <span className="flex items-center gap-1"><i className="w-2 h-2 rounded-sm bg-rose-300" /> Not logged in</span>
            </div>
          </div>
          {week.length === 0 ? (
            <div className="h-40 flex items-center justify-center text-xs text-slate-400">{loading ? 'Loading…' : 'No data yet'}</div>
          ) : (
            <div className="flex items-end gap-4 h-44">
              {week.map((d) => {
                const total = d.present + d.onLeave + d.absent;
                return (
                  <div key={d.date} className="flex-1 flex flex-col items-center gap-2">
                    <div className="text-[10px] font-semibold text-slate-600 dark:text-slate-300 tabular-nums">
                      {d.present}/{total}
                    </div>
                    <div
                      className="w-full max-w-[56px] flex flex-col-reverse rounded-md overflow-hidden bg-slate-100 dark:bg-slate-800"
                      style={{ height: `${(total / weekMax) * 120 + 4}px` }}
                      title={`${d.present} present, ${d.onLeave} on leave, ${d.absent} not logged in`}
                    >
                      <div className="bg-emerald-500" style={{ height: `${total ? (d.present / total) * 100 : 0}%` }} />
                      <div className="bg-amber-400" style={{ height: `${total ? (d.onLeave / total) * 100 : 0}%` }} />
                      <div className="bg-rose-300" style={{ height: `${total ? (d.absent / total) * 100 : 0}%` }} />
                    </div>
                    <div className="text-[11px] text-slate-500">{d.label}</div>
                  </div>
                );
              })}
            </div>
          )}
          <p className="mt-4 text-[11px] text-slate-500 dark:text-slate-400">
            The full week is emailed as an Excel workbook every Friday evening to HR, admins and managers.
          </p>
        </section>

        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-sm">Leave awaiting approval</h2>
            <Link href="/leave" className="text-[11px] text-blue-600 font-semibold flex items-center gap-0.5">
              Review <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {pendingLeaves.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">Nothing waiting for you.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {pendingLeaves.slice(0, 6).map((l) => (
                <li key={l.id} className="py-2.5">
                  <div className="text-xs font-semibold">{l.employee_name ?? 'Employee'}</div>
                  <div className="text-[11px] text-slate-500">
                    {l.leave_type_name ?? 'Leave'} • {l.start_date}
                    {l.end_date !== l.start_date ? ` → ${l.end_date}` : ''} • {l.total_days} day(s)
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-bold text-sm">First logins today</h2>
            <Link href="/presence" className="text-[11px] text-blue-600 font-semibold flex items-center gap-0.5">
              All <ArrowRight className="w-3 h-3" />
            </Link>
          </div>
          {recentLogins.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">Nobody has logged in yet today.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {recentLogins.map((r) => (
                <li key={r.employee_id} className="py-2.5 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-xs font-semibold truncate">{r.full_name}</div>
                    <div className="text-[10px] text-slate-500 flex items-center gap-1">
                      {r.wifi_networks.length > 0 && <Wifi className="w-3 h-3" />}
                      {r.wifi_networks.join(', ') || r.department_name || r.employee_code}
                    </div>
                  </div>
                  <div className="text-right text-xs tabular-nums">
                    <div className="font-semibold">{formatTime(r.first_login)}</div>
                    <div className="text-[10px] text-slate-500">
                      {r.status === 'LOGGED_IN' ? 'Active' : `Out ${formatTime(r.last_logout)}`} •{' '}
                      {formatDuration(r.worked_minutes)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6">
          <h2 className="font-bold text-sm mb-3">Not logged in yet</h2>
          {notLoggedIn.length === 0 ? (
            <p className="text-xs text-slate-400 py-6 text-center">Everyone is accounted for.</p>
          ) : (
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {notLoggedIn.map((r) => (
                <li key={r.employee_id} className="py-2.5 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold">{r.full_name}</div>
                    <div className="text-[10px] text-slate-500">{r.department_name || r.employee_code}</div>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800">
                    No login
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
