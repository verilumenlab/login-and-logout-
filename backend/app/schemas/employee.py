"""
Employee Profile and Management Pydantic Schemas
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.employee import EmploymentStatus


class DepartmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str


class WorkScheduleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    shift_start_time: str
    shift_end_time: str


class EmployeeManagerInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    email: str | None = None
    job_title: str | None = None


class EmployeeCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    employee_code: str = Field(min_length=2, max_length=50)
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=150)
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    hr_rep_id: uuid.UUID | None = None
    work_schedule_id: uuid.UUID | None = None
    hire_date: date
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    # Leave empty to auto-generate a password that is emailed to the new user.
    initial_password: str | None = Field(default=None, min_length=8)
    role_name: str | None = "Employee"


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    employee_code: str | None = Field(default=None, min_length=2, max_length=50)
    # Login / mail ID. Changing it signs the employee out so they log in with the new address.
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=150)
    department_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    hr_rep_id: uuid.UUID | None = None
    work_schedule_id: uuid.UUID | None = None
    hire_date: date | None = None
    termination_date: date | None = None
    employment_status: EmploymentStatus | None = None
    is_active: bool | None = None
    role_name: str | None = None


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: str | None = None
    job_title: str | None = None
    department_id: uuid.UUID | None = None
    department: DepartmentBrief | None = None
    work_schedule_id: uuid.UUID | None = None
    work_schedule: WorkScheduleBrief | None = None
    hire_date: date
    termination_date: date | None = None
    employment_status: EmploymentStatus
    is_active: bool
    role_name: str | None = None
    manager: EmployeeManagerInfo | None = None
    hr_rep: EmployeeManagerInfo | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    # Only set on create (and password reset): shown once so HR can confirm the welcome email.
    temporary_password: str | None = None
    credentials_email_sent: bool | None = None
    credentials_email_error: str | None = None
    # Admin-only: last password assigned by an administrator (not available after employee self-reset).
    admin_visible_password: str | None = None
    admin_password_updated_at: datetime | None = None
    has_admin_password: bool = False


class EmployeePagination(BaseModel):
    items: list[EmployeeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class EmployeeImportRowError(BaseModel):
    row: int
    employee_code: str | None = None
    email: str | None = None
    errors: list[str]


class EmployeeImportResult(BaseModel):
    success_count: int
    error_count: int
    imported_employees: list[EmployeeResponse] = Field(default_factory=list)
    errors: list[EmployeeImportRowError] = Field(default_factory=list)
