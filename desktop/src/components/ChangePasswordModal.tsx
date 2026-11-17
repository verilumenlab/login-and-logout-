import React, { useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, Lock, X } from 'lucide-react';
import { changePassword } from '../api/backend';
import { clearSavedLogin, saveLoginCredentials } from '../api/savedLogin';

interface ChangePasswordModalProps {
  email: string;
  onClose: () => void;
}

export const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({ email, onClose }) => {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (newPassword.length < 8) return setError('New password must be at least 8 characters.');
    if (newPassword !== confirmPassword) return setError('New password and confirmation do not match.');
    if (newPassword === currentPassword) return setError('New password must be different.');

    setLoading(true);
    try {
      const message = await changePassword(currentPassword, newPassword);
      await clearSavedLogin();
      await saveLoginCredentials(email, newPassword);
      setSuccess(message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not change password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Change password">
      <div className="modal-card">
        <div className="card-title-row">
          <span className="card-title">Change password</span>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close">
            <X className="icon-sm" />
          </button>
        </div>
        <p className="muted-text">Use a strong password you have not used before.</p>

        {error && (
          <div className="alert-error text-xs">
            <AlertCircle className="icon-xs" /> {error}
          </div>
        )}
        {success && (
          <div className="alert-success text-xs">
            <CheckCircle2 className="icon-xs" /> {success}
          </div>
        )}

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="chg-current">Current password</label>
            <div className="input-group">
              <Lock className="input-icon" />
              <input
                id="chg-current"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="chg-new">New password</label>
            <div className="input-group">
              <Lock className="input-icon" />
              <input
                id="chg-new"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="chg-confirm">Confirm new password</label>
            <div className="input-group">
              <Lock className="input-icon" />
              <input
                id="chg-confirm"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={8}
                required
              />
            </div>
          </div>
          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="icon-sm spin" />
                &nbsp;Saving…
              </>
            ) : (
              'Update password'
            )}
          </button>
        </form>
      </div>
    </div>
  );
};
