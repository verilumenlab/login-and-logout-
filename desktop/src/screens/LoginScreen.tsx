import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2, Lock, Mail } from 'lucide-react';
import {
  forgotPassword,
  getBackendServerUrl,
  loginUser,
  resetPasswordWithOtp,
  setBackendServerUrl,
} from '../api/backend';
import { clearSavedLogin, getSavedLogin, saveLoginCredentials } from '../api/savedLogin';
import { DeviceInfo, UserSession } from '../types';

const logoSrc = `${import.meta.env.BASE_URL}workpulse-mark.png`;

interface LoginScreenProps {
  device: DeviceInfo | null;
  onLoginSuccess: (session: UserSession) => void;
  notice?: string | null;
  /** After app update: skip saved-password auto sign-in; employee must enter email. */
  requireManualSignIn?: boolean;
}

type AuthMode = 'login' | 'forgot' | 'reset';

export const LoginScreen: React.FC<LoginScreenProps> = ({
  device,
  onLoginSuccess,
  notice,
  requireManualSignIn = false,
}) => {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [saveLogin, setSaveLogin] = useState(false);
  const [hasSavedLogin, setHasSavedLogin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [credsReady, setCredsReady] = useState(false);
  const autoLoginTried = useRef(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (requireManualSignIn) {
        await clearSavedLogin();
        if (cancelled) return;
        setEmail('');
        setPassword('');
        setSaveLogin(false);
        setHasSavedLogin(false);
        setCredsReady(true);
        return;
      }
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
  }, [requireManualSignIn]);

  const signIn = async (emailValue: string, passwordValue: string, remember: boolean) => {
    if (!device) {
      setError('Still reading this laptop’s details. Please try again in a moment.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      setInfo(null);
      setBackendServerUrl(getBackendServerUrl());
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

  useEffect(() => {
    if (requireManualSignIn) return;
    if (mode !== 'login') return;
    if (!credsReady || !device || !hasSavedLogin || autoLoginTried.current) return;
    if (!email.trim() || !password) return;
    autoLoginTried.current = true;
    void signIn(email, password, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, credsReady, device, hasSavedLogin, email, password, requireManualSignIn]);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await signIn(email, password, saveLogin);
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (!email.trim()) {
      setError('Enter your work email.');
      return;
    }
    setLoading(true);
    try {
      setBackendServerUrl(getBackendServerUrl());
      const message = await forgotPassword(email.trim());
      setInfo(message);
      setMode('reset');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not start password reset');
    } finally {
      setLoading(false);
    }
  };

  const handleResetSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setInfo(null);
    if (!email.trim()) return setError('Enter your work email.');
    if (otp.trim().length < 4) return setError('Enter the OTP / reset code from your email.');
    if (newPassword.length < 8) return setError('New password must be at least 8 characters.');
    if (newPassword !== confirmPassword) return setError('New password and confirmation do not match.');

    setLoading(true);
    try {
      setBackendServerUrl(getBackendServerUrl());
      const message = await resetPasswordWithOtp(email.trim(), otp.trim(), newPassword);
      await clearSavedLogin();
      setHasSavedLogin(false);
      setSaveLogin(false);
      setPassword(newPassword);
      setOtp('');
      setNewPassword('');
      setConfirmPassword('');
      setInfo(`${message} You can sign in now.`);
      setMode('login');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not reset password');
    } finally {
      setLoading(false);
    }
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
          <img className="brand-logo-mark" src={logoSrc} alt="WorkPulse" />
          <h2>WorkPulse Employee</h2>
          <p className="subtitle">
            {mode === 'login' && 'Sign in once — your login and logout are recorded automatically.'}
            {mode === 'forgot' && 'We will email a reset code if this account exists.'}
            {mode === 'reset' && 'Enter the email OTP / code and choose a new password.'}
          </p>
        </div>

        {mode === 'login' && (
          <div className="notice-box">
            <AlertCircle className="icon-sm tone-amber" />
            <span>
              This app is for <strong>employee</strong> accounts only. Managers, HR and admins use the web portal.
            </span>
          </div>
        )}

        {(error || notice) && (
          <div className="alert-error">
            <AlertCircle className="icon-sm" />
            <div className="text-xs">{error || notice}</div>
          </div>
        )}
        {info && (
          <div className="alert-success text-xs">
            <CheckCircle2 className="icon-xs" /> {info}
          </div>
        )}

        {mode === 'login' && (
          <form onSubmit={handleLoginSubmit} className="login-form">
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
              <input type="checkbox" checked={saveLogin} onChange={(e) => setSaveLogin(e.target.checked)} />
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

            <div className="login-row">
              <button
                type="button"
                className="text-link"
                onClick={() => {
                  setMode('forgot');
                  setError(null);
                  setInfo(null);
                }}
              >
                Forgot password?
              </button>
              <span />
            </div>

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
        )}

        {mode === 'forgot' && (
          <form onSubmit={handleForgotSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="forgot-email">Work email</label>
              <div className="input-group">
                <Mail className="input-icon" />
                <input
                  id="forgot-email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>
            <button type="submit" disabled={loading} className="btn btn-primary btn-block">
              {loading ? (
                <>
                  <Loader2 className="icon-sm spin" />
                  &nbsp;Sending…
                </>
              ) : (
                'Send reset code'
              )}
            </button>
            <button
              type="button"
              className="text-link"
              onClick={() => {
                setMode('login');
                setError(null);
                setInfo(null);
              }}
            >
              Back to sign in
            </button>
          </form>
        )}

        {mode === 'reset' && (
          <form onSubmit={handleResetSubmit} className="login-form">
            <div className="form-group">
              <label htmlFor="reset-email">Work email</label>
              <div className="input-group">
                <Mail className="input-icon" />
                <input
                  id="reset-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="reset-otp">OTP / reset code</label>
              <div className="input-group">
                <Lock className="input-icon" />
                <input
                  id="reset-otp"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="6-digit code"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value)}
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="reset-new">New password</label>
              <div className="input-group">
                <Lock className="input-icon" />
                <input
                  id="reset-new"
                  type={showPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </div>
            </div>
            <div className="form-group">
              <label htmlFor="reset-confirm">Confirm new password</label>
              <div className="input-group">
                <Lock className="input-icon" />
                <input
                  id="reset-confirm"
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  minLength={8}
                  required
                />
              </div>
            </div>
            <label className="checkbox-label">
              <input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} />
              <span>Show passwords</span>
            </label>
            <button type="submit" disabled={loading} className="btn btn-primary btn-block">
              {loading ? (
                <>
                  <Loader2 className="icon-sm spin" />
                  &nbsp;Updating…
                </>
              ) : (
                'Set new password'
              )}
            </button>
            <button
              type="button"
              className="text-link"
              onClick={() => {
                setMode('login');
                setError(null);
                setInfo(null);
              }}
            >
              Back to sign in
            </button>
          </form>
        )}

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
