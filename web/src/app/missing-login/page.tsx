'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  CheckCircle2,
  Loader2,
  RefreshCw,
  ShieldAlert,
  UserX,
  XCircle,
} from 'lucide-react';
import { apiClient, MissingLoginAlert } from '@/lib/api-client';

const STATUS_STYLE: Record<MissingLoginAlert['status'], string> = {
  PENDING: 'bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300',
  APPROVED: 'bg-blue-100 dark:bg-blue-950 text-blue-800 dark:text-blue-300',
  REJECTED: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300',
  SENT: 'bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300',
};

export default function MissingLoginApprovalPage() {
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<MissingLoginAlert[]>([]);
  const [filter, setFilter] = useState<'PENDING' | 'ALL'>('ALL');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const didAutoScan = React.useRef(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiClient.listMissingLoginAlerts(
        filter === 'PENDING' ? 'PENDING' : undefined,
        150
      );
      setAlerts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load missing-login alerts');
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const handleScan = useCallback(async (silent = false) => {
    setScanning(true);
    if (!silent) {
      setError(null);
      setNotice(null);
    }
    try {
      const result = await apiClient.scanMissingLoginAlerts();
      if (result.status === 'skipped') {
        if (!silent) {
          setNotice(
            result.reason === 'before_missing_login_cutoff'
              ? 'Before 10:30 IST — scan skipped. Try again after the grace cutoff.'
              : `Scan skipped: ${result.reason || 'unknown'}`
          );
        }
      } else {
        const sent = result.sent_count ?? 0;
        const pending = result.queued_count ?? 0;
        setNotice(
          sent > 0
            ? `Sent mail for ${sent} employee(s) not logged in (${result.work_date || 'today'}) — employee, manager, HR, admin.`
            : pending > 0
              ? `Queued ${pending} employee(s); mail pending retry.`
              : `No new missing logins for ${result.work_date || 'today'}.`
        );
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed');
    } finally {
      setScanning(false);
    }
  }, [load]);

  useEffect(() => {
    load();
  }, [load]);

  // After page open, scan once so today's not-logged-in people get mail without waiting for Celery.
  useEffect(() => {
    if (didAutoScan.current) return;
    didAutoScan.current = true;
    void handleScan(true);
  }, [handleScan]);

  const handleApprove = async (item: MissingLoginAlert) => {
    if (
      !confirm(
        `Approve and send “not logged in” mail for ${item.employee_name} (${item.employee_email}) to employee, manager, HR, and admin?`
      )
    ) {
      return;
    }
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiClient.approveMissingLoginAlert(item.id);
      setAlerts((prev) =>
        filter === 'PENDING'
          ? prev.filter((a) => a.id !== updated.id)
          : prev.map((a) => (a.id === updated.id ? updated : a))
      );
      setNotice(
        `Sent ${updated.emails_sent_count} email(s) for ${updated.employee_name} (${updated.employee_email}).`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approve failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (item: MissingLoginAlert) => {
    if (!confirm(`Reject mail for ${item.employee_name}? No email will be sent.`)) return;
    setBusyId(item.id);
    setError(null);
    setNotice(null);
    try {
      const updated = await apiClient.rejectMissingLoginAlert(item.id, 'Rejected by admin');
      setAlerts((prev) =>
        filter === 'PENDING'
          ? prev.filter((a) => a.id !== updated.id)
          : prev.map((a) => (a.id === updated.id ? updated : a))
      );
      setNotice(`Rejected alert for ${updated.employee_name}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reject failed');
    } finally {
      setBusyId(null);
    }
  };

  const handleApproveAll = async () => {
    const pending = alerts.filter((a) => a.status === 'PENDING');
    if (!pending.length) {
      setNotice('No pending alerts to approve.');
      return;
    }
    if (
      !confirm(
        `Approve and send mail for all ${pending.length} pending employee(s)? Each goes to employee, manager, HR, and admin.`
      )
    ) {
      return;
    }
    setBusyId('ALL');
    setError(null);
    setNotice(null);
    try {
      const result = await apiClient.approveAllMissingLoginAlerts();
      setNotice(`Approved ${result.approved_count} alert(s).${result.errors?.length ? ` Errors: ${result.errors.join('; ')}` : ''}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approve-all failed');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <ShieldAlert className="w-6 h-6 text-amber-600" />
            Missing Login
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            After 10:30 IST, anyone still not logged in is emailed automatically — the person, their
            manager, HR, and admin — with name and email. Use Scan &amp; send to run again now.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as 'PENDING' | 'ALL')}
            className="text-xs rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2"
          >
            <option value="ALL">All statuses</option>
            <option value="PENDING">Pending only</option>
          </select>
          <button
            onClick={() => void handleScan(false)}
            disabled={scanning || loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 hover:opacity-90 disabled:opacity-50"
          >
            {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <UserX className="w-3.5 h-3.5" />}
            Scan &amp; send
          </button>
          <button
            onClick={handleApproveAll}
            disabled={busyId === 'ALL' || loading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busyId === 'ALL' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
            Approve all pending
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300"
            aria-label="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs">
          {error}
        </div>
      )}
      {notice && (
        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs">
          {notice}
        </div>
      )}

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">Name</th>
                <th className="py-3 px-4 text-left">Email</th>
                <th className="py-3 px-4 text-left">Code</th>
                <th className="py-3 px-4 text-left">Department</th>
                <th className="py-3 px-4 text-left">Date</th>
                <th className="py-3 px-4 text-left">Status</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-400">
                    <Loader2 className="w-5 h-5 animate-spin inline mr-2" />
                    Loading…
                  </td>
                </tr>
              ) : alerts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-10 text-center text-slate-400">
                    No alerts{filter === 'PENDING' ? ' pending' : ''}. Use Scan &amp; send after 10:30 IST.
                  </td>
                </tr>
              ) : (
                alerts.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40">
                    <td className="py-3 px-4 font-medium text-slate-900 dark:text-slate-100">
                      {item.employee_name}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-600 dark:text-slate-300">
                      {item.employee_email}
                    </td>
                    <td className="py-3 px-4 font-mono">{item.employee_code}</td>
                    <td className="py-3 px-4">{item.department_name || '—'}</td>
                    <td className="py-3 px-4 font-mono">{item.work_date}</td>
                    <td className="py-3 px-4">
                      <span className={`inline-flex px-2 py-0.5 rounded-md text-[10px] font-semibold ${STATUS_STYLE[item.status]}`}>
                        {item.status}
                        {item.status === 'SENT' ? ` · ${item.emails_sent_count} mails` : ''}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right whitespace-nowrap">
                      {item.status === 'PENDING' ? (
                        <>
                          <button
                            onClick={() => handleApprove(item)}
                            disabled={busyId === item.id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 mr-1"
                          >
                            {busyId === item.id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <CheckCircle2 className="w-3 h-3" />
                            )}
                            Approve &amp; send
                          </button>
                          <button
                            onClick={() => handleReject(item)}
                            disabled={busyId === item.id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-medium border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                          >
                            <XCircle className="w-3 h-3" />
                            Reject
                          </button>
                        </>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
