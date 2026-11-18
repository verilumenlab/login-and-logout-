"""
Organization office-day policy (Asia/Kolkata).

Office hours: 09:30 – 18:30.
Every employee must complete 9 hours from their actual login time.
- At 9h: ask if still working; confirm → +10 minutes; no reply in 10 min → auto logout.
- Logout attempt before 9h: confirm continue vs logout; no reply in 10 min → auto logout.
"""

from __future__ import annotations

from datetime import time

OFFICE_START = time(9, 30)
OFFICE_END = time(18, 30)
# After 6:00 PM local, laptop system sleep means the employee left → auto logout.
SLEEP_LOGOUT_AFTER = time(18, 0)

# Login after 09:30 is fine until 10:30 (still records actual login time).
LATE_LOGIN_GRACE_MINUTES = 60
# After this local time with no login, notify employee + HR + manager + admin.
MISSING_LOGIN_ALERT = time(10, 30)

EXPECTED_WORK_MINUTES = 9 * 60
EARLY_LOGOUT_THRESHOLD_MINUTES = 7 * 60  # “early” band starts around 7h
RESPONSE_TIMEOUT_MINUTES = 10
# After confirming still working at 9h, allow this many more minutes then end the day.
NINE_HOUR_EXTENSION_MINUTES = 10

DEFAULT_SCHEDULE_NAME = "Standard Office 9:30–6:30"
DEFAULT_SCHEDULE_DESCRIPTION = (
    "Office day 09:30–18:30. Record actual login; require 9 working hours from login. "
    "At 9h ask if still working (confirm = +10 min). Early logout before 9h needs confirmation. "
    "No reply in 10 minutes auto-logs out."
)

# Structured logout detail prefix: WORKDAY|<STATUS>|<CONFIRMATION>|<worked_minutes>
WORKDAY_DETAIL_PREFIX = "WORKDAY|"
