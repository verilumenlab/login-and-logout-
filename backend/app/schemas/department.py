"""
Department Pydantic Schemas
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=2, max_length=50)
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    parent_id: uuid.UUID | None = None
    is_active: bool | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    parent_id: uuid.UUID | None = None
    is_active: bool
    employee_count: int = 0
    created_at: datetime
    updated_at: datetime
