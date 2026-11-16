import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react';
import { getBackendServerUrl, loginUser, rememberDeviceIdentifier, setBackendServerUrl } from '../api/backend';
import { clearSavedLogin, getSavedLogin, saveLoginCredentials } from '../api/savedLogin';
import { DeviceInfo, UserSession } from '../types';

const logoSrc = `${import.meta.env.BASE_URL}workpulse-logo.png`;

interface LoginScreenProps {
  device: DeviceInfo | null;
  onLoginSuccess: (session: UserSession) => void;
  notice?: string | null;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ device, onLoginSuccess, notice }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [saveLogin, setSaveLogin] = useState(false);
  const [hasSavedLogin, setHasSavedLogin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [credsReady, setCredsReady] = useState(false);
  const autoLoginTried = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const saved = await getSavedLogin();
      if (cancelled) return;
      if (saved) {
        setEmail(saved.email);
        setPassword(saved.password);
        setSaveLogin(true);
        setHasSavedLogin(true);
      }
      setCredsReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = async (emailValue: string, passwordValue: string, remember: boolean) => {
    if (!device) {
      setError('Still reading this laptop’s details. Please try again in a moment.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setBackendServerUrl(getBackendServerUrl());
      rememberDeviceIdentifier(device.device_id);
      const session = await loginUser(emailValue.trim(), passwordValue, device);
      if (remember) {
        await saveLoginCredentials(emailValue.trim(), passwordValue);
        setHasSavedLogin(true);
      } else {
        await clearSavedLogin();
        setHasSavedLogin(false);
      }
      onLoginSuccess(session);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
    } finally {
      setLoading(false);
    }
  };

  // If credentials were saved earlier, signing in uses them as soon as the laptop is ready.
  useEffect(() => {
    if (!credsReady || !device || !hasSavedLogin || autoLoginTried.current) return;
    if (!email.trim() || !password) return;
    autoLoginTried.current = true;
    void signIn(email, password, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credsReady, device, hasSavedLogin, email, password]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await signIn(email, password, saveLogin);
  };

  const handleClearSaved = async () => {
    await clearSavedLogin();
    setHasSavedLogin(false);
    setSaveLogin(false);
    setPassword('');
    setError(null);
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <img className="brand-logo-full" src={logoSrc} alt="WorkPulse" />
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

          <label className="checkbox-label login-save-label">
            <input
              type="checkbox"
              checked={saveLogin}
              onChange={(e) => setSaveLogin(e.target.checked)}
            />
            <span>Save email &amp; password on this laptop</span>
          </label>

          {hasSavedLogin && (
            <div className="login-saved-row">
              <span className="field-hint">Saved login ready — Sign in uses it automatically.</span>
              <button type="button" className="text-link" onClick={() => void handleClearSaved()}>
                Clear saved
              </button>
            </div>
          )}

          <button type="submit" disabled={loading || !device} className="btn btn-primary btn-block">
            {loading ? (
              <>
                <Loader2 className="icon-sm spin" />
                &nbsp;Signing in…
              </>
            ) : hasSavedLogin ? (
              'Sign in with saved login'
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
