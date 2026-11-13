import React, { useState } from 'react';
import {
  Calendar,
  CheckCircle2,
  Clock,
  XCircle,
  Plus,
  Trash2,
} from 'lucide-react';
import { LeaveRequest, LeaveStatus, ScreenId } from '../types';
import { cancelLeaveRequest } from '../api/backend';

interface LeaveHistoryScreenProps {
  leaveRequests: LeaveRequest[];
  onNavigate: (screen: ScreenId) => void;
  onRefresh: () => void;
}

export const LeaveHistoryScreen: React.FC<LeaveHistoryScreenProps> = ({
  leaveRequests,
  onNavigate,
  onRefresh,
}) => {
  const [filter, setFilter] = useState<'ALL' | LeaveStatus>('ALL');
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const filteredRequests = leaveRequests.filter((r) =>
    filter === 'ALL' ? true : r.status === filter
  );

  const handleCancel = async (id: string) => {
    if (!confirm('Are you sure you want to cancel this pending leave application?')) return;
    try {
      setActionLoading(id);
      await cancelLeaveRequest(id);
      onRefresh();
    } catch (e) {
      console.error('Failed to cancel leave request:', e);
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: LeaveStatus) => {
    switch (status) {
      case 'APPROVED':
        return (
          <span className="badge badge-success flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
            Approved
          </span>
        );
      case 'PENDING':
        return (
          <span className="badge badge-warning flex items-center gap-1">
            <Clock className="w-3 h-3 text-amber-600" />
            Pending Review
          </span>
        );
      case 'REJECTED':
        return (
          <span className="badge badge-danger flex items-center gap-1">
            <XCircle className="w-3 h-3 text-red-600" />
            Rejected
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="badge badge-neutral flex items-center gap-1 text-slate-500">
            Cancelled
          </span>
        );
    }
  };

  return (
    <div className="screen-container">
      {/* Header */}
      <div className="screen-header flex items-center justify-between">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <Calendar className="w-5 h-5 text-indigo-600" />
            Leave History
          </h2>
          <p className="screen-subtitle">Track, filter, and review submitted absence requests</p>
        </div>
        <button
          onClick={() => onNavigate('leave_apply')}
          className="btn btn-primary text-xs py-1.5 px-3 flex items-center gap-1 shadow-sm"
        >
          <Plus className="w-3.5 h-3.5" />
          Apply Leave
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-1.5 p-1 bg-slate-100 rounded-lg text-xs">
        {(['ALL', 'PENDING', 'APPROVED', 'REJECTED'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setFilter(tab)}
            className={`flex-1 py-1 rounded font-medium transition-colors ${
              filter === tab
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            {tab === 'ALL' ? 'All' : tab.charAt(0) + tab.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Request List */}
      <div className="space-y-2">
        {filteredRequests.length === 0 ? (
          <div className="card text-center py-8">
            <Calendar className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <h4 className="text-xs font-semibold text-slate-700">No leave records found</h4>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {filter === 'ALL'
                ? 'You have not submitted any leave requests yet.'
                : `No leave applications with status "${filter}".`}
            </p>
          </div>
        ) : (
          filteredRequests.map((req) => (
            <div key={req.id} className="card p-3 space-y-2">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-xs text-slate-900">{req.leave_type}</div>
                  <div className="text-[11px] text-slate-500 font-mono mt-0.5">
                    {req.start_date === req.end_date
                      ? req.start_date
                      : `${req.start_date} → ${req.end_date}`}{' '}
                    • <strong>{req.total_days} {req.total_days === 1 ? 'day' : 'days'}</strong>
                    {req.is_half_day && ' (Half Day)'}
                  </div>
                </div>
                {getStatusBadge(req.status)}
              </div>

              {/* Reason */}
              <div className="p-2 bg-slate-50 rounded text-xs text-slate-600 border border-slate-100 italic">
                &ldquo;{req.reason}&rdquo;
              </div>

              {/* Reviewer Note */}
              {req.reviewer_notes && (
                <div className="text-[11px] text-slate-500 flex items-center gap-1">
                  <span className="font-semibold text-slate-700">Approver:</span>
                  <span>{req.reviewer_notes}</span>
                </div>
              )}

              {/* Footer Row */}
              <div className="flex items-center justify-between pt-1 border-t border-slate-100 text-[10px] text-slate-400">
                <span>Applied: {new Date(req.applied_at).toLocaleDateString()}</span>

                {req.status === 'PENDING' && (
                  <button
                    onClick={() => handleCancel(req.id)}
                    disabled={actionLoading === req.id}
                    className="text-red-600 hover:text-red-700 font-medium flex items-center gap-1 disabled:opacity-50"
                  >
                    <Trash2 className="w-3 h-3" />
                    Cancel Application
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
