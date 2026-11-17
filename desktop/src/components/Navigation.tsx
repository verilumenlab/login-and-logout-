import React from 'react';
import { CalendarDays, Clock, KeyRound, LayoutDashboard, LogOut } from 'lucide-react';
import { ScreenId, TrackerStatus, UserSession } from '../types';

interface NavigationProps {
  session: UserSession;
  currentScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
  tracker: TrackerStatus;
  onLogout: () => void;
  loggingOut: boolean;
  onChangePassword?: () => void;
}

const NAV_ITEMS: { id: ScreenId; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'presence', label: 'Login & Logout', icon: Clock },
  { id: 'leave', label: 'Leave', icon: CalendarDays },
];

export const Navigation: React.FC<NavigationProps> = ({
  session,
  currentScreen,
  onNavigate,
  tracker,
  onLogout,
  loggingOut,
  onChangePassword,
}) => (
  <>
    <header className="app-topbar">
      <div className="topbar-brand">
        <img
          className="app-logo-mark"
          src={`${import.meta.env.BASE_URL}workpulse-mark.png`}
          alt="WorkPulse"
          width={32}
          height={32}
        />
        <div>
          <div className="topbar-name">
            {session.first_name} {session.last_name}
          </div>
          <div className="topbar-sub">
            <span
              className={`status-dot ${tracker.isOnline ? 'dot-green' : 'dot-amber'}`}
              title={tracker.isOnline ? 'Connected to server' : 'Offline: events are saved on this laptop'}
            />
            {tracker.isOnline ? 'Online' : 'Offline'}
            {tracker.pendingEvents > 0 && ` • ${tracker.pendingEvents} to sync`}
          </div>
        </div>
      </div>
      <div className="topbar-actions">
        {onChangePassword && (
          <button className="btn btn-secondary btn-sm" onClick={onChangePassword} title="Change password">
            <KeyRound className="icon-xs" />
            &nbsp;Password
          </button>
        )}
        <button className="btn btn-secondary btn-sm" onClick={onLogout} disabled={loggingOut}>
          <LogOut className="icon-xs" />
          &nbsp;{loggingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
    </header>

    <nav className="app-bottom-nav">
      {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={`nav-tab-btn ${currentScreen === id ? 'nav-tab-active' : ''}`}
        >
          <Icon className="icon-sm" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  </>
);
