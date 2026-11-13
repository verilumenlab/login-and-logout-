import React, { useCallback, useEffect, useState } from 'react';
import { CalendarCheck, CalendarX, ChevronLeft, ChevronRight, Clock, Palmtree, Briefcase, Wifi } from 'lucide-react';

import { getPresenceSummary } from '../api/backend';
import { PresenceMonthSummary, UserSession } from '../types';
import { formatDays, formatDuration, formatMonth, formatTime, monthKey } from '../utils/format';

interface DashboardScreenProps {
  session: UserSession;
  dataVersion: number;
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({ session, dataVersion }) => {
  const currentMonth = monthKey(new Date());
  const [month, setMonth] = useState(currentMonth);
  const [summary, setSummary] = useState<PresenceMonthSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSummary(await getPresenceSummary(month));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your summary');
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => {
    load();
  }, [load, dataVersion]);

  const shiftMonth = (delta: number) => {
    const [y, m] = month.split('-').map(Number);
    setMonth(monthKey(new Date(y, m - 1 + delta, 1)));
  };

  const today = summary?.today;
  const todayMinutes = today?.is_logged_in && today.first_login
    ? (Date.now() - new Date(today.first_login).getTime()) / 60000
    : today?.worked_minutes ?? 0;

  return (
    <div className="screen-container">
      <div className="screen-header">
        <h2 className="screen-title">Hello, {session.first_name}</h2>
        <p className="screen-subtitle">
          {[session.employee_code, session.department_name].filter(Boolean).join(' • ') || session.email}
        </p>
      </div>

      {error && <div className="alert-error text-xs">{error}</div>}

      <div className="card today-card">
        <div className="card-title-row">
          <span className="card-title">Today</span>
          {today?.is_logged_in ? (
            <span className="badge badge-success"><span className="pulse-dot dot-green" />&nbsp;Logged in</span>
          ) : today?.first_login ? (
            <span className="badge badge-neutral">Logged out</span>
          ) : (
            <span className="badge badge-warning">Not logged in yet</span>
          )}
        </div>
        <div className="today-grid">
          <div>
            <div className="kv-label">Login</div>
            <div className="kv-value">{formatTime(today?.first_login)}</div>
          </div>
          <div>
            <div className="kv-label">Logout</div>
            <div className="kv-value">{today?.is_logged_in ? '—' : formatTime(today?.last_logout)}</div>
          </div>
          <div>
            <div className="kv-label">Time logged in</div>
            <div className="kv-value">{formatDuration(todayMinutes)}</div>
          </div>
        </div>
        {today?.first_wifi_connected_at && (
          <div className="hint-row">
            <Wifi className="icon-xs" /> Laptop joined {today.wifi_networks.join(', ') || 'Wi-Fi'} at{' '}
            {formatTime(today.first_wifi_connected_at)}
          </div>
        )}
      </div>

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
              <span><i className="legend-dot ratio-present" /> Present {summary.present_days}</span>
              <span><i className="legend-dot ratio-leave" /> Leave {formatDays(summary.leave_days)}</span>
              <span><i className="legend-dot ratio-rest" /> Absent {summary.absent_days}</span>
            </div>
            {summary.upcoming_leave_days > 0 && (
              <div className="hint-row">Upcoming approved leave: {formatDays(summary.upcoming_leave_days)} day(s)</div>
            )}
          </div>

          <div className="card">
            <div className="card-title-row">
              <span className="card-title"><Clock className="icon-xs" /> Login time</span>
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
