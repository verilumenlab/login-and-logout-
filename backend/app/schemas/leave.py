"""
Leave Management Schemas (Phase 09)
Enterprise Pydantic schemas for Leave Policies, Requests, Approvals, Balances, and Documents.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.leave import ApprovalStatus, LeaveCategory, LeaveStatus


# ==========================================
# Leave Type Schemas
# ==========================================

class LeaveTypeBase(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    category: LeaveCategory = LeaveCategory.ANNUAL
    is_paid: bool = True
    annual_allowance: int = Field(default=15, ge=0)
    carryover_max_days: int = Field(default=5, ge=0)
    requires_attachment: bool = False
    include_weekends: bool = False
    is_active: bool = True


class LeaveTypeCreate(LeaveTypeBase):
    pass


class LeaveTypeUpdate(BaseModel):
    name: str | None = None
    category: LeaveCategory | None = None
    is_paid: bool | None = None
    annual_allowance: int | None = Field(default=None, ge=0)
    carryover_max_days: int | None = Field(default=None, ge=0)
    requires_attachment: bool | None = None
    include_weekends: bool | None = None
    is_active: bool | None = None


class LeaveTypeResponse(LeaveTypeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ==========================================
# Leave Balance Schemas
# ==========================================

class LeaveBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_type_name: str | None = None
    leave_type_code: str | None = None
    year: int
    allocated_days: float
    used_days: float
    pending_days: float
    carryover_days: float

    @computed_field
    @property
    def available_days(self) -> float:
        return max(0.0, self.allocated_days + self.carryover_days - self.used_days - self.pending_days)


# ==========================================
# Document Schemas
# ==========================================

class LeaveDocumentCreate(BaseModel):
    file_name: str = Field(..., max_length=255)
    file_url: str = Field(..., max_length=1000)
    file_size_bytes: int = Field(..., gt=0)
    mime_type: str = Field(..., max_length=100)


class LeaveDocumentResponse(LeaveDocumentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    leave_request_id: uuid.UUID
    uploaded_at: datetime


# ==========================================
# Approval Schemas
# ==========================================

class LeaveApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    leave_request_id: uuid.UUID
    approver_id: uuid.UUID
    approver_name: str | None = None
    step_order: int
    stage: str
    status: ApprovalStatus
    comments: str | None = None
    decided_at: datetime | None = None
    created_at: datetime


class LeaveReviewRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    comments: str | None = Field(default=None, max_length=500)


# ==========================================
# Leave Request Schemas
# ==========================================

class LeaveApplyRequest(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    is_half_day: bool = False
    half_day_period: Literal["FIRST_HALF", "SECOND_HALF"] | None = None
    reason: str = Field(..., min_length=3)
    emergency_contact: str | None = Field(default=None, max_length=100)


class LeaveCreate(BaseModel):
    """Legacy backward-compatible create schema."""
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    total_days: float
    reason: str
    is_half_day: bool = False
    half_day_period: str | None = None
    emergency_contact: str | None = None


class LeaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_code: str | None = None
    department_name: str | None = None
    leave_type_id: uuid.UUID
    leave_type_name: str | None = None
    leave_type_code: str | None = None
    start_date: date
    end_date: date
    total_days: float
    is_half_day: bool = False
    half_day_period: str | None = None
    reason: str
    status: LeaveStatus
    manager_approval_status: ApprovalStatus
    hr_approval_status: ApprovalStatus
    withdrawn_at: datetime | None = None
    emergency_contact: str | None = None
    created_at: datetime
    updated_at: datetime
    approvals: list[LeaveApprovalResponse] = []
    documents: list[LeaveDocumentResponse] = []


# ==========================================
# Dashboard & Summary Schemas
# ==========================================

class LeaveDashboardSummary(BaseModel):
    pending_manager_reviews: int = 0
    pending_hr_reviews: int = 0
    my_pending_requests: int = 0
    my_approved_requests: int = 0
    recent_requests: list[LeaveResponse] = []
