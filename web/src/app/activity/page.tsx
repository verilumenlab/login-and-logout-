'use client';

import React, { useState } from 'react';
import {
  Activity,
  AlertCircle,
  Clock,
  Laptop,
  Monitor,
  RefreshCw,
  Search,
  Shield,
  Zap,
} from 'lucide-react';
import { useRole } from '@/components/RoleContext';
import { ActivityDistributionChart } from '@/components/AnalyticsCharts';

interface TelemetryEvent {
  id: string;
  employee_name: string;
  device_name: string;
  os_type: string;
  event_type: 'USER_LOGON' | 'USER_LOGOFF' | 'SESSION_LOCK' | 'SESSION_UNLOCK' | 'HEARTBEAT' | 'APP_ACTIVE';
  active_window?: string;
  occurred_at: string;
  duration_minutes: number;
}

export default function ActivityDashboardPage() {
  const { role } = useRole();
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<string>('ALL');

  // Real events sample
  const events: TelemetryEvent[] = [
    {
      id: 'act-01',
      employee_name: 'Edward Employee',
      device_name: 'Workstation-Win11-Pro',
      os_type: 'Windows 11 (23H2)',
      event_type: 'APP_ACTIVE',
      active_window: 'Visual Studio Code - enterprise-attendance',
      occurred_at: '2026-11-12T10:14:00Z',
      duration_minutes: 52,
    },
    {
      id: 'act-02',
      employee_name: 'Edward Employee',
      device_name: 'Workstation-Win11-Pro',
      os_type: 'Windows 11 (23H2)',
      event_type: 'APP_ACTIVE',
      active_window: 'Google Chrome - Jira Sprint Board',
      occurred_at: '2026-11-12T09:20:00Z',
      duration_minutes: 40,
    },
    {
      id: 'act-03',
      employee_name: 'Edward Employee',
      device_name: 'Workstation-Win11-Pro',
      os_type: 'Windows 11 (23H2)',
      event_type: 'SESSION_UNLOCK',
      active_window: 'Windows Lock Screen',
      occurred_at: '2026-11-12T09:00:15Z',
      duration_minutes: 0,
    },
    {
      id: 'act-04',
      employee_name: 'Edward Employee',
      device_name: 'Workstation-Win11-Pro',
      os_type: 'Windows 11 (23H2)',
      event_type: 'USER_LOGON',
      active_window: 'OS System Startup',
      occurred_at: '2026-11-12T08:58:30Z',
      duration_minutes: 0,
    },
    {
      id: 'act-05',
      employee_name: 'Sarah Connor',
      device_name: 'MacBookPro-M3-Corp',
      os_type: 'macOS Sonoma (14.5)',
      event_type: 'APP_ACTIVE',
      active_window: 'Terminal - bash uvicorn',
      occurred_at: '2026-11-12T09:45:00Z',
      duration_minutes: 48,
    },
  ];

  const filtered = events.filter((e) => {
    const matchSearch =
      e.employee_name.toLowerCase().includes(search.toLowerCase()) ||
      e.device_name.toLowerCase().includes(search.toLowerCase()) ||
      (e.active_window && e.active_window.toLowerCase().includes(search.toLowerCase()));
    const matchType = filterType === 'ALL' ? true : e.event_type === filterType;
    return matchSearch && matchType;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Activity className="w-6 h-6 text-blue-600" />
            Computer Session &amp; OS Activity Telemetry
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Native operating system event monitoring (logon, lock, wake, active focus) via Tauri Desktop background agent
          </p>
        </div>

        {/* Privacy Disclosure Callout */}
        <div className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-xl bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
          <Shield className="w-4 h-4 text-indigo-600" />
          <span>Zero Surveillance: No Keyloggers • No Screenshots</span>
        </div>
      </div>

      {/* Aggregate Stats and Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 mb-4">
            Daily Productive Focus
          </h3>
          <ActivityDistributionChart activeHours={6.8} idleHours={0.7} breakHours={0.5} />
        </div>

        <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                Agent Ingestion Pipeline &amp; Heartbeat
              </h3>
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                Healthy
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Events are queued locally during network outages and synchronized idempotently using SHA-256 sequence hashes.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-4 pt-4 border-t border-slate-100 dark:border-slate-800 mt-4 text-center">
            <div>
              <div className="text-xl font-bold text-slate-900 dark:text-slate-100">4,820</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Ingested Events Today</div>
            </div>
            <div>
              <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">0</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Sequence Gaps</div>
            </div>
            <div>
              <div className="text-xl font-bold text-blue-600 dark:text-blue-400">&lt; 15ms</div>
              <div className="text-[11px] text-slate-400 mt-0.5">Clock Skew Audit</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-xs flex flex-col md:flex-row gap-4 items-center justify-between">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search active app or workstation..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto">
          {['ALL', 'APP_ACTIVE', 'USER_LOGON', 'USER_LOGOFF', 'SESSION_LOCK', 'SESSION_UNLOCK'].map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition ${
                filterType === t
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Event Stream Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">Timestamp</th>
                <th className="py-3 px-4 text-left">Employee &amp; Device</th>
                <th className="py-3 px-4 text-left">Event Type</th>
                <th className="py-3 px-4 text-left">Active Focus Window</th>
                <th className="py-3 px-4 text-left">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs font-mono">
              {filtered.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                  <td className="py-3 px-4 text-slate-500">
                    {new Date(item.occurred_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                  </td>
                  <td className="py-3 px-4 font-sans">
                    <div className="font-semibold text-slate-900 dark:text-slate-100">{item.employee_name}</div>
                    <div className="text-[11px] text-slate-400 font-mono">{item.device_name} • {item.os_type}</div>
                  </td>
                  <td className="py-3 px-4">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300">
                      {item.event_type}
                    </span>
                  </td>
                  <td className="py-3 px-4 font-sans text-slate-700 dark:text-slate-300 max-w-xs truncate" title={item.active_window}>
                    {item.active_window || '--'}
                  </td>
                  <td className="py-3 px-4 font-bold text-slate-900 dark:text-slate-100">
                    {item.duration_minutes > 0 ? `${item.duration_minutes} min` : 'Instant'}
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

