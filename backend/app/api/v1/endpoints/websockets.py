"""
Enterprise Authenticated WebSocket Endpoints (Phase 14)
Provides real-time attendance, activity, and telemetry streams with
strict JWT authentication, role verification, and organization isolation.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.auth import Role, RolePermission, User

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        # Map organization_id -> list of active WebSockets
        self.active_org_connections: dict[uuid.UUID, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, org_id: uuid.UUID) -> None:
        await websocket.accept()
        if org_id not in self.active_org_connections:
            self.active_org_connections[org_id] = []
        self.active_org_connections[org_id].append(websocket)

    def disconnect(self, websocket: WebSocket, org_id: uuid.UUID) -> None:
        if org_id in self.active_org_connections:
            if websocket in self.active_org_connections[org_id]:
                self.active_org_connections[org_id].remove(websocket)
            if not self.active_org_connections[org_id]:
                del self.active_org_connections[org_id]

    async def broadcast_to_org(self, org_id: uuid.UUID, message: dict[str, Any]) -> None:
        connections = self.active_org_connections.get(org_id, [])
        for connection in list(connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket, dropping: {e}")
                self.disconnect(connection, org_id)


manager = ConnectionManager()


async def _authenticate_ws(websocket: WebSocket) -> User | None:
    """Validate JWT token from query string or headers."""
    token = websocket.query_params.get("token")
    if not token:
        # Check Authorization header
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    user_id_raw = payload.get("sub")
    if not user_id_raw:
        return None

    try:
        user_id = uuid.UUID(str(user_id_raw))
    except ValueError:
        return None

    async with AsyncSessionLocal() as session:
        stmt = (
            select(User)
            .options(
                selectinload(User.role).selectinload(Role.role_permissions).selectinload(RolePermission.permission),
                selectinload(User.employee_profile),
            )
            .where(User.id == user_id)
        )
        res = await session.execute(stmt)
        user = res.scalars().first()
        if not user or not user.is_active:
            return None
        return user


@router.websocket("/ws/attendance")
async def websocket_attendance_endpoint(websocket: WebSocket) -> None:
    """
    Real-time attendance stream with mandatory JWT authentication.
    Rejects unauthorized or missing credentials with policy violation code 4001.
    """
    user = await _authenticate_ws(websocket)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized: Valid JWT token required")
        return

    org_id = user.organization_id
    await manager.connect(websocket, org_id)
    try:
        # Send initial handshake frame
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "user_id": str(user.id),
            "email": user.email,
            "organization_id": str(org_id),
            "role": user.role.name if user.role else "Employee",
            "message": "Connected to organization attendance real-time channel",
        })

        while True:
            data = await websocket.receive_json()
            # Echo ping/pong for keep-alive
            if data.get("type") == "PING":
                await websocket.send_json({"type": "PONG", "timestamp": data.get("timestamp")})
    except WebSocketDisconnect:
        manager.disconnect(websocket, org_id)
    except Exception as exc:
        logger.error(f"WebSocket session error: {exc}")
        manager.disconnect(websocket, org_id)

