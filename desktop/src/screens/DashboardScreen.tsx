import React from 'react';
import {
  Clock,
  Activity,
  Calendar,
  Coffee,
  Play,
  Square,
  ArrowRight,
  Wifi,
  WifiOff,
  RefreshCw,
} from 'lucide-react';
import {
  UserSession,
  TodayAttendanceSummary,
  ActiveWindowInfo,
  LeaveBalance,
  ConnectionState,
  ScreenId,
} from '../types';

interface DashboardScreenProps {
  session: UserSession;
  attendance: TodayAttendanceSummary;
  activeWindow: ActiveWindowInfo;
  leaveBalances: LeaveBalance[];
  connection: ConnectionState;
  onNavigate: (screen: ScreenId) => void;
  onClockAction: (action: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END') => void;
  onForceSync: () => void;
}

export const DashboardScreen: React.FC<DashboardScreenProps> = ({
  session,
  attendance,
  activeWindow,
  leaveBalances,
  connection,
  onNavigate,
  onClockAction,
  onForceSync,
}) => {
  // Format seconds into HH:MM:SS
  const formatDuration = (totalSecs: number): string => {
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs
      .toString()
      .padStart(2, '0')}`;
  };

  const getAttendanceBadge = () => {
    switch (attendance.mode) {
      case 'CLOCKED_IN':
        return (
          <span className="badge badge-success">
            <span className="pulse-dot bg-emerald-500 mr-1.5" />
            Clocked In
          </span>
        );
      case 'ON_BREAK':
        return (
          <span className="badge badge-warning">
            <Coffee className="w-3.5 h-3.5 mr-1 text-amber-600" />
            On Break ({attendance.currentBreakType || 'Rest'})
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral">
            <span className="w-2 h-2 rounded-full bg-slate-400 mr-1.5" />
            Clocked Out
          </span>
        );
    }
  };

  return (
    <div className="screen-container">
      {/* Welcome Banner */}
      <div className="welcome-banner">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            Welcome back, {session.first_name} {session.last_name}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            {session.employee_code || 'EMP-001'} • {session.job_title || 'Software Engineer'} •{' '}
            {session.department_name || 'Engineering'}
          </p>
        </div>
        <div className="connection-pill">
          {connection.is_online ? (
            <span className="inline-flex items-center text-xs text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full border border-emerald-200">
              <Wifi className="w-3 h-3 mr-1 text-emerald-600" />
              Online
            </span>
          ) : (
            <span className="inline-flex items-center text-xs text-amber-700 bg-amber-50 px-2 py-1 rounded-full border border-amber-200">
              <WifiOff className="w-3 h-3 mr-1 text-amber-600" />
              Offline Mode
            </span>
          )}
        </div>
      </div>

      {/* Primary Attendance Card */}
      <div className="card attendance-hero-card">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-indigo-600" />
            <h3 className="font-semibold text-slate-800 text-sm">Shift Attendance</h3>
          </div>
          {getAttendanceBadge()}
        </div>

        <div className="shift-timer-display">
          <div className="timer-value">{formatDuration(attendance.totalWorkedSeconds)}</div>
          <div className="timer-label">Today&apos;s Active Work Duration</div>
        </div>

        {/* Quick Action Controls */}
        <div className="grid grid-cols-2 gap-2 mt-2">
          {attendance.mode === 'CLOCKED_OUT' ? (
            <button
              onClick={() => onClockAction('CLOCK_IN')}
              className="btn btn-primary col-span-2 flex items-center justify-center gap-2 py-2.5"
            >
              <Play className="w-4 h-4 fill-current" />
              Clock In Workstation
            </button>
          ) : attendance.mode === 'CLOCKED_IN' ? (
            <>
              <button
                onClick={() => onClockAction('BREAK_START')}
                className="btn btn-secondary flex items-center justify-center gap-1.5 py-2"
              >
                <Coffee className="w-4 h-4" />
                Take Break
              </button>
              <button
                onClick={() => onClockAction('CLOCK_OUT')}
                className="btn btn-danger flex items-center justify-center gap-1.5 py-2"
              >
                <Square className="w-4 h-4 fill-current" />
                Clock Out
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => onClockAction('BREAK_END')}
                className="btn btn-primary flex items-center justify-center gap-1.5 py-2"
              >
                <Play className="w-4 h-4 fill-current" />
                Resume Work
              </button>
              <button
                onClick={() => onClockAction('CLOCK_OUT')}
                className="btn btn-danger flex items-center justify-center gap-1.5 py-2"
              >
                <Square className="w-4 h-4 fill-current" />
                Clock Out
              </button>
            </>
          )}
        </div>

        <button
          onClick={() => onNavigate('attendance')}
          className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center justify-end gap-1 mt-1 font-medium"
        >
          View Detailed Logs & Breaks
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* Computer Activity Telemetry (Transparent) */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-emerald-600" />
            <h3 className="font-semibold text-slate-800 text-sm">Computer Activity</h3>
          </div>
          <span className="text-[11px] font-mono text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            Transparent Tracking
          </span>
        </div>

        <div className="space-y-2 text-xs">
          <div className="flex justify-between items-center bg-slate-50 p-2 rounded-lg border border-slate-100">
            <span className="text-slate-500">Foreground App:</span>
            <span className="font-semibold text-slate-800 truncate max-w-[200px]" title={activeWindow.application_name}>
              {activeWindow.application_name}
            </span>
          </div>

          <div className="flex justify-between items-center bg-slate-50 p-2 rounded-lg border border-slate-100">
            <span className="text-slate-500">Active Window:</span>
            <span className="font-mono text-slate-700 truncate max-w-[200px]" title={activeWindow.window_title}>
              {activeWindow.window_title || 'Active Desktop Task'}
            </span>
          </div>

          <div className="flex justify-between items-center text-slate-600 px-1">
            <span>System Idle Timer:</span>
            <span className="font-mono font-medium text-slate-800">{activeWindow.idle_seconds}s</span>
          </div>
        </div>

        <button
          onClick={() => onNavigate('activity')}
          className="text-xs text-indigo-600 hover:text-indigo-800 flex items-center justify-end gap-1 mt-1 font-medium"
        >
          View Activity Timeline
          <ArrowRight className="w-3 h-3" />
        </button>
      </div>

      {/* Leave Balances Snapshot */}
      <div className="card">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-blue-600" />
            <h3 className="font-semibold text-slate-800 text-sm">Leave Balances</h3>
          </div>
          <button
            onClick={() => onNavigate('leave_apply')}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800"
          >
            Apply Leave
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2">
          {leaveBalances.slice(0, 4).map((b) => (
            <div key={b.leave_type} className="bg-slate-50 p-2.5 rounded-lg border border-slate-100">
              <div className="text-[11px] text-slate-500 truncate">{b.leave_type}</div>
              <div className="flex items-baseline justify-between mt-1">
                <span className="text-base font-bold text-slate-900">{b.available}</span>
                <span className="text-[10px] text-slate-400">of {b.total_allowed}d</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Synchronization & Queue Status */}
      <div className="card bg-slate-50/70 border-dashed">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-slate-600">
            <RefreshCw className="w-3.5 h-3.5 text-slate-400" />
            <span>
              Queue: <strong>{connection.pending_queue_count}</strong> pending items
            </span>
          </div>
          <button
            onClick={onForceSync}
            disabled={connection.pending_queue_count === 0}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-40"
          >
            Force Sync
          </button>
        </div>
      </div>
    </div>
  );
};
