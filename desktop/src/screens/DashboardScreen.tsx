import React, { useCallback, useEffect, useState } from 'react';
import {
  CalendarCheck,
  CalendarX,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coffee,
  LogIn,
  LogOut,
  Palmtree,
  Briefcase,
  Wifi,
} from 'lucide-react';

import { getLeaveBalances, getPresenceSummary } from '../api/backend';
import { BreakTrackerStatus } from '../presence/usePresenceTracker';
import { LeaveBalance, PresenceMonthSummary, UserSession } from '../types';
import { formatDays, formatDuration, formatMonth, formatTime, monthKey } from '../utils/format';

interface DashboardScreenProps {
  session: UserSession;
  dataVersion: number;
  breakStatus?: BreakTrackerStatus;
  /** Local tracker logged-in flag — used when server summary is still stale. */
  trackerLoggedIn?: boolean | null;
  onWorkLogin?: () => Promise<void>;
  onWorkLogout?: () => Promise<void>;
  onFirstLoginKnown?: (iso: string) => void;
}

function available(b: LeaveBalance): number {
  return Math.max(0, b.allocated_days + b.carryover_days - b.used_days - b.pending_days);
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({
  session,
  dataVersion,
  breakStatus,
  trackerLoggedIn,
  onWorkLogin,
  onWorkLogout,
  onFirstLoginKnown,
}) => {
  const currentMonth = monthKey(new Date());
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<PresenceMonthSummary | null>(null);
  const [balances, setBalances] = useState<LeaveBalance[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<'login' | 'logout' | null>(null);

  const load = useCallback(async (soft = false) => {
    if (!soft) setLoading(true);
    try {
      const [presence, leaveBalances] = await Promise.all([
        getPresenceSummary(month),
        getLeaveBalances().catch(() => [] as LeaveBalance[]),
      ]);
      setSummary(presence);
      // Only seed 9h policy from an open session — not a closed prior logout day.
      if (presence.today?.first_login && presence.today?.is_logged_in) {
        onFirstLoginKnown?.(presence.today.first_login);
      }
      setBalances(
        leaveBalances.filter((b) =>
          ['ANNUAL', 'SICK', 'CASUAL'].includes((b.leave_type_code || '').toUpperCase())
        )
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your summary');
    } finally {
      setLoading(false);
    }
  }, [month, onFirstLoginKnown]);

  useEffect(() => {
    void load(false);
  }, [load]);

  useEffect(() => {
    // Silent auto-refresh from the presence poller (every ~15s / on focus).
    if (dataVersion === 0) return;
    void load(true);
  }, [dataVersion, load]);

  // Live tick for "Worked" while logged in
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!summary?.today?.is_logged_in) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 15_000);
    return () => window.clearInterval(id);
  }, [summary?.today?.is_logged_in]);

  const shiftMonth = (delta: number) => {
    const [y, m] = month.split('-').map(Number);
    setMonth(monthKey(new Date(y, m - 1 + delta, 1)));
  };

  const today = summary?.today;
  const isWorking = Boolean(today?.is_logged_in) || trackerLoggedIn === true;
  const todayMinutes = (() => {
    if (!today?.first_login) return today?.worked_minutes ?? 0;
    const startMs = new Date(today.first_login).getTime();
    const dayStart = new Date();
    dayStart.setHours(0, 0, 0, 0);
    const dayEnd = new Date(dayStart);
    dayEnd.setDate(dayEnd.getDate() + 1);
    const start = Math.max(startMs, dayStart.getTime());
    if (isWorking) {
      return Math.max(0, (Math.min(Date.now(), dayEnd.getTime()) - start) / 60000);
    }
    if (today.last_logout) {
      const end = Math.min(new Date(today.last_logout).getTime(), dayEnd.getTime());
      return Math.max(0, (end - start) / 60000);
    }
    return today.worked_minutes ?? 0;
  })();

  const liveBreakMinutes = breakStatus?.isOnBreak ? breakStatus.breakElapsedMinutes || 0 : 0;
  const todayBreakMinutes = (today?.total_break_minutes || 0) + liveBreakMinutes;
  const todayBreakCount = (today?.break_count || 0) + (breakStatus?.isOnBreak ? 1 : 0);
  const statusLabel = breakStatus?.isOnBreak
    ? `${breakStatus.breakType === 'LUNCH' ? 'Lunch break' : 'On break'}${
        liveBreakMinutes ? ` · ${liveBreakMinutes}m` : ''
      }`
    : isWorking
      ? 'Working (Logged In)'
      : today?.first_login
        ? 'Logged out'
        : 'Not logged in yet';

  const runAction = async (kind: 'login' | 'logout') => {
    if (busyAction) return;
    setBusyAction(kind);
    const safety = window.setTimeout(() => setBusyAction(null), 20_000);
    try {
      if (kind === 'login') await onWorkLogin?.();
      else await onWorkLogout?.();
      await load(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not ${kind}`);
    } finally {
      window.clearTimeout(safety);
      setBusyAction(null);
    }
  };

  return (
    <div className="screen-container">
      <div className="screen-header">
        <h2 className="screen-title">Hello, {session.first_name}</h2>
        <p className="screen-subtitle">
          {[session.employee_code, session.job_title || session.department_name].filter(Boolean).join(' • ') ||
            session.email}
        </p>
      </div>

      {error && <div className="alert-error text-xs">{error}</div>}

      <div className="card today-card dash-today">
        <div className="card-title-row">
          <span className="card-title">Today</span>
          <span
            className={`badge ${
              breakStatus?.isOnBreak ? 'badge-warning' : isWorking ? 'badge-success' : 'badge-neutral'
            }`}
          >
            {isWorking && !breakStatus?.isOnBreak ? <span className="pulse-dot dot-green" /> : null}
            {isWorking && !breakStatus?.isOnBreak ? '\u00a0' : null}
            {statusLabel}
          </span>
        </div>

        <div className="today-grid">
          <div>
            <div className="kv-label">Login</div>
            <div className="kv-value">{formatTime(today?.first_login)}</div>
          </div>
          <div>
            <div className="kv-label">Logout</div>
            <div className="kv-value">{isWorking ? '—' : formatTime(today?.last_logout)}</div>
          </div>
          <div>
            <div className="kv-label">Worked</div>
            <div className="kv-value">{formatDuration(todayMinutes)}</div>
          </div>
        </div>

        <div className="today-grid two dash-break-row">
          <div>
            <div className="kv-label">
              <Coffee className="icon-xs" /> Breaks today
            </div>
            <div className="kv-value">{todayBreakCount}</div>
          </div>
          <div>
            <div className="kv-label">Break time</div>
            <div className="kv-value">{formatDuration(todayBreakMinutes)}</div>
          </div>
        </div>

        {today?.first_wifi_connected_at && (
          <div className="hint-row">
            <Wifi className="icon-xs" /> Laptop joined {today.wifi_networks.join(', ') || 'Wi-Fi'} at{' '}
            {formatTime(today.first_wifi_connected_at)}
          </div>
        )}

        <div className="dash-action-row">
          <button
            type="button"
            className="dash-action dash-action-login"
            disabled={busyAction !== null || isWorking}
            onClick={() => runAction('login')}
            title={isWorking ? 'Already logged in' : 'Clock in'}
          >
            <span className="dash-action-circle">
              <LogIn className="icon-md" />
            </span>
            <span className="dash-action-label">{busyAction === 'login' ? 'Logging in…' : 'Login'}</span>
          </button>
          <button
            type="button"
            className="dash-action dash-action-logout"
            disabled={busyAction !== null || !isWorking}
            onClick={() => runAction('logout')}
            title={!isWorking ? 'Already logged out' : 'Clock out'}
          >
            <span className="dash-action-circle">
              <LogOut className="icon-md" />
            </span>
            <span className="dash-action-label">
              {busyAction === 'logout' ? 'Logging out…' : 'Logout (Clock Out)'}
            </span>
          </button>
        </div>
      </div>

      {balances.length > 0 && (
        <div className="balance-row dash-leave-balances">
          {balances.map((b) => (
            <div key={b.id} className="balance-chip">
              <div className="balance-value">{formatDays(available(b))}</div>
              <div className="balance-label">{b.leave_type_name || b.leave_type_code}</div>
              <div className="balance-meta">{formatDays(b.allocated_days)} / year</div>
            </div>
          ))}
        </div>
      )}

      <div className="month-switcher">
        <button className="icon-btn" onClick={() => shiftMonth(-1)} aria-label="Previous month">
          <ChevronLeft className="icon-sm" />
        </button>
        <span className="month-label">{formatMonth(month)}</span>
        <button
          className="icon-btn"
          onClick={() => shiftMonth(1)}
          disabled={month >= currentMonth}
          aria-label="Next month"
        >
          <ChevronRight className="icon-sm" />
        </button>
      </div>

      {loading && !summary ? (
        <div className="card muted-text">Loading…</div>
      ) : summary ? (
        <>
          <div className="stat-grid">
            <div className="stat-tile">
              <Briefcase className="stat-icon tone-blue" />
              <div className="stat-value">{summary.working_days}</div>
              <div className="stat-label">Working days</div>
            </div>
            <div className="stat-tile">
              <CalendarCheck className="stat-icon tone-green" />
              <div className="stat-value">{summary.present_days}</div>
              <div className="stat-label">Days present</div>
            </div>
            <div className="stat-tile">
              <Palmtree className="stat-icon tone-amber" />
              <div className="stat-value">{formatDays(summary.leave_days)}</div>
              <div className="stat-label">Leave taken</div>
            </div>
            <div className="stat-tile">
              <CalendarX className="stat-icon tone-red" />
              <div className="stat-value">{summary.absent_days}</div>
              <div className="stat-label">Absent</div>
            </div>
          </div>

          <div className="card">
            <div className="card-title-row">
              <span className="card-title">Total days vs leave</span>
            </div>
            <div className="ratio-bar">
              <div
                className="ratio-present"
                style={{ width: `${summary.working_days ? (summary.present_days / summary.working_days) * 100 : 0}%` }}
              />
              <div
                className="ratio-leave"
                style={{ width: `${summary.working_days ? (summary.leave_days / summary.working_days) * 100 : 0}%` }}
              />
            </div>
            <div className="legend-row">
              <span>
                <i className="legend-dot ratio-present" /> Present {summary.present_days}
              </span>
              <span>
                <i className="legend-dot ratio-leave" /> Leave {formatDays(summary.leave_days)}
              </span>
              <span>
                <i className="legend-dot ratio-rest" /> Absent {summary.absent_days}
              </span>
            </div>
            {summary.upcoming_leave_days > 0 && (
              <div className="hint-row">Upcoming approved leave: {formatDays(summary.upcoming_leave_days)} day(s)</div>
            )}
          </div>

          <div className="card">
            <div className="card-title-row">
              <span className="card-title">
                <Clock className="icon-xs" /> Login time
              </span>
            </div>
            <div className="today-grid two">
              <div>
                <div className="kv-label">Total this month</div>
                <div className="kv-value big">{formatDuration(summary.total_worked_minutes)}</div>
              </div>
              <div>
                <div className="kv-label">Average per day</div>
                <div className="kv-value big">{formatDuration(summary.average_daily_minutes)}</div>
              </div>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
};
