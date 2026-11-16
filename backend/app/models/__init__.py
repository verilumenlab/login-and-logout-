"""
Database Models Registry
Exports all 35 domain entities for SQLAlchemy and Alembic autodiscovery.
"""

from app.core.database import Base
from app.models.attendance import (
    AdjustmentStatus,
    AdjustmentType,
    AttendanceAdjustment,
    AttendanceBreak,
    AttendanceDay,
    AttendanceEvent,
    AttendanceEventType,
    AttendanceSource,
    AttendanceStatus,
    BreakSource,
    BreakType,
)
from app.models.auth import (
    AuditLog,
    IdempotencyKey,
    LoginHistory,
    PasswordResetToken,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
)
from app.models.base import JSONBType, TenantMixin, TimestampMixin, UUIDMixin
from app.models.department import Department
from app.models.device import (
    AgentHeartbeat,
    Device,
    DeviceSession,
    OSActivityEvent,
)
from app.models.employee import (
    EmployeeProfile,
    EmploymentStatus,
    ManagerAssignment,
)
from app.models.leave import (
    ApprovalStatus,
    LeaveApproval,
    LeaveBalance,
    LeaveCategory,
    LeaveDocument,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)
from app.models.notification import (
    DeliveryEventType,
    EmailDeliveryLog,
    EmailOutbox,
    EmailTemplate,
    OutboxStatus,
)
from app.models.office import (
    LocationEvent,
    LocationVerification,
    Office,
    OfficeGeofence,
    OfficeNetwork,
    VerificationStatus,
)
from app.models.os_event import (
    OSSessionEvent,
    OSSessionEventType,
)
from app.models.organization import Organization
from app.models.presence import PresenceAttendanceAction, PresenceEvent, PresenceEventType
from app.models.release import (
    ApplicationRelease,
    ApplicationReleaseChannel,
    ApplicationReleaseFile,
    ApplicationUpdateEvent,
    ApplicationUpdatePolicy,
    EmployeeAppInstallation,
    EmployeeUpdateHistory,
)
from app.models.reporting import (
    ReportFile,
    ReportJob,
    ReportStatus,
    ReportType,
)
from app.models.schedule import Holiday, WorkSchedule

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "TenantMixin",
    "JSONBType",
    # 1. Organizations
    "Organization",
    # 2. Users
    "User",
    # 3. Roles
    "Role",
    # 4. Permissions
    "Permission",
    "RolePermission",
    # 5. Employee profiles
    "EmployeeProfile",
    "EmploymentStatus",
    # 6. Departments
    "Department",
    # 7. Manager assignments
    "ManagerAssignment",
    # 8. Work schedules
    "WorkSchedule",
    # 9. Holidays
    "Holiday",
    # 10. Devices
    "Device",
    # 11. Device sessions
    "DeviceSession",
    # 12. OS activity events
    "OSActivityEvent",
    # 12b. OS session events (Phase 06)
    "OSSessionEvent",
    "OSSessionEventType",
    # 12c. Desktop presence events (app login/logout, Wi-Fi connect/disconnect)
    "PresenceEvent",
    "PresenceEventType",
    "PresenceAttendanceAction",
    # 13. Agent heartbeats
    "AgentHeartbeat",
    # 14. Attendance days
    "AttendanceDay",
    "AttendanceStatus",
    # 15. Attendance events
    "AttendanceEvent",
    "AttendanceEventType",
    "AttendanceSource",
    # 16. Attendance breaks
    "AttendanceBreak",
    "BreakSource",
    "BreakType",
    # 17. Attendance adjustments
    "AttendanceAdjustment",
    "AdjustmentType",
    "AdjustmentStatus",
    # 18. Offices
    "Office",
    # 19. Office geofences
    "OfficeGeofence",
    # 20. Office networks
    "OfficeNetwork",
    # 21. Location events
    "LocationEvent",
    # 22. Location verifications
    "LocationVerification",
    "VerificationStatus",
    # 23. Leave types
    "LeaveType",
    "LeaveCategory",
    # 24. Leave balances
    "LeaveBalance",
    # 25. Leave requests
    "LeaveRequest",
    "LeaveStatus",
    # 26. Leave approvals
    "LeaveApproval",
    "ApprovalStatus",
    # 27. Leave documents
    "LeaveDocument",
    # 28. Report jobs
    "ReportJob",
    "ReportType",
    "ReportStatus",
    # 29. Report files
    "ReportFile",
    # 30. Email templates
    "EmailTemplate",
    # 31. Email outbox
    "EmailOutbox",
    "OutboxStatus",
    # 32. Email delivery logs
    "EmailDeliveryLog",
    "DeliveryEventType",
    # 33. Audit logs
    "AuditLog",
    # 34. Refresh tokens
    "RefreshToken",
    # 35. Idempotency keys
    "IdempotencyKey",
    # Security Extensions
    "PasswordResetToken",
    "LoginHistory",
    # Application releases (Electron / Windows)
    "ApplicationReleaseChannel",
    "ApplicationRelease",
    "ApplicationReleaseFile",
    "ApplicationUpdatePolicy",
    "EmployeeAppInstallation",
    "EmployeeUpdateHistory",
    "ApplicationUpdateEvent",
]
