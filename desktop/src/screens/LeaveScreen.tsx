import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Send, Undo2 } from 'lucide-react';

import { applyForLeave, getLeaveBalances, getLeaveRequests, getLeaveTypes, withdrawLeave } from '../api/backend';
import { LeaveBalance, LeaveRequest, LeaveStatus, LeaveType } from '../types';
import { formatDay, formatDays, toDateInput } from '../utils/format';

const STATUS_BADGE: Record<LeaveStatus, string> = {
  PENDING: 'badge-warning',
  APPROVED: 'badge-success',
  REJECTED: 'badge-danger',
  CANCELLED: 'badge-neutral',
};

/** Preferred order matching current org leave policy. */
const TYPE_ORDER = ['ANNUAL', 'SICK', 'CASUAL'];
const ALLOWED_CODES = new Set(TYPE_ORDER);

const POLICY_QUOTA: Record<string, number> = {
  ANNUAL: 24,
  SICK: 12,
  CASUAL: 12,
};

function available(b: LeaveBalance): number {
  return Math.max(0, b.allocated_days + b.carryover_days - b.used_days - b.pending_days);
}

function sortLeaveTypes(types: LeaveType[]): LeaveType[] {
  return [...types].sort((a, b) => {
    const ai = TYPE_ORDER.indexOf((a.code || '').toUpperCase());
    const bi = TYPE_ORDER.indexOf((b.code || '').toUpperCase());
    const aRank = ai === -1 ? 99 : ai;
    const bRank = bi === -1 ? 99 : bi;
    if (aRank !== bRank) return aRank - bRank;
    return a.name.localeCompare(b.name);
  });
}

function sortBalances(balances: LeaveBalance[]): LeaveBalance[] {
  return [...balances].sort((a, b) => {
    const ai = TYPE_ORDER.indexOf((a.leave_type_code || '').toUpperCase());
    const bi = TYPE_ORDER.indexOf((b.leave_type_code || '').toUpperCase());
    const aRank = ai === -1 ? 99 : ai;
    const bRank = bi === -1 ? 99 : bi;
    if (aRank !== bRank) return aRank - bRank;
    return (a.leave_type_name || '').localeCompare(b.leave_type_name || '');
  });
}

function chipTone(code: string): string {
  switch (code) {
    case 'ANNUAL':
      return 'balance-chip-annual';
    case 'SICK':
      return 'balance-chip-sick';
    case 'CASUAL':
      return 'balance-chip-casual';
    default:
      return '';
  }
}

interface LeaveScreenProps {
  dataVersion?: number;
}

export const LeaveScreen: React.FC<LeaveScreenProps> = ({ dataVersion = 0 }) => {
  const [types, setTypes] = useState<LeaveType[]>([]);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const today = toDateInput(new Date());
  const [leaveTypeId, setLeaveTypeId] = useState('');
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState(today);
  const [isHalfDay, setIsHalfDay] = useState(false);
  const [halfDayPeriod, setHalfDayPeriod] = useState<'FIRST_HALF' | 'SECOND_HALF'>('FIRST_HALF');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [t, b, r] = await Promise.all([getLeaveTypes(), getLeaveBalances(), getLeaveRequests()]);
      const orderedTypes = sortLeaveTypes(
        t.filter((x) => ALLOWED_CODES.has((x.code || '').toUpperCase()))
      );
      const orderedBalances = sortBalances(
        b.filter((x) => ALLOWED_CODES.has((x.leave_type_code || '').toUpperCase()))
      );
      setTypes(orderedTypes);
      setBalances(orderedBalances);
      setRequests(r);
      setLeaveTypeId((current) => {
        if (current && orderedTypes.some((x) => x.id === current)) return current;
        return orderedTypes[0]?.id || '';
      });
      setLoadError(null);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not load leave data');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, dataVersion]);

  const selectedType = useMemo(() => types.find((t) => t.id === leaveTypeId) || null, [types, leaveTypeId]);
  const selectedBalance = useMemo(
    () => balances.find((b) => b.leave_type_id === leaveTypeId),
    [balances, leaveTypeId]
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccess(null);
    if (!leaveTypeId) return setFormError('Choose a leave type.');
    if (endDate < startDate) return setFormError('End date cannot be before the start date.');
    if (isHalfDay && startDate !== endDate) return setFormError('A half day must start and end on the same date.');
    if (reason.trim().length < 3) return setFormError('Please enter a reason (at least 3 characters).');
    if (selectedBalance && available(selectedBalance) <= 0) {
      return setFormError(`No ${selectedType?.name || 'leave'} balance left this year.`);
    }

    setSubmitting(true);
    try {
      const created = await applyForLeave({
        leave_type_id: leaveTypeId,
        start_date: startDate,
        end_date: endDate,
        is_half_day: isHalfDay,
        half_day_period: isHalfDay ? halfDayPeriod : null,
        reason: reason.trim(),
      });
      setSuccess(`Leave request sent for ${formatDays(created.total_days)} day(s). Your manager will review it.`);
      setReason('');
      setIsHalfDay(false);
      await load();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not submit the request');
    } finally {
      setSubmitting(false);
    }
  };

  const handleWithdraw = async (id: string) => {
    setBusyId(id);
    try {
      await withdrawLeave(id);
      await load();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not withdraw the request');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="screen-container">
      <div className="screen-header">
        <h2 className="screen-title">Apply for Leave</h2>
        <p className="screen-subtitle">Company policy this year</p>
      </div>

      <div className="leave-policy-strip">
        <div className="leave-policy-item">
          <span className="leave-policy-num">24</span>
          <span className="leave-policy-name">Annual</span>
        </div>
        <div className="leave-policy-item">
          <span className="leave-policy-num">12</span>
          <span className="leave-policy-name">Sick</span>
        </div>
        <div className="leave-policy-item">
          <span className="leave-policy-num">12</span>
          <span className="leave-policy-name">Casual</span>
        </div>
      </div>

      {loadError && <div className="alert-error text-xs">{loadError}</div>}

      {balances.length > 0 && (
        <div className="balance-row">
          {balances.map((b) => {
            const code = (b.leave_type_code || '').toUpperCase();
            const yearly = POLICY_QUOTA[code] ?? b.allocated_days ?? selectedType?.annual_allowance ?? 0;
            const leftOfYear = Math.max(0, yearly + b.carryover_days - b.used_days - b.pending_days);
            const active = leaveTypeId === b.leave_type_id;
            return (
              <button
                key={b.id}
                type="button"
                className={`balance-chip balance-chip-btn ${chipTone(code)} ${active ? 'balance-chip-active' : ''}`}
                onClick={() => setLeaveTypeId(b.leave_type_id)}
              >
                <div className="balance-value">{formatDays(leftOfYear)}</div>
                <div className="balance-label">{b.leave_type_name || b.leave_type_code}</div>
                <div className="balance-meta">
                  {`${formatDays(leftOfYear)} left of ${formatDays(yearly)} · ${formatDays(b.used_days)} used${
                    b.pending_days ? ` · ${formatDays(b.pending_days)} pending` : ''
                  }`}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <form className="card form-card" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="leave-type">Leave type</label>
          <select id="leave-type" className="field" value={leaveTypeId} onChange={(e) => setLeaveTypeId(e.target.value)}>
            {types.map((t) => {
              const code = (t.code || '').toUpperCase();
              const quota = POLICY_QUOTA[code] ?? t.annual_allowance;
              return (
                <option key={t.id} value={t.id}>
                  {t.name}
                  {quota > 0 ? ` (${quota}/year)` : ''}
                </option>
              );
            })}
          </select>
          {selectedBalance && selectedType ? (
            <span className="field-hint">
              {(() => {
                const code = (selectedType.code || '').toUpperCase();
                const yearly =
                  POLICY_QUOTA[code] ??
                  (selectedBalance.allocated_days || selectedType.annual_allowance || 0);
                const left = Math.max(
                  0,
                  yearly +
                    selectedBalance.carryover_days -
                    selectedBalance.used_days -
                    selectedBalance.pending_days
                );
                return (
                  <>
                    {formatDays(left)} day(s) available of {formatDays(yearly)}
                    {selectedBalance.carryover_days > 0
                      ? ` (includes ${formatDays(selectedBalance.carryover_days)} carryover)`
                      : ''}
                  </>
                );
              })()}
            </span>
          ) : null}
          {selectedType?.requires_attachment && (
            <span className="field-hint">HR may ask for a supporting document for this leave type.</span>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="leave-start">From</label>
            <input
              id="leave-start"
              type="date"
              className="field"
              value={startDate}
              onChange={(e) => {
                setStartDate(e.target.value);
                if (endDate < e.target.value) setEndDate(e.target.value);
              }}
            />
          </div>
          <div className="form-group">
            <label htmlFor="leave-end">To</label>
            <input
              id="leave-end"
              type="date"
              className="field"
              value={endDate}
              min={startDate}
              disabled={isHalfDay}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
        </div>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={isHalfDay}
            onChange={(e) => {
              setIsHalfDay(e.target.checked);
              if (e.target.checked) setEndDate(startDate);
            }}
          />
          <span>Half day</span>
          {isHalfDay && (
            <select
              className="field field-inline"
              value={halfDayPeriod}
              onChange={(e) => setHalfDayPeriod(e.target.value as 'FIRST_HALF' | 'SECOND_HALF')}
            >
              <option value="FIRST_HALF">First half</option>
              <option value="SECOND_HALF">Second half</option>
            </select>
          )}
        </label>

        <div className="form-group">
          <label htmlFor="leave-reason">Reason</label>
          <textarea
            id="leave-reason"
            className="field"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Family function"
          />
        </div>

        {formError && <div className="alert-error text-xs">{formError}</div>}
        {success && (
          <div className="alert-success text-xs">
            <CheckCircle2 className="icon-xs" /> {success}
          </div>
        )}

        <button type="submit" className="btn btn-primary" disabled={submitting || types.length === 0}>
          {submitting ? <Loader2 className="icon-sm spin" /> : <Send className="icon-sm" />}
          &nbsp;Submit request
        </button>
      </form>

      <div className="section-title">My requests</div>
      {requests.length === 0 ? (
        <div className="card muted-text">You have not applied for leave yet.</div>
      ) : (
        requests.map((r) => (
          <div key={r.id} className="card leave-item">
            <div className="card-title-row">
              <span className="card-title">{r.leave_type_name || 'Leave'}</span>
              <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status}</span>
            </div>
            <div className="leave-dates">
              {formatDay(r.start_date)}
              {r.end_date !== r.start_date && <> → {formatDay(r.end_date)}</>} • {formatDays(r.total_days)} day(s)
              {r.is_half_day && ' (half day)'}
            </div>
            <div className="muted-text">{r.reason}</div>
            <div className="approval-row">
              <span>Manager: {r.manager_approval_status}</span>
              <span>HR: {r.hr_approval_status}</span>
            </div>
            {r.approvals
              .filter((a) => a.comments)
              .map((a, i) => (
                <div key={i} className="hint-row">
                  {a.stage} {a.approver_name ? `(${a.approver_name})` : ''}: {a.comments}
                </div>
              ))}
            {r.status === 'PENDING' && (
              <button className="btn btn-secondary btn-sm" disabled={busyId === r.id} onClick={() => handleWithdraw(r.id)}>
                <Undo2 className="icon-xs" />
                &nbsp;Withdraw
              </button>
            )}
          </div>
        ))
      )}
    </div>
  );
};
