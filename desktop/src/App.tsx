import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { DeviceInfo, ScreenId, UserSession } from './types';
import { getNativeDeviceInfo, setUpdateContext } from './api/ipc';
import { clearLocalSession, getStoredUserSession, logoutUser, rememberDeviceIdentifier } from './api/backend';
import { bindBreakQueueToUser } from './attendance/breakTracker';
import { bindQueueToUser } from './presence/tracker';
import { usePresenceTracker, WorkdayCheckRequest } from './presence/usePresenceTracker';
import {
  logoutReasonForTimeout,
  markCheckpointConfirmed,
} from './presence/workdayPolicy';

import { ChangePasswordModal } from './components/ChangePasswordModal';
import { WorkdayCheckModal } from './components/WorkdayCheckModal';
import { Navigation } from './components/Navigation';
import { UpdateBanner } from './components/UpdateBanner';
import { LoginScreen } from './screens/LoginScreen';
import { DashboardScreen } from './screens/DashboardScreen';
import { PresenceScreen } from './screens/PresenceScreen';
import { LeaveScreen } from './screens/LeaveScreen';

export default function App() {
  const [session, setSession] = useState<UserSession | null>(() => {
    const stored = getStoredUserSession();
    if (stored) {
      bindQueueToUser(stored.user_id);
      bindBreakQueueToUser(stored.user_id);
    }
    return stored;
  });
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [screen, setScreen] = useState<ScreenId>('dashboard');
  const [notice, setNotice] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [workdayCheck, setWorkdayCheck] = useState<WorkdayCheckRequest | null>(null);

  useEffect(() => {
    getNativeDeviceInfo().then((info) => {
      setDevice(info);
      rememberDeviceIdentifier(info.device_id);
    });
  }, []);

  const handleSessionExpired = useCallback((reason?: 'expired' | 'blocked') => {
    clearLocalSession();
    setSession(null);
    setWorkdayCheck(null);
    setNotice(
      reason === 'blocked'
        ? 'This device was blocked by an administrator. Contact HR/Admin to resume access.'
        : 'Your session expired. Please sign in again — your login times are kept on this laptop.'
    );
  }, []);

  const { status, breakStatus, dataVersion, refresh, recordAppLogout, recordWorkLogin, recordWorkLogout, syncWorkStartFromServer } =
    usePresenceTracker(device, session !== null, handleSessionExpired, session, setNotice, setWorkdayCheck);

  const handleLogin = (newSession: UserSession) => {
    bindQueueToUser(newSession.user_id);
    bindBreakQueueToUser(newSession.user_id);
    setNotice(null);
    setScreen('dashboard');
    setSession(newSession);
    void setUpdateContext({
      deviceId: device?.device_id || localStorage.getItem('__device_id') || null,
      channel: import.meta.env.VITE_RELEASE_CHANNEL || 'production',
    });
  };

  const handleLogout = async () => {
    setLoggingOut(true);
    try {
      await recordAppLogout();
      await logoutUser();
    } finally {
      setLoggingOut(false);
      setWorkdayCheck(null);
      setSession(null);
    }
  };

  const handleStayInOffice = useCallback(() => {
    if (!workdayCheck) return;
    markCheckpointConfirmed(workdayCheck.checkpoint);
    setWorkdayCheck(null);
    setNotice(
      workdayCheck.checkpoint === '9h'
        ? 'Thanks — marked as still in office after 9 hours. Log out when you finish.'
        : 'Thanks — marked as still in office after 7 hours.'
    );
  }, [workdayCheck]);

  const handleLeaveOffice = useCallback(async () => {
    setWorkdayCheck(null);
    await recordWorkLogout('still_in_office_no');
    setNotice('Logged out — you confirmed you are not in the office.');
  }, [recordWorkLogout]);

  const handleCheckTimeout = useCallback(async () => {
    if (!workdayCheck) return;
    const reason = logoutReasonForTimeout(workdayCheck.checkpoint);
    setWorkdayCheck(null);
    await recordWorkLogout(reason);
    setNotice(
      reason === 'no_response_9h'
        ? 'Auto logged out — no response after the 9-hour office check.'
        : 'Auto logged out — no response after the 7-hour office check.'
    );
  }, [workdayCheck, recordWorkLogout]);

  if (!session) {
    return <LoginScreen device={device} onLoginSuccess={handleLogin} notice={notice} />;
  }

  return (
    <div className="app-shell">
      <Navigation
        session={session}
        currentScreen={screen}
        onNavigate={setScreen}
        tracker={status}
        onLogout={handleLogout}
        loggingOut={loggingOut}
        onChangePassword={() => setShowChangePassword(true)}
      />
      <UpdateBanner />
      {notice && (
        <div className="app-notice" role="status">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}
      <main className="app-main">
        {screen === 'dashboard' && (
          <DashboardScreen
            session={session}
            dataVersion={dataVersion}
            breakStatus={breakStatus}
            onWorkLogin={recordWorkLogin}
            onWorkLogout={() => recordWorkLogout()}
            onFirstLoginKnown={syncWorkStartFromServer}
          />
        )}
        {screen === 'presence' && <PresenceScreen tracker={status} dataVersion={dataVersion} onSyncNow={refresh} />}
        {screen === 'leave' && <LeaveScreen dataVersion={dataVersion} />}
      </main>
      {showChangePassword && (
        <ChangePasswordModal email={session.email} onClose={() => setShowChangePassword(false)} />
      )}
      {workdayCheck && (
        <WorkdayCheckModal
          checkpoint={workdayCheck.checkpoint}
          openedAt={workdayCheck.openedAt}
          onStay={handleStayInOffice}
          onLeave={() => void handleLeaveOffice()}
          onTimeout={() => void handleCheckTimeout()}
        />
      )}
    </div>
  );
}
