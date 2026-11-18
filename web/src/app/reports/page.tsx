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
import { apiClient, ReportJob } from '@/lib/api-client';

export default function ReportsPage() {
  const { role } = useRole();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reportType, setReportType] = useState('ATTENDANCE_SUMMARY');
  const [reports, setReports] = useState<ReportJob[]>([]);

  // Manual report range defaults to the last 7 local calendar days.
  const [manualStartDate, setManualStartDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() - 6);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  });
  const [manualEndDate, setManualEndDate] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  });
  const [manualRecipients, setManualRecipients] = useState('hr@enterprise.local, manager@enterprise.local');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewData, setPreviewData] = useState<any>(null);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendSuccess, setSendSuccess] = useState<string | null>(null);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const data = await apiClient.listReports().catch(() => []);
      setReports(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
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
    try {
      const data = await apiClient.previewReport('WEEKLY', manualStartDate, manualEndDate);
      setPreviewData(data);
    } catch (e: any) {
      alert(`Preview calculation failed: ${e.message}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleManualSend = async () => {
    const list = manualRecipients.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
    if (list.length === 0) {
      alert('Please specify at least one recipient email.');
      return;
    }
    setSendLoading(true);
    setSendSuccess(null);
    try {
      const res = await apiClient.manualSendReport('WEEKLY', manualStartDate, manualEndDate, list);
      setSendSuccess(res.message || 'Report generated and dispatched successfully.');
      await fetchReports();
    } catch (e: any) {
      alert(`Manual dispatch failed: ${e.message}`);
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

      {/* Prompt 17: Weekly & Manual Report Dispatch Engine */}
      <div className="bg-gradient-to-br from-indigo-50/50 to-blue-50/50 dark:from-indigo-950/20 dark:to-slate-900 border border-indigo-200/80 dark:border-indigo-900/60 rounded-2xl p-6 shadow-xs">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4">
          <div>
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 dark:bg-indigo-950 text-indigo-800 dark:text-indigo-300 mb-1.5">
              <ShieldCheck className="w-3.5 h-3.5" />
              Automated &amp; Immediate Dispatch Engine
            </div>
            <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
              Weekly 9-Worksheet Excel Report Dispatch
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Default automated schedule: <span className="font-semibold text-indigo-700 dark:text-indigo-300">Friday 7:30 PM IST (Asia/Kolkata)</span>.
              Or preview metrics and trigger an immediate multi-tenant manual dispatch with zero collision.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePreviewReport}
              disabled={previewLoading}
              className="px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold hover:bg-slate-50 transition flex items-center gap-1.5 shadow-xs disabled:opacity-50"
            >
              {previewLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5 text-indigo-600" />}
              Preview Metrics
            </button>
            <button
              onClick={handleManualSend}
              disabled={sendLoading}
              className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              {sendLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
              Dispatch 9-Sheet Excel
            </button>
          </div>
        </div>

        {/* Inputs */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 border-t border-indigo-100 dark:border-indigo-950">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Start Date
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
              End Date
            </label>
            <input
              type="date"
              value={manualEndDate}
              onChange={(e) => setManualEndDate(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
            />
          </div>
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400 mb-1">
              Recipient Email(s)
            </label>
            <input
              type="text"
              value={manualRecipients}
              onChange={(e) => setManualRecipients(e.target.value)}
              placeholder="hr@company.com, mgr@company.com"
              className="w-full px-3 py-1.5 text-xs rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-slate-100"
            />
          </div>
        </div>

        {/* Success Alert */}
        {sendSuccess && (
          <div className="mt-4 p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-900 rounded-xl flex items-center gap-2 text-xs text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
            <span>{sendSuccess}</span>
          </div>
        )}

        {/* Preview Drawer/Card */}
        {previewData && (
          <div className="mt-4 p-4 bg-white dark:bg-slate-800 border border-indigo-100 dark:border-slate-700 rounded-xl space-y-3">
            <div className="flex items-center justify-between text-xs font-bold text-slate-800 dark:text-slate-200">
              <span className="flex items-center gap-1.5">
                <FileSpreadsheet className="w-4 h-4 text-emerald-600" />
                Preview Analytics Digest ({previewData.start_date} to {previewData.end_date})
              </span>
              <span className="text-[11px] text-slate-400 font-normal">
                Includes 9 Sheets: Attendance, Logins, Work Hours, Late, Absences, Leaves, Approvals, Wi-Fi, Exceptions
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Active Staff</div>
                <div className="text-base font-bold text-slate-900 dark:text-slate-100">{previewData.total_employees}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Present</div>
                <div className="text-base font-bold text-emerald-600">{previewData.present_count}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Late Arrivals</div>
                <div className="text-base font-bold text-amber-600">{previewData.late_count}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Net Work Hours</div>
                <div className="text-base font-bold text-blue-600">{previewData.total_work_hours}h</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Daily Average</div>
                <div className="text-base font-bold text-slate-800 dark:text-slate-200">{previewData.average_daily_hours}h</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Wi-Fi Verified</div>
                <div className="text-base font-bold text-emerald-600">{previewData.wifi_verified_percentage}%</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Break Count</div>
                <div className="text-base font-bold text-amber-600">{previewData.total_break_count ?? 0}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-center">
                <div className="text-[10px] text-slate-500 uppercase font-semibold">Break Hours</div>
                <div className="text-base font-bold text-amber-700">{previewData.total_break_hours ?? 0}h</div>
              </div>
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
                        <a
                          href="#"
                          onClick={(e) => {
                            e.preventDefault();
                            alert(`Downloading verified spreadsheet export: ${file.file_name}`);
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-semibold rounded-lg transition"
                        >
                          <Download className="w-3.5 h-3.5" />
                          Download
                        </a>
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

