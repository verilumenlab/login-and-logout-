import React, { useEffect, useRef, useState } from 'react';

import {
  RESPONSE_TIMEOUT_MS,
  WorkdayPromptKind,
  earlyHoursLabel,
} from '../presence/workdayPolicy';

interface WorkdayCheckModalProps {
  kind: WorkdayPromptKind;
  openedAt: number;
  workedMinutes: number;
  onContinue: () => void;
  onLogout: () => void;
  onTimeout: () => void;
}

function formatCountdown(msLeft: number): string {
  const total = Math.max(0, Math.ceil(msLeft / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export const WorkdayCheckModal: React.FC<WorkdayCheckModalProps> = ({
  kind,
  openedAt,
  workedMinutes,
  onContinue,
  onLogout,
  onTimeout,
}) => {
  const [msLeft, setMsLeft] = useState(() => Math.max(0, openedAt + RESPONSE_TIMEOUT_MS - Date.now()));
  const timedOut = useRef(false);

  useEffect(() => {
    timedOut.current = false;
    const tick = () => {
      const left = openedAt + RESPONSE_TIMEOUT_MS - Date.now();
      setMsLeft(Math.max(0, left));
      if (left <= 0 && !timedOut.current) {
        timedOut.current = true;
        onTimeout();
      }
    };
    tick();
    const id = window.setInterval(tick, 250);
    return () => window.clearInterval(id);
  }, [openedAt, onTimeout]);

  const isNine = kind === 'nine_hour';

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Working hours check">
      <div className="modal-card workday-check-modal">
        <h2>{isNine ? '9 hours completed' : 'Early logout'}</h2>
        {isNine ? (
          <p className="muted-text">
            You have completed <strong>9 hours of work</strong>. Are you still working in the office?
          </p>
        ) : (
          <p className="muted-text">
            You have not completed your required <strong>9 working hours</strong> (currently{' '}
            <strong>{earlyHoursLabel(workedMinutes)}</strong>). Are you still working, or do you want to log
            out?
          </p>
        )}
        <p className="workday-check-countdown">
          {isNine
            ? 'If you confirm, you get 10 more minutes. '
            : null}
          Auto logout in <strong>{formatCountdown(msLeft)}</strong> if there is no response
        </p>
        <div className="modal-actions workday-check-actions">
          <button type="button" className="btn btn-primary" onClick={onContinue}>
            {isNine ? 'Yes — still working (+10 min)' : 'Continue Working'}
          </button>
          <button type="button" className="btn btn-secondary" onClick={onLogout}>
            Logout
          </button>
        </div>
      </div>
    </div>
  );
};
