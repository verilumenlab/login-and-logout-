import React, { useState } from 'react';
import {
  Calendar,
  Send,
  Upload,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import { LeaveBalance, ScreenId } from '../types';
import { submitLeaveRequest } from '../api/backend';

interface LeaveApplyScreenProps {
  balances: LeaveBalance[];
  onNavigate: (screen: ScreenId) => void;
  onLeaveSubmitted: () => void;
}

export const LeaveApplyScreen: React.FC<LeaveApplyScreenProps> = ({
  balances,
  onNavigate,
  onLeaveSubmitted,
}) => {
  const [leaveType, setLeaveType] = useState('Annual Leave');
  const [startDate, setStartDate] = useState(
    new Date(Date.now() + 86400000).toISOString().split('T')[0]
  );
  const [endDate, setEndDate] = useState(
    new Date(Date.now() + 86400000 * 2).toISOString().split('T')[0]
  );
  const [isHalfDay, setIsHalfDay] = useState(false);
  const [halfDayPeriod, setHalfDayPeriod] = useState<'FIRST_HALF' | 'SECOND_HALF'>('FIRST_HALF');
  const [reason, setReason] = useState('');
  const [documentName, setDocumentName] = useState<string | undefined>(undefined);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Calculate requested days
  const calculateDays = (): number => {
    if (isHalfDay) return 0.5;
    const start = new Date(startDate);
    const end = new Date(endDate);
    if (isNaN(start.getTime()) || isNaN(end.getTime()) || end < start) return 0;
    const diffTime = Math.abs(end.getTime() - start.getTime());
    return Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
  };

  const requestedDays = calculateDays();
  const selectedBalance = balances.find((b) => b.leave_type === leaveType);
  const availableDays = selectedBalance ? selectedBalance.available : 0;
  const isBalanceExceeded = requestedDays > availableDays;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) {
      setError('Please provide a reason for the leave application.');
      return;
    }
    if (requestedDays <= 0) {
      setError('End date must be on or after start date.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      await submitLeaveRequest({
        leave_type: leaveType,
        start_date: startDate,
        end_date: isHalfDay ? startDate : endDate,
        total_days: requestedDays,
        is_half_day: isHalfDay,
        half_day_period: isHalfDay ? halfDayPeriod : undefined,
        reason: reason.trim(),
        document_name: documentName,
      });
      setSuccess(true);
      onLeaveSubmitted();
      setTimeout(() => {
        onNavigate('leave_history');
      }, 1500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to submit leave request';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSimulateUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setDocumentName(file.name);
    }
  };

  return (
    <div className="screen-container">
      {/* Header */}
      <div className="screen-header">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <Calendar className="w-5 h-5 text-indigo-600" />
            Apply for Leave
          </h2>
          <p className="screen-subtitle">Submit absence requests for manager & HR approval</p>
        </div>
      </div>

      {/* Success Notification */}
      {success && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-xs text-emerald-800">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>Leave application successfully submitted! Redirecting to history...</span>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <div className="alert-error">
          <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span className="text-xs">{error}</span>
        </div>
      )}

      {/* Leave Application Form */}
      <form onSubmit={handleSubmit} className="card space-y-3">
        {/* Leave Type */}
        <div className="form-group">
          <label className="text-xs font-semibold text-slate-700">Leave Category *</label>
          <select
            value={leaveType}
            onChange={(e) => setLeaveType(e.target.value)}
            className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
          >
            {balances.map((b) => (
              <option key={b.leave_type} value={b.leave_type}>
                {b.leave_type} (Available: {b.available} days)
              </option>
            ))}
          </select>
        </div>

        {/* Date Selectors */}
        <div className="grid grid-cols-2 gap-2">
          <div className="form-group">
            <label className="text-xs font-semibold text-slate-700">Start Date *</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg"
              required
            />
          </div>
          <div className="form-group">
            <label className="text-xs font-semibold text-slate-700">End Date *</label>
            <input
              type="date"
              value={isHalfDay ? startDate : endDate}
              onChange={(e) => setEndDate(e.target.value)}
              disabled={isHalfDay}
              className="w-full px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg disabled:bg-slate-100"
              required
            />
          </div>
        </div>

        {/* Half-Day Checkbox */}
        <div className="flex items-center justify-between p-2 bg-slate-50 rounded-lg border border-slate-200">
          <label className="flex items-center gap-2 text-xs text-slate-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isHalfDay}
              onChange={(e) => setIsHalfDay(e.target.checked)}
              className="rounded text-indigo-600"
            />
            <span>Half-Day Request (0.5 day)</span>
          </label>

          {isHalfDay && (
            <select
              value={halfDayPeriod}
              onChange={(e) => setHalfDayPeriod(e.target.value as 'FIRST_HALF' | 'SECOND_HALF')}
              className="text-[11px] px-2 py-1 border border-slate-300 rounded bg-white"
            >
              <option value="FIRST_HALF">First Half (Morning)</option>
              <option value="SECOND_HALF">Second Half (Afternoon)</option>
            </select>
          )}
        </div>

        {/* Balance Validation Card */}
        <div className={`p-2.5 rounded-lg border text-xs flex justify-between items-center ${
          isBalanceExceeded ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-slate-50 border-slate-200 text-slate-700'
        }`}>
          <span>
            Requested: <strong>{requestedDays} day(s)</strong> • Available: <strong>{availableDays} day(s)</strong>
          </span>
          {isBalanceExceeded && (
            <span className="text-[10px] font-semibold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded">
              Balance Exceeded
            </span>
          )}
        </div>

        {/* Reason Field */}
        <div className="form-group">
          <label className="text-xs font-semibold text-slate-700">Reason / Notes *</label>
          <textarea
            rows={3}
            placeholder="Please detail the reason for your absence..."
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full p-2.5 text-xs border border-slate-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
            required
          />
        </div>

        {/* Attachment Upload Simulator */}
        <div className="form-group">
          <label className="text-xs font-semibold text-slate-700">Supporting Document (Optional)</label>
          <div className="mt-1 flex items-center gap-2">
            <label className="btn btn-secondary text-xs px-3 py-1.5 cursor-pointer flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5" />
              <span>Choose File</span>
              <input type="file" onChange={handleSimulateUpload} className="hidden" />
            </label>
            <span className="text-xs text-slate-500 truncate">
              {documentName ? documentName : 'No file chosen (PDF, JPG, PNG)'}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2 pt-2 border-t border-slate-100">
          <button
            type="button"
            onClick={() => onNavigate('leave_history')}
            className="btn btn-secondary flex-1 text-xs py-2"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary flex-1 text-xs py-2 flex items-center justify-center gap-1.5 disabled:opacity-50"
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Submit Application
          </button>
        </div>
      </form>
    </div>
  );
};
