"""
Excel Report Generation Engine (Phase 11)
Professional multi-worksheet Excel workbook generation using openpyxl.

Supports:
1. Daily Reports
2. Weekly Reports
3. Monthly Reports
4. Individual Employee Workbooks
5. Consolidated Company/HR Workbooks
6. Manager Team Reports

Includes:
- Professional styling, corporate palette, header banners, thin gridlines
- Validated Excel formulas: =SUM(), =AVERAGE(), =COUNTIF()
- Auto-adjusted column widths
- Multiple worksheets (Summary, Attendance Logs, OS Activity Events, Leave Details)
- Strict employee data isolation (Zero leakage of other employees in individual reports)
"""

from __future__ import annotations

import logging
import os
import pathlib
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Sequence

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger("enterprise.reports")

# Corporate Style Constants
COLOR_NAVY = "1E3A8A"
COLOR_LIGHT_BLUE = "DBEAFE"
COLOR_SLATE_HEADER = "F1F5F9"
COLOR_TEXT_MAIN = "0F172A"
COLOR_WHITE = "FFFFFF"

COLOR_GREEN_BG = "DCFCE7"
COLOR_GREEN_TXT = "166534"
COLOR_AMBER_BG = "FEF3C7"
COLOR_AMBER_TXT = "92400E"
COLOR_RED_BG = "FEE2E2"
COLOR_RED_TXT = "991B1B"
COLOR_BLUE_BG = "E0F2FE"
COLOR_BLUE_TXT = "075985"

FONT_TITLE = Font(name="Calibri", size=15, bold=True, color=COLOR_WHITE)
FONT_SECTION = Font(name="Calibri", size=11, bold=True, color=COLOR_TEXT_MAIN)
FONT_HEADER = Font(name="Calibri", size=10, bold=True, color=COLOR_WHITE)
FONT_REGULAR = Font(name="Calibri", size=10, color=COLOR_TEXT_MAIN)
FONT_BOLD = Font(name="Calibri", size=10, bold=True, color=COLOR_TEXT_MAIN)
FONT_CODE = Font(name="Consolas", size=9.5, color=COLOR_TEXT_MAIN)

FILL_TITLE = PatternFill(start_color=COLOR_NAVY, end_color=COLOR_NAVY, fill_type="solid")
FILL_HEADER = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
FILL_SUBHEADER = PatternFill(start_color=COLOR_SLATE_HEADER, end_color=COLOR_SLATE_HEADER, fill_type="solid")
FILL_TOTAL = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

THIN_SIDE = Side(border_style="thin", color="CBD5E1")
DOUBLE_BOTTOM = Side(border_style="double", color="0F172A")
BORDER_CELL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)
BORDER_TOTAL = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=DOUBLE_BOTTOM)

ALIGN_LEFT = Alignment(horizontal="left", vertical="center")
ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
ALIGN_RIGHT = Alignment(horizontal="right", vertical="center")


def _apply_status_badge(cell, status_val: str):
    """Applies conditional soft badge styling to status cells."""
    val = str(status_val or "").upper()
    if val in ("PRESENT", "APPROVED", "VERIFIED", "COMPLETED"):
        cell.fill = PatternFill(start_color=COLOR_GREEN_BG, end_color=COLOR_GREEN_BG, fill_type="solid")
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_GREEN_TXT)
    elif val in ("LATE", "PENDING", "HALF_DAY"):
        cell.fill = PatternFill(start_color=COLOR_AMBER_BG, end_color=COLOR_AMBER_BG, fill_type="solid")
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_AMBER_TXT)
    elif val in ("ABSENT", "REJECTED", "CANCELLED", "FAILED", "BLOCKED"):
        cell.fill = PatternFill(start_color=COLOR_RED_BG, end_color=COLOR_RED_BG, fill_type="solid")
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_RED_TXT)
    elif val in ("ON_LEAVE", "WFH", "HOLIDAY"):
        cell.fill = PatternFill(start_color=COLOR_BLUE_BG, end_color=COLOR_BLUE_BG, fill_type="solid")
        cell.font = Font(name="Calibri", size=10, bold=True, color=COLOR_BLUE_TXT)
    else:
        cell.font = FONT_REGULAR
    cell.alignment = ALIGN_CENTER
    cell.border = BORDER_CELL


def _autofit_columns(ws, min_width=12, max_width=45):
    """Calculates column width based on maximum content length."""
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = 0
        for cell in col:
            # Skip title merged banner rows
            if cell.row in (1, 2):
                continue
            if cell.value:
                val_str = str(cell.value)
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(min_width, min(max_len + 4, max_width))


class ExcelReportEngine:
    """Enterprise openpyxl Excel Workbook Generator."""

    @staticmethod
    def get_storage_dir(job_id: uuid.UUID) -> pathlib.Path:
        base_dir = pathlib.Path(__file__).parent.parent.parent / "storage" / "reports" / str(job_id)
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    @classmethod
    def generate_consolidated_report(
        cls,
        job_id: uuid.UUID,
        org_name: str,
        report_title: str,
        start_date: date,
        end_date: date,
        employees_data: list[dict[str, Any]],
        attendance_logs: list[dict[str, Any]],
        os_events: list[dict[str, Any]],
        leaves_data: list[dict[str, Any]],
    ) -> tuple[str, str, int]:
        """
        Generates a consolidated company or manager team workbook with multiple worksheets:
        1. Executive Summary
        2. Attendance Master Log
        3. OS Activity Telemetry
        4. Leave Entitlements & Approvals
        """
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        # -------------------------------------------------------------
        # Worksheet 1: Executive Summary
        # -------------------------------------------------------------
        ws_sum = wb.create_sheet(title="Executive Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        # Header Banner
        ws_sum.merge_cells("A1:K1")
        title_cell = ws_sum["A1"]
        title_cell.value = f"{org_name} — {report_title}"
        title_cell.font = FONT_TITLE
        title_cell.fill = FILL_TITLE
        title_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_sum.row_dimensions[1].height = 36

        ws_sum.merge_cells("A2:K2")
        meta_cell = ws_sum["A2"]
        meta_cell.value = f"Reporting Period: {start_date} to {end_date}  |  Generated UTC: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}  |  Scope: Consolidated Company"
        meta_cell.font = Font(name="Calibri", size=9.5, italic=True, color="64748B")
        meta_cell.fill = FILL_SUBHEADER
        meta_cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_sum.row_dimensions[2].height = 22

        # Summary Table Headers
        headers_sum = [
            "Employee Code",
            "Employee Name",
            "Email",
            "Department",
            "Manager",
            "Total Days",
            "Present Days",
            "Late Days",
            "Leave Days",
            "Total Work Hours",
            "Avg Daily Hours",
        ]

        row_idx = 4
        for col_idx, h in enumerate(headers_sum, start=1):
            c = ws_sum.cell(row=row_idx, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 6, 7, 8, 9, 10, 11) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_sum.row_dimensions[row_idx].height = 24

        start_data_row = row_idx + 1
        curr_row = start_data_row

        for emp in employees_data:
            ws_sum.cell(row=curr_row, column=1, value=emp.get("code", "")).alignment = ALIGN_CENTER
            ws_sum.cell(row=curr_row, column=2, value=emp.get("name", "")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_row, column=3, value=emp.get("email", "")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_row, column=4, value=emp.get("department", "General")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_row, column=5, value=emp.get("manager", "None")).alignment = ALIGN_LEFT
            
            c_tot = ws_sum.cell(row=curr_row, column=6, value=emp.get("total_days", 0))
            c_tot.alignment = ALIGN_CENTER
            c_tot.number_format = "#,##0"

            c_pres = ws_sum.cell(row=curr_row, column=7, value=emp.get("present_days", 0))
            c_pres.alignment = ALIGN_CENTER
            c_pres.number_format = "#,##0"

            c_late = ws_sum.cell(row=curr_row, column=8, value=emp.get("late_days", 0))
            c_late.alignment = ALIGN_CENTER
            c_late.number_format = "#,##0"

            c_leave = ws_sum.cell(row=curr_row, column=9, value=emp.get("leave_days", 0.0))
            c_leave.alignment = ALIGN_CENTER
            c_leave.number_format = "0.0"

            c_hours = ws_sum.cell(row=curr_row, column=10, value=round(emp.get("total_hours", 0.0), 2))
            c_hours.alignment = ALIGN_RIGHT
            c_hours.number_format = "#,##0.00"

            # Validated Excel Formula: Average Daily Hours = Total Work Hours / Present Days
            c_avg = ws_sum.cell(
                row=curr_row,
                column=11,
                value=f"=IF(G{curr_row}>0, J{curr_row}/G{curr_row}, 0)",
            )
            c_avg.alignment = ALIGN_RIGHT
            c_avg.number_format = "0.00"

            for c_i in range(1, 12):
                ws_sum.cell(row=curr_row, column=c_i).border = BORDER_CELL
                ws_sum.cell(row=curr_row, column=c_i).font = FONT_REGULAR

            curr_row += 1

        end_data_row = curr_row - 1
        if end_data_row >= start_data_row:
            # Totals Row with Validated Formulas
            ws_sum.cell(row=curr_row, column=1, value="TOTALS").font = FONT_BOLD
            ws_sum.cell(row=curr_row, column=1).alignment = ALIGN_CENTER
            for ci in range(2, 6):
                ws_sum.cell(row=curr_row, column=ci, value="")

            # Total Days Sum
            c_f_tot = ws_sum.cell(row=curr_row, column=6, value=f"=SUM(F{start_data_row}:F{end_data_row})")
            c_f_tot.number_format = "#,##0"
            c_f_tot.font = FONT_BOLD

            # Total Present Sum
            c_f_pres = ws_sum.cell(row=curr_row, column=7, value=f"=SUM(G{start_data_row}:G{end_data_row})")
            c_f_pres.number_format = "#,##0"
            c_f_pres.font = FONT_BOLD

            # Total Late Sum
            c_f_late = ws_sum.cell(row=curr_row, column=8, value=f"=SUM(H{start_data_row}:H{end_data_row})")
            c_f_late.number_format = "#,##0"
            c_f_late.font = FONT_BOLD

            # Total Leave Days
            c_f_leave = ws_sum.cell(row=curr_row, column=9, value=f"=SUM(I{start_data_row}:I{end_data_row})")
            c_f_leave.number_format = "#,##0.0"
            c_f_leave.font = FONT_BOLD

            # Total Work Hours Sum
            c_f_hrs = ws_sum.cell(row=curr_row, column=10, value=f"=SUM(J{start_data_row}:J{end_data_row})")
            c_f_hrs.number_format = "#,##0.00"
            c_f_hrs.font = FONT_BOLD

            # Overall Average Hours formula
            c_f_avg = ws_sum.cell(row=curr_row, column=11, value=f"=AVERAGE(K{start_data_row}:K{end_data_row})")
            c_f_avg.number_format = "0.00"
            c_f_avg.font = FONT_BOLD

            for ci in range(1, 12):
                cell = ws_sum.cell(row=curr_row, column=ci)
                cell.fill = FILL_TOTAL
                cell.border = BORDER_TOTAL

        _autofit_columns(ws_sum)

        # -------------------------------------------------------------
        # Worksheet 2: Attendance Master Log
        # -------------------------------------------------------------
        ws_att = wb.create_sheet(title="Attendance Master Log")
        ws_att.views.sheetView[0].showGridLines = True

        ws_att.merge_cells("A1:K1")
        h_att = ws_att["A1"]
        h_att.value = "Daily Attendance & Shift Records"
        h_att.font = FONT_TITLE
        h_att.fill = FILL_TITLE
        h_att.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_att.row_dimensions[1].height = 32

        headers_att = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Clock-In",
            "Clock-Out",
            "Work Duration",
            "Break (min)",
            "Net Hours",
            "Status",
            "Location Verification",
        ]
        row_att = 3
        for col_idx, h in enumerate(headers_att, start=1):
            c = ws_att.cell(row=row_att, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 8, 10, 11) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_att.row_dimensions[row_att].height = 22

        r_att_curr = 4
        for log in attendance_logs:
            ws_att.cell(row=r_att_curr, column=1, value=str(log.get("date", ""))).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att_curr, column=2, value=log.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att_curr, column=3, value=log.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_att.cell(row=r_att_curr, column=4, value=log.get("department", "")).alignment = ALIGN_LEFT
            ws_att.cell(row=r_att_curr, column=5, value=log.get("clock_in", "--:--")).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att_curr, column=6, value=log.get("clock_out", "--:--")).alignment = ALIGN_CENTER
            
            c_wh = ws_att.cell(row=r_att_curr, column=7, value=log.get("work_duration", "0h 0m"))
            c_wh.alignment = ALIGN_RIGHT

            c_br = ws_att.cell(row=r_att_curr, column=8, value=log.get("break_minutes", 0))
            c_br.alignment = ALIGN_RIGHT
            c_br.number_format = "#,##0"

            c_nh = ws_att.cell(row=r_att_curr, column=9, value=round(log.get("net_hours", 0.0), 2))
            c_nh.alignment = ALIGN_RIGHT
            c_nh.number_format = "0.00"

            # Status Badge
            c_st = ws_att.cell(row=r_att_curr, column=10, value=log.get("status", "PRESENT"))
            _apply_status_badge(c_st, log.get("status", "PRESENT"))

            # Location
            c_loc = ws_att.cell(row=r_att_curr, column=11, value=log.get("location_status", "VERIFIED"))
            _apply_status_badge(c_loc, log.get("location_status", "VERIFIED"))

            for ci in range(1, 10):
                ws_att.cell(row=r_att_curr, column=ci).border = BORDER_CELL
                ws_att.cell(row=r_att_curr, column=ci).font = FONT_REGULAR

            r_att_curr += 1

        _autofit_columns(ws_att)

        # -------------------------------------------------------------
        # Worksheet 3: OS Activity Telemetry
        # -------------------------------------------------------------
        ws_os = wb.create_sheet(title="OS Activity Events")
        ws_os.views.sheetView[0].showGridLines = True

        ws_os.merge_cells("A1:G1")
        h_os = ws_os["A1"]
        h_os.value = "Operating System Native Session & Logon Events"
        h_os.font = FONT_TITLE
        h_os.fill = FILL_TITLE
        h_os.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_os.row_dimensions[1].height = 32

        headers_os = [
            "Occurred At (UTC)",
            "Employee Code",
            "Employee Name",
            "Device Identifier",
            "Event Type",
            "Active Window / Process",
            "Duration (min)",
        ]
        row_os = 3
        for col_idx, h in enumerate(headers_os, start=1):
            c = ws_os.cell(row=row_os, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 4, 5, 7) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_os.row_dimensions[row_os].height = 22

        r_os_curr = 4
        for ev in os_events:
            ws_os.cell(row=r_os_curr, column=1, value=str(ev.get("occurred_at", ""))).alignment = ALIGN_CENTER
            ws_os.cell(row=r_os_curr, column=2, value=ev.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_os.cell(row=r_os_curr, column=3, value=ev.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_os.cell(row=r_os_curr, column=4, value=ev.get("device_name", "")).alignment = ALIGN_CENTER
            
            c_type = ws_os.cell(row=r_os_curr, column=5, value=ev.get("event_type", ""))
            _apply_status_badge(c_type, ev.get("event_type", ""))

            ws_os.cell(row=r_os_curr, column=6, value=ev.get("active_window", "--")).alignment = ALIGN_LEFT
            
            c_dur = ws_os.cell(row=r_os_curr, column=7, value=ev.get("duration_minutes", 0))
            c_dur.alignment = ALIGN_RIGHT
            c_dur.number_format = "#,##0"

            for ci in (1, 2, 3, 4, 6, 7):
                ws_os.cell(row=r_os_curr, column=ci).border = BORDER_CELL
                ws_os.cell(row=r_os_curr, column=ci).font = FONT_REGULAR

            r_os_curr += 1

        _autofit_columns(ws_os)

        # -------------------------------------------------------------
        # Worksheet 4: Leave Records
        # -------------------------------------------------------------
        ws_lv = wb.create_sheet(title="Leave & Absence Records")
        ws_lv.views.sheetView[0].showGridLines = True

        ws_lv.merge_cells("A1:J1")
        h_lv = ws_lv["A1"]
        h_lv.value = "Employee Leave Applications & Multi-Tier Approvals"
        h_lv.font = FONT_TITLE
        h_lv.fill = FILL_TITLE
        h_lv.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_lv.row_dimensions[1].height = 32

        headers_lv = [
            "Application Date",
            "Employee Code",
            "Employee Name",
            "Leave Category",
            "Start Date",
            "End Date",
            "Days",
            "Manager Status",
            "HR Status",
            "Final Status",
        ]
        row_lv = 3
        for col_idx, h in enumerate(headers_lv, start=1):
            c = ws_lv.cell(row=row_lv, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 7, 8, 9, 10) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_lv.row_dimensions[row_lv].height = 22

        r_lv_curr = 4
        for lv in leaves_data:
            ws_lv.cell(row=r_lv_curr, column=1, value=str(lv.get("created_at", ""))).alignment = ALIGN_CENTER
            ws_lv.cell(row=r_lv_curr, column=2, value=lv.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_lv.cell(row=r_lv_curr, column=3, value=lv.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_lv.cell(row=r_lv_curr, column=4, value=lv.get("leave_type", "")).alignment = ALIGN_LEFT
            ws_lv.cell(row=r_lv_curr, column=5, value=str(lv.get("start_date", ""))).alignment = ALIGN_CENTER
            ws_lv.cell(row=r_lv_curr, column=6, value=str(lv.get("end_date", ""))).alignment = ALIGN_CENTER
            
            c_d = ws_lv.cell(row=r_lv_curr, column=7, value=lv.get("total_days", 0.0))
            c_d.alignment = ALIGN_CENTER
            c_d.number_format = "0.0"

            c_mgr = ws_lv.cell(row=r_lv_curr, column=8, value=lv.get("manager_approval_status", "PENDING"))
            _apply_status_badge(c_mgr, lv.get("manager_approval_status", "PENDING"))

            c_hr = ws_lv.cell(row=r_lv_curr, column=9, value=lv.get("hr_approval_status", "PENDING"))
            _apply_status_badge(c_hr, lv.get("hr_approval_status", "PENDING"))

            c_fin = ws_lv.cell(row=r_lv_curr, column=10, value=lv.get("status", "PENDING"))
            _apply_status_badge(c_fin, lv.get("status", "PENDING"))

            for ci in (1, 2, 3, 4, 5, 6, 7):
                ws_lv.cell(row=r_lv_curr, column=ci).border = BORDER_CELL
                ws_lv.cell(row=r_lv_curr, column=ci).font = FONT_REGULAR

            r_lv_curr += 1

        _autofit_columns(ws_lv)

        # Save Workbook to Secure Storage
        out_dir = cls.get_storage_dir(job_id)
        clean_title = report_title.lower().replace(" ", "_").replace("—", "_")
        file_name = f"{clean_title}_{start_date}_{end_date}.xlsx"
        file_path = out_dir / file_name
        wb.save(str(file_path))

        file_size = os.path.getsize(str(file_path))
        return file_name, str(file_path), file_size

    @classmethod
    def generate_individual_report(
        cls,
        job_id: uuid.UUID,
        org_name: str,
        employee_info: dict[str, Any],
        start_date: date,
        end_date: date,
        attendance_logs: list[dict[str, Any]],
        os_events: list[dict[str, Any]],
        leaves_data: list[dict[str, Any]],
    ) -> tuple[str, str, int]:
        """
        Generates an individual employee workbook.
        STRICT COMPLIANCE RULE: Contains ONLY the records of this specific employee.
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        emp_code = employee_info.get("employee_code", "EMP-001")
        emp_name = employee_info.get("name", "Employee")
        emp_dept = employee_info.get("department", "Engineering")
        emp_mgr = employee_info.get("manager", "Manager")

        # -------------------------------------------------------------
        # Sheet 1: Individual Executive Summary
        # -------------------------------------------------------------
        ws_sum = wb.create_sheet(title="Personal Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.merge_cells("A1:G1")
        h1 = ws_sum["A1"]
        h1.value = f"{org_name} — Individual Performance & Attendance Summary"
        h1.font = FONT_TITLE
        h1.fill = FILL_TITLE
        h1.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_sum.row_dimensions[1].height = 34

        # Profile Cards Row
        profile_rows = [
            ("Employee Name:", emp_name, "Employee Code:", emp_code),
            ("Department:", emp_dept, "Direct Manager:", emp_mgr),
            ("Reporting Period:", f"{start_date} to {end_date}", "Generated UTC:", datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")),
        ]

        p_row = 3
        for label1, val1, label2, val2 in profile_rows:
            ws_sum.cell(row=p_row, column=1, value=label1).font = FONT_BOLD
            ws_sum.cell(row=p_row, column=2, value=val1).font = FONT_REGULAR
            ws_sum.cell(row=p_row, column=4, value=label2).font = FONT_BOLD
            ws_sum.cell(row=p_row, column=5, value=val2).font = FONT_REGULAR
            p_row += 1

        # Summary KPIs Box
        kpi_row = 7
        ws_sum.cell(row=kpi_row, column=1, value="Metric").font = FONT_HEADER
        ws_sum.cell(row=kpi_row, column=1).fill = FILL_HEADER
        ws_sum.cell(row=kpi_row, column=1).border = BORDER_CELL

        ws_sum.cell(row=kpi_row, column=2, value="Value").font = FONT_HEADER
        ws_sum.cell(row=kpi_row, column=2).fill = FILL_HEADER
        ws_sum.cell(row=kpi_row, column=2).alignment = ALIGN_RIGHT
        ws_sum.cell(row=kpi_row, column=2).border = BORDER_CELL

        tot_present = sum(1 for a in attendance_logs if a.get("status") in ("PRESENT", "LATE", "HALF_DAY"))
        tot_late = sum(1 for a in attendance_logs if a.get("status") == "LATE")
        tot_leave_days = sum(l.get("total_days", 0) for l in leaves_data if l.get("status") == "APPROVED")
        tot_hours = sum(a.get("net_hours", 0.0) for a in attendance_logs)

        kpis = [
            ("Days Logged / Workdays", len(attendance_logs)),
            ("Days Present", tot_present),
            ("Late Arrival Days", tot_late),
            ("Approved Leave Days Taken", tot_leave_days),
            ("Net Working Hours Logged", round(tot_hours, 2)),
            ("Average Daily Productive Hours", round(tot_hours / max(tot_present, 1), 2)),
        ]

        curr_k = kpi_row + 1
        for label, val in kpis:
            c_l = ws_sum.cell(row=curr_k, column=1, value=label)
            c_l.font = FONT_REGULAR
            c_l.border = BORDER_CELL

            c_v = ws_sum.cell(row=curr_k, column=2, value=val)
            c_v.font = FONT_BOLD
            c_v.alignment = ALIGN_RIGHT
            c_v.border = BORDER_CELL
            if isinstance(val, float):
                c_v.number_format = "#,##0.00"
            curr_k += 1

        _autofit_columns(ws_sum)

        # -------------------------------------------------------------
        # Sheet 2: Daily Attendance Logs
        # -------------------------------------------------------------
        ws_att = wb.create_sheet(title="Attendance Logs")
        ws_att.views.sheetView[0].showGridLines = True

        ws_att.merge_cells("A1:H1")
        h_att = ws_att["A1"]
        h_att.value = f"Attendance Activity Log — {emp_name} ({emp_code})"
        h_att.font = FONT_TITLE
        h_att.fill = FILL_TITLE
        h_att.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_att.row_dimensions[1].height = 32

        headers_att = [
            "Date",
            "Clock-In Time",
            "Clock-Out Time",
            "Gross Duration",
            "Break (min)",
            "Net Hours",
            "Attendance Status",
            "Location Verification",
        ]
        r_head = 3
        for col_idx, h in enumerate(headers_att, start=1):
            c = ws_att.cell(row=r_head, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 3, 5, 7, 8) else ALIGN_RIGHT
            c.border = BORDER_CELL

        r_att = 4
        start_att_row = r_att
        for a in attendance_logs:
            ws_att.cell(row=r_att, column=1, value=str(a.get("date", ""))).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att, column=2, value=a.get("clock_in", "--:--")).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att, column=3, value=a.get("clock_out", "--:--")).alignment = ALIGN_CENTER
            ws_att.cell(row=r_att, column=4, value=a.get("work_duration", "0h 0m")).alignment = ALIGN_RIGHT

            c_b = ws_att.cell(row=r_att, column=5, value=a.get("break_minutes", 0))
            c_b.alignment = ALIGN_RIGHT
            c_b.number_format = "#,##0"

            c_n = ws_att.cell(row=r_att, column=6, value=round(a.get("net_hours", 0.0), 2))
            c_n.alignment = ALIGN_RIGHT
            c_n.number_format = "0.00"

            c_s = ws_att.cell(row=r_att, column=7, value=a.get("status", "PRESENT"))
            _apply_status_badge(c_s, a.get("status", "PRESENT"))

            c_loc = ws_att.cell(row=r_att, column=8, value=a.get("location_status", "VERIFIED"))
            _apply_status_badge(c_loc, a.get("location_status", "VERIFIED"))

            for ci in (1, 2, 3, 4, 5, 6):
                ws_att.cell(row=r_att, column=ci).border = BORDER_CELL
                ws_att.cell(row=r_att, column=ci).font = FONT_REGULAR

            r_att += 1

        end_att_row = r_att - 1
        if end_att_row >= start_att_row:
            # Totals formula
            ws_att.cell(row=r_att, column=1, value="TOTALS").font = FONT_BOLD
            ws_att.cell(row=r_att, column=1).alignment = ALIGN_CENTER
            for ci in range(2, 5):
                ws_att.cell(row=r_att, column=ci, value="")

            # Total Break Formula
            c_tot_b = ws_att.cell(row=r_att, column=5, value=f"=SUM(E{start_att_row}:E{end_att_row})")
            c_tot_b.number_format = "#,##0"
            c_tot_b.font = FONT_BOLD

            # Total Net Hours Formula
            c_tot_h = ws_att.cell(row=r_att, column=6, value=f"=SUM(F{start_att_row}:F{end_att_row})")
            c_tot_h.number_format = "0.00"
            c_tot_h.font = FONT_BOLD

            for ci in range(1, 9):
                cell = ws_att.cell(row=r_att, column=ci)
                cell.fill = FILL_TOTAL
                cell.border = BORDER_TOTAL

        _autofit_columns(ws_att)

        # -------------------------------------------------------------
        # Sheet 3: OS Activity & Sessions
        # -------------------------------------------------------------
        ws_os = wb.create_sheet(title="OS Activity")
        ws_os.views.sheetView[0].showGridLines = True

        ws_os.merge_cells("A1:E1")
        h_os = ws_os["A1"]
        h_os.value = f"Operating System Sessions & Focus Activity — {emp_name}"
        h_os.font = FONT_TITLE
        h_os.fill = FILL_TITLE
        h_os.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_os.row_dimensions[1].height = 32

        headers_os = [
            "Timestamp (UTC)",
            "Device Workstation",
            "Event Type",
            "Active Window",
            "Duration (min)",
        ]
        r_head_os = 3
        for col_idx, h in enumerate(headers_os, start=1):
            c = ws_os.cell(row=r_head_os, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 3, 5) else ALIGN_LEFT
            c.border = BORDER_CELL

        r_os = 4
        for ev in os_events:
            ws_os.cell(row=r_os, column=1, value=str(ev.get("occurred_at", ""))).alignment = ALIGN_CENTER
            ws_os.cell(row=r_os, column=2, value=ev.get("device_name", "")).alignment = ALIGN_CENTER
            
            c_type = ws_os.cell(row=r_os, column=3, value=ev.get("event_type", ""))
            _apply_status_badge(c_type, ev.get("event_type", ""))

            ws_os.cell(row=r_os, column=4, value=ev.get("active_window", "--")).alignment = ALIGN_LEFT

            c_d = ws_os.cell(row=r_os, column=5, value=ev.get("duration_minutes", 0))
            c_d.alignment = ALIGN_RIGHT
            c_d.number_format = "#,##0"

            for ci in (1, 2, 4, 5):
                ws_os.cell(row=r_os, column=ci).border = BORDER_CELL
                ws_os.cell(row=r_os, column=ci).font = FONT_REGULAR

            r_os += 1

        _autofit_columns(ws_os)

        # -------------------------------------------------------------
        # Sheet 4: Leave History
        # -------------------------------------------------------------
        ws_lv = wb.create_sheet(title="Leave History")
        ws_lv.views.sheetView[0].showGridLines = True

        ws_lv.merge_cells("A1:H1")
        h_lv = ws_lv["A1"]
        h_lv.value = f"Absence & Leave Application Records — {emp_name}"
        h_lv.font = FONT_TITLE
        h_lv.fill = FILL_TITLE
        h_lv.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_lv.row_dimensions[1].height = 32

        headers_lv = [
            "Application Date",
            "Leave Category",
            "Start Date",
            "End Date",
            "Charged Days",
            "Manager Status",
            "HR Status",
            "Final Status",
        ]
        r_head_lv = 3
        for col_idx, h in enumerate(headers_lv, start=1):
            c = ws_lv.cell(row=r_head_lv, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 3, 4, 5, 6, 7, 8) else ALIGN_LEFT
            c.border = BORDER_CELL

        r_lv = 4
        for lv in leaves_data:
            ws_lv.cell(row=r_lv, column=1, value=str(lv.get("created_at", ""))).alignment = ALIGN_CENTER
            ws_lv.cell(row=r_lv, column=2, value=lv.get("leave_type", "")).alignment = ALIGN_LEFT
            ws_lv.cell(row=r_lv, column=3, value=str(lv.get("start_date", ""))).alignment = ALIGN_CENTER
            ws_lv.cell(row=r_lv, column=4, value=str(lv.get("end_date", ""))).alignment = ALIGN_CENTER

            c_days = ws_lv.cell(row=r_lv, column=5, value=lv.get("total_days", 0.0))
            c_days.alignment = ALIGN_CENTER
            c_days.number_format = "0.0"

            c_m = ws_lv.cell(row=r_lv, column=6, value=lv.get("manager_approval_status", "PENDING"))
            _apply_status_badge(c_m, lv.get("manager_approval_status", "PENDING"))

            c_h = ws_lv.cell(row=r_lv, column=7, value=lv.get("hr_approval_status", "PENDING"))
            _apply_status_badge(c_h, lv.get("hr_approval_status", "PENDING"))

            c_f = ws_lv.cell(row=r_lv, column=8, value=lv.get("status", "PENDING"))
            _apply_status_badge(c_f, lv.get("status", "PENDING"))

            for ci in (1, 2, 3, 4, 5):
                ws_lv.cell(row=r_lv, column=ci).border = BORDER_CELL
                ws_lv.cell(row=r_lv, column=ci).font = FONT_REGULAR

            r_lv += 1

        _autofit_columns(ws_lv)

        # Save Individual Workbook
        out_dir = cls.get_storage_dir(job_id)
        clean_name = emp_name.lower().replace(" ", "_")
        file_name = f"employee_{clean_name}_{emp_code}_{start_date}_{end_date}.xlsx"
        file_path = out_dir / file_name
        wb.save(str(file_path))

        file_size = os.path.getsize(str(file_path))
        return file_name, str(file_path), file_size

    @classmethod
    def generate_weekly_consolidated_report(
        cls,
        job_id: uuid.UUID,
        org_name: str,
        report_title: str,
        start_date: date,
        end_date: date,
        employees_data: list[dict[str, Any]],
        attendance_logs: list[dict[str, Any]],
        os_events: list[dict[str, Any]],
        leaves_data: list[dict[str, Any]],
        wifi_logs: list[dict[str, Any]] | None = None,
        exceptions_data: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str, int]:
        """
        Generates the weekly consolidated Excel report:
        1. Daily Login (simple 10-column sheet for HR/Manager)
        2. Attendance Summary
        3. Login & Logout Details
        4. Working Hours
        5. Late Attendance
        6. Absence Report
        7. Leave Applications
        8. Leave Approvals
        9. Wi-Fi Verification
        10. Attendance Exceptions
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # -------------------------------------------------------------
        # Worksheet 1: Daily Login (screenshot-matching HR/Manager view)
        # -------------------------------------------------------------
        ws_daily = wb.create_sheet(title="Daily Login", index=0)
        ws_daily.views.sheetView[0].showGridLines = True

        daily_headers = [
            "Date",
            "Code",
            "Name",
            "Department",
            "Status",
            "Login",
            "Logout",
            "Hours",
            "First Wi-Fi",
            "Wi-Fi networks",
        ]
        for col_idx, h in enumerate(daily_headers, start=1):
            c = ws_daily.cell(row=1, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER
            c.border = BORDER_CELL
        ws_daily.row_dimensions[1].height = 22

        def _daily_date(val: Any) -> str:
            raw = str(val or "").strip()
            if not raw:
                return ""
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(raw[:10], fmt).strftime("%d-%m-%Y")
                except ValueError:
                    continue
            return raw

        def _daily_hours(log: dict[str, Any]) -> str:
            explicit = log.get("work_duration")
            if isinstance(explicit, str) and explicit.strip():
                return explicit.strip()
            hours = float(log.get("net_hours", log.get("net_duration_hours", 0.0)) or 0.0)
            total_mins = int(round(hours * 60))
            return f"{total_mins // 60}h {total_mins % 60:02d}m"

        def _daily_status(log: dict[str, Any]) -> str:
            status = str(log.get("status") or "").upper()
            clock_out = str(log.get("clock_out") or "")
            if clock_out.lower().startswith("still logged") or status in ("OPEN",):
                return "Logged in"
            if status in ("PRESENT", "LATE", "HALF_DAY"):
                return "Logged in" if not clock_out else status.title().replace("_", " ")
            if status == "ABSENT":
                return "Absent"
            if status == "LEAVE":
                return "On leave"
            return status.title().replace("_", " ") if status else ""

        def _daily_wifi(val: Any) -> str:
            raw = str(val or "").strip()
            if not raw:
                return ""
            parts = [p.strip() for p in raw.replace(",", "/").split("/") if p.strip()]
            return " / ".join(dict.fromkeys(parts))

        curr_daily = 2
        for log in attendance_logs:
            logout_val = log.get("clock_out") or ""
            if str(logout_val).lower().startswith("still logged"):
                logout_val = "Still logged"

            row_vals = [
                _daily_date(log.get("date") or log.get("work_date")),
                log.get("employee_code", ""),
                log.get("employee_name", ""),
                log.get("department", ""),
                _daily_status(log),
                log.get("clock_in", "") or "",
                logout_val,
                _daily_hours(log),
                log.get("first_wifi_connected", "") or "",
                _daily_wifi(log.get("wifi_networks")),
            ]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws_daily.cell(row=curr_daily, column=col_idx, value=val)
                cell.font = FONT_REGULAR
                cell.border = BORDER_CELL
                cell.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 7, 8, 9) else ALIGN_LEFT
            curr_daily += 1

        # Fixed widths so Login / First Wi-Fi never show as ########
        daily_widths = {
            "A": 12,
            "B": 10,
            "C": 18,
            "D": 14,
            "E": 12,
            "F": 12,
            "G": 12,
            "H": 10,
            "I": 12,
            "J": 36,
        }
        for col_letter, width in daily_widths.items():
            ws_daily.column_dimensions[col_letter].width = width

        # -------------------------------------------------------------
        # Worksheet 2: Attendance Summary
        # -------------------------------------------------------------
        ws_sum = wb.create_sheet(title="Attendance Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum.merge_cells("A1:K1")
        t1 = ws_sum["A1"]
        t1.value = f"{org_name} — {report_title}"
        t1.font = FONT_TITLE
        t1.fill = FILL_TITLE
        t1.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_sum.row_dimensions[1].height = 36

        ws_sum.merge_cells("A2:K2")
        m1 = ws_sum["A2"]
        m1.value = f"Reporting Period: {start_date} to {end_date}  |  Generated UTC: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}  |  Scope: Weekly Consolidated Digest"
        m1.font = Font(name="Calibri", size=9.5, italic=True, color="64748B")
        m1.fill = FILL_SUBHEADER
        m1.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_sum.row_dimensions[2].height = 22

        headers_1 = [
            "Employee Code",
            "Employee Name",
            "Email",
            "Department",
            "Manager",
            "Total Days",
            "Present Days",
            "Late Days",
            "Leave Days",
            "Total Work Hours",
            "Avg Daily Hours",
        ]
        row_1 = 4
        for col_idx, h in enumerate(headers_1, start=1):
            c = ws_sum.cell(row=row_1, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 6, 7, 8, 9, 10, 11) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_sum.row_dimensions[row_1].height = 24

        curr_r1 = 5
        for emp in employees_data:
            ws_sum.cell(row=curr_r1, column=1, value=emp.get("code") or emp.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_sum.cell(row=curr_r1, column=2, value=emp.get("name") or emp.get("full_name", "")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_r1, column=3, value=emp.get("email", "")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_r1, column=4, value=emp.get("department", "General")).alignment = ALIGN_LEFT
            ws_sum.cell(row=curr_r1, column=5, value=emp.get("manager", "None")).alignment = ALIGN_LEFT
            
            c_tot = ws_sum.cell(row=curr_r1, column=6, value=emp.get("total_days", 5))
            c_tot.alignment = ALIGN_CENTER
            c_tot.number_format = "#,##0"

            c_pres = ws_sum.cell(row=curr_r1, column=7, value=emp.get("present_days", 5))
            c_pres.alignment = ALIGN_CENTER
            c_pres.number_format = "#,##0"

            c_late = ws_sum.cell(row=curr_r1, column=8, value=emp.get("late_days", 0))
            c_late.alignment = ALIGN_CENTER
            c_late.number_format = "#,##0"

            c_leave = ws_sum.cell(row=curr_r1, column=9, value=emp.get("leave_days", 0.0))
            c_leave.alignment = ALIGN_CENTER
            c_leave.number_format = "0.0"

            c_hrs = ws_sum.cell(row=curr_r1, column=10, value=round(float(emp.get("total_hours", emp.get("net_hours", 0.0)) or 0.0), 2))
            c_hrs.alignment = ALIGN_RIGHT
            c_hrs.number_format = "#,##0.00"

            c_avg = ws_sum.cell(row=curr_r1, column=11, value=f"=IF(G{curr_r1}>0, J{curr_r1}/G{curr_r1}, 0)")
            c_avg.alignment = ALIGN_RIGHT
            c_avg.number_format = "0.00"

            for ci in range(1, 12):
                ws_sum.cell(row=curr_r1, column=ci).border = BORDER_CELL
                ws_sum.cell(row=curr_r1, column=ci).font = FONT_REGULAR

            curr_r1 += 1

        end_r1 = curr_r1 - 1
        if end_r1 >= 5:
            ws_sum.cell(row=curr_r1, column=1, value="TOTALS").font = FONT_BOLD
            ws_sum.cell(row=curr_r1, column=1).alignment = ALIGN_CENTER
            for ci in range(2, 6):
                ws_sum.cell(row=curr_r1, column=ci, value="")
            ws_sum.cell(row=curr_r1, column=6, value=f"=SUM(F5:F{end_r1})").number_format = "#,##0"
            ws_sum.cell(row=curr_r1, column=7, value=f"=SUM(G5:G{end_r1})").number_format = "#,##0"
            ws_sum.cell(row=curr_r1, column=8, value=f"=SUM(H5:H{end_r1})").number_format = "#,##0"
            ws_sum.cell(row=curr_r1, column=9, value=f"=SUM(I5:I{end_r1})").number_format = "#,##0.0"
            ws_sum.cell(row=curr_r1, column=10, value=f"=SUM(J5:J{end_r1})").number_format = "#,##0.00"
            ws_sum.cell(row=curr_r1, column=11, value=f"=AVERAGE(K5:K{end_r1})").number_format = "0.00"
            for ci in range(1, 12):
                c = ws_sum.cell(row=curr_r1, column=ci)
                c.fill = FILL_TOTAL
                c.border = BORDER_TOTAL
                c.font = FONT_BOLD

        _autofit_columns(ws_sum)

        # -------------------------------------------------------------
        # Worksheet 2: Login & Logout Details
        # -------------------------------------------------------------
        ws_log = wb.create_sheet(title="Login & Logout Details")
        ws_log.views.sheetView[0].showGridLines = True

        ws_log.merge_cells("A1:N1")
        t2 = ws_log["A1"]
        t2.value = "Daily Login & Logout (first app login / Wi-Fi connect to last app logout / Wi-Fi disconnect)"
        t2.font = FONT_TITLE
        t2.fill = FILL_TITLE
        t2.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_log.row_dimensions[1].height = 32

        headers_2 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Login Time",
            "Logout Time",
            "Work Duration",
            "Break (min)",
            "Net Hours",
            "Status",
            "Login Source",
            "Logout Source",
            "First Wi-Fi Connect",
            "Wi-Fi Network(s)",
        ]
        row_2 = 3
        for col_idx, h in enumerate(headers_2, start=1):
            c = ws_log.cell(row=row_2, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 8, 10, 11, 12, 13) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_log.row_dimensions[row_2].height = 22

        curr_r2 = 4
        for log in attendance_logs:
            gross_h = float(log.get("gross_duration_hours") or 0.0)
            ws_log.cell(row=curr_r2, column=1, value=str(log.get("date") or log.get("work_date", ""))).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=2, value=log.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=3, value=log.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_log.cell(row=curr_r2, column=4, value=log.get("department", "")).alignment = ALIGN_LEFT
            ws_log.cell(row=curr_r2, column=5, value=log.get("clock_in", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=6, value=log.get("clock_out", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=7, value=log.get("work_duration") or (f"{gross_h:.1f}h" if gross_h else "")).alignment = ALIGN_RIGHT

            c_br = ws_log.cell(row=curr_r2, column=8, value=log.get("break_minutes", int(float(log.get("break_duration_hours") or 0.0) * 60)))
            c_br.alignment = ALIGN_RIGHT
            c_br.number_format = "#,##0"

            c_nh = ws_log.cell(row=curr_r2, column=9, value=round(float(log.get("net_hours", log.get("net_duration_hours", 0.0)) or 0.0), 2))
            c_nh.alignment = ALIGN_RIGHT
            c_nh.number_format = "0.00"

            c_st = ws_log.cell(row=curr_r2, column=10, value=log.get("status", ""))
            _apply_status_badge(c_st, log.get("status", ""))

            ws_log.cell(row=curr_r2, column=11, value=log.get("location_status", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=12, value=log.get("logout_source", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=13, value=log.get("first_wifi_connected", "")).alignment = ALIGN_CENTER
            ws_log.cell(row=curr_r2, column=14, value=log.get("wifi_networks", "")).alignment = ALIGN_LEFT

            for ci in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14):
                ws_log.cell(row=curr_r2, column=ci).border = BORDER_CELL
                ws_log.cell(row=curr_r2, column=ci).font = FONT_REGULAR

            curr_r2 += 1

        _autofit_columns(ws_log)

        # -------------------------------------------------------------
        # Worksheet 3: Working Hours
        # -------------------------------------------------------------
        ws_wh = wb.create_sheet(title="Working Hours")
        ws_wh.views.sheetView[0].showGridLines = True

        ws_wh.merge_cells("A1:J1")
        t3 = ws_wh["A1"]
        t3.value = "Employee Working Hours, Shift Standard (8.00h) & Overtime Analytics"
        t3.font = FONT_TITLE
        t3.fill = FILL_TITLE
        t3.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_wh.row_dimensions[1].height = 32

        headers_3 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Gross Duration (hrs)",
            "Break Duration (hrs)",
            "Net Working Hours",
            "Standard Shift (hrs)",
            "Overtime Hours",
            "Variance vs Plan",
        ]
        row_3 = 3
        for col_idx, h in enumerate(headers_3, start=1):
            c = ws_wh.cell(row=row_3, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 8) else (ALIGN_RIGHT if col_idx in (5, 6, 7, 9, 10) else ALIGN_LEFT)
            c.border = BORDER_CELL
        ws_wh.row_dimensions[row_3].height = 22

        curr_r3 = 4
        for log in attendance_logs:
            if not log.get("clock_in"):
                continue
            net_h = float(log.get("net_hours", log.get("net_duration_hours", 0.0)) or 0.0)
            break_h = float(log.get("break_duration_hours") or (log.get("break_minutes", 0) / 60.0))
            gross_h = net_h + break_h
            ot_h = max(0.0, net_h - 8.0)
            variance = net_h - 8.0

            ws_wh.cell(row=curr_r3, column=1, value=str(log.get("date") or log.get("work_date", ""))).alignment = ALIGN_CENTER
            ws_wh.cell(row=curr_r3, column=2, value=log.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_wh.cell(row=curr_r3, column=3, value=log.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_wh.cell(row=curr_r3, column=4, value=log.get("department", "Operations")).alignment = ALIGN_LEFT

            c_g = ws_wh.cell(row=curr_r3, column=5, value=round(gross_h, 2))
            c_g.alignment = ALIGN_RIGHT
            c_g.number_format = "0.00"

            c_b = ws_wh.cell(row=curr_r3, column=6, value=round(break_h, 2))
            c_b.alignment = ALIGN_RIGHT
            c_b.number_format = "0.00"

            c_n = ws_wh.cell(row=curr_r3, column=7, value=round(net_h, 2))
            c_n.alignment = ALIGN_RIGHT
            c_n.number_format = "0.00"

            c_s = ws_wh.cell(row=curr_r3, column=8, value=8.00)
            c_s.alignment = ALIGN_RIGHT
            c_s.number_format = "0.00"

            c_o = ws_wh.cell(row=curr_r3, column=9, value=round(ot_h, 2))
            c_o.alignment = ALIGN_RIGHT
            c_o.number_format = "0.00"

            c_v = ws_wh.cell(row=curr_r3, column=10, value=round(variance, 2))
            c_v.alignment = ALIGN_RIGHT
            c_v.number_format = "+0.00;-0.00;0.00"

            for ci in range(1, 11):
                ws_wh.cell(row=curr_r3, column=ci).border = BORDER_CELL
                ws_wh.cell(row=curr_r3, column=ci).font = FONT_REGULAR

            curr_r3 += 1

        _autofit_columns(ws_wh)

        # -------------------------------------------------------------
        # Worksheet 4: Late Attendance
        # -------------------------------------------------------------
        ws_late = wb.create_sheet(title="Late Attendance")
        ws_late.views.sheetView[0].showGridLines = True

        ws_late.merge_cells("A1:I1")
        t4 = ws_late["A1"]
        t4.value = "Shift Late Arrivals & Grace Period Exceedances"
        t4.font = FONT_TITLE
        t4.fill = FILL_TITLE
        t4.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_late.row_dimensions[1].height = 32

        headers_4 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Scheduled Start",
            "Actual Clock-In",
            "Late (Minutes)",
            "Shift Status",
            "Remarks",
        ]
        row_4 = 3
        for col_idx, h in enumerate(headers_4, start=1):
            c = ws_late.cell(row=row_4, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 7, 8) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_late.row_dimensions[row_4].height = 22

        curr_r4 = 4
        late_logs = [l for l in attendance_logs if str(l.get("status", "")).upper() == "LATE" or float(l.get("late_minutes", 0)) > 0]
        if not late_logs:
            # Add clean compliance placeholder row
            ws_late.merge_cells(f"A4:I4")
            c_none = ws_late["A4"]
            c_none.value = "100% Punctuality Compliance — Zero late arrivals recorded during this reporting period."
            c_none.font = Font(name="Calibri", size=10, italic=True, color=COLOR_GREEN_TXT)
            c_none.fill = PatternFill(start_color=COLOR_GREEN_BG, end_color=COLOR_GREEN_BG, fill_type="solid")
            c_none.alignment = ALIGN_CENTER
            ws_late.row_dimensions[4].height = 24
        else:
            for log in late_logs:
                ws_late.cell(row=curr_r4, column=1, value=str(log.get("date") or log.get("work_date", ""))).alignment = ALIGN_CENTER
                ws_late.cell(row=curr_r4, column=2, value=log.get("employee_code", "")).alignment = ALIGN_CENTER
                ws_late.cell(row=curr_r4, column=3, value=log.get("employee_name", "")).alignment = ALIGN_LEFT
                ws_late.cell(row=curr_r4, column=4, value=log.get("department", "Operations")).alignment = ALIGN_LEFT
                ws_late.cell(row=curr_r4, column=5, value=log.get("scheduled_start", "")).alignment = ALIGN_CENTER
                ws_late.cell(row=curr_r4, column=6, value=log.get("clock_in", "")).alignment = ALIGN_CENTER

                c_lm = ws_late.cell(row=curr_r4, column=7, value=log.get("late_minutes", 0))
                c_lm.alignment = ALIGN_CENTER
                c_lm.number_format = "#,##0"

                c_st = ws_late.cell(row=curr_r4, column=8, value="LATE")
                _apply_status_badge(c_st, "LATE")

                ws_late.cell(row=curr_r4, column=9, value=log.get("remarks", "")).alignment = ALIGN_LEFT

                for ci in (1, 2, 3, 4, 5, 6, 7, 9):
                    ws_late.cell(row=curr_r4, column=ci).border = BORDER_CELL
                    ws_late.cell(row=curr_r4, column=ci).font = FONT_REGULAR

                curr_r4 += 1

        _autofit_columns(ws_late)

        # -------------------------------------------------------------
        # Worksheet 5: Absence Report
        # -------------------------------------------------------------
        ws_abs = wb.create_sheet(title="Absence Report")
        ws_abs.views.sheetView[0].showGridLines = True

        ws_abs.merge_cells("A1:H1")
        t5 = ws_abs["A1"]
        t5.value = "Employee Absences, Half-Days & Unplanned Leave Register"
        t5.font = FONT_TITLE
        t5.fill = FILL_TITLE
        t5.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_abs.row_dimensions[1].height = 32

        headers_5 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Reporting Manager",
            "Absence Classification",
            "Duration (Days)",
            "Notification Status",
        ]
        row_5 = 3
        for col_idx, h in enumerate(headers_5, start=1):
            c = ws_abs.cell(row=row_5, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 6, 7, 8) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_abs.row_dimensions[row_5].height = 22

        curr_r5 = 4
        absent_logs = [l for l in attendance_logs if str(l.get("status", "")).upper() in ("ABSENT", "HALF_DAY")]
        if not absent_logs:
            ws_abs.merge_cells("A4:H4")
            c_none = ws_abs["A4"]
            c_none.value = "Zero unnotified absences during this reporting period."
            c_none.font = Font(name="Calibri", size=10, italic=True, color=COLOR_GREEN_TXT)
            c_none.fill = PatternFill(start_color=COLOR_GREEN_BG, end_color=COLOR_GREEN_BG, fill_type="solid")
            c_none.alignment = ALIGN_CENTER
            ws_abs.row_dimensions[4].height = 24
        else:
            for log in absent_logs:
                ws_abs.cell(row=curr_r5, column=1, value=str(log.get("date") or log.get("work_date", ""))).alignment = ALIGN_CENTER
                ws_abs.cell(row=curr_r5, column=2, value=log.get("employee_code", "")).alignment = ALIGN_CENTER
                ws_abs.cell(row=curr_r5, column=3, value=log.get("employee_name", "")).alignment = ALIGN_LEFT
                ws_abs.cell(row=curr_r5, column=4, value=log.get("department", "Operations")).alignment = ALIGN_LEFT
                ws_abs.cell(row=curr_r5, column=5, value=log.get("manager", "Manager")).alignment = ALIGN_LEFT
                
                c_st = ws_abs.cell(row=curr_r5, column=6, value=log.get("status", "ABSENT"))
                _apply_status_badge(c_st, log.get("status", "ABSENT"))

                ws_abs.cell(row=curr_r5, column=7, value=1.0 if log.get("status") == "ABSENT" else 0.5).alignment = ALIGN_CENTER
                ws_abs.cell(row=curr_r5, column=8, value="Recorded on Server").alignment = ALIGN_CENTER

                for ci in (1, 2, 3, 4, 5, 7, 8):
                    ws_abs.cell(row=curr_r5, column=ci).border = BORDER_CELL
                    ws_abs.cell(row=curr_r5, column=ci).font = FONT_REGULAR

                curr_r5 += 1

        _autofit_columns(ws_abs)

        # -------------------------------------------------------------
        # Worksheet 6: Leave Applications
        # -------------------------------------------------------------
        ws_la = wb.create_sheet(title="Leave Applications")
        ws_la.views.sheetView[0].showGridLines = True

        ws_la.merge_cells("A1:I1")
        t6 = ws_la["A1"]
        t6.value = "Workforce Leave Applications & Employee Justifications"
        t6.font = FONT_TITLE
        t6.fill = FILL_TITLE
        t6.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_la.row_dimensions[1].height = 32

        headers_6 = [
            "Application Date",
            "Employee Code",
            "Employee Name",
            "Leave Category",
            "Start Date",
            "End Date",
            "Days",
            "Reason",
            "Current Status",
        ]
        row_6 = 3
        for col_idx, h in enumerate(headers_6, start=1):
            c = ws_la.cell(row=row_6, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 6, 7, 9) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_la.row_dimensions[row_6].height = 22

        curr_r6 = 4
        for lv in leaves_data:
            ws_la.cell(row=curr_r6, column=1, value=str(lv.get("created_at") or start_date)).alignment = ALIGN_CENTER
            ws_la.cell(row=curr_r6, column=2, value=lv.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_la.cell(row=curr_r6, column=3, value=lv.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_la.cell(row=curr_r6, column=4, value=lv.get("leave_type", "Standard Leave")).alignment = ALIGN_LEFT
            ws_la.cell(row=curr_r6, column=5, value=str(lv.get("start_date", ""))).alignment = ALIGN_CENTER
            ws_la.cell(row=curr_r6, column=6, value=str(lv.get("end_date", ""))).alignment = ALIGN_CENTER

            c_days = ws_la.cell(row=curr_r6, column=7, value=lv.get("total_days", 1.0))
            c_days.alignment = ALIGN_CENTER
            c_days.number_format = "0.0"

            ws_la.cell(row=curr_r6, column=8, value=lv.get("reason", "Personal request")).alignment = ALIGN_LEFT

            c_st = ws_la.cell(row=curr_r6, column=9, value=lv.get("status", "PENDING"))
            _apply_status_badge(c_st, lv.get("status", "PENDING"))

            for ci in (1, 2, 3, 4, 5, 6, 7, 8):
                ws_la.cell(row=curr_r6, column=ci).border = BORDER_CELL
                ws_la.cell(row=curr_r6, column=ci).font = FONT_REGULAR

            curr_r6 += 1

        _autofit_columns(ws_la)

        # -------------------------------------------------------------
        # Worksheet 7: Leave Approvals
        # -------------------------------------------------------------
        ws_appr = wb.create_sheet(title="Leave Approvals")
        ws_appr.views.sheetView[0].showGridLines = True

        ws_appr.merge_cells("A1:K1")
        t7 = ws_appr["A1"]
        t7.value = "Sequential Multi-Tier Approvals (Manager -> HR)"
        t7.font = FONT_TITLE
        t7.fill = FILL_TITLE
        t7.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_appr.row_dimensions[1].height = 32

        headers_7 = [
            "Request Code",
            "Employee Name",
            "Leave Category",
            "Manager Name",
            "Manager Status",
            "Manager Remarks",
            "HR Representative",
            "HR Status",
            "HR Remarks",
            "Final Status",
            "Updated At",
        ]
        row_7 = 3
        for col_idx, h in enumerate(headers_7, start=1):
            c = ws_appr.cell(row=row_7, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 5, 8, 10, 11) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_appr.row_dimensions[row_7].height = 22

        curr_r7 = 4
        for idx, lv in enumerate(leaves_data, start=101):
            req_code = lv.get("request_code") or f"LR-{idx}"
            ws_appr.cell(row=curr_r7, column=1, value=req_code).alignment = ALIGN_CENTER
            ws_appr.cell(row=curr_r7, column=2, value=lv.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_appr.cell(row=curr_r7, column=3, value=lv.get("leave_type", "Standard Leave")).alignment = ALIGN_LEFT
            ws_appr.cell(row=curr_r7, column=4, value=lv.get("manager_name") or lv.get("manager", "")).alignment = ALIGN_LEFT

            c_mgr = ws_appr.cell(row=curr_r7, column=5, value=lv.get("manager_status") or lv.get("manager_approval_status", "APPROVED"))
            _apply_status_badge(c_mgr, lv.get("manager_status") or lv.get("manager_approval_status", "APPROVED"))

            ws_appr.cell(row=curr_r7, column=6, value=lv.get("manager_comments", "")).alignment = ALIGN_LEFT
            ws_appr.cell(row=curr_r7, column=7, value=lv.get("hr_name", "")).alignment = ALIGN_LEFT

            c_hr = ws_appr.cell(row=curr_r7, column=8, value=lv.get("hr_status") or lv.get("hr_approval_status", "APPROVED"))
            _apply_status_badge(c_hr, lv.get("hr_status") or lv.get("hr_approval_status", "APPROVED"))

            ws_appr.cell(row=curr_r7, column=9, value=lv.get("hr_comments", "")).alignment = ALIGN_LEFT

            c_fin = ws_appr.cell(row=curr_r7, column=10, value=lv.get("status", "APPROVED"))
            _apply_status_badge(c_fin, lv.get("status", "APPROVED"))

            ws_appr.cell(row=curr_r7, column=11, value=str(lv.get("updated_at") or end_date)).alignment = ALIGN_CENTER

            for ci in (1, 2, 3, 4, 6, 7, 9, 11):
                ws_appr.cell(row=curr_r7, column=ci).border = BORDER_CELL
                ws_appr.cell(row=curr_r7, column=ci).font = FONT_REGULAR

            curr_r7 += 1

        _autofit_columns(ws_appr)

        # -------------------------------------------------------------
        # Worksheet 8: Wi-Fi Verification
        # -------------------------------------------------------------
        ws_wifi = wb.create_sheet(title="Wi-Fi Verification")
        ws_wifi.views.sheetView[0].showGridLines = True

        ws_wifi.merge_cells("A1:I1")
        t8 = ws_wifi["A1"]
        t8.value = "Laptop Wi-Fi Connections & Desktop App Sign-ins (every event recorded by the employee app)"
        t8.font = FONT_TITLE
        t8.fill = FILL_TITLE
        t8.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_wifi.row_dimensions[1].height = 32

        headers_8 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Event",
            "Time",
            "Wi-Fi Network (SSID)",
            "BSSID",
            "Device",
            "Attendance Effect",
        ]
        row_8 = 3
        for col_idx, h in enumerate(headers_8, start=1):
            c = ws_wifi.cell(row=row_8, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 5, 7, 9) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_wifi.row_dimensions[row_8].height = 22

        curr_r8 = 4
        if not wifi_logs:
            ws_wifi.merge_cells("A4:I4")
            c_none = ws_wifi["A4"]
            c_none.value = "No Wi-Fi or desktop app events were received during this reporting period."
            c_none.font = Font(name="Calibri", size=10, italic=True, color=COLOR_AMBER_TXT)
            c_none.alignment = ALIGN_CENTER
            ws_wifi.row_dimensions[4].height = 24

        for item in wifi_logs or []:
            ws_wifi.cell(row=curr_r8, column=1, value=str(item.get("date", ""))).alignment = ALIGN_CENTER
            ws_wifi.cell(row=curr_r8, column=2, value=item.get("employee_code", "")).alignment = ALIGN_CENTER
            ws_wifi.cell(row=curr_r8, column=3, value=item.get("employee_name", "")).alignment = ALIGN_LEFT
            ws_wifi.cell(row=curr_r8, column=4, value=item.get("event", "")).alignment = ALIGN_LEFT
            ws_wifi.cell(row=curr_r8, column=5, value=item.get("time", "")).alignment = ALIGN_CENTER
            ws_wifi.cell(row=curr_r8, column=6, value=item.get("ssid", "")).alignment = ALIGN_LEFT
            ws_wifi.cell(row=curr_r8, column=7, value=item.get("bssid", "")).alignment = ALIGN_CENTER
            ws_wifi.cell(row=curr_r8, column=8, value=item.get("device", "")).alignment = ALIGN_LEFT
            ws_wifi.cell(row=curr_r8, column=9, value=item.get("effect", "")).alignment = ALIGN_CENTER

            for ci in range(1, 10):
                ws_wifi.cell(row=curr_r8, column=ci).border = BORDER_CELL
                ws_wifi.cell(row=curr_r8, column=ci).font = FONT_REGULAR

            curr_r8 += 1

        _autofit_columns(ws_wifi)

        # -------------------------------------------------------------
        # Worksheet 9: Attendance Exceptions
        # -------------------------------------------------------------
        ws_exc = wb.create_sheet(title="Attendance Exceptions")
        ws_exc.views.sheetView[0].showGridLines = True

        ws_exc.merge_cells("A1:I1")
        t9 = ws_exc["A1"]
        t9.value = "Attendance Discrepancies, Missing Clock-Outs & Geofence Exceptions"
        t9.font = FONT_TITLE
        t9.fill = FILL_TITLE
        t9.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws_exc.row_dimensions[1].height = 32

        headers_9 = [
            "Date",
            "Employee Code",
            "Employee Name",
            "Department",
            "Exception Category",
            "Recorded Evidence",
            "Severity",
            "Resolution Status",
            "Audit Remarks",
        ]
        row_9 = 3
        for col_idx, h in enumerate(headers_9, start=1):
            c = ws_exc.cell(row=row_9, column=col_idx, value=h)
            c.font = FONT_HEADER
            c.fill = FILL_HEADER
            c.alignment = ALIGN_CENTER if col_idx in (1, 2, 7, 8) else ALIGN_LEFT
            c.border = BORDER_CELL
        ws_exc.row_dimensions[row_9].height = 22

        curr_r9 = 4
        source_exc = exceptions_data if exceptions_data is not None else [
            {
                "date": log.get("date") or log.get("work_date", str(start_date)),
                "employee_code": log.get("employee_code", ""),
                "employee_name": log.get("employee_name", ""),
                "department": log.get("department", "Operations"),
                "category": "LATE_ARRIVAL" if log.get("status") == "LATE" else "MISSING_CLOCK_OUT",
                "evidence": f"Logged at {log.get('clock_in') or 'n/a'}",
                "severity": "LOW" if log.get("status") == "LATE" else "MEDIUM",
                "status": "OPEN",
                "remarks": "",
            }
            for log in attendance_logs
            if str(log.get("status", "")).upper() in ("LATE", "ABSENT", "HALF_DAY")
        ]

        if not source_exc:
            ws_exc.merge_cells("A4:I4")
            c_none = ws_exc["A4"]
            c_none.value = "No attendance exceptions (absences, missing logouts or late logins) in this period."
            c_none.font = Font(name="Calibri", size=10, italic=True, color=COLOR_GREEN_TXT)
            c_none.fill = PatternFill(start_color=COLOR_GREEN_BG, end_color=COLOR_GREEN_BG, fill_type="solid")
            c_none.alignment = ALIGN_CENTER
            ws_exc.row_dimensions[4].height = 24
        else:
            for item in source_exc:
                ws_exc.cell(row=curr_r9, column=1, value=str(item.get("date", ""))).alignment = ALIGN_CENTER
                ws_exc.cell(row=curr_r9, column=2, value=item.get("employee_code", "")).alignment = ALIGN_CENTER
                ws_exc.cell(row=curr_r9, column=3, value=item.get("employee_name", "")).alignment = ALIGN_LEFT
                ws_exc.cell(row=curr_r9, column=4, value=item.get("department", "Operations")).alignment = ALIGN_LEFT
                ws_exc.cell(row=curr_r9, column=5, value=item.get("category", "GEOFENCE_MISMATCH")).alignment = ALIGN_LEFT
                ws_exc.cell(row=curr_r9, column=6, value=item.get("evidence", "SSID matched external")).alignment = ALIGN_LEFT

                c_sev = ws_exc.cell(row=curr_r9, column=7, value=item.get("severity", "LOW"))
                _apply_status_badge(c_sev, item.get("severity", "LOW"))

                c_st = ws_exc.cell(row=curr_r9, column=8, value=item.get("status", "RESOLVED"))
                _apply_status_badge(c_st, item.get("status", "RESOLVED"))

                ws_exc.cell(row=curr_r9, column=9, value=item.get("remarks", "Reviewed and logged")).alignment = ALIGN_LEFT

                for ci in (1, 2, 3, 4, 5, 6, 9):
                    ws_exc.cell(row=curr_r9, column=ci).border = BORDER_CELL
                    ws_exc.cell(row=curr_r9, column=ci).font = FONT_REGULAR

                curr_r9 += 1

        _autofit_columns(ws_exc)

        # Save Weekly Consolidated Workbook to Secure Storage
        out_dir = cls.get_storage_dir(job_id)
        clean_title = report_title.lower().replace(" ", "_").replace("—", "_")
        file_name = f"weekly_consolidated_{clean_title}_{start_date}_{end_date}.xlsx"
        file_path = out_dir / file_name
        wb.save(str(file_path))

        file_size = os.path.getsize(str(file_path))
        return file_name, str(file_path), file_size

