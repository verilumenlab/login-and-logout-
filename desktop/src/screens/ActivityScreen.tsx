import React, { useState, useEffect } from 'react';
import {
  Activity,
  Shield,
  PauseCircle,
  PlayCircle,
  Layers,
  Laptop,
  Lock,
  Unlock,
  Moon,
  Sun,
  LogIn,
  LogOut,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
} from 'lucide-react';
import { ActiveWindowInfo, AppUsageStat, OSSessionEventContract, EventQueueStatus } from '../types';
import {
  getOSSessionEvents,
  getEventQueueStatus,
  isWorkstationLocked,
  simulateOSSessionTransition,
  syncOSSessionEvents,
} from '../api/ipc';

interface ActivityScreenProps {
  activeWindow: ActiveWindowInfo;
  onToggleTracking: (enabled: boolean) => void;
}

export const ActivityScreen: React.FC<ActivityScreenProps> = ({
  activeWindow,
  onToggleTracking,
}) => {
  const [activeTab, setActiveTab] = useState<'processes' | 'os_events'>('processes');
  const [showPrivacyModal, setShowPrivacyModal] = useState(false);
  const [pauseReason, setPauseReason] = useState('Personal Break');

  // Phase 06 OS Session State
  const [osEvents, setOsEvents] = useState<OSSessionEventContract[]>([]);
  const [queueStatus, setQueueStatus] = useState<EventQueueStatus | null>(null);
  const [isLocked, setIsLocked] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  const sampleUsageStats: AppUsageStat[] = [
    {
      application_name: 'Visual Studio Code',
      seconds: 14200,
      percentage: 55,
      category: 'Development',
    },
    {
      application_name: 'Google Chrome / Edge',
      seconds: 6480,
      percentage: 25,
      category: 'Documentation',
    },
    {
      application_name: 'Slack / Teams',
      seconds: 3100,
      percentage: 12,
      category: 'Communication',
    },
    {
      application_name: 'Windows Terminal',
      seconds: 2070,
      percentage: 8,
      category: 'Development',
    },
  ];

  const formatHoursMinutes = (totalSecs: number): string => {
    const hrs = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    return `${hrs}h ${mins}m`;
  };

  const loadOSSessionData = async () => {
    try {
      const [events, status, locked] = await Promise.all([
        getOSSessionEvents(),
        getEventQueueStatus(),
        isWorkstationLocked(),
      ]);
      setOsEvents(events);
      setQueueStatus(status);
      setIsLocked(locked);
    } catch (err) {
      console.warn('Failed to load OS session telemetry:', err);
    }
  };

  useEffect(() => {
    loadOSSessionData();
    const interval = setInterval(loadOSSessionData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleSimulate = async (eventType: string) => {
    try {
      await simulateOSSessionTransition('current-employee-session', 'LOCAL-HW-DEVICE', eventType);
      await loadOSSessionData();
      setSyncFeedback(`Triggered ${eventType} (saved to persistent queue)`);
      setTimeout(() => setSyncFeedback(null), 3000);
    } catch (err) {
      console.error('Simulation error:', err);
    }
  };

  const handleManualSync = async () => {
    setIsSyncing(true);
    setSyncFeedback(null);
    try {
      const receipt = await syncOSSessionEvents('http://localhost:8000', 'mock-auth-token');
      setSyncFeedback(receipt.message || `Successfully synced ${receipt.inserted_count} events`);
      await loadOSSessionData();
    } catch (err: any) {
      setSyncFeedback(`Sync note: Queued locally for offline resilience (${err.message || 'Server check'})`);
    } finally {
      setIsSyncing(false);
      setTimeout(() => setSyncFeedback(null), 5000);
    }
  };

  const handlePauseConfirm = () => {
    onToggleTracking(false);
    setShowPrivacyModal(false);
  };

  const handleResume = () => {
    onToggleTracking(true);
  };

  return (
    <div className="screen-container">
      {/* Screen Title */}
      <div className="screen-header">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <Activity className="w-5 h-5 text-emerald-600" />
            Computer & OS Activity
          </h2>
          <p className="screen-subtitle">Transparent Session Monitoring & Telemetry Analytics</p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-slate-100 p-0.5 rounded-lg text-xs font-medium">
          <button
            onClick={() => setActiveTab('processes')}
            className={`px-3 py-1 rounded-md transition-colors ${
              activeTab === 'processes' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Processes & Apps
          </button>
          <button
            onClick={() => setActiveTab('os_events')}
            className={`px-3 py-1 rounded-md transition-colors flex items-center gap-1.5 ${
              activeTab === 'os_events' ? 'bg-white text-indigo-700 shadow-sm font-semibold' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            OS Session Events
            {queueStatus && queueStatus.pending_events_count > 0 && (
              <span className="bg-indigo-600 text-white text-[10px] px-1.5 py-0.2 rounded-full">
                {queueStatus.pending_events_count}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Mandatory Transparency & Negative Constraints Assurance */}
      <div className="p-3 bg-indigo-50/80 border border-indigo-200/80 rounded-xl text-xs text-indigo-950 flex items-start gap-2.5">
        <Shield className="w-4 h-4 text-indigo-600 flex-shrink-0 mt-0.5" />
        <div>
          <div className="font-semibold text-indigo-900">Privacy & Monitoring Boundaries Guarantee</div>
          <p className="text-[11px] text-indigo-700 mt-0.5 leading-relaxed">
            Operating system activity monitoring is architecturally restricted to native lifecycle events (Logon, Lock, Unlock, Sleep, Wake). 
            <strong className="text-indigo-950 font-semibold"> Keylogging, screenshots, keystroke recording, webcam monitoring, and continuous GPS are strictly prohibited by system architecture and company policy.</strong>
          </p>
        </div>
      </div>

      {activeTab === 'processes' ? (
        <>
          {/* Real-time Tracking Status Card */}
          <div className="card">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Laptop className="w-4 h-4 text-slate-500" />
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Live Workstation Monitor
                </h3>
              </div>
              {activeWindow.is_tracking ? (
                <span className="badge badge-success flex items-center gap-1">
                  <span className="pulse-dot bg-emerald-500" />
                  Tracking Active
                </span>
              ) : (
                <span className="badge badge-warning flex items-center gap-1">
                  <PauseCircle className="w-3.5 h-3.5 text-amber-600" />
                  Tracking Paused
                </span>
              )}
            </div>

            <div className="space-y-2 mt-3 text-xs">
              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100 flex justify-between items-center">
                <span className="text-slate-500 font-medium">Foreground Process:</span>
                <span className="font-mono font-semibold text-slate-900 bg-white px-2 py-0.5 rounded border border-slate-200">
                  {activeWindow.application_name}
                </span>
              </div>

              <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                <div className="text-slate-500 font-medium mb-1">Window Title:</div>
                <div className="font-mono text-slate-800 text-[11px] bg-white p-1.5 rounded border border-slate-200 break-all">
                  {activeWindow.window_title || 'No active foreground window title detected'}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1">
                <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">Process PID</div>
                  <div className="font-mono text-xs font-bold text-slate-700 mt-0.5">
                    {activeWindow.process_id || 'N/A'}
                  </div>
                </div>
                <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                  <div className="text-[10px] text-slate-400 uppercase font-semibold">User Idle Time</div>
                  <div className="font-mono text-xs font-bold text-slate-700 mt-0.5">
                    {activeWindow.idle_seconds}s
                  </div>
                </div>
              </div>
            </div>

            {/* Tracking Toggle Button */}
            <div className="mt-3 pt-3 border-t border-slate-100">
              {activeWindow.is_tracking ? (
                <button
                  onClick={() => setShowPrivacyModal(true)}
                  className="btn btn-secondary w-full flex items-center justify-center gap-1.5 py-1.5 text-xs text-slate-700"
                >
                  <PauseCircle className="w-3.5 h-3.5 text-slate-500" />
                  Pause Activity Tracking (Privacy Mode)
                </button>
              ) : (
                <button
                  onClick={handleResume}
                  className="btn btn-primary w-full flex items-center justify-center gap-1.5 py-1.5 text-xs"
                >
                  <PlayCircle className="w-3.5 h-3.5" />
                  Resume Activity Tracking
                </button>
              )}
            </div>
          </div>

          {/* Application Usage Breakdown (Today) */}
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-indigo-600" />
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  Application Usage (Today)
                </h3>
              </div>
              <span className="text-[11px] text-slate-400">Total: 7h 12m</span>
            </div>

            <div className="space-y-3">
              {sampleUsageStats.map((stat) => (
                <div key={stat.application_name} className="space-y-1">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-medium text-slate-800">{stat.application_name}</span>
                    <span className="text-slate-500 font-mono text-[11px]">
                      {formatHoursMinutes(stat.seconds)} ({stat.percentage}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        stat.category === 'Development'
                          ? 'bg-indigo-600'
                          : stat.category === 'Documentation'
                          ? 'bg-blue-500'
                          : 'bg-emerald-500'
                      }`}
                      style={{ width: `${stat.percentage}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        /* Phase 06 OS Session Events Tab */
        <div className="space-y-3">
          {/* Workstation State Diagnostics */}
          <div className="card">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
              <div className="flex items-center gap-2">
                <Clock className="w-4 h-4 text-indigo-600" />
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                  OS Session Diagnostics
                </h3>
              </div>
              <div className="flex items-center gap-2">
                {isLocked ? (
                  <span className="badge badge-warning flex items-center gap-1">
                    <Lock className="w-3 h-3 text-amber-600" />
                    Workstation Locked
                  </span>
                ) : (
                  <span className="badge badge-success flex items-center gap-1">
                    <Unlock className="w-3 h-3 text-emerald-600" />
                    Session Unlocked
                  </span>
                )}
                <button
                  onClick={handleManualSync}
                  disabled={isSyncing}
                  className="btn btn-secondary text-xs flex items-center gap-1 py-1 px-2.5"
                >
                  <RefreshCw className={`w-3 h-3 ${isSyncing ? 'animate-spin text-indigo-600' : ''}`} />
                  Sync Queue
                </button>
              </div>
            </div>

            {/* Diagnostic metrics */}
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-slate-400 text-[10px] uppercase font-semibold">Sequence Counter</span>
                <div className="font-mono font-bold text-slate-800 text-sm mt-0.5">
                  #{queueStatus?.latest_sequence_number || 0}
                </div>
                <div className="text-[10px] text-emerald-600 flex items-center gap-0.5 mt-0.5">
                  <CheckCircle2 className="w-2.5 h-2.5" /> Monotonic Guaranteed
                </div>
              </div>

              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-slate-400 text-[10px] uppercase font-semibold">Offline Queue</span>
                <div className="font-mono font-bold text-slate-800 text-sm mt-0.5">
                  {queueStatus?.pending_events_count || 0} events
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  Stored in local AppData
                </div>
              </div>

              <div className="bg-slate-50 p-2 rounded-lg border border-slate-100">
                <span className="text-slate-400 text-[10px] uppercase font-semibold">Clock Auditing</span>
                <div className="font-bold text-emerald-700 text-sm mt-0.5">
                  Synced (UTC)
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  Rollback protection active
                </div>
              </div>
            </div>

            {syncFeedback && (
              <div className="mt-2 p-2 bg-indigo-50 border border-indigo-200 rounded text-xs text-indigo-900 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-indigo-600 flex-shrink-0" />
                <span>{syncFeedback}</span>
              </div>
            )}

            {/* Test Simulation Controls */}
            <div className="mt-3 pt-3 border-t border-slate-100">
              <div className="text-[11px] font-semibold text-slate-600 mb-2 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3 text-amber-500" />
                Trigger OS State Transitions (Manual Test Suite):
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <button
                  onClick={() => handleSimulate('SESSION_LOCK')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <Lock className="w-3 h-3 text-amber-600" /> Lock Screen
                </button>
                <button
                  onClick={() => handleSimulate('SESSION_UNLOCK')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <Unlock className="w-3 h-3 text-emerald-600" /> Unlock Screen
                </button>
                <button
                  onClick={() => handleSimulate('SYSTEM_SLEEP')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <Moon className="w-3 h-3 text-indigo-600" /> Enter Sleep
                </button>
                <button
                  onClick={() => handleSimulate('SYSTEM_WAKE')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <Sun className="w-3 h-3 text-amber-500" /> System Wake
                </button>
                <button
                  onClick={() => handleSimulate('OS_LOGON')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <LogIn className="w-3 h-3 text-blue-600" /> User Logon
                </button>
                <button
                  onClick={() => handleSimulate('OS_LOGOFF')}
                  className="btn btn-secondary text-[11px] py-1 px-2 flex items-center justify-center gap-1"
                >
                  <LogOut className="w-3 h-3 text-rose-600" /> User Logoff
                </button>
              </div>
            </div>
          </div>

          {/* Local Event Queue Timeline */}
          <div className="card">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-slate-500" />
                Recorded Native Events ({osEvents.length})
              </h3>
              <span className="text-[11px] text-slate-400">Common Event Contract</span>
            </div>

            {osEvents.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-lg">
                No events currently queued in local storage. Trigger a session transition above.
              </div>
            ) : (
              <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                {osEvents.slice().reverse().map((ev) => (
                  <div
                    key={ev.event_id}
                    className="p-2 rounded-lg border border-slate-100 bg-slate-50/60 flex items-center justify-between text-xs"
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] bg-white border border-slate-200 px-1.5 py-0.5 rounded text-slate-600">
                        #{ev.sequence_number}
                      </span>
                      <div>
                        <span className="font-bold text-slate-800 mr-2">{ev.event_type}</span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          {new Date(ev.occurred_at).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase font-mono bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded border border-indigo-100">
                        {ev.operating_system}
                      </span>
                      <span className="badge badge-warning text-[10px]">Pending Sync</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Privacy Mode Reason Modal */}
      {showPrivacyModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <h3 className="text-sm font-bold text-slate-900 mb-2 flex items-center gap-2">
              <PauseCircle className="w-4 h-4 text-amber-600" />
              Pause Workstation Tracking
            </h3>
            <p className="text-xs text-slate-500 mb-3">
              Please choose a reason for auditing purposes. Activity logging will pause until resumed.
            </p>

            <div className="space-y-2 mb-4">
              {['Personal Break', 'Confidential Client Data', 'Medical Call', 'System Maintenance'].map((r) => (
                <label
                  key={r}
                  className={`flex items-center gap-2 p-2 rounded-lg border text-xs cursor-pointer ${
                    pauseReason === r
                      ? 'border-indigo-500 bg-indigo-50 text-indigo-900 font-medium'
                      : 'border-slate-200 text-slate-700'
                  }`}
                >
                  <input
                    type="radio"
                    name="pause_reason"
                    checked={pauseReason === r}
                    onChange={() => setPauseReason(r)}
                  />
                  <span>{r}</span>
                </label>
              ))}
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowPrivacyModal(false)}
                className="btn btn-secondary text-xs px-3 py-1.5"
              >
                Cancel
              </button>
              <button
                onClick={handlePauseConfirm}
                className="btn btn-danger text-xs px-3 py-1.5"
              >
                Confirm Pause
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
