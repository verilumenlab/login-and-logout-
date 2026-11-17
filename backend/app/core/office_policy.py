"""
Organization office-day policy (Asia/Kolkata).

Office hours: 09:30 – 18:30 (9 hours).
Late login grace: until 10:30 (60 minutes after start).
Presence checks: after 7h and 9h worked — employee must confirm still in office;
no response within 10 minutes → auto logout.
"""

from __future__ import annotations

from datetime import time

# Wall-clock office window
OFFICE_START = time(9, 30)
OFFICE_END = time(18, 30)

# Minutes after OFFICE_START before arrival is late (09:30 + 60 = 10:30)
LATE_LOGIN_GRACE_MINUTES = 60

# Expected paid / full day length
EXPECTED_WORK_MINUTES = 9 * 60

# Presence confirmation checkpoints (worked minutes from first login)
CHECK_EARLY_MINUTES = 7 * 60
CHECK_FULL_MINUTES = 9 * 60

# How long the employee has to answer "still in office?"
RESPONSE_TIMEOUT_MINUTES = 10

DEFAULT_SCHEDULE_NAME = "Standard Office 9:30–6:30"
DEFAULT_SCHEDULE_DESCRIPTION = (
    "Office day 09:30–18:30 (9 hours). Login grace until 10:30. "
    "Confirm still in office after 7h and 9h; no reply in 10 minutes auto-logs out."
)
