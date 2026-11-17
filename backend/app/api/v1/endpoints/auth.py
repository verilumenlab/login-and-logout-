"""
Enterprise Authentication, Session Management, RBAC & Device Security Endpoints
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import (
    get_current_active_user,
    get_user_permissions,
    require_role,
)
from app.core.rate_limit import RateLimitExceeded, check_rate_limit, rate_limit
from app.core.security import (
    create_access_token,
    generate_otp_code,
    generate_secure_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.models.auth import (
    LoginHistory,
    PasswordResetToken,
    RefreshToken,
    Role,
    RolePermission,
    User,
)
from app.models.device import Device, DeviceSession
from app.models.notification import EmailOutbox, OutboxStatus
from app.schemas.auth import (
    AccountStatusToggleRequest,
    ActiveSessionResponse,
    DesktopLoginRequest,
    DesktopLoginResponse,
    DeviceAuthRequest,
    DeviceAuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginHistoryResponse,
    LoginRequest,
    RefreshTokenRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserAuthInfo,
)
from app.schemas.user import Token, UserCreate, UserResponse

router = APIRouter()


async def _load_user_with_role(
    email: str,
    db: AsyncSession,
    organization_id: uuid.UUID | None = None,
) -> User | None:
    """Helper to load user with eager-loaded role and permissions."""
    stmt = (
        select(User)
        .options(
            selectinload(User.role).selectinload(Role.role_permissions).selectinload(RolePermission.permission),
            selectinload(User.employee_profile),
        )
        .where(User.email == email)
    )
    if organization_id:
        stmt = stmt.where(User.organization_id == organization_id)
    result = await db.execute(stmt)
    return result.scalars().first()


def _build_user_auth_info(user: User) -> UserAuthInfo:
    """Construct safe UserAuthInfo with roles and permission codes."""
    perms = sorted(get_user_permissions(user))
    role_name = user.role.name if user.role else ("Super Administrator" if user.is_superuser else "Employee")
    return UserAuthInfo(
        id=user.id,
        email=user.email,
        organization_id=user.organization_id,
        role=role_name,
        permissions=perms,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC tz-aware for robust database comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserCreate,
    current_user: User = Depends(require_role("Super Administrator", "Administrator", "Admin")),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user account within an organization (administrators only)."""
    if not current_user.is_superuser:
        if user_in.organization_id != current_user.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Administrators can only create users in their own organization",
            )
        if user_in.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a superuser can create superuser accounts",
            )

    role = (await db.execute(select(Role).where(Role.id == user_in.role_id))).scalars().first()
    if role is None or (role.organization_id is not None and role.organization_id != user_in.organization_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role for this organization",
        )

    existing = await db.execute(
        select(User).where(User.organization_id == user_in.organization_id, User.email == user_in.email)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists in organization",
        )

    user = User(
        organization_id=user_in.organization_id,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        role_id=user_in.role_id,
        is_active=user_in.is_active,
        is_superuser=user_in.is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_login"))])
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate user via email and password using Argon2id.
    Includes brute-force lockout, device check, login auditing, and rotating refresh tokens.
    """
    now = datetime.now(UTC)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user = await _load_user_with_role(payload.email, db)

    if not user:
        # Audit failed unknown email attempt
        history = LoginHistory(
            email=payload.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="User not found",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # 1. Brute-force Lockout Check
    locked_until_utc = _ensure_utc(user.locked_until)
    if locked_until_utc is not None and locked_until_utc > now:
        remaining_seconds = int((locked_until_utc - now).total_seconds())
        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="Account temporarily locked",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account is temporarily locked due to repeated failed logins. Please try again in {remaining_seconds} seconds.",
        )

    # 2. Argon2id Password Verification
    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        failure_reason = "Incorrect password"
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
            failure_reason = "Account locked after 5 failed attempts"

        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason=failure_reason,
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # 3. Account Activation Check
    if not user.is_active:
        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="Account deactivated",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact your organization administrator.",
        )

    # 3b. Desktop Client Role Restriction: Exclusive to Employee accounts (Prompt 18)
    is_desktop_client = (
        (payload.client_type and payload.client_type.strip().lower() == "desktop")
        or request.headers.get("x-client-type", "").strip().lower() == "desktop"
    )
    if is_desktop_client:
        user_role = (user.role.name if user.role else "").strip().lower()
        if user.is_superuser or user_role in (
            "admin",
            "administrator",
            "super admin",
            "super administrator",
            "hr",
            "hr manager",
            "human resources",
            "manager",
            "department manager",
            "team lead",
        ) or user_role != "employee":
            history = LoginHistory(
                organization_id=user.organization_id,
                user_id=user.id,
                email=user.email,
                ip_address=client_ip,
                user_agent=user_agent,
                is_success=False,
                failure_reason="Desktop access denied: Non-employee account attempted desktop login",
                device_identifier=payload.device_identifier,
            )
            db.add(history)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This desktop application is available exclusively to Employee accounts. Please use the web application.",
            )
    elif not user.is_superuser and (user.role.name if user.role else "").strip().lower() == "employee":
        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="Web access denied: Employee accounts must use the desktop app",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee accounts can sign in only from the WorkPulse desktop app installed on your laptop.",
        )

    # 4. Device Verification & Blocking Check
    if payload.device_identifier:
        dev_res = await db.execute(
            select(Device).where(
                Device.organization_id == user.organization_id,
                Device.device_identifier == payload.device_identifier,
            )
        )
        device = dev_res.scalars().first()
        if device and device.is_blocked:
            history = LoginHistory(
                organization_id=user.organization_id,
                user_id=user.id,
                email=user.email,
                ip_address=client_ip,
                user_agent=user_agent,
                is_success=False,
                failure_reason="Device is blocked",
                device_identifier=payload.device_identifier,
            )
            db.add(history)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This device has been blocked by an administrator.",
            )

    # 5. Optional Email OTP Check (if provided)
    if payload.otp_code:
        otp_stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.otp_code == payload.otp_code,
            PasswordResetToken.is_used == False,  # noqa: E712
            PasswordResetToken.expires_at > now,
        )
        otp_res = await db.execute(otp_stmt)
        valid_otp = otp_res.scalars().first()
        if not valid_otp:
            history = LoginHistory(
                organization_id=user.organization_id,
                user_id=user.id,
                email=user.email,
                ip_address=client_ip,
                user_agent=user_agent,
                is_success=False,
                failure_reason="Invalid or expired OTP code",
                device_identifier=payload.device_identifier,
            )
            db.add(history)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired verification OTP code.",
            )
        valid_otp.is_used = True

    # 6. Reset Lockout State & Update Login Timestamp
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    # 7. Issue Rotating Refresh Token Session with Family ID
    family_id = uuid.uuid4()
    raw_refresh_token = generate_secure_token(32)
    token_hash_val = hash_token(raw_refresh_token)
    refresh_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session_rec = RefreshToken(
        user_id=user.id,
        token_hash=token_hash_val,
        family_id=family_id,
        expires_at=refresh_expires_at,
        is_revoked=False,
        client_ip=client_ip,
        user_agent=user_agent,
        device_name=payload.device_name,
    )
    db.add(session_rec)

    # 8. Record Successful Login Audit Log
    history = LoginHistory(
        organization_id=user.organization_id,
        user_id=user.id,
        email=user.email,
        ip_address=client_ip,
        user_agent=user_agent,
        is_success=True,
        device_identifier=payload.device_identifier,
    )
    db.add(history)
    await db.commit()

    # 9. Generate Signed JWT Access Token
    user_info = _build_user_auth_info(user)
    access_token_claims = {
        "email": user.email,
        "org_id": str(user.organization_id),
        "role": user_info.role,
        "permissions": user_info.permissions,
        "is_superuser": user.is_superuser,
    }
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims=access_token_claims,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info,
    )


@router.post("/token", response_model=Token, dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_token"))])
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """OAuth2 compatible token endpoint for OpenAPI documentation authorization."""
    login_req = LoginRequest(email=form_data.username, password=form_data.password)
    res = await login(payload=login_req, request=request, db=db)
    return Token(access_token=res.access_token, token_type="bearer")


@router.post(
    "/desktop-login",
    response_model=DesktopLoginResponse,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_desktop_login"))],
)
@router.post(
    "/desktop/login",
    response_model=DesktopLoginResponse,
    dependencies=[Depends(rate_limit(max_requests=10, window_seconds=60, key_prefix="auth_desktop_login"))],
)
async def desktop_login(
    payload: DesktopLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DesktopLoginResponse:
    """
    Dedicated Employee-Only Desktop Authentication (Prompt 18).
    Strictly verifies credentials, ensures account is active, strictly verifies EMPLOYEE role,
    registers or verifies the client hardware workstation, creates an authenticated DeviceSession,
    and returns scoped tokens with device context. Non-employee accounts (Admin, HR, Manager)
    are rejected with 403 Forbidden.
    """
    now = datetime.now(UTC)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user = await _load_user_with_role(payload.email, db)

    if not user:
        history = LoginHistory(
            email=payload.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="User not found (Desktop)",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # 1. Lockout Check
    locked_until_utc = _ensure_utc(user.locked_until)
    if locked_until_utc is not None and locked_until_utc > now:
        remaining_seconds = int((locked_until_utc - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account is temporarily locked. Please try again in {remaining_seconds} seconds.",
        )

    # 2. Password Check
    if not verify_password(payload.password, user.hashed_password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=15)
        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="Incorrect password (Desktop)",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # 3. Account Active Check
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact your organization administrator.",
        )

    # 4. Strict Role Verification: EMPLOYEE ONLY (Prompt 18 Objective 3)
    user_role = (user.role.name if user.role else "").strip().lower()
    if user.is_superuser or user_role in (
        "admin",
        "administrator",
        "super admin",
        "super administrator",
        "hr",
        "hr manager",
        "human resources",
        "manager",
        "department manager",
        "team lead",
    ) or user_role != "employee":
        history = LoginHistory(
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            ip_address=client_ip,
            user_agent=user_agent,
            is_success=False,
            failure_reason="Desktop access rejected: Exclusive to Employee accounts",
            device_identifier=payload.device_identifier,
        )
        db.add(history)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This desktop application is available exclusively to Employee accounts. Please use the web application.",
        )

    # 5. Verify Employee Profile exists
    if not user.employee_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No employee profile associated with this account.",
        )

    # 6. Register or Verify Hardware Workstation Device
    dev_stmt = select(Device).where(
        Device.organization_id == user.organization_id,
        Device.device_identifier == payload.device_identifier,
    )
    dev_res = await db.execute(dev_stmt)
    device = dev_res.scalars().first()

    if not device:
        device = Device(
            organization_id=user.organization_id,
            device_identifier=payload.device_identifier,
            device_name=payload.device_name or "Employee Workstation",
            os_name=payload.os_name or "Windows",
            os_version=payload.os_version or "11",
            platform=payload.platform or "windows",
            agent_version=payload.agent_version or "0.1.0",
            mac_address=payload.mac_address,
            is_trusted=True,
            is_blocked=False,
            registered_at=now,
            last_seen_at=now,
        )
        db.add(device)
        await db.flush()
    else:
        if device.is_blocked:
            history = LoginHistory(
                organization_id=user.organization_id,
                user_id=user.id,
                email=user.email,
                ip_address=client_ip,
                user_agent=user_agent,
                is_success=False,
                failure_reason="Device is blocked (Desktop)",
                device_identifier=payload.device_identifier,
            )
            db.add(history)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This device has been blocked by an administrator.",
            )
        device.last_seen_at = now
        if payload.agent_version:
            device.agent_version = payload.agent_version

    # 7. Create Active DeviceSession
    raw_session_token = generate_secure_token(32)
    dev_session = DeviceSession(
        device_id=device.id,
        employee_id=user.employee_profile.id,
        session_token_hash=hash_token(raw_session_token),
        start_time=now,
        ip_address=client_ip,
        is_active=True,
    )
    db.add(dev_session)
    await db.flush()

    # 8. Reset Lockout State
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = now

    # 9. Issue Refresh & Access Tokens
    family_id = uuid.uuid4()
    raw_refresh_token = generate_secure_token(32)
    token_hash_val = hash_token(raw_refresh_token)
    refresh_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session_rec = RefreshToken(
        user_id=user.id,
        token_hash=token_hash_val,
        family_id=family_id,
        expires_at=refresh_expires_at,
        is_revoked=False,
        client_ip=client_ip,
        user_agent=user_agent or "EnterpriseAttendanceDesktop/0.1.0",
        device_name=payload.device_name,
    )
    db.add(session_rec)

    # Audit Log
    history = LoginHistory(
        organization_id=user.organization_id,
        user_id=user.id,
        email=user.email,
        ip_address=client_ip,
        user_agent=user_agent,
        is_success=True,
        device_identifier=payload.device_identifier,
    )
    db.add(history)
    await db.commit()

    user_info = _build_user_auth_info(user)
    access_token_claims = {
        "email": user.email,
        "org_id": str(user.organization_id),
        "role": user_info.role,
        "permissions": user_info.permissions,
        "is_superuser": user.is_superuser,
        "device_id": str(device.id),
        "device_session_id": str(dev_session.id),
    }
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims=access_token_claims,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return DesktopLoginResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info,
        device_id=device.id,
        device_identifier=device.device_identifier,
        device_session_id=dev_session.id,
        employee_id=user.employee_profile.id,
        message="Employee desktop session authenticated successfully",
    )


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(rate_limit(max_requests=30, window_seconds=60, key_prefix="auth_refresh"))])
async def refresh_token_endpoint(
    payload: RefreshTokenRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Refresh JWT access token using a rotating refresh token.
    Implements Token Replay Detection: presenting an already-revoked refresh token
    triggers automatic revocation of the entire token family.
    """
    now = datetime.now(UTC)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    device_identifier = (request.headers.get("X-Device-Identifier") or "").strip() or None

    token_hash_val = hash_token(payload.refresh_token)

    stmt = (
        select(RefreshToken)
        .options(
            selectinload(RefreshToken.user)
            .selectinload(User.role)
            .selectinload(Role.role_permissions)
            .selectinload(RolePermission.permission),
            selectinload(RefreshToken.user).selectinload(User.employee_profile),
        )
        .where(RefreshToken.token_hash == token_hash_val)
    )
    result = await db.execute(stmt)
    token_record = result.scalars().first()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # REPLAY ATTACK DETECTION
    if token_record.is_revoked:
        if token_record.family_id:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token_record.family_id)
                .values(
                    is_revoked=True,
                    revoked_at=now,
                    revocation_reason="Token reuse detected / replay attack",
                )
            )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Security alert: Token reuse detected. All sessions in this chain have been revoked.",
        )

    token_expires_at = _ensure_utc(token_record.expires_at)
    if token_expires_at and token_expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )

    user = token_record.user
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    # Resolve desktop device (header preferred) and reject blocked workstations.
    linked_device: Device | None = None
    if device_identifier:
        linked_device = (
            await db.execute(
                select(Device).where(
                    Device.organization_id == user.organization_id,
                    Device.device_identifier == device_identifier,
                )
            )
        ).scalars().first()
    if linked_device is None and token_record.device_name:
        linked_device = (
            await db.execute(
                select(Device)
                .where(
                    Device.organization_id == user.organization_id,
                    Device.device_name == token_record.device_name,
                )
                .order_by(desc(Device.last_seen_at), desc(Device.registered_at))
                .limit(1)
            )
        ).scalars().first()
    if linked_device and linked_device.is_blocked:
        token_record.is_revoked = True
        token_record.revoked_at = now
        token_record.revocation_reason = "Device blocked by administrator"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This device has been blocked by an administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Rotate presented token
    token_record.is_revoked = True
    token_record.revoked_at = now
    token_record.revocation_reason = "Rotated"

    # Issue successor token with identical family ID
    new_raw_token = generate_secure_token(32)
    new_hash_val = hash_token(new_raw_token)
    new_expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    successor = RefreshToken(
        user_id=user.id,
        token_hash=new_hash_val,
        family_id=token_record.family_id,
        expires_at=new_expires_at,
        is_revoked=False,
        client_ip=client_ip,
        user_agent=user_agent,
        device_name=token_record.device_name,
    )
    db.add(successor)
    await db.commit()

    user_info = _build_user_auth_info(user)
    access_token_claims: dict = {
        "email": user.email,
        "org_id": str(user.organization_id),
        "role": user_info.role,
        "permissions": user_info.permissions,
        "is_superuser": user.is_superuser,
    }
    if linked_device:
        access_token_claims["device_id"] = str(linked_device.id)
        if user.employee_profile:
            access_token_claims["employee_id"] = str(user.employee_profile.id)
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims=access_token_claims,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info,
    )


@router.post("/logout")
async def logout(
    payload: RefreshTokenRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke specific refresh token or current user session."""
    now = datetime.now(UTC)
    if payload and payload.refresh_token:
        token_hash_val = hash_token(payload.refresh_token)
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == current_user.id,
                RefreshToken.token_hash == token_hash_val,
            )
            .values(is_revoked=True, revoked_at=now, revocation_reason="User logged out")
        )
    else:
        # Revoke all active sessions
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True, revoked_at=now, revocation_reason="User logged out")
        )
    await db.commit()
    return {"message": "Logged out successfully"}


@router.post("/forgot-password", response_model=ForgotPasswordResponse, dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60, key_prefix="auth_forgot_pw"))])
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """
    Generate password reset token and optional 6-digit email OTP.
    Dispatches notification record into the transactional email outbox.
    """
    now = datetime.now(UTC)
    user = await _load_user_with_role(payload.email, db, payload.organization_id)

    raw_token = generate_secure_token(32)
    otp_code = generate_otp_code(6)

    if user:
        token_hash_val = hash_token(raw_token)
        reset_entry = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash_val,
            otp_code=otp_code,
            expires_at=now + timedelta(minutes=15),
            is_used=False,
        )
        db.add(reset_entry)

        # Centralized Email Notification (Phase 12)
        try:
            from app.services.email_service import EmailService
            await EmailService.notify_password_reset(db, user.id, raw_token, otp_code=otp_code)
        except Exception:
            email_item = EmailOutbox(
                organization_id=user.organization_id,
                recipient_email=user.email,
                subject="Password Reset Code & Instructions",
                body_html=f"<p>Your verification OTP code is: <strong>{otp_code}</strong></p><p>Or reset using token: {raw_token}</p>",
                status=OutboxStatus.PENDING,
            )
            db.add(email_item)
            await db.commit()

    return ForgotPasswordResponse(
        message="If an account exists for this email address, password reset instructions and OTP have been sent.",
    )


@router.post("/reset-password", dependencies=[Depends(rate_limit(max_requests=5, window_seconds=60, key_prefix="auth_reset_pw"))])
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Reset password using valid token or 6-digit OTP.
    Hashes new password with Argon2id and terminates all existing sessions.
    """
    now = datetime.now(UTC)
    token_hash_val = hash_token(payload.token_or_otp)

    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash_val,
        PasswordResetToken.is_used == False,  # noqa: E712
        PasswordResetToken.expires_at > now,
    )
    result = await db.execute(stmt)
    reset_record = result.scalars().first()

    # 6-digit OTPs are low-entropy: only accept them scoped to one account, with a per-account attempt cap.
    if reset_record is None and payload.email:
        allowed, retry_after = await check_rate_limit(
            key=f"auth_reset_otp:{payload.email.lower()}",
            max_requests=5,
            window_seconds=15 * 60,
        )
        if not allowed:
            raise RateLimitExceeded(
                retry_after=retry_after,
                detail="Too many OTP attempts for this account. Please request a new reset code later.",
            )

        user_ids = select(User.id).where(User.email == payload.email)
        if payload.organization_id:
            user_ids = user_ids.where(User.organization_id == payload.organization_id)
        otp_stmt = select(PasswordResetToken).where(
            PasswordResetToken.user_id.in_(user_ids),
            PasswordResetToken.otp_code == payload.token_or_otp,
            PasswordResetToken.is_used == False,  # noqa: E712
            PasswordResetToken.expires_at > now,
        )
        reset_record = (await db.execute(otp_stmt)).scalars().first()

    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token/OTP code.",
        )

    user_stmt = select(User).where(User.id == reset_record.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User account not found.")

    # Update password using Argon2id; clear admin-visible copy (employee chose a new secret).
    from app.core.security import clear_admin_visible_password

    user.hashed_password = get_password_hash(payload.new_password)
    clear_admin_visible_password(user)
    user.failed_login_attempts = 0
    user.locked_until = None
    reset_record.is_used = True
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.is_used == False)  # noqa: E712
        .values(is_used=True)
    )

    # Revoke all existing sessions for security
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True, revoked_at=now, revocation_reason="Password reset")
    )
    await db.commit()

    return {"message": "Password reset successfully. All active sessions have been invalidated."}


@router.post(
    "/change-password",
    dependencies=[Depends(rate_limit(max_requests=8, window_seconds=60, key_prefix="auth_change_pw"))],
)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Change password while signed in. Revokes other sessions for safety."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )

    from app.core.security import clear_admin_visible_password

    now = datetime.now(UTC)
    current_user.hashed_password = get_password_hash(payload.new_password)
    clear_admin_visible_password(current_user)
    current_user.failed_login_attempts = 0
    current_user.locked_until = None

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True, revoked_at=now, revocation_reason="Password changed")
    )
    await db.commit()
    return {"message": "Password changed successfully. Please sign in again on other devices."}


@router.get("/sessions", response_model=list[ActiveSessionResponse])
async def list_active_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[RefreshToken]:
    """List active unrevoked refresh token sessions for authenticated user."""
    now = datetime.now(UTC)
    stmt = (
        select(RefreshToken)
        .where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.is_revoked == False,  # noqa: E712
            RefreshToken.expires_at > now,
        )
        .order_by(desc(RefreshToken.created_at))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke a specific active session."""
    now = datetime.now(UTC)
    stmt = select(RefreshToken).where(RefreshToken.id == session_id)
    result = await db.execute(stmt)
    session_rec = result.scalars().first()

    if not session_rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Only owner or superuser/admin can revoke session
    if session_rec.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    session_rec.is_revoked = True
    session_rec.revoked_at = now
    session_rec.revocation_reason = "Revoked by user"
    await db.commit()

    return {"message": "Session revoked successfully"}


@router.post("/sessions/revoke-all")
async def revoke_all_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke all active sessions for authenticated user."""
    now = datetime.now(UTC)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == current_user.id, RefreshToken.is_revoked == False)  # noqa: E712
        .values(is_revoked=True, revoked_at=now, revocation_reason="Revoke all sessions requested")
    )
    await db.commit()
    return {"message": "All sessions revoked successfully"}


@router.get("/login-history", response_model=list[LoginHistoryResponse])
async def get_login_history(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[LoginHistory]:
    """Inspect login audit history for authenticated user."""
    stmt = (
        select(LoginHistory)
        .where(LoginHistory.user_id == current_user.id)
        .order_by(desc(LoginHistory.created_at))
        .limit(50)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/users/{user_id}/status")
async def toggle_account_status(
    user_id: uuid.UUID,
    payload: AccountStatusToggleRequest,
    current_user: User = Depends(require_role("Super Administrator", "Administrator", "HR Manager", "Admin", "HR")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """
    Administrative account activation/deactivation.
    Deactivating an account immediately revokes all active sessions.
    """
    stmt = select(User).where(User.id == user_id)
    if not current_user.is_superuser:
        stmt = stmt.where(User.organization_id == current_user.organization_id)

    result = await db.execute(stmt)
    target_user = result.scalars().first()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target_user.is_active = payload.is_active

    if not payload.is_active:
        now = datetime.now(UTC)
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == target_user.id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True, revoked_at=now, revocation_reason="Account deactivated by administrator")
        )

    await db.commit()
    return {
        "user_id": target_user.id,
        "is_active": target_user.is_active,
        "message": f"User account has been {'activated' if target_user.is_active else 'deactivated'}.",
    }


@router.post("/devices/authenticate", response_model=DeviceAuthResponse, dependencies=[Depends(rate_limit(max_requests=15, window_seconds=60, key_prefix="auth_device"))])
async def authenticate_device(
    payload: DeviceAuthRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DeviceAuthResponse:
    """
    Desktop client device enrollment and authentication.
    Rejects blocked hardware workstations.
    """
    now = datetime.now(UTC)
    stmt = select(Device).where(
        Device.organization_id == current_user.organization_id,
        Device.device_identifier == payload.device_identifier,
    )
    result = await db.execute(stmt)
    device = result.scalars().first()

    if not device:
        device = Device(
            organization_id=current_user.organization_id,
            device_identifier=payload.device_identifier,
            device_name=payload.device_name,
            os_name=payload.os_name,
            os_version=payload.os_version,
            platform=payload.platform,
            agent_version=payload.agent_version,
            mac_address=payload.mac_address,
            is_trusted=True,
            is_blocked=False,
            registered_at=now,
            last_seen_at=now,
        )
        db.add(device)
        await db.flush()
    else:
        if device.is_blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Device has been blocked by administrator.",
            )
        device.last_seen_at = now
        device.agent_version = payload.agent_version

    # Create active desktop device session if employee profile exists
    session_id = None
    if current_user.employee_profile:
        raw_session_token = generate_secure_token(32)
        dev_session = DeviceSession(
            device_id=device.id,
            employee_id=current_user.employee_profile.id,
            session_token_hash=hash_token(raw_session_token),
            start_time=now,
            ip_address=request.client.host if request.client else None,
            is_active=True,
        )
        db.add(dev_session)
        await db.flush()
        session_id = dev_session.id

    await db.commit()

    return DeviceAuthResponse(
        device_id=device.id,
        device_identifier=device.device_identifier,
        device_name=device.device_name,
        is_trusted=device.is_trusted,
        is_blocked=device.is_blocked,
        session_id=session_id,
        message="Device authenticated successfully",
    )


@router.post("/devices/{device_id}/block")
async def block_device(
    device_id: uuid.UUID,
    current_user: User = Depends(require_role("Super Administrator", "Administrator", "Admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Administrative hardware device blocking."""
    stmt = select(Device).where(Device.id == device_id)
    if not current_user.is_superuser:
        stmt = stmt.where(Device.organization_id == current_user.organization_id)

    result = await db.execute(stmt)
    device = result.scalars().first()

    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    device.is_blocked = True
    await db.commit()
    return {"message": f"Device {device.device_identifier} has been blocked."}


@router.get("/me", response_model=UserAuthInfo)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserAuthInfo:
    """Retrieve authenticated user's current identity and granted permissions."""
    return _build_user_auth_info(current_user)
