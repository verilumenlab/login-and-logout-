import { useCallback, useEffect, useState } from 'react';
import './App.css';
import { DeviceInfo, ScreenId, UserSession } from './types';
import { getNativeDeviceInfo, setUpdateContext } from './api/ipc';
import { clearLocalSession, getStoredUserSession, logoutUser, rememberDeviceIdentifier } from './api/backend';
import { bindBreakQueueToUser } from './attendance/breakTracker';
import { bindQueueToUser } from './presence/tracker';
import { usePresenceTracker } from './presence/usePresenceTracker';

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

  useEffect(() => {
    getNativeDeviceInfo().then((info) => {
      setDevice(info);
      rememberDeviceIdentifier(info.device_id);
    });
  }, []);

  const handleSessionExpired = useCallback((reason?: 'expired' | 'blocked') => {
    clearLocalSession();
    setSession(null);
    setNotice(
      reason === 'blocked'
        ? 'This device was blocked by an administrator. Contact HR/Admin to resume access.'
        : 'Your session expired. Please sign in again — your login times are kept on this laptop.'
    );
  }, []);

  const { status, breakStatus, dataVersion, refresh, recordAppLogout, recordWorkLogin, recordWorkLogout } =
    usePresenceTracker(device, session !== null, handleSessionExpired, session);

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
      setSession(null);
    }
  };

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
      />
      <UpdateBanner />
      <main className="app-main">
        {screen === 'dashboard' && (
          <DashboardScreen
            session={session}
            dataVersion={dataVersion}
            breakStatus={breakStatus}
            onWorkLogin={recordWorkLogin}
            onWorkLogout={recordWorkLogout}
          />
        )}
        {screen === 'presence' && <PresenceScreen tracker={status} dataVersion={dataVersion} onSyncNow={refresh} />}
        {screen === 'leave' && <LeaveScreen dataVersion={dataVersion} />}
      </main>
    </div>
  );
}
