import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, CloudOff, LogIn, LogOut, RefreshCw, Wifi, WifiOff } from 'lucide-react';

import { getPresenceHistory } from '../api/backend';
import { PresenceDay, PresenceEventType, TrackerStatus } from '../types';
import { formatDay, formatDuration, formatTime, toDateInput } from '../utils/format';

interface PresenceScreenProps {
  tracker: TrackerStatus;
  dataVersion: number;
  onSyncNow: () => void;
}

type RangeId = 'week' | 'two_weeks' | 'month';

const RANGES: { id: RangeId; label: string }[] = [
  { id: 'week', label: 'This week' },
  { id: 'two_weeks', label: 'Last 14 days' },
  { id: 'month', label: 'This month' },
];

const EVENT_LABELS: Record<PresenceEventType, string> = {
  APP_LOGIN: 'App sign-in',
  APP_LOGOUT: 'App sign-out',
  WIFI_CONNECTED: 'Wi-Fi connected',
  WIFI_DISCONNECTED: 'Wi-Fi disconnected',
};

function rangeDates(range: RangeId): [string, string] {
  const end = new Date();
  const start = new Date(end);
  if (range === 'week') {
    start.setDate(end.getDate() - ((end.getDay() + 6) % 7));
  } else if (range === 'two_weeks') {
    start.setDate(end.getDate() - 13);
  } else {
    start.setDate(1);
  }
  return [toDateInput(start), toDateInput(end)];
}

function EventIcon({ type }: { type: PresenceEventType }) {
  if (type === 'WIFI_CONNECTED') return <Wifi className="icon-xs tone-green" />;
  if (type === 'WIFI_DISCONNECTED') return <WifiOff className="icon-xs tone-red" />;
  if (type === 'APP_LOGIN') return <LogIn className="icon-xs tone-blue" />;
  return <LogOut className="icon-xs tone-slate" />;
}

export const PresenceScreen: React.FC<PresenceScreenProps> = ({ tracker, dataVersion, onSyncNow }) => {
  const [range, setRange] = useState<RangeId>('week');
  const [days, setDays] = useState<PresenceDay[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [start, end] = rangeDates(range);
      setDays((await getPresenceHistory(start, end)).days);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load login history');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    load();
  }, [load, dataVersion]);

  const totalMinutes = days.reduce((sum, d) => sum + d.worked_minutes, 0);

  return (
    <div className="screen-container">
      <div className="screen-header">
        <h2 className="screen-title">Login &amp; Logout</h2>
        <p className="screen-subtitle">
          Login is your first app sign-in or Wi-Fi connection; logout is your last sign-out or Wi-Fi disconnection.
        </p>
      </div>

      <div className="card status-strip">
        <div className="status-item">
          {tracker.wifi?.is_wifi ? <Wifi className="icon-sm tone-green" /> : <WifiOff className="icon-sm tone-slate" />}
          <div>
            <div className="kv-label">This laptop</div>
            <div className="kv-value small">{tracker.wifi?.is_wifi ? tracker.wifi.ssid || 'Wi-Fi' : 'Not on Wi-Fi'}</div>
          </div>
        </div>
        <div className="status-item">
          {tracker.isOnline ? <RefreshCw className="icon-sm tone-blue" /> : <CloudOff className="icon-sm tone-amber" />}
          <div>
            <div className="kv-label">{tracker.isOnline ? 'Synced' : 'Offline — saved on laptop'}</div>
            <div className="kv-value small">
              {tracker.pendingEvents > 0 ? `${tracker.pendingEvents} waiting` : formatTime(tracker.lastSyncAt)}
            </div>
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={onSyncNow}>
          Sync now
        </button>
      </div>

      <div className="segmented">
        {RANGES.map((r) => (
          <button
            key={r.id}
            className={`segment ${range === r.id ? 'segment-active' : ''}`}
            onClick={() => setRange(r.id)}
          >
            {r.label}
          </button>
        ))}
      </div>

      {error && <div className="alert-error text-xs">{error}</div>}

      <div className="card table-card">
        <table className="data-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Login</th>
              <th>Logout</th>
              <th className="num">Hours</th>
            </tr>
          </thead>
          <tbody>
            {loading && days.length === 0 && (
              <tr>
                <td colSpan={4} className="muted-text center">Loading…</td>
              </tr>
            )}
            {!loading && days.length === 0 && (
              <tr>
                <td colSpan={4} className="muted-text center">No logins recorded in this period.</td>
              </tr>
            )}
            {days.map((d) => {
              const isOpen = expanded === d.work_date;
              const minutes = d.is_logged_in && d.first_login
                ? (Date.now() - new Date(d.first_login).getTime()) / 60000
                : d.worked_minutes;
              return (
                <React.Fragment key={d.work_date}>
                  <tr className="clickable" onClick={() => setExpanded(isOpen ? null : d.work_date)}>
                    <td>
                      {isOpen ? <ChevronDown className="icon-xs" /> : <ChevronRight className="icon-xs" />}{' '}
                      {formatDay(d.work_date)}
                    </td>
                    <td>{formatTime(d.first_login)}</td>
                    <td>{d.is_logged_in ? <span className="badge badge-success">Active</span> : formatTime(d.last_logout)}</td>
                    <td className="num">{d.first_login ? formatDuration(minutes) : '—'}</td>
                  </tr>
                  {isOpen && (
                    <tr className="detail-row">
                      <td colSpan={4}>
                        {d.wifi_networks.length > 0 && (
                          <div className="hint-row">
                            <Wifi className="icon-xs" /> {d.wifi_networks.join(', ')} • first connected{' '}
                            {formatTime(d.first_wifi_connected_at)}
                          </div>
                        )}
                        {d.events.length === 0 ? (
                          <div className="muted-text">No app or Wi-Fi events recorded for this day.</div>
                        ) : (
                          <ul className="event-list">
                            {d.events.map((ev, i) => (
                              <li key={`${ev.occurred_at}-${i}`}>
                                <span className="event-time">{formatTime(ev.occurred_at)}</span>
                                <EventIcon type={ev.event_type} />
                                <span>{EVENT_LABELS[ev.event_type] ?? ev.event_type}</span>
                                {ev.ssid && <span className="muted-text">({ev.ssid})</span>}
                                {ev.attendance_action === 'CLOCK_IN' && <span className="badge badge-success">login</span>}
                                {ev.attendance_action === 'CLOCK_OUT' && <span className="badge badge-neutral">logout</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
          {days.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan={3}>Total ({days.filter((d) => d.first_login).length} days)</td>
                <td className="num">{formatDuration(totalMinutes)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
};
