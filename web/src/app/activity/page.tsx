'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Laptop, RefreshCw, Search } from 'lucide-react';
import { apiClient, EmployeeActivityRow } from '@/lib/api-client';
import { useRole } from '@/components/RoleContext';

function formatWhen(iso?: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function formatIdle(seconds: number): string {
  if (!seconds || seconds < 60) return `${seconds || 0}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

export default function LaptopActivityPage() {
  const { role } = useRole();
  const [rows, setRows] = useState<EmployeeActivityRow[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.getActivityBoard();
      setRows(Array.isArray(data.employees) ? data.employees : []);
      setGeneratedAt(data.generated_at || null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load laptop activity');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (role !== 'ADMIN') return;
    void load();
    const t = window.setInterval(() => void load(), 20_000);
    return () => window.clearInterval(t);
  }, [role, load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      [r.employee_name, r.employee_code, r.email, r.department_name, r.application_name, r.window_title, r.device_name]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }, [rows, search]);

  const online = rows.filter((r) => r.is_online).length;
  const idle = rows.filter((r) => r.is_online && r.is_idle).length;

  if (role !== 'ADMIN') {
    return (
      <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-sm text-slate-600 dark:text-slate-300">
        Laptop activity is visible to administrators only.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-black tracking-tight flex items-center gap-2">
            <Laptop className="w-5 h-5 text-slate-500" />
            Laptop activity
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-2xl">
            Admin-only view of what each person is using on their WorkPulse desktop (app name and window title).
            No screenshots or keylogging. Updates about every 20 seconds while the desktop app is running.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-slate-800"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ['People', String(rows.length)],
          ['Online now', String(online)],
          ['Idle', String(idle)],
          ['Updated', generatedAt ? formatWhen(generatedAt) : '—'],
        ].map(([label, value]) => (
          <div
            key={label}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4"
          >
            <div className="text-[11px] text-slate-500 font-medium">{label}</div>
            <div className="text-lg font-black mt-1 tabular-nums">{value}</div>
          </div>
        ))}
      </div>

      <div className="relative max-w-md">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name, app, window…"
          className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 pl-9 pr-3 py-2 text-sm"
        />
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 text-rose-800 px-4 py-3 text-sm">{error}</div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-slate-50 dark:bg-slate-800/60 text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="text-left font-bold px-4 py-3">Person</th>
              <th className="text-left font-bold px-4 py-3">Status</th>
              <th className="text-left font-bold px-4 py-3">Using</th>
              <th className="text-left font-bold px-4 py-3">Window</th>
              <th className="text-left font-bold px-4 py-3">Device</th>
              <th className="text-left font-bold px-4 py-3">Last seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                  No laptop activity yet. Employees need desktop app 0.2.14+ signed in and on the clock.
                </td>
              </tr>
            )}
            {filtered.map((r) => (
              <tr key={r.employee_id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40">
                <td className="px-4 py-3">
                  <div className="font-semibold">{r.employee_name}</div>
                  <div className="text-slate-500">
                    {[r.employee_code, r.department_name].filter(Boolean).join(' · ')}
                  </div>
                  {r.email && <div className="text-slate-400">{r.email}</div>}
                </td>
                <td className="px-4 py-3">
                  {r.is_online ? (
                    <span className={`font-semibold ${r.is_idle ? 'text-amber-600' : 'text-emerald-600'}`}>
                      {r.is_idle ? `Idle · ${formatIdle(r.idle_seconds)}` : 'Active'}
                    </span>
                  ) : (
                    <span className="text-slate-400">Offline</span>
                  )}
                </td>
                <td className="px-4 py-3 font-semibold tabular-nums">{r.application_name || '—'}</td>
                <td className="px-4 py-3 text-slate-600 dark:text-slate-300 max-w-[280px] truncate" title={r.window_title || ''}>
                  {r.window_title || '—'}
                </td>
                <td className="px-4 py-3 text-slate-500">{r.device_name || '—'}</td>
                <td className="px-4 py-3 tabular-nums">{formatWhen(r.last_seen_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
