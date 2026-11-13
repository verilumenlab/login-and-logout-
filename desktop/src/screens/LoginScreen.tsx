import React, { useState } from 'react';
import { AlertCircle, Eye, EyeOff, Loader2, Lock, Mail, Server, ShieldCheck } from 'lucide-react';
import { getBackendServerUrl, loginUser, setBackendServerUrl } from '../api/backend';
import { DeviceInfo, UserSession } from '../types';

interface LoginScreenProps {
  device: DeviceInfo | null;
  onLoginSuccess: (session: UserSession) => void;
  notice?: string | null;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ device, onLoginSuccess, notice }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showServerConfig, setShowServerConfig] = useState(false);
  const [serverUrl, setServerUrl] = useState(getBackendServerUrl());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!device) {
      setError('Still reading this laptop’s details. Please try again in a moment.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setBackendServerUrl(serverUrl);
      onLoginSuccess(await loginUser(email.trim(), password, device));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <div className="brand-badge">
            <ShieldCheck className="icon-md icon-white" />
          </div>
          <h2>WorkPulse Employee</h2>
          <p className="subtitle">Sign in once — your login and logout are recorded automatically.</p>
        </div>

        <div className="notice-box">
          <AlertCircle className="icon-sm tone-amber" />
          <span>
            This app is for <strong>employee</strong> accounts only. Managers, HR and admins use the web portal.
          </span>
        </div>

        {(error || notice) && (
          <div className="alert-error">
            <AlertCircle className="icon-sm" />
            <div className="text-xs">{error || notice}</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="login-email">Work email</label>
            <div className="input-group">
              <Mail className="input-icon" />
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="login-password">Password</label>
            <div className="input-group">
              <Lock className="input-icon" />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <button
                type="button"
                className="input-toggle"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? <EyeOff className="icon-sm" /> : <Eye className="icon-sm" />}
              </button>
            </div>
          </div>

          <div className="login-row">
            <span />
            <button type="button" className="text-link" onClick={() => setShowServerConfig(!showServerConfig)}>
              <Server className="icon-xs" /> Server
            </button>
          </div>

          {showServerConfig && (
            <div className="server-config-panel">
              <label htmlFor="server-url">Server address</label>
              <input
                id="server-url"
                type="text"
                value={serverUrl}
                onChange={(e) => setServerUrl(e.target.value)}
                placeholder="https://hr.company.com/api/v1"
              />
            </div>
          )}

          <button type="submit" disabled={loading || !device} className="btn btn-primary btn-block">
            {loading ? (
              <>
                <Loader2 className="icon-sm spin" />
                &nbsp;Signing in…
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        {device && (
          <div className="login-footer">
            <div className="device-id-badge">
              <span>Laptop:</span>
              <code>{device.machine_name}</code>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
