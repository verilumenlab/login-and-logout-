'use client';

import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  FileSpreadsheet,
  Globe,
  Mail,
  Play,
  RefreshCw,
  RotateCcw,
  Settings,
  XCircle,
} from 'lucide-react';
import { apiClient, ReportJob, ReportSchedule } from '@/lib/api-client';

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<ReportSchedule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [editingSchedule, setEditingSchedule] = useState<ReportSchedule | null>(null);

  const fetchSchedules = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listSchedules().catch(() => []);
      setSchedules(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSchedules();
  }, []);

  const handleManualRun = async (sched: ReportSchedule) => {
    setActionLoading(sched.id);
    setNotice(null);
    try {
      const job = await apiClient.manualRunSchedule(sched.id, true);
      setNotice({
        type: 'success',
        message: `Successfully executed ${sched.schedule_type} report job (Status: ${job.status}). Workbooks generated and email notifications queued.`,
      });
      await fetchSchedules();
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err.message || 'Failed to trigger schedule run',
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleCheckMissed = async () => {
    setActionLoading('check-missed');
    setNotice(null);
    try {
      const res = await apiClient.checkMissedSchedules();
      setNotice({
        type: 'success',
        message: `Recovery check complete: Checked ${res.schedules_checked} schedules across system restarts.`,
      });
      await fetchSchedules();
    } catch (err: any) {
      setNotice({
        type: 'error',
        message: err.message || 'Failed to check missed runs',
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleActive = async (sched: ReportSchedule) => {
    try {
      await apiClient.updateSchedule(sched.id, { is_active: !sched.is_active });
      await fetchSchedules();
    } catch (err: any) {
      alert(`Error updating schedule: ${err.message}`);
    }
  };

  const handleSaveSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingSchedule) return;

    try {
      await apiClient.updateSchedule(editingSchedule.id, {
        cron_expression: editingSchedule.cron_expression,
        timezone: editingSchedule.timezone,
        is_active: editingSchedule.is_active,
        send_email: editingSchedule.send_email,
        include_individual_reports: editingSchedule.include_individual_reports,
        include_manager_reports: editingSchedule.include_manager_reports,
        include_consolidated_report: editingSchedule.include_consolidated_report,
      });
      setEditingSchedule(null);
      await fetchSchedules();
    } catch (err: any) {
      alert(`Error saving schedule: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Clock className="w-6 h-6 text-blue-600" />
            Automated Report Scheduling (Celery Beat Engine)
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure recurrent automated generation of Daily, Weekly, and Monthly attendance workbooks with timezone-aware email dispatch
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleCheckMissed}
            disabled={!!actionLoading}
            className="flex items-center gap-2 px-4 py-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 rounded-xl text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition"
          >
            <RotateCcw className={`w-4 h-4 ${actionLoading === 'check-missed' ? 'animate-spin text-blue-600' : ''}`} />
            Recover Missed Runs
          </button>
          <button
            onClick={fetchSchedules}
            disabled={loading}
            className="p-2 border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Notifications Alert */}
      {notice && (
        <div
          className={`p-4 rounded-xl flex items-center justify-between border ${
            notice.type === 'success'
              ? 'bg-emerald-50 text-emerald-900 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800'
              : 'bg-rose-50 text-rose-900 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800'
          }`}
        >
          <div className="flex items-center gap-2 text-sm font-medium">
            {notice.type === 'success' ? <CheckCircle2 className="w-5 h-5 text-emerald-600" /> : <AlertCircle className="w-5 h-5 text-rose-600" />}
            {notice.message}
          </div>
          <button onClick={() => setNotice(null)} className="text-xs underline hover:opacity-80">
            Dismiss
          </button>
        </div>
      )}

      {/* Schedule Pipeline Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {schedules.map((sched) => (
          <div
            key={sched.id}
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs flex flex-col justify-between"
          >
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                  {sched.schedule_type} SCHEDULE
                </span>
                <button
                  onClick={() => handleToggleActive(sched)}
                  className={`text-xs font-semibold px-2.5 py-1 rounded-full border transition ${
                    sched.is_active
                      ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-800'
                      : 'bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400'
                  }`}
                >
                  {sched.is_active ? 'Active' : 'Paused'}
                </button>
              </div>

              <div>
                <h3 className="font-bold text-lg text-slate-900 dark:text-slate-100">
                  {sched.schedule_type === 'DAILY' && 'Previous Day Attendance'}
                  {sched.schedule_type === 'WEEKLY' && 'Previous Week Summary'}
                  {sched.schedule_type === 'MONTHLY' && 'Monthly Executive Audit'}
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {sched.schedule_type === 'DAILY' && 'Generates individual employee, manager team, and HR consolidated workbooks'}
                  {sched.schedule_type === 'WEEKLY' && 'Computes working hours, absences, late arrivals, and leave summaries'}
                  {sched.schedule_type === 'MONTHLY' && 'Full organizational compliance, department hours, and leave utilization audits'}
                </p>
              </div>

              <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between text-slate-600 dark:text-slate-300">
                  <span className="flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5 text-blue-600" /> Cron Schedule</span>
                  <span className="font-mono font-semibold">{sched.cron_expression}</span>
                </div>
                <div className="flex items-center justify-between text-slate-600 dark:text-slate-300">
                  <span className="flex items-center gap-1.5"><Globe className="w-3.5 h-3.5 text-blue-600" /> Timezone</span>
                  <span className="font-semibold">{sched.timezone}</span>
                </div>
                <div className="flex items-center justify-between text-slate-600 dark:text-slate-300">
                  <span className="flex items-center gap-1.5"><Mail className="w-3.5 h-3.5 text-blue-600" /> Email Dispatch</span>
                  <span className="font-semibold">{sched.send_email ? 'Enabled' : 'Disabled'}</span>
                </div>
                <div className="flex items-center justify-between text-slate-600 dark:text-slate-300">
                  <span>Last Run</span>
                  <span>{sched.last_run_at ? new Date(sched.last_run_at).toLocaleString() : 'Never'}</span>
                </div>
                <div className="flex items-center justify-between text-slate-600 dark:text-slate-300">
                  <span>Status</span>
                  <span className={`font-semibold ${sched.last_status === 'SUCCESS' ? 'text-emerald-600' : 'text-slate-500'}`}>
                    {sched.last_status || 'Pending Run'}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-3">
              <button
                onClick={() => setEditingSchedule(sched)}
                className="p-2 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
                title="Configure Schedule"
              >
                <Settings className="w-4 h-4" />
              </button>

              <button
                onClick={() => handleManualRun(sched)}
                disabled={actionLoading === sched.id}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white rounded-lg text-xs font-semibold transition"
              >
                <Play className={`w-3.5 h-3.5 ${actionLoading === sched.id ? 'animate-spin' : ''}`} />
                {actionLoading === sched.id ? 'Executing...' : 'Run Now / Rerun'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Execution History Section */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 mb-4 flex items-center gap-2">
          <FileSpreadsheet className="w-5 h-5 text-blue-600" />
          Recent Scheduled Execution Jobs
        </h2>

        {schedules.flatMap((s) => s.recent_jobs || []).length === 0 ? (
          <div className="text-center py-10 text-slate-400 text-sm">
            No report jobs executed yet. Click &quot;Run Now&quot; above to trigger an immediate scheduled cycle.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-800/50 text-xs font-semibold text-slate-500 uppercase">
                <tr>
                  <th className="px-4 py-3">Report Type</th>
                  <th className="px-4 py-3">Target Period</th>
                  <th className="px-4 py-3">Executed At</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Generated Workbooks</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {schedules
                  .flatMap((s) => s.recent_jobs || [])
                  .slice(0, 10)
                  .map((job) => (
                    <tr key={job.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/30">
                      <td className="px-4 py-3 font-semibold text-slate-900 dark:text-slate-100">
                        {job.report_type}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-blue-600 dark:text-blue-400">
                        {job.parameters_json?.period_key || 'Standard Range'}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {job.completed_at ? new Date(job.completed_at).toLocaleString() : new Date(job.created_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                            job.status === 'COMPLETED'
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400'
                              : 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-400'
                          }`}
                        >
                          {job.status === 'COMPLETED' ? <CheckCircle2 className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          {(job.files || []).map((file) => (
                            <a
                              key={file.id}
                              href={`http://localhost:8000/api/v1/reports/${file.id}/download`}
                              className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 dark:bg-slate-800 hover:bg-blue-50 hover:text-blue-600 rounded text-xs transition"
                              title={file.file_name}
                            >
                              <Download className="w-3 h-3" />
                              {file.file_name.length > 25 ? `${file.file_name.slice(0, 22)}...` : file.file_name}
                            </a>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Configuration Modal */}
      {editingSchedule && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl border border-slate-200 dark:border-slate-800">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Configure {editingSchedule.schedule_type} Schedule
            </h3>

            <form onSubmit={handleSaveSchedule} className="space-y-4 text-sm">
              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
                  Cron Expression
                </label>
                <input
                  type="text"
                  value={editingSchedule.cron_expression}
                  onChange={(e) => setEditingSchedule({ ...editingSchedule, cron_expression: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg bg-slate-50 dark:bg-slate-800 font-mono text-xs"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 dark:text-slate-300 mb-1">
                  Organization Timezone
                </label>
                <select
                  value={editingSchedule.timezone}
                  onChange={(e) => setEditingSchedule({ ...editingSchedule, timezone: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg bg-slate-50 dark:bg-slate-800 text-xs"
                >
                  <option value="UTC">UTC (Universal Coordinated Time)</option>
                  <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                  <option value="America/New_York">America/New_York (EST/EDT)</option>
                  <option value="America/Los_Angeles">America/Los_Angeles (PST/PDT)</option>
                  <option value="Europe/London">Europe/London (GMT/BST)</option>
                </select>
              </div>

              <div className="space-y-2 pt-2">
                <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={editingSchedule.send_email}
                    onChange={(e) => setEditingSchedule({ ...editingSchedule, send_email: e.target.checked })}
                    className="rounded text-blue-600"
                  />
                  Send Automated Email Notifications with Excel Attachments
                </label>

                <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={editingSchedule.include_individual_reports}
                    onChange={(e) => setEditingSchedule({ ...editingSchedule, include_individual_reports: e.target.checked })}
                    className="rounded text-blue-600"
                  />
                  Generate Individual Employee Workbooks
                </label>

                <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={editingSchedule.is_active}
                    onChange={(e) => setEditingSchedule({ ...editingSchedule, is_active: e.target.checked })}
                    className="rounded text-blue-600"
                  />
                  Enable / Active Schedule
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setEditingSchedule(null)}
                  className="px-4 py-2 border rounded-lg text-xs font-medium text-slate-600 dark:text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold"
                >
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

