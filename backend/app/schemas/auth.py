"""
Authentication, Authorization, Session, and Device Pydantic Schemas
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserAuthInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    organization_id: uuid.UUID
    role: str
    permissions: list[str] = Field(default_factory=list)
    is_active: bool
    is_superuser: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_identifier: str | None = None
    device_name: str | None = None
    otp_code: str | None = None
    client_type: str | None = None  # "desktop" or "web"
    platform: str | None = None
    os_name: str | None = None
    os_version: str | None = None
    mac_address: str | None = None
    agent_version: str | None = None


class DesktopLoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_identifier: str
    device_name: str | None = "Workstation"
    platform: str | None = "windows"
    os_name: str | None = "Windows"
    os_version: str | None = "11"
    mac_address: str | None = None
    agent_version: str | None = "0.1.0"
    otp_code: str | None = None


class DesktopLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserAuthInfo
    device_id: uuid.UUID
    device_identifier: str
    device_session_id: uuid.UUID | None = None
    employee_id: uuid.UUID
    message: str = "Employee desktop session authenticated successfully"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserAuthInfo


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    organization_id: uuid.UUID | None = None


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token_or_otp: str
    new_password: str = Field(min_length=8)
    # Required when redeeming a 6-digit OTP; ignored for full reset tokens.
    email: EmailStr | None = None
    organization_id: uuid.UUID | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class ActiveSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_name: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False


class AccountStatusToggleRequest(BaseModel):
    is_active: bool


class DeviceAuthRequest(BaseModel):
    device_identifier: str
    device_name: str
    os_name: str
    os_version: str
    platform: str
    agent_version: str
    mac_address: str | None = None


class DeviceAuthResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: uuid.UUID
    device_identifier: str
    device_name: str
    is_trusted: bool
    is_blocked: bool
    session_id: uuid.UUID | None = None
    message: str


class LoginHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    ip_address: str | None = None
    user_agent: str | None = None
    is_success: bool
    failure_reason: str | None = None
    created_at: datetime
