import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { DeviceInfo, ScreenId, UserSession } from './types';
import { getNativeDeviceInfo, setUpdateContext, showDesktopNotification } from './api/ipc';
import { clearLocalSession, getStoredUserSession, logoutUser, rememberDeviceIdentifier } from './api/backend';
import { bindBreakQueueToUser } from './attendance/breakTracker';
import { bindQueueToUser } from './presence/tracker';
import { usePresenceTracker, WorkdayCheckRequest } from './presence/usePresenceTracker';
import {
  clearEarlyLogoutPrompt,
  logoutNotice,
  markEarlyLogoutPromptOpened,
  markNineHourConfirmedWithExtension,
  shouldConfirmEarlyLogout,
  workedMinutesNow,
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
  /** When early-logout confirm finishes with Logout, also sign out of the app. */
  const [pendingAppSignOut, setPendingAppSignOut] = useState(false);

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

  const {
    status,
    breakStatus,
    dataVersion,
    refresh,
    recordAppLogout,
    recordWorkLogin,
    recordWorkLogout,
    syncWorkStartFromServer,
  } = usePresenceTracker(device, session !== null, handleSessionExpired, session, setNotice, setWorkdayCheck);

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

  const openEarlyLogoutPrompt = useCallback((alsoSignOutApp: boolean) => {
    const worked = workedMinutesNow();
    const openedAt = markEarlyLogoutPromptOpened();
    setPendingAppSignOut(alsoSignOutApp);
    setWorkdayCheck({ kind: 'early_logout', openedAt, workedMinutes: worked });
    void showDesktopNotification(
      'WorkPulse — Early logout',
      'You have not completed 9 working hours. Confirm continue working or logout within 10 minutes.'
    );
  }, []);

  const finishAppSignOut = useCallback(async () => {
    setLoggingOut(true);
    try {
      await recordAppLogout();
      await logoutUser();
    } finally {
      setLoggingOut(false);
      setWorkdayCheck(null);
      setPendingAppSignOut(false);
      setSession(null);
    }
  }, [recordAppLogout]);

  const handleLogout = async () => {
    // Sign-out from app always ends the work session; confirm if under 9h.
    if (status.isLoggedIn && shouldConfirmEarlyLogout()) {
      openEarlyLogoutPrompt(true);
      return;
    }
    await finishAppSignOut();
  };

  const handleWorkLogoutClick = useCallback(async () => {
    if (shouldConfirmEarlyLogout()) {
      openEarlyLogoutPrompt(false);
      return;
    }
    await recordWorkLogout('nine_hour_manual');
    setNotice(logoutNotice('nine_hour_manual'));
  }, [openEarlyLogoutPrompt, recordWorkLogout]);

  const handleContinue = useCallback(() => {
    if (!workdayCheck) return;
    if (workdayCheck.kind === 'nine_hour') {
      markNineHourConfirmedWithExtension();
      setWorkdayCheck(null);
      setNotice('Confirmed — you have 10 more minutes, then the day will end automatically.');
      return;
    }
    // Early logout: continue working
    clearEarlyLogoutPrompt();
    setWorkdayCheck(null);
    setPendingAppSignOut(false);
    setNotice('Session kept active — continue working toward 9 hours.');
  }, [workdayCheck]);

  const handleConfirmLogout = useCallback(async () => {
    if (!workdayCheck) return;
    const kind = workdayCheck.kind;
    const signOutApp = pendingAppSignOut;
    setWorkdayCheck(null);
    clearEarlyLogoutPrompt();

    if (kind === 'nine_hour') {
      await recordWorkLogout('nine_hour_manual');
      setNotice(logoutNotice('nine_hour_manual'));
      return;
    }

    await recordWorkLogout('early_logout_confirmed');
    setNotice(logoutNotice('early_logout_confirmed'));
    if (signOutApp) {
      setLoggingOut(true);
      try {
        await logoutUser();
      } finally {
        setLoggingOut(false);
        setPendingAppSignOut(false);
        setSession(null);
      }
    }
  }, [workdayCheck, pendingAppSignOut, recordWorkLogout]);

  const handleCheckTimeout = useCallback(async () => {
    if (!workdayCheck) return;
    const kind = workdayCheck.kind;
    const signOutApp = pendingAppSignOut;
    setWorkdayCheck(null);
    clearEarlyLogoutPrompt();

    if (kind === 'nine_hour') {
      await recordWorkLogout('nine_hour_no_response');
      setNotice(logoutNotice('nine_hour_no_response'));
      return;
    }

    await recordWorkLogout('early_logout_no_response');
    setNotice(logoutNotice('early_logout_no_response'));
    if (signOutApp) {
      setLoggingOut(true);
      try {
        await logoutUser();
      } finally {
        setLoggingOut(false);
        setPendingAppSignOut(false);
        setSession(null);
      }
    }
  }, [workdayCheck, pendingAppSignOut, recordWorkLogout]);

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
            onWorkLogout={handleWorkLogoutClick}
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
          kind={workdayCheck.kind}
          openedAt={workdayCheck.openedAt}
          workedMinutes={workdayCheck.workedMinutes}
          onContinue={handleContinue}
          onLogout={() => void handleConfirmLogout()}
          onTimeout={() => void handleCheckTimeout()}
        />
      )}
    </div>
  );
}
