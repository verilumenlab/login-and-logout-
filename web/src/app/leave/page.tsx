'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarDays, Check, RefreshCw, Search, X } from 'lucide-react';
import { apiClient, LeaveRequest } from '@/lib/api-client';
import { useRole } from '@/components/RoleContext';

type Stage = 'MANAGER' | 'HR';
type Tab = 'REVIEW' | 'ALL';

interface PendingDecision {
  leave: LeaveRequest;
  stage: Stage;
  action: 'APPROVE' | 'REJECT';
}

const STATUS_BADGE: Record<LeaveRequest['status'], string> = {
  PENDING: 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800',
  APPROVED: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800',
  REJECTED: 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800',
  CANCELLED: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700',
};

function pendingStage(leave: LeaveRequest): Stage | null {
  if (leave.status !== 'PENDING') return null;
  if (leave.manager_approval_status === 'PENDING') return 'MANAGER';
  if (leave.hr_approval_status === 'PENDING') return 'HR';
  return null;
}

function formatRange(leave: LeaveRequest): string {
  const fmt = (d: string) =>
    new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  const range = leave.start_date === leave.end_date ? fmt(leave.start_date) : `${fmt(leave.start_date)} – ${fmt(leave.end_date)}`;
  const days = leave.is_half_day ? 'Half day' : `${leave.total_days} day${leave.total_days === 1 ? '' : 's'}`;
  return `${range} • ${days}`;
}

export default function LeaveApprovalsPage() {
  const { role } = useRole();
  const [leaves, setLeaves] = useState<LeaveRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('REVIEW');
  const [search, setSearch] = useState('');
  const [decision, setDecision] = useState<PendingDecision | null>(null);
  const [comments, setComments] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setLeaves(await apiClient.listTeamLeaves());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load leave requests');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const canAct = useCallback(
    (stage: Stage) => {
      if (role === 'ADMIN') return true;
      // Manager has the same leave authority as HR (manager step + final HR step).
      return role === 'HR' || role === 'MANAGER';
    },
    [role]
  );

  const reviewQueue = useMemo(
    () =>
      leaves.filter((l) => {
        const stage = pendingStage(l);
        return stage !== null && canAct(stage);
      }),
    [leaves, canAct]
  );

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const source = tab === 'REVIEW' ? reviewQueue : leaves;
    return source.filter(
      (l) =>
        !q ||
        (l.employee_name ?? '').toLowerCase().includes(q) ||
        (l.employee_code ?? '').toLowerCase().includes(q) ||
        (l.leave_type_name ?? '').toLowerCase().includes(q)
    );
  }, [tab, reviewQueue, leaves, search]);

  const openDecision = (leave: LeaveRequest, stage: Stage, action: 'APPROVE' | 'REJECT') => {
    setDecision({ leave, stage, action });
    setComments('');
    setNotice(null);
  };

  const submitDecision = async () => {
    if (!decision) return;
    const note = comments.trim();
    if (decision.action === 'REJECT' && !note) return;
    setSaving(true);
    try {
      const { leave, stage, action } = decision;
      const updated =
        stage === 'MANAGER'
          ? await apiClient.reviewManagerLeave(leave.id, action, note || undefined)
          : await apiClient.reviewHrLeave(leave.id, action, note || undefined);
      setLeaves((prev) => prev.map((l) => (l.id === updated.id ? { ...l, ...updated } : l)));
      setNotice(
        `${leave.employee_name ?? 'Request'}: ${action === 'REJECT' ? 'rejected' : stage === 'HR' ? 'approved (final)' : 'approved, sent for HR approval'}.`
      );
      setDecision(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the decision');
    } finally {
      setSaving(false);
    }
  };

  const stageLabel = (stage: Stage) => (stage === 'MANAGER' ? 'Waiting for manager' : 'Waiting for HR final approval');

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <CalendarDays className="w-5 h-5 text-blue-600" /> Leave
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Employees apply from the desktop app. Manager and HR share the same org-wide leave queue (manager step, then final approval).
          </p>
        </div>
        <button
          onClick={load}
          className="self-start sm:self-auto p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300"
          aria-label="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800">
        {(
          [
            { id: 'REVIEW', label: 'To review', count: reviewQueue.length },
            { id: 'ALL', label: 'All requests', count: leaves.length },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-2 text-xs font-semibold border-b-2 -mb-px ${
              tab === t.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            {t.label}
            <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-[10px]">{t.count}</span>
          </button>
        ))}
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

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden">
        <div className="p-3 border-b border-slate-200 dark:border-slate-800">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, code or leave type"
              className="w-full pl-9 pr-3 py-2 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
          </div>
        </div>

        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {loading && leaves.length === 0 && <li className="px-4 py-10 text-center text-xs text-slate-400">Loading…</li>}
          {!loading && visible.length === 0 && (
            <li className="px-4 py-10 text-center text-xs text-slate-400">
              {tab === 'REVIEW' ? 'Nothing is waiting for you.' : 'No leave requests yet.'}
            </li>
          )}
          {visible.map((leave) => {
            const stage = pendingStage(leave);
            const isOpen = decision?.leave.id === leave.id;
            return (
              <li key={leave.id} className="px-4 py-4">
                <div className="flex flex-col md:flex-row md:items-start gap-3 justify-between">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-sm text-slate-900 dark:text-slate-100">{leave.employee_name ?? 'Employee'}</span>
                      <span className="text-[10px] font-mono text-slate-500">
                        {leave.employee_code}
                        {leave.department_name ? ` • ${leave.department_name}` : ''}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${STATUS_BADGE[leave.status]}`}>
                        {stage ? stageLabel(stage) : leave.status.charAt(0) + leave.status.slice(1).toLowerCase()}
                      </span>
                    </div>
                    <div className="text-xs text-slate-700 dark:text-slate-300">
                      <span className="font-semibold">{leave.leave_type_name ?? 'Leave'}</span> — {formatRange(leave)}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400 break-words">“{leave.reason}”</p>
                    {(leave.approvals ?? [])
                      .filter((a) => a.decided_at)
                      .map((a) => (
                        <p key={a.id} className="text-[10px] text-slate-500">
                          {a.stage === 'HR' ? 'HR' : 'Manager'} {a.status.toLowerCase()}
                          {a.approver_name ? ` by ${a.approver_name}` : ''}
                          {a.comments ? ` — ${a.comments}` : ''}
                        </p>
                      ))}
                  </div>
                  {stage && canAct(stage) && !isOpen && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => openDecision(leave, stage, 'REJECT')}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-rose-200 dark:border-rose-800 text-rose-600 text-xs font-semibold hover:bg-rose-50 dark:hover:bg-rose-950/40"
                      >
                        <X className="w-3.5 h-3.5" /> Reject
                      </button>
                      <button
                        onClick={() => openDecision(leave, stage, 'APPROVE')}
                        className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold"
                      >
                        <Check className="w-3.5 h-3.5" /> {stage === 'HR' ? 'Final approve' : 'Approve'}
                      </button>
                    </div>
                  )}
                </div>

                {isOpen && decision && (
                  <div className="mt-3 p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 space-y-2">
                    <label className="block text-xs font-semibold">
                      {decision.action === 'REJECT' ? 'Reason for rejection (required)' : 'Comment (optional)'}
                    </label>
                    <textarea
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                      rows={2}
                      maxLength={500}
                      autoFocus
                      className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setDecision(null)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={submitDecision}
                        disabled={saving || (decision.action === 'REJECT' && !comments.trim())}
                        className={`px-3 py-1.5 rounded-lg text-white text-xs font-semibold disabled:opacity-50 ${
                          decision.action === 'REJECT' ? 'bg-rose-600 hover:bg-rose-700' : 'bg-emerald-600 hover:bg-emerald-700'
                        }`}
                      >
                        {saving ? 'Saving…' : decision.action === 'REJECT' ? 'Reject request' : 'Confirm approval'}
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
