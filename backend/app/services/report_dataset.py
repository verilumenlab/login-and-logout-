"""
Report Dataset Builder

Collects one organization's attendance, leave and desktop presence (app login/logout,
laptop Wi-Fi connect/disconnect) for a date window and shapes it into the row dicts
consumed by ExcelReportEngine. Shared by the Friday scheduler and the manual send API.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.attendance import AttendanceDay, AttendanceEvent, AttendanceEventType, AttendanceStatus
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.office import LocationVerification
from app.models.os_event import OSSessionEvent
from app.models.presence import PresenceEvent, PresenceEventType
from app.models.schedule import Holiday
from app.services.attendance_engine import ensure_utc

DEFAULT_WORKING_WEEKDAYS = [1, 2, 3, 4, 5]

_PRESENCE_LABELS = {
    PresenceEventType.APP_LOGIN.value: "App login",
    PresenceEventType.APP_LOGOUT.value: "App logout",
    PresenceEventType.WIFI_CONNECTED.value: "Wi-Fi connected",
    PresenceEventType.WIFI_DISCONNECTED.value: "Wi-Fi disconnected",
}
_PRESENCE_EFFECT = {"CLOCK_IN": "Login recorded", "CLOCK_OUT": "Logout recorded"}


def _tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("UTC")


def _source_label(notes: str | None, source: Any) -> str:
    text = (notes or "").lower()
    if text.startswith("wi-fi"):
        return "WI-FI"
    if text.startswith("desktop app"):
        return "DESKTOP APP"
    if text.startswith("auto-closed"):
        return "AUTO-CLOSED"
    return source.value if hasattr(source, "value") else str(source or "")


def _gps_coords(event: AttendanceEvent | None) -> tuple[str, str]:
    """Latitude/longitude from the location event linked to a clock-in/out, if any."""
    if event is None:
        return "", ""
    verification = event.location_verification
    if verification is None or verification.location_event is None:
        return "", ""
    loc = verification.location_event
    return str(loc.latitude), str(loc.longitude)


def _empty_attendance_fields(
    *,
    status: str,
    scheduled_start: str = "",
    leave_type: str = "",
    location_status: str = "",
    gps_latitude: str = "",
    gps_longitude: str = "",
) -> dict[str, Any]:
    return {
        "clock_in": "",
        "clock_out": "",
        "work_duration": "",
        "gross_duration_hours": 0.0,
        "break_duration_hours": 0.0,
        "break_minutes": 0,
        "break_count": 0,
        "net_duration_hours": 0.0,
        "status": status,
        "late_minutes": 0,
        "scheduled_start": scheduled_start,
        "location_status": location_status,
        "logout_source": "",
        "first_wifi_connected": "",
        "wifi_networks": "",
        "leave_type": leave_type,
        "gps_latitude": gps_latitude,
        "gps_longitude": gps_longitude,
    }


@dataclass
class ReportDataset:
    employees: list[EmployeeProfile]
    employees_data: list[dict[str, Any]] = field(default_factory=list)
    attendance_logs: list[dict[str, Any]] = field(default_factory=list)
    os_events: list[dict[str, Any]] = field(default_factory=list)
    leaves_data: list[dict[str, Any]] = field(default_factory=list)
    wifi_logs: list[dict[str, Any]] = field(default_factory=list)
    exceptions_data: list[dict[str, Any]] = field(default_factory=list)

    def for_employees(self, employee_ids: set[str]) -> ReportDataset:
        """Subset restricted to the given employees (e.g. one manager's team)."""
        def keep(rows: list[dict[str, Any]], key: str = "employee_id") -> list[dict[str, Any]]:
            return [r for r in rows if r.get(key) in employee_ids]

        return ReportDataset(
            employees=[e for e in self.employees if str(e.id) in employee_ids],
            employees_data=keep(self.employees_data, "id"),
            attendance_logs=keep(self.attendance_logs),
            os_events=keep(self.os_events),
            leaves_data=keep(self.leaves_data),
            wifi_logs=keep(self.wifi_logs),
            exceptions_data=keep(self.exceptions_data),
        )

    def stats(self, scope: str) -> dict[str, Any]:
        worked = [a for a in self.attendance_logs if a.get("clock_in")]
        total_net = sum(float(a["net_duration_hours"]) for a in worked)
        possible_days = sum(int(e["total_days"]) for e in self.employees_data)
        present_days = sum(int(e["present_days"]) for e in self.employees_data)
        return {
            "scope": scope,
            "present_count": len({a["employee_id"] for a in worked}),
            "late_count": sum(int(e["late_days"]) for e in self.employees_data),
            "leave_count": len(self.leaves_data),
            "absent_days": sum(1 for a in self.attendance_logs if a["status"] == "ABSENT"),
            "total_net_hours": round(total_net, 1),
            "total_working_hours": round(total_net, 1),
            "total_break_hours": round(sum(float(a["break_duration_hours"]) for a in worked), 1),
            "total_break_count": sum(int(a.get("break_count") or 0) for a in worked),
            "attendance_rate": round(present_days / possible_days * 100, 1) if possible_days else 0.0,
            "resolved_leaves": sum(1 for lv in self.leaves_data if lv["status"] in ("APPROVED", "REJECTED")),
            "active_headcount": len(self.employees_data),
            "compliance_rate": round(
                100.0 * (1 - len(self.exceptions_data) / max(1, len(self.attendance_logs))), 1
            ),
            "total_overtime_hours": round(sum(max(0.0, float(a["net_duration_hours"]) - 8.0) for a in worked), 1),
        }


async def build_report_dataset(
    db: AsyncSession,
    organization_id: uuid.UUID,
    start_date: date,
    end_date: date,
    tz_name: str = "UTC",
    *,
    include_all_calendar_days: bool = False,
) -> ReportDataset:
    tz = _tz(tz_name)
    today_local = datetime.now(tz).date()
    window_start = datetime.combine(start_date, time.min, tzinfo=tz).astimezone(UTC)
    window_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)

    employees = list(
        (
            await db.execute(
                select(EmployeeProfile)
                .options(
                    selectinload(EmployeeProfile.user),
                    selectinload(EmployeeProfile.department),
                    selectinload(EmployeeProfile.work_schedule),
                    selectinload(EmployeeProfile.direct_managers).selectinload(ManagerAssignment.manager).selectinload(EmployeeProfile.user),
                    selectinload(EmployeeProfile.direct_reports).selectinload(ManagerAssignment.employee).selectinload(EmployeeProfile.user),
                )
                .where(
                    EmployeeProfile.organization_id == organization_id,
                    EmployeeProfile.employment_status == EmploymentStatus.ACTIVE,
                )
                .order_by(EmployeeProfile.employee_code)
            )
        ).scalars().all()
    )
    emp_ids = [e.id for e in employees]

    attendance_days = (
        await db.execute(
            select(AttendanceDay)
            .options(
                selectinload(AttendanceDay.events)
                .selectinload(AttendanceEvent.location_verification)
                .selectinload(LocationVerification.location_event),
                selectinload(AttendanceDay.breaks),
            )
            .where(
                AttendanceDay.organization_id == organization_id,
                AttendanceDay.work_date >= start_date,
                AttendanceDay.work_date <= end_date,
            )
            .order_by(AttendanceDay.work_date)
        )
    ).scalars().all()

    leaves = (
        await db.execute(
            select(LeaveRequest)
            .options(selectinload(LeaveRequest.leave_type))
            .where(
                LeaveRequest.organization_id == organization_id,
                LeaveRequest.start_date <= end_date,
                LeaveRequest.end_date >= start_date,
            )
            .order_by(LeaveRequest.start_date)
        )
    ).scalars().all()

    holidays = set(
        (
            await db.execute(
                select(Holiday.holiday_date).where(
                    Holiday.organization_id == organization_id,
                    Holiday.holiday_date >= start_date,
                    Holiday.holiday_date <= end_date,
                )
            )
        ).scalars().all()
    )

    presence_events = []
    os_events = []
    if emp_ids:
        presence_events = (
            await db.execute(
                select(PresenceEvent)
                .where(
                    PresenceEvent.employee_id.in_(emp_ids),
                    PresenceEvent.occurred_at >= window_start,
                    PresenceEvent.occurred_at < window_end,
                )
                .order_by(PresenceEvent.occurred_at)
            )
        ).scalars().all()
        os_events = (
            await db.execute(
                select(OSSessionEvent).where(
                    OSSessionEvent.employee_id.in_(emp_ids),
                    OSSessionEvent.occurred_at >= window_start,
                    OSSessionEvent.occurred_at < window_end,
                )
            )
        ).scalars().all()

    def local(dt: datetime | None) -> datetime | None:
        utc_dt = ensure_utc(dt)
        return utc_dt.astimezone(tz) if utc_dt else None

    def hhmm(dt: datetime | None) -> str:
        loc = local(dt)
        return loc.strftime("%H:%M") if loc else ""

    ds = ReportDataset(employees=employees)
    emp_map = {e.id: e for e in employees}
    identity: dict[uuid.UUID, dict[str, str]] = {}
    for e in employees:
        managers = ", ".join(
            f"{a.manager.first_name} {a.manager.last_name}" for a in e.direct_managers if a.manager
        )
        identity[e.id] = {
            "employee_id": str(e.id),
            "employee_code": e.employee_code,
            "employee_name": f"{e.first_name} {e.last_name}",
            "department": e.department.name if e.department else "",
            "manager": managers or "None",
        }

    wifi_by_emp_date: dict[tuple[uuid.UUID, date], list[PresenceEvent]] = {}
    for ev in presence_events:
        ident = identity.get(ev.employee_id)
        occurred = local(ev.occurred_at)
        if ident is None or occurred is None:
            continue
        ds.wifi_logs.append({
            **ident,
            "date": str(occurred.date()),
            "event": _PRESENCE_LABELS.get(ev.event_type, ev.event_type),
            "time": occurred.strftime("%H:%M:%S"),
            "ssid": ev.ssid or "",
            "bssid": ev.bssid or "",
            "device": ev.device_id or "",
            "effect": _PRESENCE_EFFECT.get(ev.attendance_action, ""),
        })
        if ev.event_type == PresenceEventType.WIFI_CONNECTED.value:
            wifi_by_emp_date.setdefault((ev.employee_id, occurred.date()), []).append(ev)

    leave_weight: dict[tuple[uuid.UUID, date], float] = {}
    leave_type_by_day: dict[tuple[uuid.UUID, date], str] = {}
    for lv in leaves:
        ident = identity.get(lv.employee_id)
        if ident is None:
            continue
        leave_name = lv.leave_type.name if lv.leave_type else "Leave"
        ds.leaves_data.append({
            **ident,
            "leave_type": leave_name,
            "created_at": str(local(getattr(lv, "created_at", None)).date()) if getattr(lv, "created_at", None) else "",
            "start_date": str(lv.start_date),
            "end_date": str(lv.end_date),
            "total_days": float(lv.total_days),
            "status": lv.status.value,
            "manager_status": lv.manager_approval_status.value,
            "hr_status": lv.hr_approval_status.value,
            "reason": lv.reason or "",
        })
        if lv.status == LeaveStatus.APPROVED:
            d = max(lv.start_date, start_date)
            while d <= min(lv.end_date, end_date):
                leave_weight[(lv.employee_id, d)] = 0.5 if lv.is_half_day else 1.0
                leave_type_by_day[(lv.employee_id, d)] = leave_name
                d += timedelta(days=1)

    att_by_emp: dict[uuid.UUID, dict[date, AttendanceDay]] = {}
    for a in attendance_days:
        if a.employee_id in emp_map:
            att_by_emp.setdefault(a.employee_id, {})[a.work_date] = a

    for e in employees:
        ident = identity[e.id]
        schedule = e.work_schedule
        weekdays = schedule.working_days if (schedule and schedule.working_days) else DEFAULT_WORKING_WEEKDAYS
        scheduled_start = schedule.shift_start_time.strftime("%H:%M") if schedule else ""
        calendar_dates = [
            start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)
        ]
        working_dates = [
            d for d in calendar_dates if d.isoweekday() in weekdays and d not in holidays
        ]
        days = att_by_emp.get(e.id, {})
        worked_days = {d: a for d, a in days.items() if a.shift_start is not None}
        base_dates = calendar_dates if include_all_calendar_days else working_dates

        for work_date in sorted(set(worked_days) | {d for d in base_dates if d <= today_local}):
            a = worked_days.get(work_date)
            day_leave = leave_type_by_day.get((e.id, work_date), "")
            if a is None:
                if leave_weight.get((e.id, work_date), 0.0) >= 1.0:
                    ds.attendance_logs.append({
                        **ident,
                        "work_date": str(work_date),
                        **_empty_attendance_fields(
                            status="ON_LEAVE",
                            scheduled_start=scheduled_start,
                            leave_type=day_leave or "Leave",
                        ),
                    })
                    continue
                if work_date in holidays:
                    ds.attendance_logs.append({
                        **ident,
                        "work_date": str(work_date),
                        **_empty_attendance_fields(status="HOLIDAY", scheduled_start=scheduled_start),
                    })
                    continue
                if work_date.isoweekday() not in weekdays:
                    ds.attendance_logs.append({
                        **ident,
                        "work_date": str(work_date),
                        **_empty_attendance_fields(status="WEEKEND", scheduled_start=scheduled_start),
                    })
                    continue
                ds.attendance_logs.append({
                    **ident,
                    "work_date": str(work_date),
                    **_empty_attendance_fields(status="ABSENT", scheduled_start=scheduled_start),
                })
                ds.exceptions_data.append({
                    **ident,
                    "date": str(work_date),
                    "category": "ABSENT",
                    "evidence": "No app login or Wi-Fi connection and no approved leave",
                    "severity": "HIGH",
                    "status": "OPEN",
                    "remarks": "",
                })
                continue

            ordered = sorted(a.events, key=lambda ev: ensure_utc(ev.timestamp) or window_start)
            first_in = next((ev for ev in ordered if ev.event_type == AttendanceEventType.CLOCK_IN), None)
            last_out = next((ev for ev in reversed(ordered) if ev.event_type == AttendanceEventType.CLOCK_OUT), None)
            still_open = bool(ordered) and ordered[-1].event_type == AttendanceEventType.CLOCK_IN
            net_min = a.total_work_minutes or 0
            break_min = a.total_break_minutes or 0
            break_count = len(a.breaks or [])
            wifi_events = wifi_by_emp_date.get((e.id, work_date), [])
            logout_source = "" if still_open else (_source_label(last_out.notes, last_out.source) if last_out else "")
            gps_lat, gps_lng = _gps_coords(first_in)
            if not gps_lat and last_out is not None:
                gps_lat, gps_lng = _gps_coords(last_out)
            status_value = a.status.value
            leave_label = day_leave
            if status_value == AttendanceStatus.ON_LEAVE.value and not leave_label:
                leave_label = "Leave"

            ds.attendance_logs.append({
                **ident,
                "work_date": str(work_date),
                "clock_in": hhmm(a.shift_start),
                "clock_out": "Still logged in" if still_open else hhmm(a.shift_end),
                "work_duration": f"{(net_min + break_min) // 60}h {(net_min + break_min) % 60:02d}m",
                "gross_duration_hours": round((net_min + break_min) / 60.0, 2),
                "break_duration_hours": round(break_min / 60.0, 2),
                "break_minutes": break_min,
                "break_count": break_count,
                "net_duration_hours": round(net_min / 60.0, 2),
                "status": status_value,
                "late_minutes": a.late_minutes or 0,
                "scheduled_start": scheduled_start,
                "location_status": _source_label(first_in.notes, first_in.source) if first_in else "",
                "logout_source": logout_source,
                "first_wifi_connected": hhmm(wifi_events[0].occurred_at) if wifi_events else "",
                "wifi_networks": ", ".join(dict.fromkeys(ev.ssid for ev in wifi_events if ev.ssid)),
                "leave_type": leave_label,
                "gps_latitude": gps_lat,
                "gps_longitude": gps_lng,
            })

            missing_logout = logout_source == "AUTO-CLOSED" or a.is_missing_checkout or (
                still_open and work_date < today_local
            )
            if missing_logout:
                ds.exceptions_data.append({
                    **ident,
                    "date": str(work_date),
                    "category": "MISSING_LOGOUT",
                    "evidence": f"Login {hhmm(a.shift_start)}; no app logout or Wi-Fi disconnect received",
                    "severity": "MEDIUM",
                    "status": "OPEN",
                    "remarks": "Logout time taken from the last signal seen" if logout_source == "AUTO-CLOSED" else "",
                })
            if a.status == AttendanceStatus.LATE or (a.late_minutes or 0) > 0:
                ds.exceptions_data.append({
                    **ident,
                    "date": str(work_date),
                    "category": "LATE_ARRIVAL",
                    "evidence": f"Login {hhmm(a.shift_start)} vs scheduled {scheduled_start or 'n/a'}",
                    "severity": "LOW",
                    "status": "OPEN",
                    "remarks": f"{a.late_minutes} minutes late",
                })

        ds.employees_data.append({
            "id": str(e.id),
            "employee_code": e.employee_code,
            "code": e.employee_code,
            "full_name": ident["employee_name"],
            "name": ident["employee_name"],
            "email": e.user.email if e.user else "",
            "department": ident["department"],
            "manager": ident["manager"],
            "hire_date": str(e.hire_date),
            "total_days": len(working_dates),
            "present_days": len(worked_days),
            "late_days": sum(1 for a in worked_days.values() if a.status == AttendanceStatus.LATE or (a.late_minutes or 0) > 0),
            "leave_days": sum(leave_weight.get((e.id, d), 0.0) for d in working_dates),
            "total_hours": round(sum((a.total_work_minutes or 0) for a in worked_days.values()) / 60.0, 2),
        })

    for ev in os_events:
        ident = identity.get(ev.employee_id)
        if ident is None:
            continue
        loc = local(ev.occurred_at)
        ds.os_events.append({
            **ident,
            "event_type": ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type),
            "occurred_at": loc.strftime("%Y-%m-%d %H:%M:%S") if loc else "",
            "operating_system": ev.operating_system.value if hasattr(ev.operating_system, "value") else str(ev.operating_system),
            "sync_status": "SYNCED",
        })

    for row in ds.attendance_logs:
        row["date"] = row["work_date"]
        row["net_hours"] = row["net_duration_hours"]
    ds.attendance_logs.sort(key=lambda r: (r["work_date"], r["employee_code"]))
    ds.exceptions_data.sort(key=lambda r: (r["date"], r["employee_code"]))
    return ds
