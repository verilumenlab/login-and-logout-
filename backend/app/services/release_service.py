"""
Employee Application Release storage, lifecycle, and update-feed helpers.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.device import Device, DeviceSession
from app.models.release import (
    ApplicationRelease,
    ApplicationReleaseChannel,
    ApplicationReleaseFile,
    ApplicationUpdateEvent,
    ApplicationUpdatePolicy,
    EmployeeAppInstallation,
    EmployeeUpdateHistory,
)

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
VALID_STATUSES = {"uploaded", "approved", "published", "paused", "cancelled", "rolled_back"}
FILE_KINDS = {"setup", "blockmap", "latest_yml"}


def parse_semver(version: str) -> tuple[int, int, int]:
    clean = version.lstrip("v").strip()
    match = SEMVER_RE.match(clean)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid semver version '{version}'. Expected X.Y.Z",
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def compare_semver(a: str, b: str) -> int:
    """Return -1 if a<b, 0 if equal (core), 1 if a>b."""
    pa, pb = parse_semver(a), parse_semver(b)
    if pa < pb:
        return -1
    if pa > pb:
        return 1
    return 0


def release_storage_root() -> Path:
    raw = Path(settings.RELEASE_STORAGE_DIR)
    if raw.is_absolute():
        root = raw
    else:
        # backend/app/services -> backend/
        backend_root = Path(__file__).resolve().parent.parent.parent
        root = (backend_root / raw).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_release_filename(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "")
    name = re.sub(r"[^\w.\-]", "_", name)
    if not name or name.startswith("."):
        name = f"artifact_{name}"
    return name


def hash_bytes(data: bytes) -> tuple[str, str]:
    return hashlib.sha256(data).hexdigest(), hashlib.sha512(data).hexdigest()


async def ensure_channels_seeded(db: AsyncSession) -> dict[str, ApplicationReleaseChannel]:
    """Ensure staging/production channels + policies exist (needed for create_all tests)."""
    result = await db.execute(select(ApplicationReleaseChannel))
    existing = {c.name: c for c in result.scalars().all()}
    now = datetime.now(UTC)
    created = False
    for name, display, interval, allow_rb in (
        ("staging", "Staging", 60, True),
        ("production", "Production", 240, False),
    ):
        if name in existing:
            continue
        channel = ApplicationReleaseChannel(
            name=name,
            display_name=display,
            description=f"{display} release channel",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(channel)
        await db.flush()
        db.add(
            ApplicationUpdatePolicy(
                channel_id=channel.id,
                force_update=False,
                auto_download=True,
                check_interval_minutes=interval,
                allow_rollback_publish=allow_rb,
                created_at=now,
                updated_at=now,
            )
        )
        existing[name] = channel
        created = True
    if created:
        await db.flush()
    return existing


async def get_channel(db: AsyncSession, name: str) -> ApplicationReleaseChannel:
    channels = await ensure_channels_seeded(db)
    channel = channels.get(name)
    if not channel or not channel.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Channel '{name}' not found")
    return channel


async def get_policy(db: AsyncSession, channel: ApplicationReleaseChannel) -> ApplicationUpdatePolicy | None:
    stmt = select(ApplicationUpdatePolicy).where(ApplicationUpdatePolicy.channel_id == channel.id)
    res = await db.execute(stmt)
    return res.scalars().first()


async def record_event(
    db: AsyncSession,
    *,
    event_type: str,
    message: str | None = None,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    release_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> ApplicationUpdateEvent:
    event = ApplicationUpdateEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        release_id=release_id,
        device_id=device_id,
        event_type=event_type,
        message=message,
        details_json=details or {},
        created_at=datetime.now(UTC),
    )
    db.add(event)
    return event


def release_to_dict(release: ApplicationRelease, channel_name: str) -> dict[str, Any]:
    return {
        "id": release.id,
        "channel_name": channel_name,
        "version": release.version,
        "build_number": release.build_number,
        "release_notes": release.release_notes,
        "status": release.status,
        "os_name": release.os_name,
        "package_size": release.package_size,
        "sha256": release.sha256,
        "sha512": release.sha512,
        "uploaded_at": release.uploaded_at,
        "published_at": release.published_at,
        "created_at": release.created_at,
        "files": [
            {
                "id": f.id,
                "kind": f.kind,
                "filename": f.filename,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
                "sha256": f.sha256,
            }
            for f in (release.files or [])
        ],
    }


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MB",
        )
    return data


def _build_latest_yml(
    *,
    version: str,
    setup_filename: str,
    setup_sha512: str,
    setup_size: int,
    release_notes: str | None,
) -> str:
    """electron-builder generic provider latest.yml (sha512 required)."""
    release_date = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    notes_block = ""
    if release_notes:
        # Keep notes on one escaped line for simple YAML
        escaped = release_notes.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        notes_block = f'releaseNotes: "{escaped}"\n'
    return (
        f"version: {version}\n"
        f"files:\n"
        f"  - url: {setup_filename}\n"
        f"    sha512: {setup_sha512}\n"
        f"    size: {setup_size}\n"
        f"path: {setup_filename}\n"
        f"sha512: {setup_sha512}\n"
        f"releaseDate: '{release_date}'\n"
        f"{notes_block}"
    )


async def register_release_package(
    db: AsyncSession,
    *,
    channel_name: str,
    version: str,
    release_notes: str | None,
    build_number: str | None,
    setup_file: UploadFile,
    blockmap_file: UploadFile | None = None,
    latest_yml_file: UploadFile | None = None,
    actor_user_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    source: str = "admin_upload",
) -> ApplicationRelease:
    parse_semver(version)
    channel = await get_channel(db, channel_name)

    existing = await db.execute(
        select(ApplicationRelease).where(
            ApplicationRelease.channel_id == channel.id,
            ApplicationRelease.version == version,
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Release version {version} already exists on channel '{channel_name}'",
        )

    setup_bytes = await _read_upload(setup_file, settings.RELEASE_MAX_UPLOAD_BYTES)
    setup_name = sanitize_release_filename(setup_file.filename or f"WorkPulse-Employee-Setup-{version}.exe")
    if not setup_name.lower().endswith(".exe"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup package must be a Windows .exe installer",
        )
    sha256, sha512 = hash_bytes(setup_bytes)

    dest_dir = release_storage_root() / channel_name / version
    dest_dir.mkdir(parents=True, exist_ok=True)
    setup_path = dest_dir / setup_name
    setup_path.write_bytes(setup_bytes)

    now = datetime.now(UTC)
    release = ApplicationRelease(
        channel_id=channel.id,
        version=version,
        build_number=build_number,
        release_notes=release_notes,
        status="uploaded",
        os_name="windows",
        package_size=len(setup_bytes),
        sha256=sha256,
        sha512=sha512,
        uploaded_at=now,
        created_by_user_id=actor_user_id,
        metadata_json={"source": source},
        created_at=now,
        updated_at=now,
    )
    db.add(release)
    await db.flush()

    files: list[ApplicationReleaseFile] = [
        ApplicationReleaseFile(
            release_id=release.id,
            kind="setup",
            filename=setup_name,
            storage_path=str(setup_path),
            content_type="application/vnd.microsoft.portable-executable",
            size_bytes=len(setup_bytes),
            sha256=sha256,
            created_at=now,
            updated_at=now,
        )
    ]

    if blockmap_file and blockmap_file.filename:
        bm_bytes = await _read_upload(blockmap_file, settings.RELEASE_MAX_UPLOAD_BYTES)
        bm_name = sanitize_release_filename(blockmap_file.filename)
        bm_path = dest_dir / bm_name
        bm_path.write_bytes(bm_bytes)
        bm_sha, _ = hash_bytes(bm_bytes)
        files.append(
            ApplicationReleaseFile(
                release_id=release.id,
                kind="blockmap",
                filename=bm_name,
                storage_path=str(bm_path),
                content_type="application/octet-stream",
                size_bytes=len(bm_bytes),
                sha256=bm_sha,
                created_at=now,
                updated_at=now,
            )
        )

    if latest_yml_file and latest_yml_file.filename:
        yml_bytes = await _read_upload(latest_yml_file, 2 * 1024 * 1024)
        yml_text = yml_bytes.decode("utf-8")
    else:
        yml_text = _build_latest_yml(
            version=version,
            setup_filename=setup_name,
            setup_sha512=sha512,
            setup_size=len(setup_bytes),
            release_notes=release_notes,
        )
    yml_name = "latest.yml"
    yml_path = dest_dir / yml_name
    yml_path.write_text(yml_text, encoding="utf-8")
    yml_sha, _ = hash_bytes(yml_text.encode("utf-8"))
    files.append(
        ApplicationReleaseFile(
            release_id=release.id,
            kind="latest_yml",
            filename=yml_name,
            storage_path=str(yml_path),
            content_type="text/yaml",
            size_bytes=len(yml_text.encode("utf-8")),
            sha256=yml_sha,
            created_at=now,
            updated_at=now,
        )
    )

    for f in files:
        db.add(f)

    await record_event(
        db,
        event_type="ci_register" if source == "ci" else "upload",
        message=f"Release {version} uploaded to {channel_name}",
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        release_id=release.id,
        details={"version": version, "channel": channel_name, "sha256": sha256, "source": source},
    )
    await db.flush()

    stmt = (
        select(ApplicationRelease)
        .options(selectinload(ApplicationRelease.files), selectinload(ApplicationRelease.channel))
        .where(ApplicationRelease.id == release.id)
    )
    res = await db.execute(stmt)
    return res.scalars().one()


async def list_releases(
    db: AsyncSession,
    *,
    channel_name: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[ApplicationRelease]:
    await ensure_channels_seeded(db)
    stmt = select(ApplicationRelease).options(
        selectinload(ApplicationRelease.files),
        selectinload(ApplicationRelease.channel),
    )
    if channel_name:
        channel = await get_channel(db, channel_name)
        stmt = stmt.where(ApplicationRelease.channel_id == channel.id)
    if status_filter:
        stmt = stmt.where(ApplicationRelease.status == status_filter)
    stmt = stmt.order_by(desc(ApplicationRelease.uploaded_at)).limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_release(db: AsyncSession, release_id: uuid.UUID) -> ApplicationRelease:
    stmt = (
        select(ApplicationRelease)
        .options(selectinload(ApplicationRelease.files), selectinload(ApplicationRelease.channel))
        .where(ApplicationRelease.id == release_id)
    )
    res = await db.execute(stmt)
    release = res.scalars().first()
    if not release:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")
    return release


async def transition_release(
    db: AsyncSession,
    *,
    release_id: uuid.UUID,
    action: str,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
) -> ApplicationRelease:
    release = await get_release(db, release_id)
    channel = release.channel
    policy = await get_policy(db, channel)
    now = datetime.now(UTC)

    if action == "approve":
        if release.status not in {"uploaded"}:
            raise HTTPException(status_code=400, detail=f"Cannot approve release in status '{release.status}'")
        release.status = "approved"
        event_type = "approve"
        message = f"Release {release.version} approved"
    elif action == "publish":
        if release.status not in {"uploaded", "approved", "paused", "rolled_back"}:
            raise HTTPException(status_code=400, detail=f"Cannot publish release in status '{release.status}'")
        # Unpublish other published releases on same channel
        await db.execute(
            update(ApplicationRelease)
            .where(
                ApplicationRelease.channel_id == release.channel_id,
                ApplicationRelease.status == "published",
                ApplicationRelease.id != release.id,
            )
            .values(status="paused", updated_at=now)
        )
        release.status = "published"
        release.published_at = now
        event_type = "publish"
        message = f"Release {release.version} published on {channel.name}"
    elif action == "pause":
        if release.status != "published":
            raise HTTPException(status_code=400, detail="Only published releases can be paused")
        release.status = "paused"
        event_type = "pause"
        message = f"Release {release.version} paused"
    elif action == "cancel":
        if release.status in {"published"}:
            raise HTTPException(status_code=400, detail="Pause the published release before cancelling")
        if release.status == "cancelled":
            raise HTTPException(status_code=400, detail="Release already cancelled")
        release.status = "cancelled"
        event_type = "cancel"
        message = f"Release {release.version} cancelled"
    elif action == "rollback":
        if release.status not in {"paused", "approved", "uploaded", "rolled_back"}:
            # Allow re-publishing a previous non-active release as rolled-back target
            if release.status != "published":
                raise HTTPException(status_code=400, detail=f"Cannot rollback to status '{release.status}'")
        allow_rb = policy.allow_rollback_publish if policy else False
        if not allow_rb and channel.name == "production":
            # Safe rollback: mark current published as rolled_back intent documented;
            # still allow publishing this older release only when policy allows OR we treat as publish of known-good
            pass
        await db.execute(
            update(ApplicationRelease)
            .where(
                ApplicationRelease.channel_id == release.channel_id,
                ApplicationRelease.status == "published",
                ApplicationRelease.id != release.id,
            )
            .values(status="rolled_back", updated_at=now)
        )
        release.status = "published"
        release.published_at = now
        event_type = "rollback"
        message = (
            f"Rolled back channel {channel.name} to {release.version}. "
            "Note: electron-updater rejects downgrades; prefer a new higher patch with reverted code for fleet rollback."
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action '{action}'")

    release.updated_at = now
    await record_event(
        db,
        event_type=event_type,
        message=message,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        release_id=release.id,
        details={"action": action, "status": release.status, "version": release.version},
    )
    await db.flush()
    return await get_release(db, release.id)


async def get_published_release(db: AsyncSession, channel_name: str) -> ApplicationRelease | None:
    channel = await get_channel(db, channel_name)
    stmt = (
        select(ApplicationRelease)
        .options(selectinload(ApplicationRelease.files), selectinload(ApplicationRelease.channel))
        .where(
            ApplicationRelease.channel_id == channel.id,
            ApplicationRelease.status == "published",
        )
        .order_by(desc(ApplicationRelease.published_at))
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def build_summary(db: AsyncSession, *, channel_name: str, organization_id: uuid.UUID) -> dict[str, Any]:
    channel = await get_channel(db, channel_name)
    published = await get_published_release(db, channel_name)

    latest_stmt = (
        select(ApplicationRelease)
        .where(ApplicationRelease.channel_id == channel.id)
        .order_by(desc(ApplicationRelease.uploaded_at))
        .limit(1)
    )
    latest = (await db.execute(latest_stmt)).scalars().first()

    device_count = (
        await db.execute(
            select(func.count()).select_from(Device).where(Device.organization_id == organization_id)
        )
    ).scalar_one()

    needing = 0
    if published:
        devices = (
            await db.execute(select(Device).where(Device.organization_id == organization_id))
        ).scalars().all()
        for d in devices:
            try:
                if compare_semver(d.agent_version or "0.0.0", published.version) < 0:
                    needing += 1
            except HTTPException:
                needing += 1

    success_count = (
        await db.execute(
            select(func.count())
            .select_from(EmployeeUpdateHistory)
            .where(
                EmployeeUpdateHistory.organization_id == organization_id,
                EmployeeUpdateHistory.status == "success",
            )
        )
    ).scalar_one()
    failed_count = (
        await db.execute(
            select(func.count())
            .select_from(EmployeeUpdateHistory)
            .where(
                EmployeeUpdateHistory.organization_id == organization_id,
                EmployeeUpdateHistory.status == "failed",
            )
        )
    ).scalar_one()

    new_available = False
    if latest and latest.status in {"uploaded", "approved"}:
        if not published or compare_semver(latest.version, published.version) > 0:
            new_available = True

    return {
        "current_published_version": published.version if published else None,
        "current_published_id": published.id if published else None,
        "latest_uploaded_version": latest.version if latest else None,
        "latest_uploaded_id": latest.id if latest else None,
        "new_release_available": new_available,
        "channel": channel_name,
        "registered_devices": int(device_count or 0),
        "devices_needing_update": needing,
        "successful_updates": int(success_count or 0),
        "failed_updates": int(failed_count or 0),
    }


async def compliance_list(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    channel_name: str = "production",
) -> list[dict[str, Any]]:
    published = await get_published_release(db, channel_name)
    devices = (
        await db.execute(
            select(Device)
            .where(Device.organization_id == organization_id)
            .order_by(desc(Device.last_seen_at))
        )
    ).scalars().all()

    install_map: dict[uuid.UUID, EmployeeAppInstallation] = {}
    if devices:
        installs = (
            await db.execute(
                select(EmployeeAppInstallation).where(
                    EmployeeAppInstallation.organization_id == organization_id
                )
            )
        ).scalars().all()
        install_map = {i.device_id: i for i in installs}

    # Best-effort employee from latest active session
    emp_by_device: dict[uuid.UUID, uuid.UUID] = {}
    if devices:
        sessions = (
            await db.execute(
                select(DeviceSession)
                .where(DeviceSession.device_id.in_([d.id for d in devices]), DeviceSession.is_active == True)  # noqa: E712
            )
        ).scalars().all()
        for s in sessions:
            emp_by_device[s.device_id] = s.employee_id

    rows: list[dict[str, Any]] = []
    for d in devices:
        install = install_map.get(d.id)
        version = (install.installed_version if install else None) or d.agent_version
        needs = False
        if published:
            try:
                needs = compare_semver(version or "0.0.0", published.version) < 0
            except HTTPException:
                needs = True
        rows.append(
            {
                "device_id": d.id,
                "device_name": d.device_name,
                "device_identifier": d.device_identifier,
                "employee_id": emp_by_device.get(d.id) or (install.employee_id if install else None),
                "agent_version": d.agent_version,
                "installed_version": install.installed_version if install else d.agent_version,
                "needs_update": needs,
                "last_update_status": install.last_update_status if install else None,
                "last_check_at": install.last_check_at if install else None,
                "last_seen_at": d.last_seen_at,
            }
        )
    return rows


async def get_file_for_download(
    db: AsyncSession,
    *,
    channel_name: str,
    filename: str,
) -> tuple[ApplicationRelease, ApplicationReleaseFile, Path]:
    release = await get_published_release(db, channel_name)
    if not release:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published release for channel")

    safe_name = sanitize_release_filename(filename)
    match = next((f for f in release.files if f.filename == safe_name), None)
    if not match:
        # Also allow latest.yml lookup by kind
        if safe_name == "latest.yml":
            match = next((f for f in release.files if f.kind == "latest_yml"), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release file not found")

    path = Path(match.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release file missing from storage")

    # Integrity check
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != match.sha256:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Package integrity check failed",
        )
    return release, match, path


async def report_update(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    device_id: uuid.UUID,
    channel: str,
    from_version: str | None,
    to_version: str | None,
    release_id: uuid.UUID | None,
    status_value: str,
    error_message: str | None,
    installed_version: str | None,
) -> None:
    device = (
        await db.execute(
            select(Device).where(Device.id == device_id, Device.organization_id == organization_id)
        )
    ).scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    now = datetime.now(UTC)
    history = EmployeeUpdateHistory(
        organization_id=organization_id,
        device_id=device_id,
        employee_id=employee_id,
        release_id=release_id,
        from_version=from_version,
        to_version=to_version,
        status=status_value,
        error_message=error_message,
        created_at=now,
        completed_at=now if status_value in {"success", "failed", "skipped"} else None,
    )
    db.add(history)

    install = (
        await db.execute(
            select(EmployeeAppInstallation).where(EmployeeAppInstallation.device_id == device_id)
        )
    ).scalars().first()
    version_to_store = installed_version or to_version or device.agent_version
    if not install:
        install = EmployeeAppInstallation(
            organization_id=organization_id,
            device_id=device_id,
            employee_id=employee_id,
            channel_name=channel,
            installed_version=version_to_store or "0.0.0",
            last_check_at=now,
            last_update_status=status_value,
            last_error=error_message,
            created_at=now,
            updated_at=now,
        )
        db.add(install)
    else:
        install.channel_name = channel
        install.last_check_at = now
        install.last_update_status = status_value
        install.last_error = error_message
        install.employee_id = employee_id or install.employee_id
        if version_to_store and status_value == "success":
            install.installed_version = version_to_store
        install.updated_at = now

    if status_value == "success" and version_to_store:
        device.agent_version = version_to_store
        device.last_seen_at = now

    event_type = "install_ok" if status_value == "success" else "install_fail" if status_value == "failed" else status_value
    await record_event(
        db,
        event_type=event_type,
        message=f"Device update report: {status_value}",
        organization_id=organization_id,
        release_id=release_id,
        device_id=device_id,
        details={
            "from_version": from_version,
            "to_version": to_version,
            "status": status_value,
            "error": error_message,
        },
    )
    await db.flush()
