import React, { useState } from 'react';
import {
  Lock,
  Mail,
  Server,
  ShieldCheck,
  AlertCircle,
  Loader2,
  HardDrive,
  Eye,
  EyeOff,
} from 'lucide-react';
import { loginUser, getBackendServerUrl, setBackendServerUrl } from '../api/backend';
import { UserSession } from '../types';

interface LoginScreenProps {
  onLoginSuccess: (session: UserSession) => void;
  deviceId: string;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLoginSuccess, deviceId }) => {
  const [email, setEmail] = useState('employee@enterprise.corp');
  const [password, setPassword] = useState('WelcomeTitan123!');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberDevice, setRememberDevice] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Server URL custom config
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [serverUrl, setServerUrl] = useState(getBackendServerUrl());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setError('Please provide your corporate email and password.');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setBackendServerUrl(serverUrl);
      const session = await loginUser(email, password, deviceId);
      onLoginSuccess(session);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Authentication failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        {/* Header */}
        <div className="login-header">
          <div className="brand-badge">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <h2>Enterprise Employee Agent</h2>
          <p className="subtitle">Secure Attendance & Activity Tracker</p>
          <div className="mt-2 inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
            EMPLOYEE WORKSTATION ONLY
          </div>
        </div>

        {/* Role Enforcement Notice */}
        <div className="p-2.5 rounded-lg bg-amber-50/80 border border-amber-200 text-amber-800 text-[11px] leading-tight flex items-start gap-1.5 my-1">
          <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
          <span>
            <strong>Role Notice:</strong> This desktop application is exclusively for <strong>Employee</strong> accounts.
            Admin, HR, and Manager accounts must sign in via the web application.
          </span>
        </div>

        {/* Security Assurance Banner */}
        <div className="security-banner">
          <Lock className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
          <span>Secured with OS Credential Vault (Argon2id + AES)</span>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="alert-error">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <div className="text-xs">{error}</div>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label>Corporate Email</label>
            <div className="input-group">
              <Mail className="input-icon" />
              <input
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label>Password</label>
            <div className="input-group">
              <Lock className="input-icon" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="input-toggle"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="login-row">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={rememberDevice}
                onChange={(e) => setRememberDevice(e.target.checked)}
              />
              <span>Remember this device</span>
            </label>
            <button
              type="button"
              className="text-link"
              onClick={() => setShowServerConfig(!showServerConfig)}
            >
              <Server className="w-3 h-3 inline mr-1" />
              Endpoint
            </button>
          </div>

          {showServerConfig && (
            <div className="server-config-panel">
              <label>API Gateway Endpoint</label>
              <input
                type="text"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                placeholder="http://localhost:8000/api/v1"
              />
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Authenticating...
              </>
            ) : (
              'Sign In to Workstation'
            )}
          </button>
        </form>

        {/* Device Identifier */}
        <div className="login-footer">
          <div className="device-id-badge">
            <HardDrive className="w-3 h-3 text-slate-400 mr-1" />
            <span>Hardware ID: </span>
            <code>{deviceId}</code>
          </div>
        </div>
      </div>
    </div>
  );
};

