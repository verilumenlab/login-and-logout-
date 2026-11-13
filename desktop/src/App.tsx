import { useState, useEffect, useCallback } from 'react';
import './App.css';
import {
  ScreenId,
  UserSession,
  TodayAttendanceSummary,
  ActiveWindowInfo,
  LeaveBalance,
  LeaveRequest,
  DeviceInfo,
  ConnectionState,
} from './types';
import {
  getNativeDeviceInfo,
  getActiveWindowInfo,
  sendDesktopNotification,
  getOfflineQueue,
  clearOfflineQueue,
} from './api/ipc';
import {
  getStoredUserSession,
  submitAttendanceEvent,
  getLeaveBalances,
  getLeaveRequests,
  pingBackend,
  sendDeviceHeartbeat,
} from './api/backend';

// Screens
import { LoginScreen } from './screens/LoginScreen';
import { DashboardScreen } from './screens/DashboardScreen';
import { AttendanceScreen } from './screens/AttendanceScreen';
import { ActivityScreen } from './screens/ActivityScreen';
import { LeaveApplyScreen } from './screens/LeaveApplyScreen';
import { LeaveHistoryScreen } from './screens/LeaveHistoryScreen';
import { DeviceInfoScreen } from './screens/DeviceInfoScreen';
import { SettingsScreen } from './screens/SettingsScreen';
import { Navigation } from './components/Navigation';

export default function App() {
  const [session, setSession] = useState<UserSession | null>(null);
  const [currentScreen, setCurrentScreen] = useState<ScreenId>('dashboard');

  // Device Info
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo>({
    device_id: 'DEV-INITIALIZING',
    machine_name: 'Workstation',
    os_type: 'windows',
    os_version: 'Loading OS...',
    arch: 'x86_64',
    ip_address: '127.0.0.1',
    mac_address: '00:00:00:00:00:00',
    battery_percent: 100,
    is_charging: true,
    enrolled: true,
    last_heartbeat: null,
    agent_version: '0.1.0-tauri2',
  });

  // Attendance State
  const [attendance, setAttendance] = useState<TodayAttendanceSummary>({
    mode: 'CLOCKED_OUT',
    clockInTime: null,
    clockOutTime: null,
    totalWorkedSeconds: 0,
    totalBreakSeconds: 0,
    currentBreakType: null,
    currentBreakStartTime: null,
    events: [],
  });

  // Active Window Telemetry
  const [activeWindow, setActiveWindow] = useState<ActiveWindowInfo>({
    application_name: 'Visual Studio Code',
    window_title: 'enterprise-attendance-desktop — src/App.tsx',
    process_id: 10420,
    idle_seconds: 0,
    is_tracking: true,
  });

  // Leave Balances & Requests
  const [leaveBalances, setLeaveBalances] = useState<LeaveBalance[]>([]);
  const [leaveRequests, setLeaveRequests] = useState<LeaveRequest[]>([]);

  // Connectivity & Sync
  const [connection, setConnection] = useState<ConnectionState>({
    is_online: true,
    last_ping_latency_ms: 12,
    last_successful_sync: new Date().toISOString(),
    pending_queue_count: 0,
  });

  // Initial Load: Check session and hardware
  useEffect(() => {
    const existing = getStoredUserSession();
    if (existing) {
      setSession(existing);
    }
    getNativeDeviceInfo().then(setDeviceInfo);
    setConnection((prev) => ({
      ...prev,
      pending_queue_count: getOfflineQueue().length,
    }));
  }, []);

  // Load balances & leaves when logged in
  const refreshLeaveData = useCallback(async () => {
    try {
      const [bals, reqs] = await Promise.all([getLeaveBalances(), getLeaveRequests()]);
      setLeaveBalances(bals);
      setLeaveRequests(reqs);
    } catch (e) {
      console.warn('Failed to refresh leaves:', e);
    }
  }, []);

  useEffect(() => {
    if (session) {
      refreshLeaveData();
    }
  }, [session, refreshLeaveData]);

  // Real-time Shift Stopwatch
  useEffect(() => {
    const timer = setInterval(() => {
      setAttendance((prev) => {
        if (prev.mode === 'CLOCKED_IN') {
          return {
            ...prev,
            totalWorkedSeconds: prev.totalWorkedSeconds + 1,
          };
        } else if (prev.mode === 'ON_BREAK') {
          return {
            ...prev,
            totalBreakSeconds: prev.totalBreakSeconds + 1,
          };
        }
        return prev;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Active Window & Idle Poller (every 5 seconds)
  useEffect(() => {
    const poller = setInterval(async () => {
      if (activeWindow.is_tracking) {
        try {
          const info = await getActiveWindowInfo();
          setActiveWindow((prev) => ({
            ...info,
            is_tracking: prev.is_tracking,
          }));
        } catch {
          // ignore
        }
      }
    }, 5000);
    return () => clearInterval(poller);
  }, [activeWindow.is_tracking]);

  // Background Connection Monitor & Heartbeat (every 15s)
  useEffect(() => {
    const monitor = setInterval(async () => {
      const { online, latencyMs } = await pingBackend();
      setConnection((prev) => ({
        ...prev,
        is_online: online,
        last_ping_latency_ms: latencyMs > 0 ? latencyMs : prev.last_ping_latency_ms,
        pending_queue_count: getOfflineQueue().length,
      }));

      // If online and queue has items, auto-flush
      if (online) {
        const queue = getOfflineQueue();
        if (queue.length > 0) {
          clearOfflineQueue();
          setConnection((prev) => ({
            ...prev,
            pending_queue_count: 0,
            last_successful_sync: new Date().toISOString(),
          }));
        }
      }
    }, 15000);
    return () => clearInterval(monitor);
  }, []);

  // Periodic Telemetry Heartbeat (every 60s)
  useEffect(() => {
    const hb = setInterval(() => {
      if (session) {
        sendDeviceHeartbeat(deviceInfo);
        setDeviceInfo((prev) => ({
          ...prev,
          last_heartbeat: new Date().toISOString(),
        }));
      }
    }, 60000);
    return () => clearInterval(hb);
  }, [session, deviceInfo]);

  // Attendance Actions
  const handleClockAction = async (
    action: 'CLOCK_IN' | 'CLOCK_OUT' | 'BREAK_START' | 'BREAK_END',
    note?: string,
    locationData?: {
      latitude?: number;
      longitude?: number;
      accuracy_meters?: number;
      permission_status?: any;
      ssid?: string;
    }
  ) => {
    const nowIso = new Date().toISOString();
    const event = await submitAttendanceEvent(action, note, locationData);

    setAttendance((prev) => {
      let newMode = prev.mode;
      let clockInTime = prev.clockInTime;
      let clockOutTime = prev.clockOutTime;
      let currentBreakType = prev.currentBreakType;
      let currentBreakStartTime = prev.currentBreakStartTime;

      if (action === 'CLOCK_IN') {
        newMode = 'CLOCKED_IN';
        if (!clockInTime) clockInTime = nowIso;
        sendDesktopNotification('Workstation Clock-In', 'Shift successfully started. Have a productive day!');
      } else if (action === 'CLOCK_OUT') {
        newMode = 'CLOCKED_OUT';
        clockOutTime = nowIso;
        sendDesktopNotification('Workstation Clock-Out', 'Shift ended. Summary recorded.');
      } else if (action === 'BREAK_START') {
        newMode = 'ON_BREAK';
        currentBreakType = note ? note.replace('Break: ', '') : 'Rest';
        currentBreakStartTime = nowIso;
        sendDesktopNotification('Break Started', `Enjoy your ${currentBreakType} break.`);
      } else if (action === 'BREAK_END') {
        newMode = 'CLOCKED_IN';
        currentBreakType = null;
        currentBreakStartTime = null;
        sendDesktopNotification('Break Ended', 'Shift resumed. Tracking active.');
      }

      return {
        ...prev,
        mode: newMode,
        clockInTime,
        clockOutTime,
        currentBreakType,
        currentBreakStartTime,
        events: [event, ...prev.events],
      };
    });

    setConnection((prev) => ({
      ...prev,
      pending_queue_count: getOfflineQueue().length,
    }));
  };

  // Activity Tracking Toggle
  const handleToggleTracking = (enabled: boolean) => {
    setActiveWindow((prev) => ({
      ...prev,
      is_tracking: enabled,
    }));
    sendDesktopNotification(
      'Tracking Privacy Mode',
      enabled ? 'Activity tracking resumed.' : 'Activity tracking paused.'
    );
  };

  // Force Sync Button
  const handleForceSync = () => {
    clearOfflineQueue();
    setConnection((prev) => ({
      ...prev,
      pending_queue_count: 0,
      last_successful_sync: new Date().toISOString(),
    }));
  };

  // If not logged in, show Login Screen
  if (!session) {
    return (
      <LoginScreen
        deviceId={deviceInfo.device_id}
        onLoginSuccess={(newSession) => {
          setSession(newSession);
          setCurrentScreen('dashboard');
        }}
      />
    );
  }

  return (
    <div className="app-shell">
      {/* Top Application Header */}
      <Navigation
        currentScreen={currentScreen}
        onNavigate={setCurrentScreen}
        connection={connection}
        onForceSync={handleForceSync}
      />

      {/* Screen Router */}
      <main className="flex-1">
        {currentScreen === 'dashboard' && (
          <DashboardScreen
            session={session}
            attendance={attendance}
            activeWindow={activeWindow}
            leaveBalances={leaveBalances}
            connection={connection}
            onNavigate={setCurrentScreen}
            onClockAction={handleClockAction}
            onForceSync={handleForceSync}
          />
        )}

        {currentScreen === 'attendance' && (
          <AttendanceScreen
            attendance={attendance}
            onClockAction={handleClockAction}
          />
        )}

        {currentScreen === 'activity' && (
          <ActivityScreen
            activeWindow={activeWindow}
            onToggleTracking={handleToggleTracking}
          />
        )}

        {currentScreen === 'leave_apply' && (
          <LeaveApplyScreen
            balances={leaveBalances}
            onNavigate={setCurrentScreen}
            onLeaveSubmitted={refreshLeaveData}
          />
        )}

        {currentScreen === 'leave_history' && (
          <LeaveHistoryScreen
            leaveRequests={leaveRequests}
            onNavigate={setCurrentScreen}
            onRefresh={refreshLeaveData}
          />
        )}

        {currentScreen === 'device_info' && (
          <DeviceInfoScreen
            deviceInfo={deviceInfo}
            onRefresh={() => getNativeDeviceInfo().then(setDeviceInfo)}
          />
        )}

        {currentScreen === 'settings' && (
          <SettingsScreen
            onLogout={() => {
              setSession(null);
              setCurrentScreen('login');
            }}
            onForceSync={handleForceSync}
          />
        )}
      </main>
    </div>
  );
}
