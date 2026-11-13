'use client';

import React, { useState } from 'react';

interface LeaveRequestItem {
  id: string;
  employee_name: string;
  employee_code: string;
  department_name: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  total_days: number;
  is_half_day: boolean;
  half_day_period?: string;
  reason: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
  manager_approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  hr_approval_status: 'PENDING' | 'APPROVED' | 'REJECTED';
  applied_at: string;
  document_url?: string;
}

export default function LeaveDashboardPage() {
  const [activeTab, setActiveTab] = useState<'MANAGER' | 'HR' | 'ALL'>('MANAGER');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ id: string; msg: string; type: 'success' | 'error' } | null>(null);

  // Sample production-aligned mock state matching Phase 09 backend contracts
  const [requests, setRequests] = useState<LeaveRequestItem[]>([
    {
      id: 'lv-001',
      employee_name: 'Edward Employee',
      employee_code: 'EMP-7842',
      department_name: 'Engineering',
      leave_type: 'Annual Leave',
      start_date: '2026-11-16',
      end_date: '2026-11-18',
      total_days: 3,
      is_half_day: false,
      reason: 'Family vacation and personal downtime',
      status: 'PENDING',
      manager_approval_status: 'PENDING',
      hr_approval_status: 'PENDING',
      applied_at: '2026-11-12T08:30:00Z',
    },
    {
      id: 'lv-002',
      employee_name: 'Sarah Connor',
      employee_code: 'EMP-9021',
      department_name: 'Operations',
      leave_type: 'Sick Leave',
      start_date: '2026-11-14',
      end_date: '2026-11-14',
      total_days: 0.5,
      is_half_day: true,
      half_day_period: 'FIRST_HALF',
      reason: 'Specialist medical checkup appointment',
      status: 'PENDING',
      manager_approval_status: 'APPROVED',
      hr_approval_status: 'PENDING',
      applied_at: '2026-11-11T14:15:00Z',
      document_url: 'https://docs.corp/cert_sarah.pdf',
    },
    {
      id: 'lv-003',
      employee_name: 'David Miller',
      employee_code: 'EMP-4310',
      department_name: 'Engineering',
      leave_type: 'Additional Leave (Unpaid)',
      start_date: '2026-11-23',
      end_date: '2026-11-25',
      total_days: 3,
      is_half_day: false,
      reason: 'Relocation assistance and moving',
      status: 'APPROVED',
      manager_approval_status: 'APPROVED',
      hr_approval_status: 'APPROVED',
      applied_at: '2026-11-08T10:00:00Z',
    },
  ]);

  const handleManagerReview = (id: string, action: 'APPROVE' | 'REJECT') => {
    setActionLoading(id);
    setTimeout(() => {
      setRequests((prev) =>
        prev.map((r) => {
          if (r.id !== id) return r;
          if (action === 'REJECT') {
            return {
              ...r,
              manager_approval_status: 'REJECTED',
              status: 'REJECTED',
            };
          }
          return {
            ...r,
            manager_approval_status: 'APPROVED',
            // status remains PENDING awaiting HR
          };
        })
      );
      setActionLoading(null);
      setFeedback({
        id,
        msg: action === 'APPROVE' ? 'Manager approval recorded. Forwarded to HR for final sign-off.' : 'Request rejected and closed.',
        type: 'success',
      });
    }, 400);
  };

  const handleHrReview = (id: string, action: 'APPROVE' | 'REJECT') => {
    setActionLoading(id);
    setTimeout(() => {
      setRequests((prev) =>
        prev.map((r) => {
          if (r.id !== id) return r;
          if (action === 'REJECT') {
            return {
              ...r,
              hr_approval_status: 'REJECTED',
              status: 'REJECTED',
            };
          }
          return {
            ...r,
            hr_approval_status: 'APPROVED',
            status: 'APPROVED', // Final approval!
          };
        })
      );
      setActionLoading(null);
      setFeedback({
        id,
        msg: action === 'APPROVE' ? 'Final approval granted! Attendance calendar updated.' : 'Request rejected by HR.',
        type: 'success',
      });
    }, 400);
  };

  // Filtering
  const filteredRequests = requests.filter((r) => {
    if (activeTab === 'MANAGER') {
      return r.status === 'PENDING' && r.manager_approval_status === 'PENDING';
    }
    if (activeTab === 'HR') {
      return r.status === 'PENDING' && r.manager_approval_status === 'APPROVED' && r.hr_approval_status === 'PENDING';
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Leave Approvals & Multi-Tier Workflow</h1>
          <p className="text-sm text-slate-500 mt-1">
            Tier 1: Designated Manager Review → Tier 2: HR Final Sign-off → Auto-Attendance Sync
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">
            Phase 09: Leave Engine
          </span>
        </div>
      </div>

      {/* Workflow Rule Alert */}
      <div className="bg-indigo-50 border-l-4 border-indigo-500 p-4 rounded-r-lg">
        <div className="flex">
          <div className="ml-1">
            <h3 className="text-sm font-semibold text-indigo-800">Sequential Hierarchy Enforced</h3>
            <div className="mt-1 text-xs text-indigo-700 space-y-1">
              <p>• <strong>Manager Approval</strong> is mandatory before HR can inspect or review.</p>
              <p>• <strong>Rejection</strong> at either Manager or HR level immediately closes the request and restores pending balance days.</p>
              <p>• <strong>Self-approval</strong> is strictly blocked across all management tiers.</p>
              <p>• <strong>Final Approval</strong> by HR automatically updates employee attendance records (status: ON_LEAVE or HALF_DAY).</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab('MANAGER')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition flex items-center gap-2 ${
              activeTab === 'MANAGER'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            Manager Inbox (Tier 1)
            <span className="bg-amber-100 text-amber-800 text-xs px-2 py-0.5 rounded-full font-bold">
              {requests.filter((r) => r.status === 'PENDING' && r.manager_approval_status === 'PENDING').length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('HR')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition flex items-center gap-2 ${
              activeTab === 'HR'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            HR Final Approval (Tier 2)
            <span className="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded-full font-bold">
              {requests.filter((r) => r.status === 'PENDING' && r.manager_approval_status === 'APPROVED' && r.hr_approval_status === 'PENDING').length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('ALL')}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition ${
              activeTab === 'ALL'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            All Organization Requests ({requests.length})
          </button>
        </nav>
      </div>

      {/* Feedback banner */}
      {feedback && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-xs flex justify-between items-center">
          <span>{feedback.msg}</span>
          <button onClick={() => setFeedback(null)} className="text-emerald-900 font-bold ml-2">×</button>
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase font-medium">
            <tr>
              <th className="py-3 px-4 text-left">Employee</th>
              <th className="py-3 px-4 text-left">Leave Type</th>
              <th className="py-3 px-4 text-left">Duration & Dates</th>
              <th className="py-3 px-4 text-left">Reason & Document</th>
              <th className="py-3 px-4 text-left">Workflow State</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {filteredRequests.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-400 text-xs">
                  No requests pending review in this queue.
                </td>
              </tr>
            ) : (
              filteredRequests.map((req) => (
                <tr key={req.id} className="hover:bg-slate-50/70 transition">
                  {/* Employee */}
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-900">{req.employee_name}</div>
                    <div className="text-xs text-slate-500 font-mono">{req.employee_code} • {req.department_name}</div>
                  </td>

                  {/* Type */}
                  <td className="py-3 px-4">
                    <span className="font-medium text-slate-800">{req.leave_type}</span>
                    {req.is_half_day && (
                      <span className="block text-xs text-indigo-600 font-medium">
                        Half Day ({req.half_day_period === 'FIRST_HALF' ? 'Morning' : 'Afternoon'})
                      </span>
                    )}
                  </td>

                  {/* Dates */}
                  <td className="py-3 px-4 font-mono text-xs text-slate-600">
                    <div>{req.start_date} → {req.end_date}</div>
                    <div className="font-bold text-slate-800 mt-0.5">
                      {req.total_days} {req.total_days === 1 ? 'day' : 'days'}
                    </div>
                  </td>

                  {/* Reason */}
                  <td className="py-3 px-4 max-w-xs">
                    <p className="text-xs text-slate-700 italic truncate" title={req.reason}>
                      &ldquo;{req.reason}&rdquo;
                    </p>
                    {req.document_url && (
                      <a
                        href={req.document_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline mt-1 font-medium"
                      >
                        📄 Attachment
                      </a>
                    )}
                  </td>

                  {/* Workflow State */}
                  <td className="py-3 px-4">
                    <div className="space-y-1 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-medium w-16">Manager:</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          req.manager_approval_status === 'APPROVED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : req.manager_approval_status === 'REJECTED'
                            ? 'bg-rose-100 text-rose-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}>
                          {req.manager_approval_status}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-slate-500 font-medium w-16">HR Final:</span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          req.hr_approval_status === 'APPROVED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : req.hr_approval_status === 'REJECTED'
                            ? 'bg-rose-100 text-rose-800'
                            : req.manager_approval_status === 'APPROVED'
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-slate-100 text-slate-400'
                        }`}>
                          {req.hr_approval_status === 'PENDING' && req.manager_approval_status !== 'APPROVED'
                            ? 'AWAITING MGR'
                            : req.hr_approval_status}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Actions */}
                  <td className="py-3 px-4 text-right whitespace-nowrap">
                    {/* Tier 1 Manager Actions */}
                    {activeTab === 'MANAGER' && req.status === 'PENDING' && req.manager_approval_status === 'PENDING' && (
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleManagerReview(req.id, 'APPROVE')}
                          disabled={actionLoading === req.id}
                          className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded transition disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleManagerReview(req.id, 'REJECT')}
                          disabled={actionLoading === req.id}
                          className="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium rounded transition disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {/* Tier 2 HR Final Actions */}
                    {activeTab === 'HR' && req.status === 'PENDING' && req.manager_approval_status === 'APPROVED' && req.hr_approval_status === 'PENDING' && (
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleHrReview(req.id, 'APPROVE')}
                          disabled={actionLoading === req.id}
                          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded transition disabled:opacity-50"
                        >
                          Final Approval
                        </button>
                        <button
                          onClick={() => handleHrReview(req.id, 'REJECT')}
                          disabled={actionLoading === req.id}
                          className="px-3 py-1 bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium rounded transition disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    )}

                    {/* Final Status Badges for Read-Only / All */}
                    {activeTab === 'ALL' && (
                      <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                        req.status === 'APPROVED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : req.status === 'REJECTED'
                          ? 'bg-rose-100 text-rose-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}>
                        {req.status}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

