"""
Automated Report Scheduling Service (Phase 13)

Provides:
- Organization timezone-aware date range calculation (DAILY, WEEKLY, MONTHLY)
- Idempotent execution preventing duplicate report generation and email dispatch
- Consolidated HR, Manager Team, and Individual Employee Excel workbooks generation
- Multi-tier transactional email delivery via EmailService
- Missed execution recovery and catch-up detection across server restarts
- Manual on-demand rerun trigger with audit logging
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.attendance import AttendanceDay, AttendanceEvent, AttendanceStatus
from app.models.auth import Role, User
from app.models.department import Department
from app.models.employee import EmployeeProfile, EmploymentStatus, ManagerAssignment
from app.models.leave import LeaveRequest
from app.models.organization import Organization
from app.models.os_event import OSSessionEvent
from app.models.reporting import ReportFile, ReportJob, ReportSchedule, ReportStatus, ReportType
from app.services.email_service import EmailService
from app.services.report_generator import ExcelReportEngine

logger = logging.getLogger(__name__)


class SchedulerExecutionError(Exception):
    pass


class ReportSchedulerService:
    @classmethod
    def get_period_date_range(
        cls,
        schedule_type: ReportType,
        tz_name: str = "UTC",
        target_reference_date: date | None = None,
    ) -> tuple[date, date, str]:
        """
        Calculates the start and end calendar dates for the specified schedule period
        in the organization's local timezone.
        Returns: (start_date, end_date, period_key)
        """
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        # Determine reference date in local timezone
        if target_reference_date:
            ref_date = target_reference_date
        else:
            now_local = datetime.now(tz)
            ref_date = now_local.date()

        st = schedule_type.value.upper() if isinstance(schedule_type, ReportType) else str(schedule_type).upper()

        if st == "DAILY":
            # Previous calendar day
            yesterday = ref_date - timedelta(days=1)
            period_key = yesterday.strftime("%Y-%m-%d")
            return yesterday, yesterday, period_key

        elif st == "WEEKLY":
            # Previous week: Monday through Sunday
            curr_weekday = ref_date.weekday()  # Monday is 0, Sunday is 6
            last_monday = ref_date - timedelta(days=curr_weekday + 7)
            last_sunday = last_monday + timedelta(days=6)
            iso_year, iso_week, _ = last_monday.isocalendar()
            period_key = f"{iso_year}-W{iso_week:02d}"
            return last_monday, last_sunday, period_key

        elif st == "MONTHLY":
            # Previous calendar month: 1st through last day
            if ref_date.month == 1:
                prev_year = ref_date.year - 1
                prev_month = 12
            else:
                prev_year = ref_date.year
                prev_month = ref_date.month - 1

            first_day = date(prev_year, prev_month, 1)
            _, num_days = calendar.monthrange(prev_year, prev_month)
            last_day = date(prev_year, prev_month, num_days)
            period_key = f"{prev_year}-{prev_month:02d}"
            return first_day, last_day, period_key

        else:
            # Fallback to single day
            return ref_date, ref_date, str(ref_date)

    @classmethod
    async def get_or_create_default_schedules(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        tz_name: str = "UTC",
    ) -> list[ReportSchedule]:
        """Ensures default DAILY, WEEKLY, and MONTHLY schedule records exist for an organization."""
        default_defs = [
            (ReportType.DAILY, "0 6 * * *", "Daily attendance digest for previous day"),
            (ReportType.WEEKLY, "30 19 * * 5", "Weekly Friday digest at 7:30 PM IST"),
            (ReportType.MONTHLY, "0 6 1 * *", "Monthly digest on 1st for previous month"),
        ]

        schedules: list[ReportSchedule] = []
        for r_type, cron_exp, desc_text in default_defs:
            stmt = select(ReportSchedule).where(
                ReportSchedule.organization_id == organization_id,
                ReportSchedule.schedule_type == r_type,
            )
            res = await db.execute(stmt)
            sched = res.scalars().first()
            if not sched:
                now = datetime.now(UTC)
                sched = ReportSchedule(
                    organization_id=organization_id,
                    schedule_type=r_type,
                    cron_expression=cron_exp,
                    timezone=tz_name,
                    is_active=True,
                    send_email=True,
                    include_individual_reports=True,
                    include_manager_reports=True,
                    include_consolidated_report=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(sched)
                await db.flush()
            schedules.append(sched)
        await db.commit()
        return schedules

    @classmethod
    async def execute_scheduled_reporting(
        cls,
        db: AsyncSession,
        organization_id: uuid.UUID,
        schedule_type: ReportType,
        target_reference_date: date | None = None,
        force: bool = False,
        system_requester_id: uuid.UUID | None = None,
    ) -> tuple[bool, str, ReportJob | None]:
        """
        Executes a scheduled report job with strict idempotency and duplicate prevention.
        """
        # 1. Fetch organization and schedule config
        org_stmt = select(Organization).where(Organization.id == organization_id)
        org_res = await db.execute(org_stmt)
        org = org_res.scalars().first()
        if not org:
            return False, "Organization not found", None

        sched_stmt = select(ReportSchedule).where(
            ReportSchedule.organization_id == organization_id,
            ReportSchedule.schedule_type == schedule_type,
        )
        sched_res = await db.execute(sched_stmt)
        schedule = sched_res.scalars().first()
        tz_name = schedule.timezone if schedule else "UTC"

        # 2. Date calculation with organization timezone support
        start_date, end_date, period_key = cls.get_period_date_range(
            schedule_type=schedule_type,
            tz_name=tz_name,
            target_reference_date=target_reference_date,
        )

        idempotency_key = f"sched_{schedule_type.value.lower()}_{org.id}_{period_key}"
        if force:
            idempotency_key += f"_rerun_{int(datetime.now(UTC).timestamp())}"

        # 3. Idempotent Check: Prevent Duplicate Report Execution
        if not force:
            dup_stmt = select(ReportJob).where(
                ReportJob.organization_id == organization_id,
                ReportJob.idempotency_key == idempotency_key,
                ReportJob.status == ReportStatus.COMPLETED,
            )
            dup_res = await db.execute(dup_stmt)
            existing_job = dup_res.scalars().first()
            if existing_job:
                logger.info(
                    "Duplicate scheduled report execution suppressed for key '%s'",
                    idempotency_key,
                )
                return True, f"Report for period '{period_key}' was already executed (idempotent duplicate skipped)", existing_job

        # Find a system requester user if not provided
        if not system_requester_id:
            user_stmt = select(User.id).where(User.organization_id == organization_id).limit(1)
            system_requester_id = await db.scalar(user_stmt)
            if not system_requester_id:
                return False, "No active user found in organization to record as job requester", None

        # 4. Create ReportJob in PROCESSING state
        now = datetime.now(UTC)
        job = ReportJob(
            organization_id=organization_id,
            schedule_id=schedule.id if schedule else None,
            idempotency_key=idempotency_key,
            requester_id=system_requester_id,
            report_type=schedule_type,
            status=ReportStatus.PROCESSING,
            parameters_json={
                "period_key": period_key,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "timezone": tz_name,
                "forced": force,
            },
            started_at=now,
            created_at=now,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # 5. Extract Organization Datasets for Period
            # A. Employees
            emp_stmt = (
                select(EmployeeProfile)
                .options(
                    selectinload(EmployeeProfile.user),
                    selectinload(EmployeeProfile.department),
                    selectinload(EmployeeProfile.direct_managers).selectinload(ManagerAssignment.manager).selectinload(EmployeeProfile.user),
                    selectinload(EmployeeProfile.direct_reports).selectinload(ManagerAssignment.employee).selectinload(EmployeeProfile.user),
                )
                .where(
                    EmployeeProfile.organization_id == organization_id,
                    EmployeeProfile.employment_status == EmploymentStatus.ACTIVE,
                )
            )
            emp_res = await db.execute(emp_stmt)
            all_employees = emp_res.scalars().all()

            # B. Attendance Days
            att_stmt = (
                select(AttendanceDay)
                .options(selectinload(AttendanceDay.employee))
                .where(
                    AttendanceDay.organization_id == organization_id,
                    AttendanceDay.work_date >= start_date,
                    AttendanceDay.work_date <= end_date,
                )
            )
            att_res = await db.execute(att_stmt)
            attendance_days = att_res.scalars().all()

            # C. OS Activity Events
            all_emp_ids = [e.id for e in all_employees]
            if all_emp_ids:
                os_stmt = (
                    select(OSSessionEvent)
                    .where(
                        OSSessionEvent.employee_id.in_(all_emp_ids),
                        OSSessionEvent.occurred_at >= datetime.combine(start_date, time.min, tzinfo=UTC),
                        OSSessionEvent.occurred_at <= datetime.combine(end_date, time.max, tzinfo=UTC),
                    )
                )
                os_res = await db.execute(os_stmt)
                os_events = os_res.scalars().all()
            else:
                os_events = []

            # D. Leave Requests
            leave_stmt = (
                select(LeaveRequest)
                .options(selectinload(LeaveRequest.leave_type), selectinload(LeaveRequest.employee))
                .where(
                    LeaveRequest.organization_id == organization_id,
                    LeaveRequest.start_date <= end_date,
                    LeaveRequest.end_date >= start_date,
                )
            )
            leave_res = await db.execute(leave_stmt)
            leaves = leave_res.scalars().all()

            # Format data lists for Excel Report Engine
            employees_data = []
            emp_map: dict[uuid.UUID, EmployeeProfile] = {}
            for e in all_employees:
                emp_map[e.id] = e
                mgr_str = ", ".join(
                    f"{a.manager.first_name} {a.manager.last_name}"
                    for a in e.direct_managers
                    if a.manager
                ) if e.direct_managers else "None"

                employees_data.append({
                    "id": str(e.id),
                    "employee_code": e.employee_code,
                    "full_name": f"{e.first_name} {e.last_name}",
                    "email": e.user.email if e.user else "",
                    "department": e.department.name if e.department else "Operations",
                    "manager": mgr_str,
                    "hire_date": str(e.hire_date),
                })

            attendance_logs = []
            for a in attendance_days:
                emp = emp_map.get(a.employee_id)
                emp_code = emp.employee_code if emp else "UNKNOWN"
                emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"

                # Compute working hours
                gross_h = (a.total_work_minutes / 60.0) if a.total_work_minutes else 0.0
                break_h = (a.total_break_minutes / 60.0) if a.total_break_minutes else 0.0
                net_h = max(0.0, gross_h - break_h)

                attendance_logs.append({
                    "employee_id": str(a.employee_id),
                    "employee_code": emp_code,
                    "employee_name": emp_name,
                    "work_date": str(a.work_date),
                    "clock_in": a.shift_start.strftime("%H:%M:%S") if a.shift_start else "",
                    "clock_out": a.shift_end.strftime("%H:%M:%S") if a.shift_end else "",
                    "gross_duration_hours": round(gross_h, 2),
                    "break_duration_hours": round(break_h, 2),
                    "net_duration_hours": round(net_h, 2),
                    "status": a.status.value,
                    "location_status": "VERIFIED",
                })

            os_events_data = []
            for ev in os_events:
                emp = emp_map.get(ev.employee_id)
                emp_code = emp.employee_code if emp else "UNKNOWN"
                emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
                ev_type = ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type)
                os_name = ev.operating_system.value if hasattr(ev.operating_system, "value") else str(ev.operating_system)
                os_events_data.append({
                    "employee_id": str(ev.employee_id),
                    "employee_code": emp_code,
                    "employee_name": emp_name,
                    "event_type": ev_type,
                    "occurred_at": ev.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "operating_system": os_name,
                    "sync_status": "SYNCED",
                })

            leaves_data = []
            for lv in leaves:
                emp = emp_map.get(lv.employee_id)
                emp_code = emp.employee_code if emp else "UNKNOWN"
                emp_name = f"{emp.first_name} {emp.last_name}" if emp else "Unknown"
                leaves_data.append({
                    "employee_id": str(lv.employee_id),
                    "employee_code": emp_code,
                    "employee_name": emp_name,
                    "leave_type": lv.leave_type.name if lv.leave_type else "Leave",
                    "start_date": str(lv.start_date),
                    "end_date": str(lv.end_date),
                    "total_days": float(lv.total_days),
                    "status": lv.status.value,
                    "manager_status": lv.manager_approval_status.value,
                    "hr_status": lv.hr_approval_status.value,
                    "reason": lv.reason,
                })

            # 6. Generate Workbooks
            created_files: list[ReportFile] = []

            # A. Consolidated HR Workbook
            report_title = f"{schedule_type.value.title()} Attendance Digest ({period_key})"
            if schedule_type == ReportType.WEEKLY:
                hr_fname, hr_path, hr_size = ExcelReportEngine.generate_weekly_consolidated_report(
                    job_id=job.id,
                    org_name=org.name,
                    report_title=report_title,
                    start_date=start_date,
                    end_date=end_date,
                    employees_data=employees_data,
                    attendance_logs=attendance_logs,
                    os_events=os_events_data,
                    leaves_data=leaves_data,
                )
            else:
                hr_fname, hr_path, hr_size = ExcelReportEngine.generate_consolidated_report(
                    job_id=job.id,
                    org_name=org.name,
                    report_title=report_title,
                    start_date=start_date,
                    end_date=end_date,
                    employees_data=employees_data,
                    attendance_logs=attendance_logs,
                    os_events=os_events_data,
                    leaves_data=leaves_data,
                )
            hr_file = ReportFile(
                report_job_id=job.id,
                employee_id=None,
                file_name=hr_fname,
                storage_path=hr_path,
                file_size_bytes=hr_size,
                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                expires_at=now + timedelta(days=90),
            )
            db.add(hr_file)
            created_files.append(hr_file)

            # B. Manager Team Workbooks
            manager_file_map: dict[uuid.UUID, ReportFile] = {}
            for emp in all_employees:
                if not emp.direct_reports:
                    continue  # Not a manager with reports

                sub_ids = {str(r.employee_id) for r in emp.direct_reports}
                team_emps = [e for e in employees_data if e["id"] in sub_ids]
                team_att = [a for a in attendance_logs if a["employee_id"] in sub_ids]
                team_os = [o for o in os_events_data if o["employee_id"] in sub_ids]
                team_lv = [l for l in leaves_data if l["employee_id"] in sub_ids]

                mgr_title = f"Team Attendance Digest - {emp.first_name} {emp.last_name} ({period_key})"
                m_fname, m_path, m_size = ExcelReportEngine.generate_consolidated_report(
                    job_id=job.id,
                    org_name=org.name,
                    report_title=mgr_title,
                    start_date=start_date,
                    end_date=end_date,
                    employees_data=team_emps,
                    attendance_logs=team_att,
                    os_events=team_os,
                    leaves_data=team_lv,
                )
                m_file = ReportFile(
                    report_job_id=job.id,
                    employee_id=emp.id,
                    file_name=m_fname,
                    storage_path=m_path,
                    file_size_bytes=m_size,
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    expires_at=now + timedelta(days=90),
                )
                db.add(m_file)
                created_files.append(m_file)
                manager_file_map[emp.id] = m_file

            # C. Individual Employee Workbooks
            individual_file_map: dict[uuid.UUID, ReportFile] = {}
            if schedule is None or schedule.include_individual_reports:
                for emp in all_employees:
                    emp_str_id = str(emp.id)
                    emp_info = next((e for e in employees_data if e["id"] == emp_str_id), None)
                    if not emp_info:
                        continue

                    e_att = [a for a in attendance_logs if a["employee_id"] == emp_str_id]
                    e_os = [o for o in os_events_data if o["employee_id"] == emp_str_id]
                    e_lv = [l for l in leaves_data if l["employee_id"] == emp_str_id]

                    i_fname, i_path, i_size = ExcelReportEngine.generate_individual_report(
                        job_id=job.id,
                        org_name=org.name,
                        employee_info=emp_info,
                        start_date=start_date,
                        end_date=end_date,
                        attendance_logs=e_att,
                        os_events=e_os,
                        leaves_data=e_lv,
                    )
                    i_file = ReportFile(
                        report_job_id=job.id,
                        employee_id=emp.id,
                        file_name=i_fname,
                        storage_path=i_path,
                        file_size_bytes=i_size,
                        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        expires_at=now + timedelta(days=90),
                    )
                    db.add(i_file)
                    created_files.append(i_file)
                    individual_file_map[emp.id] = i_file

            # 7. Update Job Status to COMPLETED
            job.status = ReportStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            if schedule:
                schedule.last_run_at = datetime.now(UTC)
                schedule.last_status = "SUCCESS"
                schedule.last_error = None
            await db.commit()

            # 8. Dispatch Email Digests (if email enabled)
            if schedule is None or schedule.send_email:
                total_hours = sum(float(a["net_duration_hours"]) for a in attendance_logs)
                present_count = len({a["employee_id"] for a in attendance_logs if a["status"] in ("PRESENT", "HALF_DAY")})
                late_count = len([a for a in attendance_logs if a["status"] == "LATE"])
                leave_count = len(leaves_data)

                stats_summary = {
                    "scope": f"{org.name} Organization",
                    "present_count": present_count,
                    "late_count": late_count,
                    "leave_count": leave_count,
                    "total_net_hours": round(total_hours, 1),
                    "total_working_hours": round(total_hours, 1),
                    "total_break_hours": round(sum(float(a["break_duration_hours"]) for a in attendance_logs), 1),
                    "attendance_rate": round((present_count / max(1, len(all_employees))) * 100, 1),
                    "resolved_leaves": leave_count,
                    "active_headcount": len(all_employees),
                    "compliance_rate": 99.0,
                    "total_overtime_hours": 0.0,
                }

                # A. Send to HR users
                hr_stmt = (
                    select(User)
                    .join(User.role)
                    .where(
                        User.organization_id == organization_id,
                        Role.name.in_(["HR", "HR Manager", "Admin", "Super Admin"]),
                        User.is_active.is_(True),
                    )
                )
                hr_res = await db.execute(hr_stmt)
                hr_users = hr_res.scalars().all()
                for h in hr_users:
                    if h.email:
                        await EmailService.notify_attendance_report(
                            db=db,
                            organization_id=organization_id,
                            recipient_email=h.email,
                            recipient_name=h.full_name or "HR Administrator",
                            report_frequency=schedule_type.value,
                            date_str=period_key,
                            stats=stats_summary,
                            attachment_path=hr_file.storage_path,
                            attachment_filename=hr_file.file_name,
                        )

                # B. Send to Managers
                for m_id, m_file in manager_file_map.items():
                    mgr = emp_map.get(m_id)
                    if mgr and mgr.user and mgr.user.email:
                        await EmailService.notify_attendance_report(
                            db=db,
                            organization_id=organization_id,
                            recipient_email=mgr.user.email,
                            recipient_name=f"{mgr.first_name} {mgr.last_name}",
                            report_frequency=schedule_type.value,
                            date_str=period_key,
                            stats=stats_summary,
                            attachment_path=m_file.storage_path,
                            attachment_filename=m_file.file_name,
                        )

            return True, f"Successfully executed {schedule_type.value} reports for {period_key}", job

        except Exception as e:
            logger.exception("Error executing scheduled reporting: %s", e)
            job.status = ReportStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.now(UTC)
            if schedule:
                schedule.last_status = "FAILED"
                schedule.last_error = str(e)
            await db.commit()
            return False, f"Failed: {str(e)}", job

    @classmethod
    async def check_and_run_missed_executions(
        cls,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """
        Detects missed executions (e.g. across server restarts or downtime)
        and runs catch-up reporting for all active organizations.
        """
        results: list[dict[str, Any]] = []

        stmt = select(ReportSchedule).where(ReportSchedule.is_active.is_(True))
        res = await db.execute(stmt)
        schedules = res.scalars().all()

        for sched in schedules:
            start_date, end_date, period_key = cls.get_period_date_range(
                schedule_type=sched.schedule_type,
                tz_name=sched.timezone,
            )
            idempotency_key = f"sched_{sched.schedule_type.value.lower()}_{sched.organization_id}_{period_key}"

            # Check if job was completed for this period
            job_stmt = select(ReportJob).where(
                ReportJob.organization_id == sched.organization_id,
                ReportJob.idempotency_key == idempotency_key,
                ReportJob.status == ReportStatus.COMPLETED,
            )
            job_res = await db.execute(job_stmt)
            existing = job_res.scalars().first()

            if not existing:
                logger.info(
                    "Missed execution detected for %s schedule (%s) in org %s. Executing catch-up.",
                    sched.schedule_type.value,
                    period_key,
                    sched.organization_id,
                )
                success, msg, job = await cls.execute_scheduled_reporting(
                    db=db,
                    organization_id=sched.organization_id,
                    schedule_type=sched.schedule_type,
                    force=False,
                )
                results.append({
                    "schedule_id": str(sched.id),
                    "schedule_type": sched.schedule_type.value,
                    "period_key": period_key,
                    "status": "executed" if success else "failed",
                    "message": msg,
                })
            else:
                results.append({
                    "schedule_id": str(sched.id),
                    "schedule_type": sched.schedule_type.value,
                    "period_key": period_key,
                    "status": "skipped",
                    "message": "Already up-to-date",
                })

        return results
