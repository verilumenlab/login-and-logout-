import React, { useEffect, useRef, useState } from 'react';

import {
  RESPONSE_TIMEOUT_MS,
  WorkdayCheckpoint,
  checkpointLabel,
} from '../presence/workdayPolicy';

interface WorkdayCheckModalProps {
  checkpoint: WorkdayCheckpoint;
  openedAt: number;
  onStay: () => void;
  onLeave: () => void;
  onTimeout: () => void;
}

function formatCountdown(msLeft: number): string {
  const total = Math.max(0, Math.ceil(msLeft / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export const WorkdayCheckModal: React.FC<WorkdayCheckModalProps> = ({
  checkpoint,
  openedAt,
  onStay,
  onLeave,
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

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Office presence check">
      <div className="modal-card workday-check-modal">
        <h2>Are you still in the office?</h2>
        <p className="muted-text">
          You have completed about <strong>{checkpointLabel(checkpoint)}</strong>. Confirm you are still
          working, or log out now.
        </p>
        <p className="workday-check-countdown">
          Auto logout in <strong>{formatCountdown(msLeft)}</strong> if there is no response
        </p>
        <div className="modal-actions workday-check-actions">
          <button type="button" className="btn btn-primary" onClick={onStay}>
            Yes — still in office
          </button>
          <button type="button" className="btn btn-secondary" onClick={onLeave}>
            No — log me out
          </button>
        </div>
      </div>
    </div>
  );
};
