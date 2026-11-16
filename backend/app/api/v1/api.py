"""
API v1 Router Aggregator
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    activity,
    attendance,
    audit,
    auth,
    departments,
    devices,
    employees,
    health,
    leave,
    locations,
    notifications,
    offices,
    os_events,
    presence,
    releases,
    reporting,
    schedules,
    updates,
    websockets,
)

api_router = APIRouter()

# Health endpoints
api_router.include_router(health.router, tags=["Health"])

# Core modules
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(departments.router, prefix="/departments", tags=["Department Management"])
api_router.include_router(employees.router, prefix="/employees", tags=["Employee Management"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(offices.router, prefix="/offices", tags=["Offices & Geofences"])
api_router.include_router(locations.router, prefix="/locations", tags=["Location Verification"])
api_router.include_router(activity.router, prefix="/activity", tags=["Computer Activity"])
api_router.include_router(os_events.router, prefix="/os-events", tags=["OS Session Monitoring"])
api_router.include_router(presence.router, prefix="/presence", tags=["Employee Presence"])
api_router.include_router(leave.router, prefix="/leave", tags=["Leave Management"])
api_router.include_router(devices.router, prefix="/devices", tags=["Device Management"])
api_router.include_router(releases.router, prefix="/releases", tags=["Application Releases"])
api_router.include_router(updates.router, prefix="/updates", tags=["Desktop Updates"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["Audit Logs"])
api_router.include_router(reporting.router, prefix="/reports", tags=["Reporting & Exports"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications & Email"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["Report Scheduling"])
api_router.include_router(websockets.router, tags=["WebSockets Realtime"])
