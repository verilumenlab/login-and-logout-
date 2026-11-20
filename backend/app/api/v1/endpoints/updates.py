"""
Desktop update feed + check/report endpoints for Electron electron-updater (Windows).
Feed layout (generic provider):
  GET /updates/windows/{channel}/latest.yml
  GET /updates/windows/{channel}/{filename}
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.models.auth import User
from app.models.employee import EmployeeProfile
from app.models.release import EmployeeAppInstallation
from app.schemas.release import (
    UpdateCheckRequest,
    UpdateCheckResponse,
    UpdatePolicyOut,
    UpdateReportRequest,
    UpdateReportResponse,
)
from app.services import release_service

router = APIRouter()


async def _employee_id_for_user(db: AsyncSession, user: User) -> uuid.UUID | None:
    if user.employee_profile:
        return user.employee_profile.id
    res = await db.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == user.id))
    emp = res.scalars().first()
    return emp.id if emp else None


@router.get("/windows/{channel}/latest.yml")
async def windows_latest_yml(
    channel: str,
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """
    electron-updater generic provider feed — published releases only.

    Public (no auth): the desktop updater must read this before/without a session.
    Only the currently published channel package is exposed.
    """
    release = await release_service.get_published_release(db, channel)
    if not release:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No published Windows release")

    yml_file = next((f for f in release.files if f.kind == "latest_yml"), None)
    setup = next((f for f in release.files if f.kind == "setup"), None)

    if yml_file:
        path = Path(yml_file.storage_path)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return PlainTextResponse(content=text, media_type="text/yaml; charset=utf-8")

    # Render ephemeral disks lose uploaded binaries after redeploy. If the DB still
    # points at a published version but files are gone, fail with an actionable message.
    missing_setup = not setup or not Path(setup.storage_path).is_file()
    raise HTTPException(
        status_code=404,
        detail=(
            "Update package files are missing on the server. "
            "Re-upload and publish this Windows release in App Releases"
            + (f" (v{release.version})" if release.version else "")
            + (" — setup exe missing" if missing_setup else " — latest.yml missing")
            + "."
        ),
    )


@router.get("/windows/{channel}/{filename}", response_model=None)
async def windows_download(
    channel: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse | PlainTextResponse:
    """
    Download a published Windows update artifact (setup / blockmap).

    Public read of the published package so electron-updater can install without
    racing the employee login token.
    """
    if filename.lower() in {"latest.yml", "latest.yaml"}:
        return await windows_latest_yml(channel=channel, db=db)

    release, file_row, path = await release_service.get_file_for_download(
        db, channel_name=channel, filename=filename
    )
    await release_service.record_event(
        db,
        event_type="download",
        message=f"Downloaded {filename}",
        organization_id=None,
        actor_user_id=None,
        release_id=release.id,
        details={"filename": filename, "sha256": file_row.sha256, "channel": channel},
    )
    await db.commit()
    return FileResponse(
        path=str(path),
        filename=file_row.filename,
        media_type=file_row.content_type or "application/octet-stream",
    )


# Backward-compatible aliases (query channel)
@router.get("/windows/latest.yml")
async def windows_latest_yml_alias(
    channel: str = Query("production"),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    return await windows_latest_yml(channel=channel, db=db)


@router.post("/check", response_model=UpdateCheckResponse)
async def check_for_update(
    payload: UpdateCheckRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateCheckResponse:
    channel = await release_service.get_channel(db, payload.channel)
    policy = await release_service.get_policy(db, channel)
    published = await release_service.get_published_release(db, payload.channel)

    if payload.device_id:
        now = datetime.now(UTC)
        install = (
            await db.execute(
                select(EmployeeAppInstallation).where(
                    EmployeeAppInstallation.device_id == payload.device_id
                )
            )
        ).scalars().first()
        if install:
            install.last_check_at = now
            install.updated_at = now
        await db.commit()

    if not published:
        return UpdateCheckResponse(update_available=False)

    try:
        available = release_service.compare_semver(payload.current_version, published.version) < 0
    except HTTPException:
        available = True

    mandatory = False
    if policy:
        mandatory = policy.force_update
        if policy.min_supported_version:
            try:
                if release_service.compare_semver(payload.current_version, policy.min_supported_version) < 0:
                    mandatory = True
            except HTTPException:
                mandatory = True

    setup = next((f for f in published.files if f.kind == "setup"), None)
    download_url = None
    if setup:
        download_url = f"/api/v1/updates/windows/{payload.channel}/{setup.filename}"

    return UpdateCheckResponse(
        update_available=available,
        version=published.version if available else None,
        release_id=published.id if available else None,
        notes=published.release_notes if available else None,
        mandatory=mandatory if available else False,
        package_size=published.package_size if available else None,
        sha256=published.sha256 if available else None,
        download_url=download_url if available else None,
    )


@router.post("/report", response_model=UpdateReportResponse)
async def report_update_status(
    payload: UpdateReportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UpdateReportResponse:
    employee_id = await _employee_id_for_user(db, current_user)
    await release_service.report_update(
        db,
        organization_id=current_user.organization_id,
        employee_id=employee_id,
        device_id=payload.device_id,
        channel=payload.channel,
        from_version=payload.from_version,
        to_version=payload.to_version,
        release_id=payload.release_id,
        status_value=payload.status,
        error_message=payload.error_message,
        installed_version=payload.installed_version,
    )
    await db.commit()
    return UpdateReportResponse(ok=True, message="Update report recorded")


@router.get("/policy", response_model=UpdatePolicyOut)
async def desktop_update_policy(
    channel: str = Query("production"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UpdatePolicyOut:
    _ = current_user
    ch = await release_service.get_channel(db, channel)
    policy = await release_service.get_policy(db, ch)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return UpdatePolicyOut(
        channel_name=ch.name,
        min_supported_version=policy.min_supported_version,
        force_update=policy.force_update,
        auto_download=policy.auto_download,
        check_interval_minutes=policy.check_interval_minutes,
        allow_rollback_publish=policy.allow_rollback_publish,
    )
