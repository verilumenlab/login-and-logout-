import React, { useState, useEffect } from 'react';
import {
  Settings,
  Bell,
  Power,
  Server,
  Database,
  Lock,
  LogOut,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import {
  setAutoStart,
  getAutoStartStatus,
  sendDesktopNotification,
  clearOfflineQueue,
  getOfflineQueue,
} from '../api/ipc';
import {
  getBackendServerUrl,
  setBackendServerUrl,
  pingBackend,
  logoutUser,
} from '../api/backend';

interface SettingsScreenProps {
  onLogout: () => void;
  onForceSync: () => void;
}

export const SettingsScreen: React.FC<SettingsScreenProps> = ({
  onLogout,
  onForceSync,
}) => {
  const [autostart, setAutostartState] = useState(false);
  const [notifications, setNotifications] = useState(
    localStorage.getItem('__notif_enabled') !== 'false'
  );
  const [serverUrl, setServerUrl] = useState(getBackendServerUrl());

  const [testingPing, setTestingPing] = useState(false);
  const [pingResult, setPingResult] = useState<string | null>(null);
  const [queueCount, setQueueCount] = useState(getOfflineQueue().length);

  useEffect(() => {
    getAutoStartStatus().then(setAutostartState);
  }, []);

  const handleToggleAutostart = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setAutostartState(val);
    await setAutoStart(val);
  };

  const handleToggleNotifications = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.checked;
    setNotifications(val);
    localStorage.setItem('__notif_enabled', val ? 'true' : 'false');
  };

  const handleTestNotification = async () => {
    await sendDesktopNotification(
      'Workforce Agent Notification',
      'Desktop notifications are configured and active.'
    );
  };

  const handleTestConnection = async () => {
    setTestingPing(true);
    setPingResult(null);
    setBackendServerUrl(serverUrl);
    const { online, latencyMs } = await pingBackend();
    setTestingPing(false);
    if (online) {
      setPingResult(`Connected successfully (${latencyMs}ms latency)`);
    } else {
      setPingResult('Cannot connect to endpoint. Please verify server URL.');
    }
  };

  const handleClearCache = () => {
    if (confirm('Clear local offline queue? Un-synced events will be discarded.')) {
      clearOfflineQueue();
      setQueueCount(0);
    }
  };

  const handleSignOut = async () => {
    if (confirm('Sign out of Enterprise Attendance Agent? Tokens will be cleared from OS Credential Vault.')) {
      await logoutUser();
      onLogout();
    }
  };

  return (
    <div className="screen-container">
      {/* Header */}
      <div className="screen-header">
        <div>
          <h2 className="screen-title flex items-center gap-2">
            <Settings className="w-5 h-5 text-indigo-600" />
            Agent Settings
          </h2>
          <p className="screen-subtitle">Workstation preferences, connectivity, and credential management</p>
        </div>
      </div>

      {/* Auto-Start with User Consent */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
              <Power className="w-3.5 h-3.5 text-indigo-600" />
              System Auto-Start
            </div>
            <p className="text-[11px] text-slate-500 leading-normal max-w-[280px]">
              Automatically launch agent upon OS boot/logon with user consent (Windows Registry / macOS LaunchAgent).
            </p>
          </div>
          <input
            type="checkbox"
            checked={autostart}
            onChange={handleToggleAutostart}
            className="w-4 h-4 rounded text-indigo-600 mt-1 cursor-pointer"
          />
        </div>
      </div>

      {/* Notifications */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div className="space-y-0.5">
            <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
              <Bell className="w-3.5 h-3.5 text-blue-600" />
              Desktop Notifications
            </div>
            <p className="text-[11px] text-slate-500 leading-normal max-w-[280px]">
              Display alerts for shift check-ins, break limits, and approved leaves.
            </p>
          </div>
          <input
            type="checkbox"
            checked={notifications}
            onChange={handleToggleNotifications}
            className="w-4 h-4 rounded text-indigo-600 mt-1 cursor-pointer"
          />
        </div>

        {notifications && (
          <div className="mt-2 pt-2 border-t border-slate-100 flex justify-end">
            <button
              onClick={handleTestNotification}
              className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium"
            >
              Test Notification Alert
            </button>
          </div>
        )}
      </div>

      {/* API Gateway URL */}
      <div className="card space-y-2">
        <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
          <Server className="w-3.5 h-3.5 text-slate-600" />
          Backend API Gateway Endpoint
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            className="flex-1 px-2.5 py-1.5 text-xs border border-slate-300 rounded-lg font-mono"
            placeholder="http://localhost:8000/api/v1"
          />
          <button
            onClick={handleTestConnection}
            disabled={testingPing}
            className="btn btn-secondary text-xs px-3 py-1.5 flex items-center gap-1"
          >
            {testingPing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            Test
          </button>
        </div>

        {pingResult && (
          <div
            className={`p-2 rounded text-xs flex items-center gap-1.5 ${
              pingResult.includes('successfully')
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'bg-red-50 text-red-700 border border-red-200'
            }`}
          >
            {pingResult.includes('successfully') ? (
              <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            )}
            <span>{pingResult}</span>
          </div>
        )}
      </div>

      {/* Offline Storage Buffer */}
      <div className="card space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-slate-800 flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-slate-600" />
            Offline Queue Buffer
          </div>
          <span className="text-xs font-mono font-bold text-slate-700">
            {queueCount} records
          </span>
        </div>
        <p className="text-[11px] text-slate-500">
          Attendance actions and activity telemetry cached during network interruptions.
        </p>

        <div className="flex gap-2 pt-1">
          <button
            onClick={() => {
              onForceSync();
              setTimeout(() => setQueueCount(getOfflineQueue().length), 1000);
            }}
            disabled={queueCount === 0}
            className="btn btn-secondary flex-1 text-xs py-1.5 flex items-center justify-center gap-1 disabled:opacity-40"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Flush Queue Now
          </button>
          <button
            onClick={handleClearCache}
            disabled={queueCount === 0}
            className="btn btn-secondary text-xs px-2.5 py-1.5 text-red-600 hover:text-red-700 disabled:opacity-40"
            title="Clear Queue"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Security Info & Logout */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2 text-xs text-slate-700 font-semibold">
          <Lock className="w-3.5 h-3.5 text-emerald-600" />
          OS Credential Storage Facility
        </div>
        <div className="p-2.5 bg-slate-50 border border-slate-100 rounded text-[11px] text-slate-600 space-y-1">
          <p>Tokens encrypted and stored in operating system vault:</p>
          <ul className="list-disc list-inside text-slate-500 font-mono text-[10px]">
            <li>Windows: Windows Credential Manager (CredWriteW / CredReadW)</li>
            <li>macOS: Keychain Services (SecKeychainAddGenericPassword)</li>
          </ul>
        </div>

        <button
          onClick={handleSignOut}
          className="btn btn-danger w-full text-xs py-2 flex items-center justify-center gap-1.5 shadow-sm"
        >
          <LogOut className="w-3.5 h-3.5" />
          Sign Out & Clear Vault Credentials
        </button>
      </div>
    </div>
  );
};
