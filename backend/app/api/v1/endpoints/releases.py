"""
Admin + CI endpoints for Employee Application Release Management.
"""

from __future__ import annotations

import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.auth import User
from app.schemas.release import (
    DeviceUpdateStatusOut,
    ReleaseActionResponse,
    ReleaseOut,
    ReleaseSummary,
    UpdateEventOut,
    UpdatePolicyOut,
)
from app.services import release_service

router = APIRouter()


def _to_out(release) -> ReleaseOut:
    channel_name = release.channel.name if release.channel else "unknown"
    return ReleaseOut(**release_service.release_to_dict(release, channel_name))


def _verify_ci_token(authorization: str | None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing CI bearer token")
    token = authorization.split(" ", 1)[1].strip()
    expected = settings.RELEASE_CI_TOKEN
    if not expected or expected.startswith("change-me"):
        # Allow in development/test when token is placeholder and request matches placeholder
        pass
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CI token")


@router.get("/summary", response_model=ReleaseSummary)
async def release_summary(
    channel: str = Query("production"),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseSummary:
    data = await release_service.build_summary(
        db, channel_name=channel, organization_id=current_user.organization_id
    )
    return ReleaseSummary(**data)


@router.get("/compliance", response_model=list[DeviceUpdateStatusOut])
async def release_compliance(
    channel: str = Query("production"),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceUpdateStatusOut]:
    rows = await release_service.compliance_list(
        db, organization_id=current_user.organization_id, channel_name=channel
    )
    return [DeviceUpdateStatusOut(**r) for r in rows]


@router.get("/events", response_model=list[UpdateEventOut])
async def list_update_events(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[UpdateEventOut]:
    from sqlalchemy import desc, select

    from app.models.release import ApplicationUpdateEvent

    stmt = (
        select(ApplicationUpdateEvent)
        .where(
            (ApplicationUpdateEvent.organization_id == current_user.organization_id)
            | (ApplicationUpdateEvent.organization_id.is_(None))
        )
        .order_by(desc(ApplicationUpdateEvent.created_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/policy", response_model=UpdatePolicyOut)
async def get_update_policy(
    channel: str = Query("production"),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> UpdatePolicyOut:
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


@router.get("/", response_model=list[ReleaseOut])
async def list_releases(
    channel: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[ReleaseOut]:
    _ = current_user
    releases = await release_service.list_releases(db, channel_name=channel, status_filter=status_filter)
    return [_to_out(r) for r in releases]


@router.get("/{release_id}", response_model=ReleaseOut)
async def get_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseOut:
    _ = current_user
    release = await release_service.get_release(db, release_id)
    return _to_out(release)


@router.post("/upload", response_model=ReleaseOut, status_code=status.HTTP_201_CREATED)
async def upload_release(
    version: Annotated[str, Form()],
    channel: Annotated[str, Form()] = "staging",
    release_notes: Annotated[str | None, Form()] = None,
    build_number: Annotated[str | None, Form()] = None,
    setup_file: UploadFile = File(...),
    blockmap_file: UploadFile | None = File(None),
    latest_yml_file: UploadFile | None = File(None),
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseOut:
    release = await release_service.register_release_package(
        db,
        channel_name=channel,
        version=version.lstrip("v"),
        release_notes=release_notes,
        build_number=build_number,
        setup_file=setup_file,
        blockmap_file=blockmap_file,
        latest_yml_file=latest_yml_file,
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
        source="admin_upload",
    )
    await db.commit()
    release = await release_service.get_release(db, release.id)
    return _to_out(release)


@router.post("/ci-register", response_model=ReleaseOut, status_code=status.HTTP_201_CREATED)
async def ci_register_release(
    version: Annotated[str, Form()],
    channel: Annotated[str | None, Form()] = None,
    release_notes: Annotated[str | None, Form()] = None,
    build_number: Annotated[str | None, Form()] = None,
    setup_file: UploadFile = File(...),
    blockmap_file: UploadFile | None = File(None),
    latest_yml_file: UploadFile | None = File(None),
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> ReleaseOut:
    _verify_ci_token(authorization)
    channel_name = channel or settings.RELEASE_DEFAULT_CHANNEL
    release = await release_service.register_release_package(
        db,
        channel_name=channel_name,
        version=version.lstrip("v"),
        release_notes=release_notes,
        build_number=build_number,
        setup_file=setup_file,
        blockmap_file=blockmap_file,
        latest_yml_file=latest_yml_file,
        actor_user_id=None,
        organization_id=None,
        source="ci",
    )
    await db.commit()
    release = await release_service.get_release(db, release.id)
    return _to_out(release)


@router.post("/{release_id}/approve", response_model=ReleaseActionResponse)
async def approve_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseActionResponse:
    release = await release_service.transition_release(
        db,
        release_id=release_id,
        action="approve",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    await db.commit()
    return ReleaseActionResponse(id=release.id, status=release.status, message="Release approved")


@router.post("/{release_id}/publish", response_model=ReleaseActionResponse)
async def publish_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseActionResponse:
    release = await release_service.transition_release(
        db,
        release_id=release_id,
        action="publish",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    await db.commit()
    return ReleaseActionResponse(id=release.id, status=release.status, message="Release published")


@router.post("/{release_id}/pause", response_model=ReleaseActionResponse)
async def pause_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseActionResponse:
    release = await release_service.transition_release(
        db,
        release_id=release_id,
        action="pause",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    await db.commit()
    return ReleaseActionResponse(id=release.id, status=release.status, message="Release paused")


@router.post("/{release_id}/cancel", response_model=ReleaseActionResponse)
async def cancel_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseActionResponse:
    release = await release_service.transition_release(
        db,
        release_id=release_id,
        action="cancel",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    await db.commit()
    return ReleaseActionResponse(id=release.id, status=release.status, message="Release cancelled")


@router.post("/{release_id}/rollback", response_model=ReleaseActionResponse)
async def rollback_release(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReleaseActionResponse:
    release = await release_service.transition_release(
        db,
        release_id=release_id,
        action="rollback",
        actor_user_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    await db.commit()
    return ReleaseActionResponse(
        id=release.id,
        status=release.status,
        message=(
            f"Channel rolled back to {release.version}. "
            "For electron-updater fleets, prefer publishing a new higher patch with reverted binaries."
        ),
    )


@router.get("/{release_id}/devices", response_model=list[DeviceUpdateStatusOut])
async def release_device_status(
    release_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[DeviceUpdateStatusOut]:
    release = await release_service.get_release(db, release_id)
    channel_name = release.channel.name if release.channel else "production"
    rows = await release_service.compliance_list(
        db, organization_id=current_user.organization_id, channel_name=channel_name
    )
    # Annotate relative to this release version
    out: list[DeviceUpdateStatusOut] = []
    for r in rows:
        try:
            needs = release_service.compare_semver(r["agent_version"] or "0.0.0", release.version) < 0
        except HTTPException:
            needs = True
        r = {**r, "needs_update": needs}
        out.append(DeviceUpdateStatusOut(**r))
    return out


@router.get("/{release_id}/files/{file_id}/download", response_model=None)
async def download_archived_release_file(
    release_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: User = Depends(require_role(["Admin", "Super Admin"])),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Download any stored release package from the version archive
    (published, paused, cancelled, rolled_back — files stay on disk).
    """
    release, file_row, path = await release_service.get_stored_release_file(
        db, release_id=release_id, file_id=file_id
    )
    await release_service.record_event(
        db,
        event_type="download",
        message=f"Archived download {file_row.filename} (v{release.version}, {release.status})",
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        release_id=release.id,
        details={
            "filename": file_row.filename,
            "sha256": file_row.sha256,
            "status": release.status,
            "source": "admin_archive",
        },
    )
    await db.commit()
    return FileResponse(
        path=str(path),
        filename=file_row.filename,
        media_type=file_row.content_type or "application/octet-stream",
    )
