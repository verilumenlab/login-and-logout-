import React from 'react';
import { CalendarDays, Clock, LayoutDashboard, LogOut } from 'lucide-react';
import { ScreenId, TrackerStatus, UserSession } from '../types';

interface NavigationProps {
  session: UserSession;
  currentScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
  tracker: TrackerStatus;
  onLogout: () => void;
  loggingOut: boolean;
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
}) => (
  <>
    <header className="app-topbar">
      <div className="topbar-brand">
        <div className="app-logo-badge">WP</div>
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
      <button className="btn btn-secondary btn-sm" onClick={onLogout} disabled={loggingOut}>
        <LogOut className="icon-xs" />
        &nbsp;{loggingOut ? 'Signing out…' : 'Sign out'}
      </button>
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
