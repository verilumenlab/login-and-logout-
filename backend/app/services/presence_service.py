"""
Employee Presence Engine

Turns desktop-agent signals into attendance:
- LOGIN  = earliest of (app login, office Wi-Fi connected)  -> opens a session (clock-in)
- LOGOUT = latest of (app logout, office Wi-Fi disconnected) -> closes the session (clock-out)

Wi-Fi connect/disconnect only affects attendance when the SSID is a trusted office
network (Offices & Wi-Fi). Home / personal Wi-Fi is stored for audit but ignored
for clock-in/out — important for employees on personal laptops.

Every raw signal is stored as a PresenceEvent so the employee and HR can see exactly
when the app was used and when the laptop joined or left a Wi-Fi network.
"""

from __future__ import annotations

import calendar
import hashlib
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import (
    AttendanceBreak,
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
)
from app.models.auth import Role, User
from app.models.employee import EmployeeProfile, EmploymentStatus
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.office import Office, OfficeNetwork
from app.models.presence import (
    AUDIT_ONLY_PRESENCE_EVENT_TYPES,
    LOGIN_EVENT_TYPES,
    LOGOUT_EVENT_TYPES,
    PresenceAttendanceAction,
    PresenceEvent,
    PresenceEventType,
)
from app.models.schedule import Holiday
from app.schemas.presence import (
    PresenceBreakOut,
    PresenceDay,
    PresenceEventIn,
    PresenceEventOut,
    PresenceEventResult,
    PresenceMonthSummary,
    TeamPresenceCounts,
    TeamPresenceRow,
)
from app.core.office_policy import SLEEP_LOGOUT_AFTER
from app.services.attendance_engine import (
    determine_work_date_for_clock_in,
    ensure_utc,
    finalize_break,
    is_clock_in,
    local_day_bounds,
    local_work_date,
    org_zone,
    recalculate_attendance_day,
)

MAX_EVENT_AGE = timedelta(days=7)
MAX_CLOCK_SKEW = timedelta(minutes=5)
DEFAULT_WORKING_WEEKDAYS = [1, 2, 3, 4, 5]
_WIFI_ATTENDANCE_TYPES = frozenset(
    {
        PresenceEventType.WIFI_CONNECTED,
        PresenceEventType.WIFI_DISCONNECTED,
        PresenceEventType.WIFI_CONNECTED.value,
        PresenceEventType.WIFI_DISCONNECTED.value,
    }
)


def _attendance_client_event_id(employee_id: uuid.UUID, client_event_id: str) -> str:
    digest = hashlib.sha256(f"{employee_id}:{client_event_id}".encode()).hexdigest()[:40]
    return f"presence:{digest}"


async def _open_session(db: AsyncSession, employee_id: uuid.UUID) -> tuple[AttendanceDay, datetime] | None:
    """Returns (day, last clock-in time) when the employee's latest attendance day is still open."""
    day = (
        await db.execute(
            select(AttendanceDay)
            .where(AttendanceDay.employee_id == employee_id, AttendanceDay.shift_start.is_not(None))
            .order_by(AttendanceDay.work_date.desc())
            .limit(1)
        )
    ).scalars().first()
    if day is None:
        return None

    events = (
        await db.execute(
            select(AttendanceEvent)
            .where(AttendanceEvent.attendance_day_id == day.id)
            .order_by(AttendanceEvent.timestamp)
        )
    ).scalars().all()
    if not events or not is_clock_in(events[-1].event_type):
        return None
    return day, ensure_utc(events[-1].timestamp) or datetime.now(UTC)


async def _add_attendance_event(
    db: AsyncSession,
    day: AttendanceDay,
    event_type: AttendanceEventType,
    occurred_at: datetime,
    client_event_id: str,
    notes: str,
) -> None:
    existing = (
        await db.execute(
            select(AttendanceEvent).where(AttendanceEvent.client_event_id == client_event_id)
        )
    ).scalars().first()
    if existing is not None:
        await recalculate_attendance_day(db, day.id, commit=False)
        return
    db.add(
        AttendanceEvent(
            attendance_day_id=day.id,
            event_type=event_type,
            timestamp=occurred_at,
            source=AttendanceSource.DESKTOP,
            client_event_id=client_event_id,
            sync_delay_seconds=round(max(0.0, (datetime.now(UTC) - occurred_at).total_seconds()), 2),
            notes=notes,
        )
    )
    await db.flush()
    await recalculate_attendance_day(db, day.id, commit=False)


async def _clock_in(
    db: AsyncSession, employee: EmployeeProfile, occurred_at: datetime, client_event_id: str, notes: str
) -> None:
    work_date = determine_work_date_for_clock_in(occurred_at, employee.work_schedule)
    day = (
        await db.execute(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == employee.id,
                AttendanceDay.work_date == work_date,
            )
        )
    ).scalars().first()
    if day is None:
        day = AttendanceDay(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            work_date=work_date,
            status=AttendanceStatus.PRESENT,
            shift_start=occurred_at,
        )
        db.add(day)
        await db.flush()
    await _add_attendance_event(db, day, AttendanceEventType.CLOCK_IN, occurred_at, client_event_id, notes)


def _describe(event: PresenceEventIn) -> str:
    if event.detail and event.detail.strip():
        # Keep full WORKDAY|… — message so metadata can be parsed later.
        return event.detail.strip()[:500]
    labels = {
        PresenceEventType.APP_LOGIN: "Desktop app login",
        PresenceEventType.APP_LOGOUT: "Desktop app logout",
        PresenceEventType.WIFI_CONNECTED: "Wi-Fi connected",
        PresenceEventType.WIFI_DISCONNECTED: "Wi-Fi disconnected",
        PresenceEventType.SYSTEM_SHUTDOWN: "Laptop shut down",
        PresenceEventType.SYSTEM_SUSPEND: "Laptop sleep / hibernate",
        PresenceEventType.SYSTEM_RESUME: "Laptop wake from sleep",
        PresenceEventType.SYSTEM_STARTUP: "Laptop powered on",
    }
    label = labels.get(event.event_type, str(event.event_type))
    return f"{label} ({event.ssid})" if event.ssid else label


def _parse_workday_detail(detail: str | None) -> dict[str, object] | None:
    """Parse WORKDAY|<status>|<confirmation>|<minutes> — message."""
    if not detail:
        return None
    head = detail.split(" — ", 1)[0].strip()
    if not head.startswith("WORKDAY|"):
        return None
    parts = head.split("|")
    if len(parts) < 3:
        return None
    status = parts[1].strip().upper()
    confirmation = parts[2].strip().upper()
    worked = None
    if len(parts) >= 4 and parts[3].strip().isdigit():
        worked = int(parts[3].strip())
    return {
        "status": status,
        "confirmation": confirmation,
        "worked_minutes_reported": worked,
        "completed_nine_hours": status == "COMPLETED_9H",
        "early_logout": status == "EARLY_LOGOUT",
        "auto_logout": confirmation in {"NO_RESPONSE", "EXTENSION_ENDED", "EOD_IDLE"} or status == "AUTO_LOGOUT",
        "raw": detail[:500],
    }


def _apply_workday_metadata(day: AttendanceDay, detail: str | None) -> None:
    parsed = _parse_workday_detail(detail)
    if not parsed:
        return
    meta = dict(day.metadata_json or {})
    meta["workday"] = parsed
    day.metadata_json = meta


def _workday_fields_from_day(day: AttendanceDay) -> dict[str, object]:
    meta = day.metadata_json or {}
    workday = meta.get("workday") if isinstance(meta, dict) else None
    if not isinstance(workday, dict):
        # Fall back to parsing last clock-out note.
        note = _last_clock_out_note(day)
        parsed = _parse_workday_detail(note) if note and note.startswith("WORKDAY|") else None
        # Notes are human-only after _describe; try metadata only.
        if not parsed:
            # Reconstruct from human note keywords when structured meta missing.
            if note:
                lower = note.lower()
                early = "early logout" in lower
                completed = "9-hour" in lower or "9 hours" in lower or "completing 9" in lower
                no_resp = "no response" in lower
                auto = (
                    "auto-logout" in lower
                    or "auto logout" in lower
                    or "system sleep" in lower
                )
                return {
                    "workday_status": "EARLY_LOGOUT" if early else ("COMPLETED_9H" if completed else ("AUTO_LOGOUT" if auto else None)),
                    "confirmation_status": "NO_RESPONSE" if no_resp else None,
                    "completed_nine_hours": bool(completed) or (day.total_work_minutes or 0) >= 9 * 60,
                    "early_logout": early or (0 < (day.total_work_minutes or 0) < 9 * 60),
                    "auto_logout": auto,
                    "logout_note": note,
                }
            return {
                "workday_status": None,
                "confirmation_status": None,
                "completed_nine_hours": (day.total_work_minutes or 0) >= 9 * 60,
                "early_logout": 0 < (day.total_work_minutes or 0) < 9 * 60,
                "auto_logout": False,
                "logout_note": None,
            }
        workday = parsed

    note = _last_clock_out_note(day)
    mins = int(day.total_work_minutes or 0)
    return {
        "workday_status": workday.get("status"),
        "confirmation_status": workday.get("confirmation"),
        "completed_nine_hours": bool(workday.get("completed_nine_hours")) or mins >= 9 * 60,
        "early_logout": bool(workday.get("early_logout")) or (0 < mins < 9 * 60),
        "auto_logout": bool(workday.get("auto_logout")),
        "logout_note": note,
    }


def _last_clock_out_note(day: AttendanceDay) -> str | None:
    outs = [
        e
        for e in (day.events or [])
        if getattr(e.event_type, "value", e.event_type) in ("CLOCK_OUT", AttendanceEventType.CLOCK_OUT)
    ]
    if not outs:
        return None
    last = max(outs, key=lambda e: ensure_utc(e.timestamp) or datetime.min.replace(tzinfo=UTC))
    note = (last.notes or "").strip()
    return note or None


def _wifi_display_from_events(events: list[PresenceEvent]) -> tuple[datetime | None, list[str]]:
    """
    Prefer real WIFI_CONNECTED rows. If the laptop was already on Wi-Fi and never
    emitted a connect today, fall back to APP_LOGIN.ssid so the board is not blank.
    """
    connects = [e for e in events if e.event_type == PresenceEventType.WIFI_CONNECTED.value]
    if connects:
        return (
            ensure_utc(connects[0].occurred_at),
            list(dict.fromkeys(e.ssid for e in connects if e.ssid)),
        )
    logins_with_ssid = [
        e
        for e in events
        if e.event_type == PresenceEventType.APP_LOGIN.value and e.ssid
    ]
    if logins_with_ssid:
        return (
            ensure_utc(logins_with_ssid[0].occurred_at),
            list(dict.fromkeys(e.ssid for e in logins_with_ssid if e.ssid)),
        )
    return None, []


async def _office_ssids(db: AsyncSession, organization_id: uuid.UUID) -> set[str]:
    """Active trusted office Wi-Fi names for the organization (case-insensitive)."""
    rows = (
        await db.execute(
            select(OfficeNetwork.ssid)
            .join(Office, OfficeNetwork.office_id == Office.id)
            .where(
                Office.organization_id == organization_id,
                Office.is_active.is_(True),
                OfficeNetwork.is_active.is_(True),
                OfficeNetwork.ssid.is_not(None),
            )
        )
    ).scalars().all()
    return {str(ssid).strip().casefold() for ssid in rows if ssid and str(ssid).strip()}


def _is_wifi_attendance_event(event_type: object) -> bool:
    val = event_type.value if hasattr(event_type, "value") else event_type
    return val in _WIFI_ATTENDANCE_TYPES


def _ssid_is_office(ssid: str | None, office_ssids: set[str]) -> bool:
    if not ssid or not office_ssids:
        return False
    return ssid.strip().casefold() in office_ssids


async def record_presence_event(
    db: AsyncSession,
    employee: EmployeeProfile,
    event: PresenceEventIn,
) -> PresenceEventResult:
    """Stores one presence signal and opens/closes the attendance session according to the login/logout rule."""
    now = datetime.now(UTC)
    occurred_at = ensure_utc(event.occurred_at) or now

    if occurred_at > now + MAX_CLOCK_SKEW:
        return PresenceEventResult(
            client_event_id=event.client_event_id, status="REJECTED", detail="Event time is in the future"
        )
    if occurred_at < now - MAX_EVENT_AGE:
        return PresenceEventResult(
            client_event_id=event.client_event_id, status="REJECTED", detail="Event is older than 7 days"
        )

    existing = (
        await db.execute(
            select(PresenceEvent).where(
                PresenceEvent.employee_id == employee.id,
                PresenceEvent.client_event_id == event.client_event_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        return PresenceEventResult(
            client_event_id=event.client_event_id,
            status="DUPLICATE",
            attendance_action=PresenceAttendanceAction(existing.attendance_action),
        )

    attendance_id = _attendance_client_event_id(employee.id, event.client_event_id)
    action = PresenceAttendanceAction.NONE
    open_session = await _open_session(db, employee.id)
    event_work_date = determine_work_date_for_clock_in(occurred_at, employee.work_schedule)

    # Home / personal Wi-Fi must not clock in or out — only trusted office SSIDs.
    wifi_counts_for_attendance = True
    if _is_wifi_attendance_event(event.event_type):
        office_ssids = await _office_ssids(db, employee.organization_id)
        wifi_counts_for_attendance = _ssid_is_office(event.ssid, office_ssids)

    if wifi_counts_for_attendance and event.event_type in LOGIN_EVENT_TYPES:
        if open_session is not None and open_session[0].work_date < event_work_date:
            # Previous day never logged out: prefer evening sleep/shutdown time so hours
            # stop then — do not wait for / invent a next-morning logout.
            stale_day, last_in = open_session
            close_at, close_note = await _best_previous_day_logout(
                db,
                employee_id=employee.id,
                stale_day=stale_day,
                last_in=last_in,
                before=occurred_at,
            )
            await _add_attendance_event(
                db,
                stale_day,
                AttendanceEventType.CLOCK_OUT,
                close_at,
                f"{attendance_id}:autoclose"[:100],
                close_note,
            )
            open_session = None

        if open_session is None:
            await _clock_in(db, employee, occurred_at, attendance_id, _describe(event))
            action = PresenceAttendanceAction.CLOCK_IN
        else:
            # A signal synced late (e.g. Wi-Fi connected before the app started) moves the day's login earlier.
            day = open_session[0]
            first_in = ensure_utc(day.shift_start)
            if day.work_date == event_work_date and first_in is not None and occurred_at < first_in:
                await _add_attendance_event(
                    db, day, AttendanceEventType.CLOCK_IN, occurred_at, attendance_id, _describe(event)
                )
                action = PresenceAttendanceAction.CLOCK_IN
    elif event.event_type == PresenceEventType.SYSTEM_SUSPEND:
        # After 6:00 PM, laptop sleep means the person left → clock out at sleep time.
        # Before 6:00 PM, sleep is audited only (AUTO_SLEEP break tracks the gap).
        action = PresenceAttendanceAction.NONE
        if (
            open_session is not None
            and _is_evening_sleep_logout_time(occurred_at)
            and occurred_at >= open_session[1]
        ):
            close_at = _logout_timestamp_for_day(
                open_session[0].work_date,
                occurred_at,
                not_before=open_session[1],
            )
            await _add_attendance_event(
                db,
                open_session[0],
                AttendanceEventType.CLOCK_OUT,
                close_at,
                attendance_id,
                "Auto-logout — laptop system sleep after 6:00 PM",
            )
            _apply_workday_metadata(
                open_session[0],
                f"WORKDAY|AUTO_LOGOUT|EOD_SLEEP|0 — Auto-logout after 6:00 PM — laptop system sleep",
            )
            meta = dict(open_session[0].metadata_json or {})
            meta["sleep_auto_logout_at"] = close_at.isoformat()
            meta["sleep_auto_logout_reason"] = "system_suspend_after_18"
            open_session[0].metadata_json = meta
            action = PresenceAttendanceAction.CLOCK_OUT
    elif event.event_type == PresenceEventType.SYSTEM_RESUME:
        action = PresenceAttendanceAction.NONE
    elif event.event_type == PresenceEventType.SYSTEM_SHUTDOWN:
        # Shut down always ends the work day at the power-off time (ganesh: 06:30 PM),
        # even if the event syncs later or another day is already open.
        action = await _apply_system_shutdown_logout(
            db,
            employee=employee,
            occurred_at=occurred_at,
            event_work_date=event_work_date,
            attendance_id=attendance_id,
            open_session=open_session,
        )
    elif wifi_counts_for_attendance and event.event_type in LOGOUT_EVENT_TYPES:
        is_office_wifi_out = event.event_type == PresenceEventType.WIFI_DISCONNECTED
        if open_session is not None:
            if occurred_at >= open_session[1]:
                notes = (
                    "Auto-logout — left office Wi-Fi"
                    if is_office_wifi_out
                    else _describe(event)
                )
                close_at = _logout_timestamp_for_day(
                    open_session[0].work_date,
                    occurred_at,
                    not_before=open_session[1],
                )
                await _add_attendance_event(
                    db, open_session[0], AttendanceEventType.CLOCK_OUT, close_at, attendance_id, notes
                )
                if is_office_wifi_out:
                    _apply_workday_metadata(
                        open_session[0],
                        "WORKDAY|AUTO_LOGOUT|OFFICE_WIFI|0 — Auto-logout — left office Wi-Fi",
                    )
                else:
                    _apply_workday_metadata(open_session[0], event.detail or notes)
                action = PresenceAttendanceAction.CLOCK_OUT
        else:
            # Already logged out today: a later app logout / Wi-Fi disconnect becomes the day's logout time.
            day = (
                await db.execute(
                    select(AttendanceDay).where(
                        AttendanceDay.employee_id == employee.id,
                        AttendanceDay.work_date == event_work_date,
                    )
                )
            ).scalars().first()
            last_out = ensure_utc(day.shift_end) if day is not None else None
            if day is not None and last_out is not None and occurred_at > last_out:
                notes = (
                    "Auto-logout — left office Wi-Fi"
                    if is_office_wifi_out
                    else _describe(event)
                )
                close_at = _logout_timestamp_for_day(
                    day.work_date,
                    occurred_at,
                    not_before=ensure_utc(day.shift_start) or last_out,
                )
                if close_at > last_out:
                    await _add_attendance_event(
                        db, day, AttendanceEventType.CLOCK_OUT, close_at, attendance_id, notes
                    )
                    if is_office_wifi_out:
                        _apply_workday_metadata(
                            day,
                            "WORKDAY|AUTO_LOGOUT|OFFICE_WIFI|0 — Auto-logout — left office Wi-Fi",
                        )
                    else:
                        _apply_workday_metadata(day, event.detail or notes)
                    action = PresenceAttendanceAction.CLOCK_OUT

    db.add(
        PresenceEvent(
            organization_id=employee.organization_id,
            employee_id=employee.id,
            event_type=event.event_type.value,
            occurred_at=occurred_at,
            client_event_id=event.client_event_id,
            device_id=event.device_id,
            ssid=event.ssid,
            bssid=event.bssid,
            attendance_action=action.value,
        )
    )
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        # Concurrent duplicate sync → treat as already recorded.
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            existing_dup = (
                await db.execute(
                    select(PresenceEvent).where(
                        PresenceEvent.employee_id == employee.id,
                        PresenceEvent.client_event_id == event.client_event_id,
                    )
                )
            ).scalars().first()
            if existing_dup is not None:
                return PresenceEventResult(
                    client_event_id=event.client_event_id,
                    status="DUPLICATE",
                    attendance_action=PresenceAttendanceAction(existing_dup.attendance_action),
                )
        raise
    return PresenceEventResult(client_event_id=event.client_event_id, status="RECORDED", attendance_action=action)


async def is_logged_in(db: AsyncSession, employee_id: uuid.UUID) -> bool:
    return await _open_session(db, employee_id) is not None


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """UTC window for inclusive local calendar dates (Asia/Kolkata by default)."""
    start_utc, _ = local_day_bounds(start)
    _, end_utc = local_day_bounds(end)
    return start_utc, end_utc


def _is_evening_sleep_logout_time(occurred_at: datetime) -> bool:
    """True when local time is at/after 6:00 PM (system sleep → logout)."""
    local = (ensure_utc(occurred_at) or datetime.now(UTC)).astimezone(org_zone())
    return (local.hour, local.minute) >= (SLEEP_LOGOUT_AFTER.hour, SLEEP_LOGOUT_AFTER.minute)


def _evening_sleep_cutoff_utc(work_date: date) -> datetime:
    """6:00 PM local on the work date, as UTC."""
    return datetime.combine(work_date, SLEEP_LOGOUT_AFTER, tzinfo=org_zone()).astimezone(UTC)


_EVENING_POWER_OFF_TYPES = frozenset(
    {
        PresenceEventType.SYSTEM_SUSPEND.value,
        PresenceEventType.SYSTEM_SHUTDOWN.value,
        "SYSTEM_SUSPEND",
        "SYSTEM_SHUTDOWN",
    }
)
_EVENING_WAKE_TYPES = frozenset(
    {
        PresenceEventType.SYSTEM_RESUME.value,
        PresenceEventType.SYSTEM_STARTUP.value,
        "SYSTEM_RESUME",
        "SYSTEM_STARTUP",
    }
)


def _final_evening_power_off_at(signals: list[PresenceEvent]) -> tuple[datetime | None, str | None]:
    """
    Last sleep/shutdown after 6:00 PM that was not followed by wake/startup the same evening.
    Returns (occurred_at, reason_label) or (None, None).
    """
    power_off_at: datetime | None = None
    reason: str | None = None
    for sig in signals:
        et = str(getattr(sig.event_type, "value", sig.event_type))
        ts = ensure_utc(sig.occurred_at)
        if ts is None:
            continue
        if et in _EVENING_POWER_OFF_TYPES:
            power_off_at = ts
            reason = "shutdown" if "SHUTDOWN" in et.upper() else "sleep"
        elif et in _EVENING_WAKE_TYPES:
            power_off_at = None
            reason = None
    return power_off_at, reason


def _infer_effective_logout(
    signals: list[PresenceEvent],
    *,
    work_date: date,
    office_ssids: set[str],
) -> tuple[datetime | None, str | None]:
    """
    Infer when worked time should stop for the day:

    1. After 6:00 PM — system sleep (no wake) or system shutdown → logout
    2. Office Wi-Fi disconnect (no later office Wi-Fi / app login) → logout

    Hours after that point must not count.
    """
    evening_start = _evening_sleep_cutoff_utc(work_date)
    ordered = sorted(
        signals,
        key=lambda e: ensure_utc(e.occurred_at) or datetime.min.replace(tzinfo=UTC),
    )
    logout_at: datetime | None = None
    reason: str | None = None

    for sig in ordered:
        et = str(getattr(sig.event_type, "value", sig.event_type))
        ts = ensure_utc(sig.occurred_at)
        if ts is None:
            continue
        ssid = sig.ssid
        is_office = _ssid_is_office(ssid, office_ssids)

        # Back on office network → work continues.
        if et in (PresenceEventType.WIFI_CONNECTED.value, "WIFI_CONNECTED") and is_office:
            logout_at = None
            reason = None
            continue
        # Any APP_LOGIN reopens the day (SSID optional — desktop often sends none).
        if et in (PresenceEventType.APP_LOGIN.value, "APP_LOGIN"):
            logout_at = None
            reason = None
            continue

        # Left office Wi-Fi → logout; hours after this must not count until office returns.
        if et in (PresenceEventType.WIFI_DISCONNECTED.value, "WIFI_DISCONNECTED") and is_office:
            logout_at = ts
            reason = "office_wifi"
            continue

        if et in (PresenceEventType.APP_LOGOUT.value, "APP_LOGOUT"):
            logout_at = ts
            reason = "app_logout"
            continue

        # Shutdown after 6:00 PM ends the day; midday reboot is break/audit only for inference.
        if et in (PresenceEventType.SYSTEM_SHUTDOWN.value, "SYSTEM_SHUTDOWN") and ts >= evening_start:
            logout_at = ts
            reason = "shutdown"
            continue

        # Sleep before 6:00 PM is break-only; after 6:00 PM it ends the day.
        if et in (PresenceEventType.SYSTEM_SUSPEND.value, "SYSTEM_SUSPEND") and ts >= evening_start:
            logout_at = ts
            reason = "sleep"
            continue

    return logout_at, reason


def _logout_note_for_reason(reason: str) -> str:
    if reason == "shutdown":
        return "Auto-logout — laptop shut down after 6:00 PM"
    if reason == "sleep":
        return "Auto-logout — laptop system sleep after 6:00 PM"
    if reason == "office_wifi":
        return "Auto-logout — left office Wi-Fi"
    if reason == "app_logout":
        return "Desktop app logout"
    if reason == "eod_no_office_wifi":
        return "Auto-logout — not on office Wi-Fi after 6:30 PM"
    return "Auto-logout"


def _fallback_eod_without_office_wifi(
    signals: list[PresenceEvent],
    *,
    work_date: date,
    office_ssids: set[str],
    shift_end: datetime | None,
    day_end: datetime,
    now: datetime | None = None,
) -> tuple[datetime | None, str | None]:
    """
    If the day was left open until midnight and there was no office Wi-Fi after 6:00 PM,
    stop hours at 6:30 PM (office end). Covers missing disconnect events (Manasa/Poojitha).

    Never apply during the morning/afternoon of the same day — that incorrectly
    clocked people out at 6:30 PM while they were still trying to log in.
    """
    from app.core.office_policy import OFFICE_END

    now = ensure_utc(now) or datetime.now(UTC)
    eod = datetime.combine(work_date, OFFICE_END, tzinfo=org_zone()).astimezone(UTC)
    # Only after office end (or for a past work date).
    if now < eod:
        return None, None

    shift_end_utc = ensure_utc(shift_end) if shift_end is not None else None
    # Open session past EOD, or logout stamped at/near midnight (shows as 11:59 PM + ~14h).
    open_or_midnight = shift_end_utc is None or shift_end_utc >= day_end - timedelta(minutes=1)
    if not open_or_midnight:
        return None, None

    # No office SSIDs configured: still cap false midnight days at office end.
    if not office_ssids:
        return eod, "eod_no_office_wifi"

    evening_start = _evening_sleep_cutoff_utc(work_date)
    for sig in signals:
        et = str(getattr(sig.event_type, "value", sig.event_type))
        ts = ensure_utc(sig.occurred_at)
        if ts is None or ts < evening_start:
            continue
        if et in (PresenceEventType.WIFI_CONNECTED.value, "WIFI_CONNECTED") and _ssid_is_office(
            sig.ssid, office_ssids
        ):
            return None, None
        if et in (PresenceEventType.APP_LOGIN.value, "APP_LOGIN") and _ssid_is_office(
            sig.ssid, office_ssids
        ):
            return None, None

    return eod, "eod_no_office_wifi"


async def _apply_system_shutdown_logout(
    db: AsyncSession,
    *,
    employee: EmployeeProfile,
    occurred_at: datetime,
    event_work_date: date,
    attendance_id: str,
    open_session: tuple[AttendanceDay, datetime] | None,
) -> PresenceAttendanceAction:
    """
    System shut down always stops worked time at the shut-down timestamp.
    Targets the shut-down's own work date — not whatever day happens to be open now.
    """
    day: AttendanceDay | None = None
    if open_session is not None and open_session[0].work_date == event_work_date:
        day = open_session[0]
    if day is None:
        day = (
            await db.execute(
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.events))
                .where(
                    AttendanceDay.employee_id == employee.id,
                    AttendanceDay.work_date == event_work_date,
                )
            )
        ).scalars().first()
    if day is None or day.shift_start is None:
        return PresenceAttendanceAction.NONE

    last_in = ensure_utc(day.shift_start) or occurred_at
    ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or occurred_at)
    for ev in reversed(ordered):
        if is_clock_in(ev.event_type):
            last_in = ensure_utc(ev.timestamp) or last_in
            break

    if occurred_at < last_in:
        return PresenceAttendanceAction.NONE

    close_at = _logout_timestamp_for_day(event_work_date, occurred_at, not_before=last_in)
    last_out = ensure_utc(day.shift_end)
    still_open = bool(ordered) and is_clock_in(ordered[-1].event_type)
    needs = still_open or last_out is None or last_out > close_at + timedelta(minutes=2)
    if not needs:
        return PresenceAttendanceAction.NONE

    evening = _is_evening_sleep_logout_time(occurred_at)
    notes = (
        "Auto-logout — laptop shut down after 6:00 PM"
        if evening
        else "Auto-logout — laptop shut down"
    )
    await _add_attendance_event(db, day, AttendanceEventType.CLOCK_OUT, close_at, attendance_id, notes)
    if evening:
        _apply_workday_metadata(
            day,
            "WORKDAY|AUTO_LOGOUT|EOD_SHUTDOWN|0 — Auto-logout after 6:00 PM — laptop shut down",
        )
    else:
        _apply_workday_metadata(day, f"WORKDAY|AUTO_LOGOUT|SHUTDOWN|0 — {notes}")
    meta = dict(day.metadata_json or {})
    meta["sleep_auto_logout_at"] = close_at.isoformat()
    meta["sleep_auto_logout_reason"] = "system_shutdown"
    day.metadata_json = meta
    # Keep the same unit of work as PresenceEvent insert (commit=False).
    # A mid-ingest commit left orphan CLOCK_OUT rows; retries then 500'd on unique
    # client_event_id and blocked the whole desktop sync batch.
    await recalculate_attendance_day(db, day.id, commit=False)
    return PresenceAttendanceAction.CLOCK_OUT


async def _best_previous_day_logout(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    stale_day: AttendanceDay,
    last_in: datetime,
    before: datetime,
) -> tuple[datetime, str]:
    """
    Choose logout for a day left open overnight.
    Prefer evening sleep/shutdown or office Wi-Fi disconnect — not next-morning login.
    """
    day_start, day_end = local_day_bounds(stale_day.work_date)
    emp = await db.get(EmployeeProfile, employee_id)
    office_ssids = await _office_ssids(db, emp.organization_id) if emp is not None else set()
    signals = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id == employee_id,
                PresenceEvent.occurred_at >= day_start,
                PresenceEvent.occurred_at < min(before, day_end),
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()
    leave_at, reason = _infer_effective_logout(
        list(signals), work_date=stale_day.work_date, office_ssids=office_ssids
    )
    if leave_at is not None and reason is not None:
        close_at = _logout_timestamp_for_day(stale_day.work_date, leave_at, not_before=last_in)
        return close_at, _logout_note_for_reason(reason)

    last_seen = await db.scalar(
        select(PresenceEvent.occurred_at)
        .where(
            PresenceEvent.employee_id == employee_id,
            PresenceEvent.occurred_at >= last_in,
            PresenceEvent.occurred_at < before,
        )
        .order_by(PresenceEvent.occurred_at.desc())
        .limit(1)
    )
    close_at = _logout_timestamp_for_day(
        stale_day.work_date,
        ensure_utc(last_seen) or last_in,
        not_before=last_in,
    )
    return close_at, "Auto-closed: no logout was recorded"


def _logout_timestamp_for_day(
    work_date: date,
    occurred_at: datetime,
    *,
    not_before: datetime | None = None,
) -> datetime:
    """
    Clamp a clock-out onto the attendance work day.
    Next-morning Wi-Fi disconnect / late sync must not become a "10:31 AM" logout
    with hours counted through midnight.
    """
    day_start, day_end = local_day_bounds(work_date)
    day_cap = day_end - timedelta(seconds=1)
    ts = ensure_utc(occurred_at) or day_cap
    capped = min(max(ts, day_start), day_cap)
    if not_before is not None:
        nb = ensure_utc(not_before) or capped
        if capped < nb:
            capped = min(nb, day_cap)
    return capped


def _clamp_session_to_work_date(
    *,
    first_login: datetime | None,
    last_logout: datetime | None,
    is_open: bool,
    work_date: date,
    now: datetime,
) -> tuple[datetime | None, datetime | None, int]:
    """Return (login, logout, worked_minutes) clipped to the local work day."""
    if first_login is None:
        return None, None, 0
    day_start, day_end = local_day_bounds(work_date)
    day_cap = day_end - timedelta(seconds=1)
    start = max(ensure_utc(first_login) or day_start, day_start)
    if start > day_cap:
        return None, None, 0
    if is_open:
        end = min(now, day_end)
        mins = max(0, int((end - start).total_seconds() // 60))
        return start, None, mins
    raw_end = ensure_utc(last_logout) if last_logout is not None else day_end
    if raw_end is None:
        raw_end = day_end
    # Minutes use exclusive day_end; display logout never past 11:59:59 local.
    end_for_mins = min(max(raw_end, start), day_end)
    mins = max(0, int((end_for_mins - start).total_seconds() // 60))
    display_end = day_cap if raw_end >= day_end else max(raw_end, start)
    if display_end > day_cap:
        display_end = day_cap
    return start, display_end, mins


def _display_worked_minutes(
    *,
    first_login: datetime | None,
    last_logout: datetime | None,
    is_open: bool,
    work_date: date,
    now: datetime,
    stored_minutes: int,
) -> int:
    """
    Hours shown on Login & Logout: only time inside the selected local work day.
    Fixes overnight sessions that otherwise show ~23h for a short same-looking login/logout.
    """
    _, _, mins = _clamp_session_to_work_date(
        first_login=first_login,
        last_logout=last_logout,
        is_open=is_open,
        work_date=work_date,
        now=now,
    )
    if first_login is None:
        return 0
    # Prefer recomputed day-clamped value; stored rollup can be overnight-inflated.
    if stored_minutes > 16 * 60 and mins < stored_minutes:
        return mins
    if is_open or last_logout is not None:
        return mins
    return max(0, int(stored_minutes or 0))


async def _autoclose_stale_open_day(
    db: AsyncSession,
    day: AttendanceDay,
    *,
    now: datetime,
) -> AttendanceDay:
    """If yesterday (or earlier) is still clocked in, close at evening sleep/shutdown or day end."""
    today_local = local_work_date(now)
    if day.work_date >= today_local:
        return day
    ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
    if not ordered or not is_clock_in(ordered[-1].event_type):
        return day
    last_in = ensure_utc(ordered[-1].timestamp) or now
    close_at, note = await _best_previous_day_logout(
        db,
        employee_id=day.employee_id,
        stale_day=day,
        last_in=last_in,
        before=now,
    )
    # If no evening power-off signal exists, do NOT stamp 11:59 PM (that inflates hours
    # to ~14h). Prefer office end (6:30 PM) when they were not on office Wi-Fi.
    if note == "Auto-closed: no logout was recorded":
        from app.core.office_policy import OFFICE_END

        emp = await db.get(EmployeeProfile, day.employee_id)
        office_ssids = await _office_ssids(db, emp.organization_id) if emp is not None else set()
        day_start, day_end = local_day_bounds(day.work_date)
        signals = (
            await db.execute(
                select(PresenceEvent).where(
                    PresenceEvent.employee_id == day.employee_id,
                    PresenceEvent.occurred_at >= day_start,
                    PresenceEvent.occurred_at < day_end,
                )
            )
        ).scalars().all()
        eod_at, eod_reason = _fallback_eod_without_office_wifi(
            list(signals),
            work_date=day.work_date,
            office_ssids=office_ssids,
            shift_end=None,
            day_end=day_end,
            now=now,
        )
        if eod_at is not None:
            close_at = eod_at
            note = _logout_note_for_reason(eod_reason or "eod_no_office_wifi")
        else:
            # Still avoid midnight: use office end as a safe cap for past open days.
            close_at = datetime.combine(day.work_date, OFFICE_END, tzinfo=org_zone()).astimezone(UTC)
            note = "Auto-closed at office end (no logout recorded)"
        if close_at < last_in:
            close_at = last_in
    await _add_attendance_event(
        db,
        day,
        AttendanceEventType.CLOCK_OUT,
        close_at,
        f"presence:autoclose-dayend:{day.id}"[:100],
        note,
    )
    await recalculate_attendance_day(db, day.id, commit=False)
    await db.refresh(day, attribute_names=["events", "shift_start", "shift_end", "total_work_minutes"])
    return day


async def _autoclose_prior_open_sessions(
    db: AsyncSession,
    employee_ids: list[uuid.UUID],
    *,
    before_date: date,
    now: datetime,
) -> None:
    """
    Close any still-open attendance days before `before_date`.
    Needed so overnight Active sessions do not keep counting into the next morning's board.
    """
    if not employee_ids:
        return
    stale_days = (
        await db.execute(
            select(AttendanceDay)
            .options(selectinload(AttendanceDay.events))
            .where(
                AttendanceDay.employee_id.in_(employee_ids),
                AttendanceDay.work_date < before_date,
            )
            .order_by(AttendanceDay.work_date.desc())
        )
    ).scalars().all()
    # Only touch the latest prior day per employee that is still clocked in.
    seen: set[uuid.UUID] = set()
    for day in stale_days:
        if day.employee_id in seen:
            continue
        ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
        if ordered and is_clock_in(ordered[-1].event_type):
            await _autoclose_stale_open_day(db, day, now=now)
            seen.add(day.employee_id)


def _is_premature_eod_fallback_out(event: AttendanceEvent, *, eod: datetime, now: datetime) -> bool:
    """True when a rule wrote a logout that is still in the future (morning bug)."""
    et = str(getattr(event.event_type, "value", event.event_type)).upper()
    if "CLOCK_OUT" not in et:
        return False
    ts = ensure_utc(event.timestamp)
    if ts is None or now >= eod:
        return False
    # Any logout stamped after "now" cannot be real yet today.
    if ts > now + timedelta(minutes=1):
        return True
    if abs((ts - eod).total_seconds()) > 120:
        return False
    notes = (event.notes or "").lower()
    cid = (event.client_event_id or "").lower()
    return (
        "not on office" in notes
        or "eod_no_office_wifi" in notes
        or "rule-logout" in cid
        or "auto-logout" in notes
    )


async def _reopen_premature_eod_fallback_days(
    db: AsyncSession,
    att_days: list[AttendanceDay],
    *,
    work_date: date,
    now: datetime,
) -> list[dict]:
    """
    Undo false morning/afternoon 6:30 PM clock-outs so Login works again today.
    """
    from app.core.office_policy import OFFICE_END

    eod = datetime.combine(work_date, OFFICE_END, tzinfo=org_zone()).astimezone(UTC)
    if now >= eod:
        return []

    reopened: list[dict] = []
    for day in att_days:
        ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
        if not ordered:
            continue
        last = ordered[-1]
        meta = dict(day.metadata_json or {})
        reason = str(meta.get("corrected_logout_reason") or meta.get("sleep_auto_logout_reason") or "")
        shift_end = ensure_utc(day.shift_end)
        future_end = shift_end is not None and shift_end > now + timedelta(minutes=1)
        looks_fallback = (
            "eod_no_office_wifi" in reason
            or _is_premature_eod_fallback_out(last, eod=eod, now=now)
            or future_end
        )
        if not looks_fallback:
            continue

        # Remove premature outs (future-dated or rule 6:30 PM stamps).
        removed = 0
        for ev in list(ordered):
            if _is_premature_eod_fallback_out(ev, eod=eod, now=now):
                await db.delete(ev)
                removed += 1
        if removed == 0 and not future_end:
            continue

        meta.pop("corrected_logout_at", None)
        meta.pop("corrected_logout_reason", None)
        if "eod_no_office_wifi" in str(meta.get("sleep_auto_logout_reason") or ""):
            meta.pop("sleep_auto_logout_at", None)
            meta.pop("sleep_auto_logout_reason", None)
        day.metadata_json = meta
        day.shift_end = None
        await db.flush()
        await recalculate_attendance_day(db, day.id)
        reopened.append(
            {
                "employee_id": str(day.employee_id),
                "full_name": None,
                "work_date": work_date.isoformat(),
                "reason": "reopen_premature_eod_fallback",
                "login_at": (ensure_utc(day.shift_start) or now).isoformat(),
                "logout_at": None,
                "worked_minutes": int(day.total_work_minutes or 0),
                "note": "Reopened — false 6:30 PM logout removed (before office end)",
            }
        )
    return reopened


async def repair_evening_sleep_logouts(
    db: AsyncSession,
    employee_ids: list[uuid.UUID],
    work_date: date,
) -> list[dict]:
    """
    Backend source of truth for Login & Logout + Attendance history.

    Reads each person's presence timeline for the day, decides correct logout from:
    - office Wi-Fi disconnect
    - system sleep after 6:00 PM / system shutdown
    - fallback 6:30 PM when no office Wi-Fi after 6:00 but day ran to midnight

    Writes CLOCK_OUT, recalculates hours, persists shift_end + total_work_minutes.
    """
    if not employee_ids:
        return []
    day_start, day_end = local_day_bounds(work_date)

    first_emp = await db.get(EmployeeProfile, employee_ids[0])
    office_ssids: set[str] = set()
    if first_emp is not None:
        office_ssids = await _office_ssids(db, first_emp.organization_id)

    signals = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id.in_(employee_ids),
                PresenceEvent.occurred_at >= day_start,
                PresenceEvent.occurred_at < day_end,
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()

    by_emp: dict[uuid.UUID, list[PresenceEvent]] = defaultdict(list)
    for sig in signals:
        by_emp[sig.employee_id].append(sig)

    att_days = list(
        (
            await db.execute(
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.events))
                .where(
                    AttendanceDay.employee_id.in_(employee_ids),
                    AttendanceDay.work_date == work_date,
                    AttendanceDay.shift_start.is_not(None),
                )
            )
        ).scalars().all()
    )

    repaired: list[dict] = []
    now = datetime.now(UTC)
    # Undo false morning 6:30 PM outs before applying evening rules.
    repaired.extend(
        await _reopen_premature_eod_fallback_days(db, att_days, work_date=work_date, now=now)
    )
    # Reload after reopen so evening repair sees open sessions.
    if repaired:
        att_days = list(
            (
                await db.execute(
                    select(AttendanceDay)
                    .options(selectinload(AttendanceDay.events))
                    .where(
                        AttendanceDay.employee_id.in_(employee_ids),
                        AttendanceDay.work_date == work_date,
                        AttendanceDay.shift_start.is_not(None),
                    )
                )
            ).scalars().all()
        )
    for day in att_days:
        emp_sigs = by_emp.get(day.employee_id, [])
        leave_at, reason = _infer_effective_logout(
            emp_sigs,
            work_date=work_date,
            office_ssids=office_ssids,
        )
        ordered = sorted(day.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
        still_open = bool(ordered) and is_clock_in(ordered[-1].event_type)
        shift_end = ensure_utc(day.shift_end)
        if leave_at is None:
            leave_at, reason = _fallback_eod_without_office_wifi(
                emp_sigs,
                work_date=work_date,
                office_ssids=office_ssids,
                shift_end=shift_end,
                day_end=day_end,
                now=now,
            )
        if leave_at is None or reason is None:
            continue

        close_at = _logout_timestamp_for_day(
            work_date,
            leave_at,
            not_before=ensure_utc(day.shift_start),
        )
        # Do not force-close an active session before office end with the EOD fallback.
        if reason == "eod_no_office_wifi" and still_open and now < close_at:
            continue
        # Persist whenever stored logout is missing, still open (after EOD rules), at day-end, or later than rule.
        needs = still_open or shift_end is None or shift_end >= day_end - timedelta(minutes=1) or (
            shift_end is not None and shift_end > close_at + timedelta(minutes=2)
        )
        # Also fix when hours are inflated vs login→rule logout.
        if not needs and day.shift_start is not None:
            expected = max(0, int((close_at - (ensure_utc(day.shift_start) or close_at)).total_seconds() // 60))
            if (day.total_work_minutes or 0) > expected + 15:
                needs = True
        if not needs:
            continue

        note = _logout_note_for_reason(reason)
        has_matching_out = False
        for e in ordered:
            et = str(getattr(e.event_type, "value", e.event_type)).upper()
            ts = ensure_utc(e.timestamp)
            if "CLOCK_OUT" not in et or ts is None:
                continue
            if abs((ts - close_at).total_seconds()) < 90 and (
                reason.replace("_", " ") in (e.notes or "").lower()
                or "office wi-fi" in (e.notes or "").lower()
                or "system sleep" in (e.notes or "").lower()
                or "shut down" in (e.notes or "").lower()
                or "not on office" in (e.notes or "").lower()
                or "rule-logout" in (e.client_event_id or "")
            ):
                has_matching_out = True
                break

        if not has_matching_out:
            await _add_attendance_event(
                db,
                day,
                AttendanceEventType.CLOCK_OUT,
                close_at,
                f"presence:rule-logout:{day.id}:{int(close_at.timestamp())}"[:100],
                note,
            )

        status_key = {
            "shutdown": "EOD_SHUTDOWN",
            "sleep": "EOD_SLEEP",
            "office_wifi": "OFFICE_WIFI",
            "app_logout": "APP_LOGOUT",
            "eod_no_office_wifi": "EOD_NO_OFFICE_WIFI",
        }.get(reason, "AUTO_LOGOUT")
        _apply_workday_metadata(day, f"WORKDAY|AUTO_LOGOUT|{status_key}|0 — {note}")
        meta = dict(day.metadata_json or {})
        meta["corrected_logout_at"] = close_at.isoformat()
        meta["corrected_logout_reason"] = reason
        meta["sleep_auto_logout_at"] = close_at.isoformat()
        meta["sleep_auto_logout_reason"] = f"{reason}_repair"
        day.metadata_json = meta
        await recalculate_attendance_day(db, day.id)
        # Keep stored rollup aligned to rule logout even if a later spurious out exists.
        refreshed = (
            await db.execute(
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.events))
                .where(AttendanceDay.id == day.id)
            )
        ).scalars().first()
        if refreshed is not None:
            day = refreshed
            # If recalculate still left a later shift_end (spurious out), clamp stored fields.
            stored_end = ensure_utc(day.shift_end)
            if stored_end is None or stored_end > close_at + timedelta(minutes=2):
                day.shift_end = close_at
                start = ensure_utc(day.shift_start) or close_at
                day.total_work_minutes = max(0, int((close_at - start).total_seconds() // 60))
                await db.flush()

        repaired.append(
            {
                "employee_id": str(day.employee_id),
                "full_name": None,
                "work_date": work_date.isoformat(),
                "reason": reason,
                "login_at": (ensure_utc(day.shift_start) or close_at).isoformat(),
                "logout_at": close_at.isoformat(),
                "worked_minutes": int(day.total_work_minutes or 0),
                "note": note,
            }
        )
    return repaired


async def repair_organization_history(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    days: int = 3,
) -> dict:
    """
    Scan Attendance history for the whole org for today and previous days-1,
    correct logout + hours from presence rules, return what changed.
    """
    days = max(1, min(int(days), 14))
    today = local_work_date(datetime.now(UTC))
    emp_ids = list(
        (
            await db.execute(
                select(EmployeeProfile.id).where(
                    EmployeeProfile.organization_id == organization_id,
                    EmployeeProfile.employment_status != EmploymentStatus.TERMINATED,
                )
            )
        ).scalars().all()
    )
    name_rows = (
        await db.execute(
            select(EmployeeProfile.id, EmployeeProfile.first_name, EmployeeProfile.last_name).where(
                EmployeeProfile.id.in_(emp_ids)
            )
        )
    ).all() if emp_ids else []
    names = {r[0]: f"{r[1]} {r[2]}".strip() for r in name_rows}

    all_fixed: list[dict] = []
    for offset in range(days):
        work_date = today - timedelta(days=offset)
        fixed = await repair_evening_sleep_logouts(db, emp_ids, work_date)
        for row in fixed:
            try:
                eid = uuid.UUID(str(row["employee_id"]))
            except (ValueError, TypeError):
                eid = None
            row["full_name"] = names.get(eid) if eid else None
            row["employee_id"] = str(row["employee_id"])
        all_fixed.extend(fixed)

    await db.commit()
    return {
        "status": "ok",
        "days_checked": days,
        "from_date": (today - timedelta(days=days - 1)).isoformat(),
        "to_date": today.isoformat(),
        "repaired_count": len(all_fixed),
        "repaired": all_fixed,
    }


async def get_presence_days(
    db: AsyncSession,
    employee: EmployeeProfile,
    start_date: date,
    end_date: date,
) -> list[PresenceDay]:
    """Per-day login/logout table rows (newest first) with the raw app and Wi-Fi events of each day."""
    now = datetime.now(UTC)
    # Repair only recent days (today + 2) — full-month repair on every history view is too heavy/risky.
    today_local = local_work_date(now)
    cursor = start_date
    while cursor <= end_date:
        if cursor >= today_local - timedelta(days=2):
            await repair_evening_sleep_logouts(db, [employee.id], cursor)
        cursor = cursor + timedelta(days=1)

    days = (
        await db.execute(
            select(AttendanceDay)
            .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
            .where(
                AttendanceDay.employee_id == employee.id,
                AttendanceDay.work_date >= start_date,
                AttendanceDay.work_date <= end_date,
            )
        )
    ).scalars().all()
    day_map = {d.work_date: d for d in days}

    range_start, range_end = _day_bounds(start_date, end_date)
    events = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id == employee.id,
                PresenceEvent.occurred_at >= range_start,
                PresenceEvent.occurred_at < range_end,
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()
    events_by_date: dict[date, list[PresenceEvent]] = defaultdict(list)
    for ev in events:
        occurred = ensure_utc(ev.occurred_at) or now
        events_by_date[local_work_date(occurred)].append(ev)

    rows: list[PresenceDay] = []
    for work_date in sorted(set(day_map) | set(events_by_date), reverse=True):
        att = day_map.get(work_date)
        day_events = events_by_date.get(work_date, [])
        row = PresenceDay(
            work_date=work_date,
            events=[
                PresenceEventOut(
                    event_type=e.event_type,
                    occurred_at=ensure_utc(e.occurred_at) or now,
                    ssid=e.ssid,
                    attendance_action=e.attendance_action,
                )
                for e in day_events
            ],
        )

        wifi_at, wifi_names = _wifi_display_from_events(day_events)
        row.first_wifi_connected_at = wifi_at
        row.wifi_networks = wifi_names

        if att is not None:
            breaks = list(att.breaks or [])
            row.break_count = len(breaks)
            row.total_break_minutes = att.total_break_minutes or 0
            # Merge break start/end into the same timeline managers see under Attendance history.
            break_rows: list[PresenceBreakOut] = []
            for br in breaks:
                btype = br.break_type.value if hasattr(br.break_type, "value") else str(br.break_type)
                source = br.source or "AUTO"
                start_at = ensure_utc(br.start_time) or now
                end_at = ensure_utc(br.end_time) if br.end_time is not None else None
                mins = br.duration_minutes
                if mins is None and end_at is not None:
                    mins = max(0, int((end_at - start_at).total_seconds() // 60))
                reason = br.reason
                admin_kept = bool(reason and "admin kept" in reason.lower())
                break_rows.append(
                    PresenceBreakOut(
                        id=br.id,
                        break_type=btype,
                        start_time=start_at,
                        end_time=end_at,
                        duration_minutes=mins,
                        source=source,
                        reason=reason,
                        is_paid=bool(br.is_paid),
                        admin_kept=admin_kept,
                    )
                )
                row.events.append(
                    PresenceEventOut(
                        event_type="BREAK_START",
                        occurred_at=start_at,
                        ssid=None,
                        attendance_action="NONE",
                        detail=f"{btype} · {source}",
                        break_id=br.id,
                    )
                )
                if end_at is not None:
                    row.events.append(
                        PresenceEventOut(
                            event_type="BREAK_END",
                            occurred_at=end_at,
                            ssid=None,
                            attendance_action="NONE",
                            detail=f"{btype} · {mins}m",
                            break_id=br.id,
                        )
                    )
            row.breaks = break_rows
            row.events.sort(key=lambda e: ensure_utc(e.occurred_at) or now)
        if att is not None and att.shift_start is not None:
            att = await _autoclose_stale_open_day(db, att, now=now)
            office_ssids = await _office_ssids(db, employee.organization_id)
            leave_at, leave_reason = _infer_effective_logout(
                day_events, work_date=work_date, office_ssids=office_ssids
            )
            logout_for_hours = ensure_utc(att.shift_end)
            if leave_at is None:
                leave_at, leave_reason = _fallback_eod_without_office_wifi(
                    day_events,
                    work_date=work_date,
                    office_ssids=office_ssids,
                    shift_end=logout_for_hours,
                    day_end=local_day_bounds(work_date)[1],
                    now=now,
                )
            if leave_at is not None and (
                logout_for_hours is None or logout_for_hours > leave_at + timedelta(minutes=2)
            ):
                logout_for_hours = leave_at

            from app.core.office_policy import OFFICE_END as _OFFICE_END_DAY

            eod_day = datetime.combine(work_date, _OFFICE_END_DAY, tzinfo=org_zone()).astimezone(UTC)
            day_end_utc = local_day_bounds(work_date)[1]
            # Past days stamped at 11:59 PM (~14h) are the day-cap autoclose, never a real
            # logout. Always show office end (6:30 PM) unless a real evening leave was inferred.
            logout_utc = ensure_utc(logout_for_hours) if logout_for_hours is not None else None
            if (
                work_date < local_work_date(now)
                and logout_utc is not None
                and logout_utc >= day_end_utc - timedelta(minutes=1)
            ):
                if leave_at is None or leave_at >= day_end_utc - timedelta(minutes=1):
                    leave_at, leave_reason = eod_day, "eod_no_office_wifi"
                    logout_for_hours = leave_at

            if now < eod_day and leave_reason == "eod_no_office_wifi":
                leave_at, leave_reason = None, None
            if now < eod_day and logout_for_hours is not None and logout_for_hours > now:
                logout_for_hours = None

            ordered = sorted(att.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
            last_is_in = bool(ordered) and is_clock_in(ordered[-1].event_type)
            last_ts = ensure_utc(ordered[-1].timestamp) if ordered else None
            future_out = (
                bool(ordered)
                and not last_is_in
                and last_ts is not None
                and last_ts > now
                and now < eod_day
            )
            still_open = future_out or (last_is_in and leave_at is None)
            row.is_logged_in = still_open
            row.status = att.status.value if hasattr(att.status, "value") else str(att.status)
            if still_open:
                start, _, mins = _clamp_session_to_work_date(
                    first_login=ensure_utc(att.shift_start),
                    last_logout=None,
                    is_open=True,
                    work_date=work_date,
                    now=now,
                )
                row.first_login = start
                row.worked_minutes = mins
            else:
                start, end, mins = _clamp_session_to_work_date(
                    first_login=ensure_utc(att.shift_start),
                    last_logout=logout_for_hours,
                    is_open=False,
                    work_date=work_date,
                    now=now,
                )
                row.first_login = start
                row.last_logout = end
                row.worked_minutes = mins
                if leave_reason:
                    row.logout_reason = leave_reason
                    row.logout_note = _logout_note_for_reason(leave_reason)
                else:
                    note = _last_clock_out_note(att)
                    if note and " — " in note:
                        note = note.split(" — ", 1)[1]
                    row.logout_note = note
        elif att is not None:
            row.status = att.status.value if hasattr(att.status, "value") else str(att.status)
        rows.append(row)
    return rows


async def get_team_presence(
    db: AsyncSession,
    organization_id: uuid.UUID,
    employee_ids: list[uuid.UUID] | None,
    work_date: date,
) -> tuple[list[TeamPresenceRow], TeamPresenceCounts, int]:
    """
    One row per active employee-role account for the given day: login, logout, Wi-Fi and leave.
    `employee_ids=None` means the whole organization.
    Returns (rows, counts, pending leave requests in scope).
    """
    now = datetime.now(UTC)
    # After 6:30 PM local, auto-logout idle open sessions before building the board.
    from app.services.end_of_day import eod_cutoff_utc, run_end_of_day_idle_logout

    if now >= eod_cutoff_utc(work_date) and work_date == local_work_date(now):
        await run_end_of_day_idle_logout(db, now=now, organization_id=organization_id)

    stmt = (
        select(EmployeeProfile)
        .join(User, User.id == EmployeeProfile.user_id)
        .join(Role, Role.id == User.role_id)
        .options(selectinload(EmployeeProfile.department))
        .where(
            EmployeeProfile.organization_id == organization_id,
            EmployeeProfile.employment_status != EmploymentStatus.TERMINATED,
            User.is_active.is_(True),
            func.lower(Role.name) == "employee",
        )
        .order_by(EmployeeProfile.first_name, EmployeeProfile.last_name)
    )
    if employee_ids is not None:
        if not employee_ids:
            return [], TeamPresenceCounts(), 0
        stmt = stmt.where(EmployeeProfile.id.in_(employee_ids))
    employees = (await db.execute(stmt)).scalars().all()
    ids = [e.id for e in employees]
    if not ids:
        return [], TeamPresenceCounts(), 0

    # Close overnight open sessions from earlier days before building today's board.
    await _autoclose_prior_open_sessions(db, ids, before_date=work_date, now=now)
    # Fix selected day + previous two days (e.g. open 18 → also repair 17 and 16).
    await repair_evening_sleep_logouts(db, ids, work_date)
    await repair_evening_sleep_logouts(db, ids, work_date - timedelta(days=1))
    await repair_evening_sleep_logouts(db, ids, work_date - timedelta(days=2))

    att_days = (
        await db.execute(
            select(AttendanceDay)
            .options(selectinload(AttendanceDay.events), selectinload(AttendanceDay.breaks))
            .where(AttendanceDay.employee_id.in_(ids), AttendanceDay.work_date == work_date)
        )
    ).scalars().all()
    att_by_emp = {d.employee_id: d for d in att_days}

    day_start, day_end = _day_bounds(work_date, work_date)
    signals = (
        await db.execute(
            select(PresenceEvent)
            .where(
                PresenceEvent.employee_id.in_(ids),
                PresenceEvent.occurred_at >= day_start,
                PresenceEvent.occurred_at < day_end,
            )
            .order_by(PresenceEvent.occurred_at)
        )
    ).scalars().all()
    signals_by_emp: dict[uuid.UUID, list[PresenceEvent]] = defaultdict(list)
    for sig in signals:
        signals_by_emp[sig.employee_id].append(sig)

    leaves = (
        await db.execute(
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.leave_type))
            .where(
                LeaveRequest.employee_id.in_(ids),
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= work_date,
                LeaveRequest.end_date >= work_date,
            )
        )
    ).scalars().all()
    leave_by_emp = {lv.employee_id: lv for lv in leaves}

    pending_leaves = await db.scalar(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.employee_id.in_(ids),
            LeaveRequest.status == LeaveStatus.PENDING,
        )
    ) or 0

    office_ssids = await _office_ssids(db, organization_id)
    rows: list[TeamPresenceRow] = []
    counts = TeamPresenceCounts(total=len(employees))
    for emp in employees:
        row = TeamPresenceRow(
            employee_id=emp.id,
            employee_code=emp.employee_code,
            full_name=f"{emp.first_name} {emp.last_name}".strip(),
            department_name=emp.department.name if emp.department else None,
            status="NOT_LOGGED_IN",
        )
        emp_signals = signals_by_emp.get(emp.id, [])
        if emp_signals:
            row.last_signal_at = ensure_utc(emp_signals[-1].occurred_at)
            wifi_at, wifi_names = _wifi_display_from_events(emp_signals)
            row.first_wifi_connected_at = wifi_at
            row.wifi_networks = wifi_names

        att = att_by_emp.get(emp.id)
        if att is not None and att.shift_start is not None:
            # Close yesterday's open sessions so hours stop at midnight instead of ~24h.
            att = await _autoclose_stale_open_day(db, att, now=now)
            # Repair overnight-inflated rollups / next-morning logout stamps.
            _, day_end = local_day_bounds(work_date)
            shift_end = ensure_utc(att.shift_end)
            needs_repair = (att.total_work_minutes or 0) > 16 * 60 or (
                shift_end is not None and shift_end >= day_end
            )
            if needs_repair:
                await recalculate_attendance_day(db, att.id)
                refreshed = (
                    await db.execute(
                        select(AttendanceDay)
                        .options(selectinload(AttendanceDay.events))
                        .where(AttendanceDay.id == att.id)
                    )
                ).scalars().first()
                if refreshed is not None:
                    att = refreshed
            att_by_emp[emp.id] = att
            leave_at, leave_reason = _infer_effective_logout(
                emp_signals, work_date=work_date, office_ssids=office_ssids
            )
            logout_for_hours = ensure_utc(att.shift_end)
            if leave_at is None:
                leave_at, leave_reason = _fallback_eod_without_office_wifi(
                    emp_signals,
                    work_date=work_date,
                    office_ssids=office_ssids,
                    shift_end=logout_for_hours,
                    day_end=day_end,
                    now=now,
                )
            if leave_at is not None and (
                logout_for_hours is None or logout_for_hours > leave_at + timedelta(minutes=2)
            ):
                logout_for_hours = leave_at

            # Never show a completed logout that is still in the future (morning board bug).
            from app.core.office_policy import OFFICE_END as _OFFICE_END

            eod_today = datetime.combine(work_date, _OFFICE_END, tzinfo=org_zone()).astimezone(UTC)
            logout_utc = ensure_utc(logout_for_hours) if logout_for_hours is not None else None
            if (
                work_date < local_work_date(now)
                and logout_utc is not None
                and logout_utc >= day_end - timedelta(minutes=1)
            ):
                if leave_at is None or leave_at >= day_end - timedelta(minutes=1):
                    leave_at, leave_reason = eod_today, "eod_no_office_wifi"
                    logout_for_hours = leave_at
            if now < eod_today and leave_reason == "eod_no_office_wifi":
                leave_at, leave_reason = None, None
            if now < eod_today and logout_for_hours is not None and logout_for_hours > now:
                logout_for_hours = None

            row.break_count = len(att.breaks or []) if getattr(att, "breaks", None) is not None else 0
            row.total_break_minutes = int(att.total_break_minutes or 0)

            ordered = sorted(att.events or [], key=lambda e: ensure_utc(e.timestamp) or now)
            last_is_in = bool(ordered) and is_clock_in(ordered[-1].event_type)
            last_ts = ensure_utc(ordered[-1].timestamp) if ordered else None
            # CLOCK_OUT stamped at 6:30 PM while it is still morning → still working.
            future_out = (
                bool(ordered)
                and not last_is_in
                and last_ts is not None
                and last_ts > now
                and now < eod_today
            )
            still_open = future_out or (last_is_in and leave_at is None)
            if still_open:
                row.status = "LOGGED_IN"
                start, _, mins = _clamp_session_to_work_date(
                    first_login=ensure_utc(att.shift_start),
                    last_logout=None,
                    is_open=True,
                    work_date=work_date,
                    now=now,
                )
                row.first_login = start
                row.worked_minutes = mins
            else:
                row.status = "LOGGED_OUT"
                start, end, mins = _clamp_session_to_work_date(
                    first_login=ensure_utc(att.shift_start),
                    last_logout=logout_for_hours,
                    is_open=False,
                    work_date=work_date,
                    now=now,
                )
                row.first_login = start
                row.last_logout = end
                row.worked_minutes = mins
                flags = _workday_fields_from_day(att)
                if leave_reason:
                    row.logout_reason = leave_reason
                    row.logout_note = _logout_note_for_reason(leave_reason)
                    row.auto_logout = True
                else:
                    note = flags.get("logout_note")
                    if isinstance(note, str) and " — " in note:
                        note = note.split(" — ", 1)[1]
                    row.logout_note = note if isinstance(note, str) else None
                    row.auto_logout = bool(flags.get("auto_logout"))
                row.workday_status = flags.get("workday_status") if isinstance(flags.get("workday_status"), str) else None
                row.confirmation_status = (
                    flags.get("confirmation_status") if isinstance(flags.get("confirmation_status"), str) else None
                )
                row.completed_nine_hours = bool(flags.get("completed_nine_hours"))
                row.early_logout = bool(flags.get("early_logout"))

        leave = leave_by_emp.get(emp.id)
        if leave is not None:
            row.leave_type_name = leave.leave_type.name if leave.leave_type else None
            if row.status == "NOT_LOGGED_IN":
                row.status = "ON_LEAVE"

        if row.status == "LOGGED_IN":
            counts.logged_in += 1
        elif row.status == "LOGGED_OUT":
            counts.logged_out += 1
        elif row.status == "ON_LEAVE":
            counts.on_leave += 1
        else:
            counts.not_logged_in += 1
        rows.append(row)

    await db.commit()
    return rows, counts, int(pending_leaves)


async def get_month_summary(
    db: AsyncSession,
    employee: EmployeeProfile,
    year: int,
    month: int,
) -> PresenceMonthSummary:
    """Dashboard totals: working days vs present vs leave vs absent, plus total login time."""
    today = local_work_date(datetime.now(UTC))
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    elapsed_end = min(today, month_end)

    schedule = employee.work_schedule
    working_weekdays = schedule.working_days if (schedule and schedule.working_days) else DEFAULT_WORKING_WEEKDAYS
    holidays = set(
        (
            await db.execute(
                select(Holiday.holiday_date).where(
                    Holiday.organization_id == employee.organization_id,
                    Holiday.holiday_date >= month_start,
                    Holiday.holiday_date <= month_end,
                )
            )
        ).scalars().all()
    )

    def is_working_day(d: date) -> bool:
        return d.isoweekday() in working_weekdays and d not in holidays

    rows = await get_presence_days(db, employee, month_start, month_end)
    present_dates = {r.work_date for r in rows if r.first_login is not None and r.work_date <= elapsed_end}

    leaves = (
        await db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee.id,
                LeaveRequest.status == LeaveStatus.APPROVED,
                LeaveRequest.start_date <= month_end,
                LeaveRequest.end_date >= month_start,
            )
        )
    ).scalars().all()
    leave_days = 0.0
    upcoming_leave_days = 0.0
    leave_dates: set[date] = set()
    for lv in leaves:
        weight = 0.5 if lv.is_half_day else 1.0
        d = max(lv.start_date, month_start)
        while d <= min(lv.end_date, month_end):
            if is_working_day(d):
                if d <= elapsed_end:
                    leave_days += weight
                    leave_dates.add(d)
                else:
                    upcoming_leave_days += weight
            d += timedelta(days=1)

    working_days = 0
    absent_days = 0
    d = month_start
    while d <= elapsed_end:
        if is_working_day(d):
            working_days += 1
            # Today only becomes "absent" once it is over.
            if d < today and d not in present_dates and d not in leave_dates:
                absent_days += 1
        d += timedelta(days=1)

    total_minutes = sum(r.worked_minutes for r in rows if r.work_date <= elapsed_end)
    today_row = next((r for r in rows if r.work_date == today), None)
    if today_row is None:
        today_row = (await get_presence_days(db, employee, today, today) or [PresenceDay(work_date=today)])[0]

    return PresenceMonthSummary(
        month=f"{year:04d}-{month:02d}",
        working_days=working_days,
        present_days=len(present_dates),
        leave_days=leave_days,
        upcoming_leave_days=upcoming_leave_days,
        absent_days=absent_days,
        total_worked_minutes=total_minutes,
        average_daily_minutes=int(total_minutes / len(present_dates)) if present_dates else 0,
        today=today_row,
    )


async def admin_force_logout_open_sessions(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    only_employee_ids: list[uuid.UUID] | None = None,
    keep_employee_codes: list[str] | None = None,
    keep_name_substrings: list[str] | None = None,
    occurred_at: datetime | None = None,
    note: str = "Admin force logout — employee left; desktop still running in background",
) -> dict[str, object]:
    """
    Clock out open sessions.
    - only_employee_ids: logout just those employees (per-row admin Logout).
    - otherwise: logout everyone still open except keep codes/names (bulk).
    """
    now = ensure_utc(occurred_at) or datetime.now(UTC)
    work_date = local_work_date(now)
    keep_codes = {c.strip().upper() for c in (keep_employee_codes or []) if c and c.strip()}
    keep_names = [n.strip().lower() for n in (keep_name_substrings or []) if n and n.strip()]
    only_ids = {eid for eid in (only_employee_ids or []) if eid}

    emp_q = select(EmployeeProfile).where(
        EmployeeProfile.organization_id == organization_id,
        EmployeeProfile.employment_status != EmploymentStatus.TERMINATED,
    )
    if only_ids:
        emp_q = emp_q.where(EmployeeProfile.id.in_(only_ids))
    employees = (await db.execute(emp_q)).scalars().all()

    logged_out: list[dict[str, object]] = []
    kept: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for emp in employees:
        code = (emp.employee_code or "").strip().upper()
        full_name = f"{emp.first_name or ''} {emp.last_name or ''}".strip()
        name_l = full_name.lower()
        # When targeting specific IDs, never apply keep filters.
        keep = (not only_ids) and (code in keep_codes or any(k in name_l for k in keep_names))

        open_session = await _open_session(db, emp.id)
        if open_session is None:
            skipped.append({"employee_code": code, "full_name": full_name, "reason": "not_logged_in"})
            continue
        if keep:
            kept.append({"employee_code": code, "full_name": full_name})
            continue

        day, last_in = open_session
        close_at = _logout_timestamp_for_day(day.work_date, now, not_before=last_in)
        client_id = f"admin:force-logout:{emp.id}:{int(close_at.timestamp())}"
        presence_id = f"admin:force-logout-pe:{emp.id}:{int(close_at.timestamp())}"

        # Close any open break on this day.
        open_breaks = (
            await db.execute(
                select(AttendanceBreak).where(
                    AttendanceBreak.attendance_day_id == day.id,
                    AttendanceBreak.end_time.is_(None),
                )
            )
        ).scalars().all()
        for br in open_breaks:
            finalize_break(br, close_at)

        await _add_attendance_event(
            db,
            day,
            AttendanceEventType.CLOCK_OUT,
            close_at,
            client_id,
            note,
        )
        _apply_workday_metadata(
            day,
            f"WORKDAY|AUTO_LOGOUT|ADMIN_FORCE|0 — {note}",
        )
        db.add(
            PresenceEvent(
                organization_id=organization_id,
                employee_id=emp.id,
                event_type=PresenceEventType.APP_LOGOUT.value,
                occurred_at=close_at,
                client_event_id=presence_id,
                device_id=None,
                ssid=None,
                bssid=None,
                attendance_action=PresenceAttendanceAction.CLOCK_OUT.value,
            )
        )
        await recalculate_attendance_day(db, day.id, commit=False)
        logged_out.append(
            {
                "employee_code": code,
                "full_name": full_name,
                "work_date": day.work_date.isoformat(),
                "logout_at": close_at.isoformat(),
            }
        )

    await db.commit()
    return {
        "status": "ok",
        "work_date": work_date.isoformat(),
        "logged_out_count": len(logged_out),
        "kept_count": len(kept),
        "logged_out": logged_out,
        "kept": kept,
        "skipped_count": len(skipped),
    }
