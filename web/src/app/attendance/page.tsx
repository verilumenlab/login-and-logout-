'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Clock, LogIn, LogOut, RefreshCw, Wifi, WifiOff } from 'lucide-react';
import { apiClient, PresenceDay, PresenceEvent, TeamPresenceRow } from '@/lib/api-client';
import { formatDuration, formatTime, localDateInput, shiftDate } from '@/lib/format';

type RangeId = 'week' | 'two_weeks' | 'month' | 'custom';

const EVENT_LABELS: Record<PresenceEvent['event_type'], string> = {
  APP_LOGIN: 'Desktop app sign-in',
  APP_LOGOUT: 'Desktop app sign-out',
  WIFI_CONNECTED: 'Wi-Fi connected',
  WIFI_DISCONNECTED: 'Wi-Fi disconnected',
};

function EventIcon({ type }: { type: PresenceEvent['event_type'] }) {
  if (type === 'WIFI_CONNECTED') return <Wifi className="w-3.5 h-3.5 text-emerald-600" />;
  if (type === 'WIFI_DISCONNECTED') return <WifiOff className="w-3.5 h-3.5 text-rose-500" />;
  if (type === 'APP_LOGIN') return <LogIn className="w-3.5 h-3.5 text-blue-600" />;
  return <LogOut className="w-3.5 h-3.5 text-slate-500" />;
}

function presetRange(id: Exclude<RangeId, 'custom'>): [string, string] {
  const today = new Date();
  const end = localDateInput(today);
  if (id === 'week') return [shiftDate(end, -((today.getDay() + 6) % 7)), end];
  if (id === 'two_weeks') return [shiftDate(end, -13), end];
  return [`${end.slice(0, 8)}01`, end];
}

function formatDay(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short' });
}

export default function AttendancePage() {
  const [people, setPeople] = useState<TeamPresenceRow[]>([]);
  const [employeeId, setEmployeeId] = useState('');
  const [range, setRange] = useState<RangeId>('week');
  const [[start, end], setDates] = useState<[string, string]>(presetRange('week'));
  const [days, setDays] = useState<PresenceDay[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .getTeamPresence()
      .then((board) => {
        setPeople(board.rows);
        const fromUrl = new URLSearchParams(window.location.search).get('employee');
        const initial = board.rows.find((r) => r.employee_id === fromUrl) ?? board.rows[0];
        if (initial) setEmployeeId(initial.employee_id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Could not load employees'));
  }, []);

  const load = useCallback(async () => {
    if (!employeeId) return;
    setLoading(true);
    try {
      setDays((await apiClient.getEmployeePresenceHistory(employeeId, start, end)).days);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load attendance');
    } finally {
      setLoading(false);
    }
  }, [employeeId, start, end]);

  useEffect(() => {
    load();
  }, [load]);

  const choosePreset = (id: RangeId) => {
    setRange(id);
    if (id !== 'custom') setDates(presetRange(id));
  };

  const totals = useMemo(() => {
    const worked = days.filter((d) => d.first_login);
    const minutes = worked.reduce((sum, d) => sum + d.worked_minutes, 0);
    const avgLogin = worked.length
      ? worked.reduce((sum, d) => {
          const t = new Date(d.first_login!);
          return sum + t.getHours() * 60 + t.getMinutes();
        }, 0) / worked.length
      : null;
    return { present: worked.length, minutes, avgLogin };
  }, [days]);

  const selected = people.find((p) => p.employee_id === employeeId);

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Clock className="w-5 h-5 text-emerald-600" /> Attendance history
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Day-by-day login, logout and Wi-Fi activity for one employee.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading || !employeeId}
          className="self-start md:self-auto p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 disabled:opacity-50"
          aria-label="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 flex flex-col lg:flex-row gap-4 lg:items-end">
        <div className="flex-1">
          <label htmlFor="employee" className="block text-[11px] font-semibold text-slate-500 mb-1">
            Employee
          </label>
          <select
            id="employee"
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="w-full px-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
          >
            {people.length === 0 && <option value="">No employees available</option>}
            {people.map((p) => (
              <option key={p.employee_id} value={p.employee_id}>
                {p.full_name} ({p.employee_code}){p.department_name ? ` — ${p.department_name}` : ''}
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-[11px] font-semibold text-slate-500 mb-1">Period</div>
          <div className="flex rounded-lg bg-slate-100 dark:bg-slate-800 p-0.5">
            {(
              [
                ['week', 'This week'],
                ['two_weeks', '14 days'],
                ['month', 'This month'],
                ['custom', 'Custom'],
              ] as [RangeId, string][]
            ).map(([id, label]) => (
              <button
                key={id}
                onClick={() => choosePreset(id)}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
                  range === id ? 'bg-white dark:bg-slate-900 text-blue-700 dark:text-blue-300 shadow-sm' : 'text-slate-600 dark:text-slate-400'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {range === 'custom' && (
          <div className="flex items-center gap-2 text-xs">
            <input
              type="date"
              value={start}
              max={end}
              onChange={(e) => e.target.value && setDates([e.target.value, end])}
              className="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
            />
            <span className="text-slate-400">to</span>
            <input
              type="date"
              value={end}
              min={start}
              max={localDateInput(new Date())}
              onChange={(e) => e.target.value && setDates([start, e.target.value])}
              className="px-2 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
            />
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs">
          {error}
        </div>
      )}

      {selected && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            ['Days logged in', String(totals.present)],
            ['Total time', formatDuration(totals.minutes)],
            ['Average per day', formatDuration(totals.present ? totals.minutes / totals.present : 0)],
            [
              'Average login',
              totals.avgLogin === null
                ? '—'
                : `${String(Math.floor(totals.avgLogin / 60)).padStart(2, '0')}:${String(Math.round(totals.avgLogin % 60)).padStart(2, '0')}`,
            ],
          ].map(([label, value]) => (
            <div key={label} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4">
              <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">{label}</div>
              <div className="text-xl font-black mt-1 tabular-nums">{value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
            <tr>
              <th className="text-left font-bold px-4 py-3">Date</th>
              <th className="text-left font-bold px-4 py-3">Login</th>
              <th className="text-left font-bold px-4 py-3">Logout</th>
              <th className="text-right font-bold px-4 py-3">Hours</th>
              <th className="text-left font-bold px-4 py-3">Wi-Fi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {!loading && days.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                  {employeeId ? 'No logins recorded in this period.' : 'Choose an employee.'}
                </td>
              </tr>
            )}
            {days.map((d) => {
              const open = expanded === d.work_date;
              return (
                <React.Fragment key={d.work_date}>
                  <tr
                    className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    onClick={() => setExpanded(open ? null : d.work_date)}
                  >
                    <td className="px-4 py-3 font-semibold">
                      <span className="inline-flex items-center gap-1">
                        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                        {formatDay(d.work_date)}
                      </span>
                    </td>
                    <td className="px-4 py-3 tabular-nums">{formatTime(d.first_login)}</td>
                    <td className="px-4 py-3 tabular-nums">
                      {d.is_logged_in ? <span className="text-emerald-600 font-semibold">Active</span> : formatTime(d.last_logout)}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{d.first_login ? formatDuration(d.worked_minutes) : '—'}</td>
                    <td className="px-4 py-3 text-slate-500">
                      {d.first_wifi_connected_at
                        ? `${formatTime(d.first_wifi_connected_at)} · ${d.wifi_networks.join(', ')}`
                        : '—'}
                    </td>
                  </tr>
                  {open && (
                    <tr className="bg-slate-50/60 dark:bg-slate-800/30">
                      <td colSpan={5} className="px-10 py-3">
                        {d.events.length === 0 ? (
                          <span className="text-slate-400">No app or Wi-Fi events for this day.</span>
                        ) : (
                          <ul className="space-y-1.5">
                            {d.events.map((ev, i) => (
                              <li key={`${ev.occurred_at}-${i}`} className="flex items-center gap-2">
                                <span className="w-16 font-semibold tabular-nums">{formatTime(ev.occurred_at)}</span>
                                <EventIcon type={ev.event_type} />
                                <span>{EVENT_LABELS[ev.event_type] ?? ev.event_type}</span>
                                {ev.ssid && <span className="text-slate-500">({ev.ssid})</span>}
                                {ev.attendance_action === 'CLOCK_IN' && (
                                  <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-semibold">
                                    counted as login
                                  </span>
                                )}
                                {ev.attendance_action === 'CLOCK_OUT' && (
                                  <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200 text-[10px] font-semibold">
                                    counted as logout
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
