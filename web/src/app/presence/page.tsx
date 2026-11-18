'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, Download, LogIn, RefreshCw, Search, Wifi } from 'lucide-react';
import { apiClient, TeamPresenceResponse, TeamPresenceRow, TeamPresenceStatus } from '@/lib/api-client';
import { useRole } from '@/components/RoleContext';
import { formatDuration, formatTime, localDateInput, shiftDate } from '@/lib/format';

const STATUS_META: Record<TeamPresenceStatus, { label: string; badge: string }> = {
  LOGGED_IN: {
    label: 'Logged in',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800',
  },
  LOGGED_OUT: {
    label: 'Logged out',
    badge: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700',
  },
  ON_LEAVE: {
    label: 'On leave',
    badge: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800',
  },
  NOT_LOGGED_IN: {
    label: 'Not logged in',
    badge: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800',
  },
};

type Filter = 'ALL' | TeamPresenceStatus;
type ExportPeriod = 'weekly' | 'monthly';

/** Local day window for the selected work date (ms). */
function workDayWindow(workDate: string): { dayStart: number; dayEnd: number; dayCap: number } {
  const [y, m, d] = workDate.split('-').map(Number);
  const dayStart = new Date(y, m - 1, d).getTime();
  const dayEnd = new Date(y, m - 1, d + 1).getTime();
  return { dayStart, dayEnd, dayCap: dayEnd - 1000 };
}

/** Logout time clipped to the work day so next-morning stamps don't show as AM. */
function formatLogoutTime(iso: string | null | undefined, workDate: string): string {
  if (!iso) return '—';
  const { dayCap } = workDayWindow(workDate);
  const t = new Date(iso).getTime();
  const show = Number.isFinite(t) && t > dayCap ? new Date(dayCap) : new Date(iso);
  return show.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Hours for the selected work date only.
 * Always login→logout inside the day — never trust an unclamped overnight span
 * (that made "10:19 AM → 10:31 AM" show as 13h 41m).
 */
function displayMinutes(row: TeamPresenceRow, workDate: string): number {
  return liveMinutes(row, workDate);
}

function liveMinutes(row: TeamPresenceRow, workDate: string): number {
  if (!row.first_login) return row.worked_minutes || 0;
  const { dayStart, dayEnd } = workDayWindow(workDate);
  const start = Math.max(new Date(row.first_login).getTime(), dayStart);

  if (row.status === 'LOGGED_OUT' && row.last_logout) {
    const end = Math.min(new Date(row.last_logout).getTime(), dayEnd);
    if (end > start) return (end - start) / 60000;
    // Server already day-clamped; prefer that when client clamp collapses.
    if ((row.worked_minutes || 0) > 0) return row.worked_minutes;
    return 0;
  }
  if (row.status === 'LOGGED_IN') {
    const end = Math.min(Date.now(), dayEnd);
    return Math.max(0, (end - start) / 60000);
  }
  if ((row.worked_minutes || 0) > 0 && (row.worked_minutes || 0) <= 16 * 60) {
    return row.worked_minutes;
  }
  return Math.max(0, (Math.min(Date.now(), dayEnd) - start) / 60000);
}

export default function PresencePage() {
  const { role } = useRole();
  const today = localDateInput(new Date());
  const [date, setDate] = useState(today);
  const [data, setData] = useState<TeamPresenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('ALL');
  const [search, setSearch] = useState('');
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState<ExportPeriod | null>(null);
  const exportRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await apiClient.getTeamPresence(date));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load login records');
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    load();
    if (date !== today) return;
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, [load, date, today]);

  useEffect(() => {
    if (!exportOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [exportOpen]);

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (r) =>
        (filter === 'ALL' || r.status === filter) &&
        (!q ||
          r.full_name.toLowerCase().includes(q) ||
          r.employee_code.toLowerCase().includes(q) ||
          (r.department_name ?? '').toLowerCase().includes(q))
    );
  }, [data, filter, search]);

  const exportAttendance = async (period: ExportPeriod) => {
    setExporting(period);
    setExportOpen(false);
    try {
      await apiClient.downloadAttendanceCsv(period, date);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export CSV');
    } finally {
      setExporting(null);
    }
  };

  const tiles: { id: Filter; label: string; value: number; tone: string }[] = [
    { id: 'ALL', label: 'Employees', value: data?.counts.total ?? 0, tone: 'text-slate-900 dark:text-slate-100' },
    { id: 'LOGGED_IN', label: 'Logged in now', value: data?.counts.logged_in ?? 0, tone: 'text-emerald-600' },
    { id: 'LOGGED_OUT', label: 'Logged out', value: data?.counts.logged_out ?? 0, tone: 'text-slate-600 dark:text-slate-300' },
    { id: 'ON_LEAVE', label: 'On leave', value: data?.counts.on_leave ?? 0, tone: 'text-amber-600' },
    { id: 'NOT_LOGGED_IN', label: 'Not logged in', value: data?.counts.not_logged_in ?? 0, tone: 'text-rose-600' },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <LogIn className="w-5 h-5 text-blue-600" /> Login &amp; Logout
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            {data?.scope === 'TEAM' ? 'Your direct reports. ' : 'All employees. '}
            Hours are from each person’s actual login (not only 9:30). Full day = 9h. At 9h the app asks if still
            working (confirm = +10 min). Logout before 9h needs confirmation. No reply in 10 minutes → auto logout.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
            <button
              onClick={() => setDate(shiftDate(date, -1))}
              className="p-2 text-slate-500 hover:text-slate-900 dark:hover:text-white"
              aria-label="Previous day"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <input
              type="date"
              value={date}
              max={today}
              onChange={(e) => e.target.value && setDate(e.target.value)}
              className="bg-transparent text-xs font-semibold px-1 py-1.5 focus:outline-none"
            />
            <button
              onClick={() => setDate(shiftDate(date, 1))}
              disabled={date >= today}
              className="p-2 text-slate-500 hover:text-slate-900 dark:hover:text-white disabled:opacity-30"
              aria-label="Next day"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <button
            onClick={load}
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300"
            aria-label="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <div className="relative" ref={exportRef}>
            <button
              onClick={() => setExportOpen((o) => !o)}
              disabled={!!exporting}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold disabled:opacity-50"
            >
              <Download className={`w-3.5 h-3.5 ${exporting ? 'animate-pulse' : ''}`} />
              {exporting ? 'Exporting…' : 'Export'}
              <ChevronDown className="w-3.5 h-3.5 opacity-80" />
            </button>
            {exportOpen && (
              <div className="absolute right-0 mt-1 z-20 w-64 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg py-1">
                <button
                  onClick={() => exportAttendance('weekly')}
                  className="w-full text-left px-3 py-2.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <div className="font-semibold text-slate-900 dark:text-slate-100">Weekly CSV</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Mon–Fri of selected week</div>
                </button>
                <button
                  onClick={() => exportAttendance('monthly')}
                  className="w-full text-left px-3 py-2.5 text-xs hover:bg-slate-50 dark:hover:bg-slate-800"
                >
                  <div className="font-semibold text-slate-900 dark:text-slate-100">Monthly CSV</div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Full calendar month</div>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {tiles.map((t) => (
          <button
            key={t.id}
            onClick={() => setFilter(t.id)}
            className={`text-left p-4 rounded-xl border bg-white dark:bg-slate-900 transition ${
              filter === t.id
                ? 'border-blue-500 ring-1 ring-blue-500'
                : 'border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700'
            }`}
          >
            <div className={`text-2xl font-black ${t.tone}`}>{t.value}</div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">{t.label}</div>
          </button>
        ))}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs">
          {error}
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <div className="p-3 border-b border-slate-200 dark:border-slate-800">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, code or department"
              className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <tr>
                <th className="text-left font-bold px-4 py-3">Employee</th>
                <th className="text-left font-bold px-4 py-3">Status</th>
                <th className="text-left font-bold px-4 py-3">Login</th>
                <th className="text-left font-bold px-4 py-3">Logout</th>
                <th className="text-right font-bold px-4 py-3">Hours</th>
                <th className="text-left font-bold px-4 py-3">Wi-Fi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {loading && !data && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                    Loading…
                  </td>
                </tr>
              )}
              {data && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                    {data.rows.length === 0
                      ? data.scope === 'TEAM'
                        ? 'No employees report to you yet.'
                        : 'No employee accounts found.'
                      : 'Nobody matches this filter.'}
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.employee_id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-900 dark:text-slate-100">{r.full_name}</div>
                    <div className="text-[10px] text-slate-500 font-mono">
                      {r.employee_code}
                      {r.department_name ? ` • ${r.department_name}` : ''}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-semibold ${STATUS_META[r.status].badge}`}>
                      {STATUS_META[r.status].label}
                    </span>
                    {r.leave_type_name && <div className="text-[10px] text-slate-500 mt-0.5">{r.leave_type_name}</div>}
                  </td>
                  <td className="px-4 py-3 font-semibold tabular-nums">{formatTime(r.first_login)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {r.status === 'LOGGED_IN' ? (
                      <span className="text-emerald-600">Active</span>
                    ) : (
                      <div>
                        <div>{formatLogoutTime(r.last_logout, date)}</div>
                        {r.logout_note && (
                          <div className="text-[10px] text-amber-700 dark:text-amber-400 mt-0.5 max-w-[200px] leading-snug">
                            {r.logout_note}
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {r.first_login ? (
                      <div>
                        <div>{formatDuration(displayMinutes(r, date))}</div>
                        <div className="text-[10px] text-slate-500 mt-0.5 space-y-0.5">
                          {r.completed_nine_hours && <div className="text-emerald-600">9h completed</div>}
                          {r.early_logout && <div className="text-amber-600">Early logout</div>}
                          {r.auto_logout && <div className="text-rose-600">Auto logout</div>}
                          {r.confirmation_status === 'NO_RESPONSE' && (
                            <div className="text-rose-600">No response</div>
                          )}
                        </div>
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {r.first_wifi_connected_at ? (
                      <div className="flex items-center gap-1.5">
                        <Wifi className="w-3.5 h-3.5 text-emerald-600" />
                        <span className="tabular-nums">{formatTime(r.first_wifi_connected_at)}</span>
                        <span className="text-slate-500 truncate max-w-[140px]">{r.wifi_networks.join(', ')}</span>
                      </div>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
