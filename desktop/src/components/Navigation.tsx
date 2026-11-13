import React from 'react';
import {
  Home,
  Clock,
  Activity,
  Calendar,
  HardDrive,
  Settings,
  RefreshCw,
} from 'lucide-react';
import { ScreenId, ConnectionState } from '../types';

interface NavigationProps {
  currentScreen: ScreenId;
  onNavigate: (screen: ScreenId) => void;
  connection: ConnectionState;
  onForceSync: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({
  currentScreen,
  onNavigate,
  connection,
  onForceSync,
}) => {
  const navItems: { id: ScreenId; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'dashboard', label: 'Home', icon: Home },
    { id: 'attendance', label: 'Attendance', icon: Clock },
    { id: 'activity', label: 'Activity', icon: Activity },
    { id: 'leave_history', label: 'Leaves', icon: Calendar },
    { id: 'device_info', label: 'Device', icon: HardDrive },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <>
      {/* Top Application Header */}
      <header className="app-topbar">
        <div className="flex items-center gap-2">
          <div className="app-logo-badge">AGENT</div>
          <div>
            <h1 className="text-xs font-bold text-slate-900 leading-tight">Workforce Agent</h1>
            <span className="text-[10px] text-slate-400 font-mono">Tauri v2 • Desktop</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {connection.pending_queue_count > 0 && (
            <button
              onClick={onForceSync}
              className="flex items-center gap-1 text-[10px] font-mono font-medium text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full hover:bg-amber-100 transition-colors"
              title="Click to flush pending queue"
            >
              <RefreshCw className="w-2.5 h-2.5 animate-spin" />
              <span>{connection.pending_queue_count} queued</span>
            </button>
          )}

          <div className="connection-indicator">
            {connection.is_online ? (
              <span
                className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-100"
                title={`Online • Ping: ${connection.last_ping_latency_ms ?? 0}ms`}
              />
            ) : (
              <span
                className="w-2.5 h-2.5 rounded-full bg-amber-500 ring-2 ring-amber-100 animate-pulse"
                title="Offline Mode: All events saved locally"
              />
            )}
          </div>
        </div>
      </header>

      {/* Bottom Sticky Navigation Bar */}
      <nav className="app-bottom-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            currentScreen === item.id ||
            (item.id === 'leave_history' && currentScreen === 'leave_apply');
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`nav-tab-btn ${isActive ? 'nav-tab-active' : ''}`}
            >
              <Icon className="w-4 h-4 mb-0.5" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </>
  );
};
