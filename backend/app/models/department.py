"""
Department Model
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.employee import EmployeeProfile
    from app.models.organization import Organization


class Department(Base, UUIDMixin, TenantMixin, TimestampMixin):
    """Organizational functional division."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_department_org_code"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="departments")
    parent_department: Mapped[Department | None] = relationship(
        "Department", remote_side="Department.id", back_populates="sub_departments"
    )
    sub_departments: Mapped[list[Department]] = relationship("Department", back_populates="parent_department")
    employees: Mapped[list[EmployeeProfile]] = relationship("EmployeeProfile", back_populates="department")
