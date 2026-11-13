"""
Automated Report Scheduling Service (Phase 13)

Provides:
- Organization timezone-aware date range calculation (DAILY, WEEKLY, MONTHLY)
- Idempotent execution preventing duplicate report generation and email dispatch
- Consolidated HR, Manager Team, and Individual Employee Excel workbooks generation
- Multi-tier transactional email delivery via EmailService
- Missed execution recovery and catch-up detection across server restarts
- Manual on-demand rerun trigger with audit logging

Weekly digest: sent Friday evening for the current Monday-Friday work week. HR, Administrators
and superusers receive the whole-organization workbook; each manager receives a workbook with
only their direct reports.
"""

from __future__ import annotations

import calendar
import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import Role, User
from app.models.organization import Organization
from app.models.reporting import ReportFile, ReportJob, ReportSchedule, ReportStatus, ReportType
from app.services.email_service import EmailService
from app.services.report_dataset import ReportDataset, build_report_dataset
from app.services.report_generator import ExcelReportEngine

logger = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Roles that receive the whole-organization workbook (superusers always do).
ORG_REPORT_ROLE_NAMES = (
    "HR",
    "HR Manager",
    "Human Resources",
    "Admin",
    "Administrator",
    "Super Admin",
    "Super Administrator",
)

DEFAULT_WEEKLY_SEND_TIME = (19, 30)


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
            # Monday-Friday work week. From Friday onwards this is the current week; earlier in the
            # week (e.g. a catch-up run on Monday) it is the last completed week.
            monday = ref_date - timedelta(days=ref_date.weekday())
            if ref_date.weekday() < 4:
                monday -= timedelta(days=7)
            friday = monday + timedelta(days=4)
            iso_year, iso_week, _ = monday.isocalendar()
            period_key = f"{iso_year}-W{iso_week:02d}"
            return monday, friday, period_key

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

    @staticmethod
    def weekly_catchup_reference_date(cron_expression: str | None, tz_name: str, now: datetime | None = None) -> date:
        """
        Reference date for missed-run recovery: the current week only counts as due once
        Friday's send time has passed, so a restart on Friday morning doesn't mail a partial week.
        """
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        hour, minute = DEFAULT_WEEKLY_SEND_TIME
        parts = (cron_expression or "").split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            minute, hour = int(parts[0]), int(parts[1])
        now_local = (now or datetime.now(UTC)).astimezone(tz)
        return (now_local - timedelta(hours=hour, minutes=minute)).date()

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
        for r_type, cron_exp, _desc_text in default_defs:
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

    @staticmethod
    def _generate_workbook(
        schedule_type: ReportType,
        job_id: uuid.UUID,
        org_name: str,
        title: str,
        start_date: date,
        end_date: date,
        data: ReportDataset,
    ) -> tuple[str, str, int]:
        if schedule_type == ReportType.WEEKLY:
            return ExcelReportEngine.generate_weekly_consolidated_report(
                job_id=job_id,
                org_name=org_name,
                report_title=title,
                start_date=start_date,
                end_date=end_date,
                employees_data=data.employees_data,
                attendance_logs=data.attendance_logs,
                os_events=data.os_events,
                leaves_data=data.leaves_data,
                wifi_logs=data.wifi_logs,
                exceptions_data=data.exceptions_data,
            )
        return ExcelReportEngine.generate_consolidated_report(
            job_id=job_id,
            org_name=org_name,
            report_title=title,
            start_date=start_date,
            end_date=end_date,
            employees_data=data.employees_data,
            attendance_logs=data.attendance_logs,
            os_events=data.os_events,
            leaves_data=data.leaves_data,
        )

    @staticmethod
    async def get_org_report_recipients(db: AsyncSession, organization_id: uuid.UUID) -> list[User]:
        """Active HR, Administrator and superuser accounts of the organization (one per email)."""
        users = (
            await db.execute(
                select(User)
                .outerjoin(User.role)
                .where(
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    or_(Role.name.in_(ORG_REPORT_ROLE_NAMES), User.is_superuser.is_(True)),
                )
            )
        ).scalars().all()
        unique: dict[str, User] = {}
        for u in users:
            if u.email:
                unique.setdefault(u.email.lower(), u)
        return list(unique.values())

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
            # 5. Collect attendance, leave and desktop presence (app + Wi-Fi) for the period
            dataset = await build_report_dataset(db, organization_id, start_date, end_date, tz_name)
            emp_map = {e.id: e for e in dataset.employees}

            # 6. Generate Workbooks
            # A. Consolidated organization workbook (HR / Admin)
            report_title = f"{schedule_type.value.title()} Attendance Digest ({period_key})"
            hr_fname, hr_path, hr_size = cls._generate_workbook(
                schedule_type, job.id, org.name, report_title, start_date, end_date, dataset
            )
            hr_file = ReportFile(
                report_job_id=job.id,
                employee_id=None,
                file_name=hr_fname,
                storage_path=hr_path,
                file_size_bytes=hr_size,
                mime_type=XLSX_MIME,
                expires_at=now + timedelta(days=90),
            )
            db.add(hr_file)

            # B. Manager team workbooks: only the manager's direct reports
            manager_files: dict[uuid.UUID, tuple[ReportFile, ReportDataset]] = {}
            if schedule is None or schedule.include_manager_reports:
                for mgr in dataset.employees:
                    if not mgr.direct_reports:
                        continue
                    team = dataset.for_employees({str(r.employee_id) for r in mgr.direct_reports})
                    if not team.employees_data:
                        continue
                    mgr_title = f"Team Attendance Digest - {mgr.first_name} {mgr.last_name} ({period_key})"
                    m_fname, m_path, m_size = cls._generate_workbook(
                        schedule_type, job.id, org.name, mgr_title, start_date, end_date, team
                    )
                    m_file = ReportFile(
                        report_job_id=job.id,
                        employee_id=mgr.id,
                        file_name=m_fname,
                        storage_path=m_path,
                        file_size_bytes=m_size,
                        mime_type=XLSX_MIME,
                        expires_at=now + timedelta(days=90),
                    )
                    db.add(m_file)
                    manager_files[mgr.id] = (m_file, team)

            # C. Individual Employee Workbooks
            if schedule is None or schedule.include_individual_reports:
                for emp_info in dataset.employees_data:
                    mine = dataset.for_employees({emp_info["id"]})
                    i_fname, i_path, i_size = ExcelReportEngine.generate_individual_report(
                        job_id=job.id,
                        org_name=org.name,
                        employee_info=emp_info,
                        start_date=start_date,
                        end_date=end_date,
                        attendance_logs=mine.attendance_logs,
                        os_events=mine.os_events,
                        leaves_data=mine.leaves_data,
                    )
                    db.add(
                        ReportFile(
                            report_job_id=job.id,
                            employee_id=uuid.UUID(emp_info["id"]),
                            file_name=i_fname,
                            storage_path=i_path,
                            file_size_bytes=i_size,
                            mime_type=XLSX_MIME,
                            expires_at=now + timedelta(days=90),
                        )
                    )

            # 7. Update Job Status to COMPLETED
            job.status = ReportStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            if schedule:
                schedule.last_run_at = datetime.now(UTC)
                schedule.last_status = "SUCCESS"
                schedule.last_error = None
            await db.commit()

            # 8. Email the Excel workbooks
            if schedule is None or schedule.send_email:
                date_str = period_key if schedule_type != ReportType.WEEKLY else f"{start_date} to {end_date}"

                org_stats = dataset.stats(f"{org.name} Organization")
                for recipient in await cls.get_org_report_recipients(db, organization_id):
                    await EmailService.notify_attendance_report(
                        db=db,
                        organization_id=organization_id,
                        recipient_email=recipient.email,
                        recipient_name=recipient.full_name or "HR Administrator",
                        report_frequency=schedule_type.value,
                        date_str=date_str,
                        stats=org_stats,
                        attachment_path=hr_file.storage_path,
                        attachment_filename=hr_file.file_name,
                    )

                for m_id, (m_file, team) in manager_files.items():
                    mgr = emp_map.get(m_id)
                    if mgr and mgr.user and mgr.user.email and mgr.user.is_active:
                        await EmailService.notify_attendance_report(
                            db=db,
                            organization_id=organization_id,
                            recipient_email=mgr.user.email,
                            recipient_name=f"{mgr.first_name} {mgr.last_name}",
                            report_frequency=schedule_type.value,
                            date_str=date_str,
                            stats=team.stats(f"Team of {mgr.first_name} {mgr.last_name}"),
                            attachment_path=m_file.storage_path,
                            attachment_filename=m_file.file_name,
                        )

            return True, f"Successfully executed {schedule_type.value} reports for {period_key}", job

        except Exception as e:
            logger.exception("Error executing scheduled reporting: %s", e)
            await db.rollback()
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
            reference_date = None
            if sched.schedule_type == ReportType.WEEKLY:
                reference_date = cls.weekly_catchup_reference_date(sched.cron_expression, sched.timezone)
            start_date, end_date, period_key = cls.get_period_date_range(
                schedule_type=sched.schedule_type,
                tz_name=sched.timezone,
                target_reference_date=reference_date,
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
                    target_reference_date=reference_date,
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
