"""
Combined HR attendance CSV export (weekly Mon–Fri / monthly full calendar).

Filenames:
  Weekly_Attendance_YYYY-MM-DD_to_YYYY-MM-DD.csv
  Monthly_Attendance_MonthName_YYYY.csv
"""

from __future__ import annotations

import calendar
import csv
import io
from datetime import date, timedelta
from typing import Literal

from app.services.report_dataset import ReportDataset

ExportPeriod = Literal["weekly", "monthly"]

CSV_HEADERS = [
    "Date",
    "Code",
    "Name",
    "Department",
    "Status",
    "Login",
    "Logout",
    "Hours",
    "Leave",
    "First Wi-Fi",
    "Wi-Fi networks",
    "GPS lat",
    "GPS lng",
    "Location source",
]


def weekly_range(ref: date) -> tuple[date, date]:
    """Monday–Friday of the ISO week containing `ref`."""
    monday = ref - timedelta(days=ref.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def monthly_range(ref: date) -> tuple[date, date]:
    """First and last calendar day of the month containing `ref`."""
    last_day = calendar.monthrange(ref.year, ref.month)[1]
    return date(ref.year, ref.month, 1), date(ref.year, ref.month, last_day)


def period_range(period: ExportPeriod, ref: date) -> tuple[date, date]:
    if period == "weekly":
        return weekly_range(ref)
    return monthly_range(ref)


def csv_filename(period: ExportPeriod, start: date, end: date) -> str:
    if period == "weekly":
        return f"Weekly_Attendance_{start.isoformat()}_to_{end.isoformat()}.csv"
    month_name = calendar.month_name[start.month]
    return f"Monthly_Attendance_{month_name}_{start.year}.csv"


def _hours_cell(row: dict) -> str:
    duration = row.get("work_duration") or ""
    if duration:
        return str(duration)
    hours = row.get("net_duration_hours")
    if hours is None or hours == "" or float(hours or 0) == 0:
        return ""
    total_min = int(round(float(hours) * 60))
    return f"{total_min // 60}h {total_min % 60:02d}m"


def _display_date(raw: object) -> str:
    """
    DD-MM-YYYY for Excel (IST locale). Avoid bare YYYY-MM-DD — Excel turns it into a
    date serial and shows ######## when the column is narrow.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text[:10]).strftime("%d-%m-%Y")
    except ValueError:
        return text


def build_attendance_csv(
    dataset: ReportDataset,
    period: ExportPeriod,
    start: date,
    end: date,
) -> tuple[str, bytes]:
    """
    Build UTF-8 CSV bytes sorted by date then employee code.
    Weekly exports drop Saturday/Sunday rows.
    """
    rows = list(dataset.attendance_logs)
    if period == "weekly":
        rows = [
            r
            for r in rows
            if date.fromisoformat(str(r["work_date"])).isoweekday() <= 5
        ]
    rows.sort(key=lambda r: (str(r["work_date"]), str(r.get("employee_code") or "")))

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for r in rows:
        writer.writerow(
            [
                _display_date(r.get("work_date") or r.get("date") or ""),
                r.get("employee_code") or "",
                r.get("employee_name") or "",
                r.get("department") or "",
                r.get("status") or "",
                r.get("clock_in") or "",
                r.get("clock_out") or "",
                _hours_cell(r),
                r.get("leave_type") or "",
                r.get("first_wifi_connected") or "",
                r.get("wifi_networks") or "",
                r.get("gps_latitude") or "",
                r.get("gps_longitude") or "",
                r.get("location_status") or "",
            ]
        )

    # BOM helps Excel on Windows open UTF-8 correctly
    payload = ("\ufeff" + buf.getvalue()).encode("utf-8")
    return csv_filename(period, start, end), payload
