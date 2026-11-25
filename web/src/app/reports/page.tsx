'use client';

import React, { useEffect, useState } from 'react';
import {
  Calendar,
  CheckCircle2,
  Clock,
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  Filter,
  Loader2,
  Mail,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
} from 'lucide-react';
import { useRole } from '@/components/RoleContext';
import { apiClient, ReportJob, WeeklyApprovalDefaults, WeeklyApprovalRecipient } from '@/lib/api-client';

export default function ReportsPage() {
  const { role } = useRole();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reportType, setReportType] = useState('ATTENDANCE_SUMMARY');
  const [reports, setReports] = useState<ReportJob[]>([]);

  // Weekly report approval: Mon-Fri week + HR / manager recipients come from the server.
  const [defaults, setDefaults] = useState<WeeklyApprovalDefaults | null>(null);
  const [defaultsError, setDefaultsError] = useState<string | null>(null);
  const [manualStartDate, setManualStartDate] = useState('');
  const [manualEndDate, setManualEndDate] = useState('');
  const [recipients, setRecipients] = useState<WeeklyApprovalRecipient[]>([]);
  const [newEmail, setNewEmail] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendSuccess, setSendSuccess] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendFailed, setSendFailed] = useState<{ email: string; error: string }[]>([]);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listReports().catch(() => []);
      setReports(data);
    } finally {
      setLoading(false);
    }
  };

  const fetchDefaults = async () => {
    setDefaultsError(null);
    try {
      const d = await apiClient.getWeeklyApprovalDefaults();
      setDefaults(d);
      setManualStartDate(d.start_date);
      setManualEndDate(d.end_date);
      setRecipients(d.recipients);
    } catch (e: any) {
      setDefaultsError(e?.message || 'Could not load the weekly report settings.');
    }
  };

  useEffect(() => {
    fetchReports();
    fetchDefaults();
  }, []);

  const handleGenerateReport = async () => {
    setGenerating(true);
    try {
      await apiClient.generateReport(reportType, { generated_by_role: role });
      await fetchReports();
    } catch (e: any) {
      alert(`Report Generation failed: ${e.message}`);
    } finally {
      setGenerating(false);
    }
  };

  const handlePreviewReport = async () => {
    setPreviewLoading(true);
    setSendSuccess(null);
    setSendError(null);
    try {
      const data = await apiClient.previewReport('WEEKLY', manualStartDate, manualEndDate);
      setPreviewData(data);
    } catch (e: any) {
      setSendError(`Preview failed: ${e.message}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const handleDownload = async (fileId: string, fileName: string) => {
    setDownloadingId(fileId);
    setDownloadError(null);
    try {
      await apiClient.downloadReportFile(fileId, fileName);
    } catch (e: any) {
      setDownloadError(`Download failed: ${e?.message || 'unknown error'}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const toggleRecipient = (email: string) =>
    setRecipients((prev) => prev.map((r) => (r.email === email ? { ...r, selected: !r.selected } : r)));

  const removeRecipient = (email: string) => setRecipients((prev) => prev.filter((r) => r.email !== email));

  const addRecipient = () => {
    const email = newEmail.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setSendError('Enter a valid email address to add.');
      return;
    }
    setSendError(null);
    setRecipients((prev) =>
      prev.some((r) => r.email === email) ? prev : [...prev, { email, role: 'Added by you', selected: true }]
    );
    setNewEmail('');
  };

  const selectedEmails = recipients.filter((r) => r.selected).map((r) => r.email);

  const handleApproveAndSend = async () => {
    setSendSuccess(null);
    setSendError(null);
    setSendFailed([]);
    if (selectedEmails.length === 0) {
      setSendError('Tick at least one recipient before approving.');
      return;
    }
    const ok = window.confirm(
      `Approve and send the weekly report (${manualStartDate} to ${manualEndDate}) to:\n\n${selectedEmails.join('\n')}\n\nThe 9-sheet Excel will be emailed now.`
    );
    if (!ok) return;
    setSendLoading(true);
    try {
      const res = await apiClient.manualSendReport('WEEKLY', manualStartDate, manualEndDate, selectedEmails);
      setSendSuccess(res.message || 'Weekly report approved and sent.');
      setSendFailed(res.failed_recipients || []);
      await Promise.all([fetchReports(), fetchDefaults()]);
    } catch (e: any) {
      setSendError(e?.message || 'Sending failed.');
    } finally {
      setSendLoading(false);
    }
  };

  const displayReports = reports;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-emerald-600" />
            Analytical Reporting &amp; Spreadsheet Exports
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Generate workforce summaries, overtime analysis, leave balance burn-downs, and audit reports
          </p>
        </div>

        <button
          onClick={fetchReports}
          disabled={loading}
          className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-slate-600 dark:text-slate-300 hover:text-blue-600 transition"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Weekly report: approve & send to HR / managers */}
      <div className="bg-gradient-to-br from-indigo-50/50 to-blue-50/50 dark:from-indigo-950/20 dark:to-slate-900 border border-indigo-200/80 dark:border-indigo-900/60 rounded-2xl p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300 mb-1.5">
              <ShieldCheck className="w-3.5 h-3.5" />
              Admin approval
            </div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
              Weekly Report — Approve &amp; Send to HR and Managers
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {defaults?.schedule_note || 'Automatic send: Friday 7:30 PM IST.'} Choose who receives the Excel, then
              approve.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePreviewReport}
              disabled={previewLoading || !manualStartDate}
              className="px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold hover:bg-slate-50 transition flex items-center gap-1.5 shadow-xs disabled:opacity-50"
            >
              {previewLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5 text-indigo-600" />}
              Preview
            </button>
            <button
              onClick={handleApproveAndSend}
              disabled={sendLoading || !manualStartDate || selectedEmails.length === 0}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              {sendLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Approve &amp; Send ({selectedEmails.length})
            </button>
          </div>
        </div>

        {defaultsError && (
          <div className="mb-3 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-xl text-xs text-red-800 dark:text-red-300">
            {defaultsError}
          </div>
        )}

        {/* Status of this week's send */}
        {defaults && (
          <div
            className={`mb-4 p-3 rounded-xl border text-xs flex items-start gap-2 ${
              defaults.last_sent_at
                ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900 text-emerald-800 dark:text-emerald-300'
                : 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300'
            }`}
          >
            {defaults.last_sent_at ? (
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            ) : (
              <Clock className="w-4 h-4 flex-shrink-0" />
            )}
            <span>
              {defaults.last_sent_at
                ? `Week ${defaults.start_date} to ${defaults.end_date} was sent on ${new Date(defaults.last_sent_at).toLocaleString()} to ${defaults.last_sent_recipients.join(', ') || 'recipients'}.`
                : `Week ${defaults.start_date} to ${defaults.end_date} has not been sent yet. Approve below to send it now.`}
            </span>
          </div>
        )}

        {/* Period */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-indigo-100 dark:border-indigo-950">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Week start (Monday)
            </label>
            <input
              type="date"
              value={manualStartDate}
              onChange={(e) => setManualStartDate(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Week end (Friday)
            </label>
            <input
              type="date"
              value={manualEndDate}
              onChange={(e) => setManualEndDate(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
            />
          </div>
        </div>

        {/* Recipients */}
        <div className="mt-4">
          <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-2">
            Send to (tick to approve each address)
          </label>
          <div className="space-y-1.5">
            {recipients.length === 0 && (
              <p className="text-xs text-slate-400">No recipients configured. Add an email below.</p>
            )}
            {recipients.map((r) => (
              <div
                key={r.email}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
              >
                <label className="flex items-center gap-2 text-xs text-slate-900 dark:text-slate-100 cursor-pointer min-w-0">
                  <input
                    type="checkbox"
                    checked={r.selected}
                    onChange={() => toggleRecipient(r.email)}
                    className="rounded border-slate-300"
                  />
                  <Mail className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                  <span className="truncate font-medium">{r.email}</span>
                </label>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300">
                    {r.role}
                  </span>
                  {r.role === 'Added by you' && (
                    <button
                      onClick={() => removeRecipient(r.email)}
                      className="text-[11px] text-slate-400 hover:text-red-600"
                      aria-label={`Remove ${r.email}`}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-2">
            <input
              type="email"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addRecipient();
                }
              }}
              placeholder="Add another email, e.g. manager@company.com"
              className="flex-1 px-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
            />
            <button
              onClick={addRecipient}
              className="px-3 py-1.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-xs font-bold text-slate-700 dark:text-slate-200 hover:bg-slate-50 flex items-center gap-1"
            >
              <Plus className="w-3.5 h-3.5" />
              Add
            </button>
          </div>
        </div>

        {/* Result banners */}
        {sendSuccess && (
          <div className="mt-4 p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 rounded-xl flex items-start gap-2 text-xs text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{sendSuccess}</span>
          </div>
        )}
        {sendFailed.length > 0 && (
          <div className="mt-2 p-3 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 rounded-xl text-xs text-amber-800 dark:text-amber-300">
            {sendFailed.map((f) => (
              <div key={f.email}>
                Could not send to {f.email}: {f.error}
              </div>
            ))}
          </div>
        )}
        {sendError && (
          <div className="mt-4 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-xl text-xs text-red-800 dark:text-red-300">
            {sendError}
          </div>
        )}

        {/* Preview */}
        {previewData && (
          <div className="mt-4 p-4 bg-white dark:bg-slate-800 border border-indigo-100 dark:border-slate-700 rounded-xl space-y-3">
            <div className="flex items-center justify-between text-xs font-bold text-slate-800 dark:text-slate-200">
              <span className="flex items-center gap-1.5">
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                Preview ({previewData.start_date} to {previewData.end_date})
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
              {[
                ['Active Staff', previewData.total_employees, 'text-slate-900 dark:text-slate-100'],
                ['Present', previewData.present_count, 'text-emerald-600'],
                ['Late Arrivals', previewData.late_count, 'text-amber-600'],
                ['Net Work Hours', `${previewData.total_work_hours}h`, 'text-blue-600'],
                ['Daily Average', `${previewData.average_daily_hours}h`, 'text-slate-800 dark:text-slate-200'],
                ['Wi-Fi Verified', `${previewData.wifi_verified_percentage}%`, 'text-emerald-600'],
                ['Break Count', previewData.total_break_count ?? 0, 'text-amber-600'],
                ['Break Hours', `${previewData.total_break_hours ?? 0}h`, 'text-amber-700'],
              ].map(([label, value, color]) => (
                <div
                  key={String(label)}
                  className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center"
                >
                  <div className="text-[10px] text-slate-500 uppercase font-semibold">{label}</div>
                  <div className={`text-base font-bold ${color}`}>{value}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Generator Card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-xs">
        <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 mb-1">
          Generate New Analytics Export
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
          Select target report schema and queue an asynchronous computation worker
        </p>

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <select
            value={reportType}
            onChange={(e) => setReportType(e.target.value)}
            className="w-full sm:w-80 px-3 py-2 text-xs rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
          >
            <option value="ATTENDANCE_SUMMARY">Attendance Summary (Daily Roll-up &amp; Shifts)</option>
            <option value="ACTIVITY_BREAKDOWN">Computer Activity (Active Focus vs. Idle)</option>
            <option value="LEAVE_BALANCES">Leave Entitlements &amp; Accrual Balances</option>
            <option value="AUDIT_TRAIL">Compliance &amp; Security Audit Trail</option>
          </select>

          <button
            onClick={handleGenerateReport}
            disabled={generating}
            className="w-full sm:w-auto px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition flex items-center justify-center gap-2 shadow-sm disabled:opacity-50"
          >
            {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Generate Spreadsheet
          </button>
        </div>
      </div>

      {/* Reports History Table */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-xs">
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 font-bold text-sm text-slate-800 dark:text-slate-200">
          Generated Report Files &amp; Export Archive
        </div>
        {downloadError && (
          <div className="mx-6 mt-3 p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-xl text-xs text-red-800 dark:text-red-300">
            {downloadError}
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-800 text-sm">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 text-xs uppercase font-medium">
              <tr>
                <th className="py-3 px-4 text-left">Report Type</th>
                <th className="py-3 px-4 text-left">Generated File</th>
                <th className="py-3 px-4 text-left">Size</th>
                <th className="py-3 px-4 text-left">Status</th>
                <th className="py-3 px-4 text-left">Generated At</th>
                <th className="py-3 px-4 text-right">Download</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800 text-xs font-mono">
              {displayReports.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center font-sans text-slate-400">
                    No reports generated yet.
                  </td>
                </tr>
              )}
              {displayReports.map((r) => {
                const file = r.files && r.files.length > 0 ? r.files[0] : null;
                return (
                  <tr key={r.id} className="hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition">
                    <td className="py-3.5 px-4 font-sans font-semibold text-slate-900 dark:text-slate-100">
                      {r.report_type.replace('_', ' ')}
                    </td>
                    <td className="py-3.5 px-4 text-blue-600 dark:text-blue-400 font-semibold">
                      {file?.file_name || 'Generating...'}
                    </td>
                    <td className="py-3.5 px-4 text-slate-500">
                      {file ? `${(file.file_size_bytes / 1024).toFixed(1)} KB` : '--'}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300">
                        {r.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-slate-500">
                      {new Date(r.created_at).toLocaleString()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      {file && (
                        <button
                          type="button"
                          disabled={downloadingId === file.id}
                          onClick={() => handleDownload(file.id, file.file_name)}
                          className="inline-flex items-center gap-1 px-3 py-1 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-semibold rounded-lg transition disabled:opacity-60"
                        >
                          {downloadingId === file.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Download className="w-3.5 h-3.5" />
                          )}
                          Download
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

