import { useEffect, useState } from 'react';
import {
  UpdateStatusPayload,
  checkForUpdates,
  installUpdateNow,
  onUpdateStatus,
} from '../api/ipc';

export function UpdateBanner() {
  const [status, setStatus] = useState<UpdateStatusPayload | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    const unsub = onUpdateStatus((payload) => setStatus(payload));
    // Soft check after UI mounts (packaged builds only; main process also polls)
    const t = setTimeout(() => {
      checkForUpdates();
    }, 12000);
    return () => {
      unsub();
      clearTimeout(t);
    };
  }, []);

  if (!status) return null;
  if (!['available', 'downloading', 'ready', 'error'].includes(status.state)) return null;

  const onInstall = async () => {
    setInstalling(true);
    const ok = await installUpdateNow();
    if (!ok) setInstalling(false);
  };

  return (
    <div
      style={{
        margin: '0 12px 8px',
        padding: '10px 12px',
        borderRadius: 12,
        background: status.state === 'error' ? '#fff1f2' : '#eff6ff',
        border: `1px solid ${status.state === 'error' ? '#fecdd3' : '#bfdbfe'}`,
        fontSize: 12,
        color: '#0f172a',
      }}
    >
      {status.state === 'available' && (
        <p style={{ margin: 0 }}>
          A new WorkPulse Employee version <strong>{status.version}</strong> is available.
        </p>
      )}
      {status.state === 'downloading' && (
        <p style={{ margin: 0 }}>
          Downloading update {status.version || ''}…
          {typeof status.percent === 'number' ? ` ${Math.round(status.percent)}%` : ''}
        </p>
      )}
      {status.state === 'ready' && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <p style={{ margin: 0 }}>
            Update <strong>{status.version}</strong> is ready. The app will close, install, then ask you to
            sign in again with your work email.
          </p>
          <button
            type="button"
            onClick={onInstall}
            disabled={installing}
            style={{
              border: 0,
              borderRadius: 8,
              padding: '6px 10px',
              background: '#2563eb',
              color: '#fff',
              fontWeight: 700,
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            {installing ? 'Closing…' : 'Close & update'}
          </button>
        </div>
      )}
      {status.state === 'error' && (
        <p style={{ margin: 0 }}>
          Update check unavailable. You can keep working — we will retry later.
        </p>
      )}
    </div>
  );
}
