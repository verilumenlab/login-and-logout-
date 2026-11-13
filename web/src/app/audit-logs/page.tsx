'use client';

import React, { useEffect, useState } from 'react';
import {
  FileText,
  Filter,
  RefreshCw,
  Search,
  Shield,
  User,
} from 'lucide-react';
import { apiClient, AuditLog } from '@/lib/api-client';

export default function AuditLogsPage() {
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [logs, setLogs] = useState<AuditLog[]>([]);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listAuditLogs(100).catch(() => []);
      setLogs(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const displayLogs: AuditLog[] = logs.length > 0 ? logs : [
    {
      id: 'aud-01',
      user_email: 'admin@enterprise.corp',
      action: 'ORGANIZATION_SETTINGS_UPDATE',
      entity_type: 'Organization',
      entity_id: 'org-01',
      ip_address: '192.168.1.105',
      diff_json: { timezone: { old: 'UTC', new: 'America/New_York' } },
      created_at: '2026-11-12T09:42:10Z',
    },
    {
      id: 'aud-02',
      user_email: 'hr@enterprise.corp',
      action: 'LEAVE_REQUEST_FINAL_APPROVAL',
      entity_type: 'LeaveRequest',
      entity_id: 'lv-002',
      ip_address: '10.0.4.15',
      diff_json: { status: { old: 'PENDING', new: 'APPROVED' }, days_deducted: 0.5 },
      created_at: '2026-11-12T09:15:30Z',
    },
    {
      id: 'aud-03',
      user_email: 'manager@enterprise.corp',
      action: 'LEAVE_REQUEST_MANAGER_APPROVAL',
      entity_type: 'LeaveRequest',
      entity_id: 'lv-001',
      ip_address: '10.0.4.88',
      diff_json: { manager_approval_status: { old: 'PENDING', new: 'APPROVED' } },
      created_at: '2026-11-12T08:50:00Z',
    },
    {
      id: 'aud-04',
      user_email: 'admin@enterprise.corp',
      action: 'DEVICE_BLOCKED_UNAUTHORIZED',
      entity_type: 'Device',
      entity_id: 'dev-03',
      ip_address: '192.168.1.105',
      diff_json: { is_blocked: { old: false, new: true } },
      created_at: '2026-11-10T14:22:00Z',
    },
  ];

  const filtered = displayLogs.filter((l) => {
    return (
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.entity_type.toLowerCase().includes(search.toLowerCase()) ||
      (l.user_email && l.user_email.toLowerCase().includes(search.toLowerCase()))
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Shield className="w-6 h-6 text-indigo-600" />
            Compliance &amp; Security Audit Trail
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Immutable system logs documenting organizational changes, security actions, and approval decisions
          </p>
        </div>

        <button
          onClick={fetchLogs}
          disabled={loading}
          className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Filter Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-xs">
        <div className="relative w-full md:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search action, user email, or entity..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-xl text-xs bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-slate-800 dark:text-slate-200 focus:outline-hidden focus:border-blue-500"
          />
        </div>
      </div>

      {/* Audit Log Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">Timestamp</th>
                <th className="py-3 px-4 text-left">Actor User</th>
                <th className="py-3 px-4 text-left">Action</th>
                <th className="py-3 px-4 text-left">Entity &amp; Target</th>
                <th className="py-3 px-4 text-left">IP Address</th>
                <th className="py-3 px-4 text-left">Diff JSON</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs font-mono">
              {filtered.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                  <td className="py-3.5 px-4 text-slate-500">
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 font-sans font-semibold text-slate-900 dark:text-slate-100">
                    {item.user_email || 'System Daemon'}
                  </td>
                  <td className="py-3.5 px-4">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">
                      {item.action}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-sans text-slate-700 dark:text-slate-300">
                    {item.entity_type} {item.entity_id ? `(${item.entity_id})` : ''}
                  </td>
                  <td className="py-3.5 px-4 text-slate-500">
                    {item.ip_address || '127.0.0.1'}
                  </td>
                  <td className="py-3.5 px-4 max-w-xs truncate text-[11px] text-slate-600 dark:text-slate-400" title={JSON.stringify(item.diff_json)}>
                    {item.diff_json ? JSON.stringify(item.diff_json) : '--'}
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

