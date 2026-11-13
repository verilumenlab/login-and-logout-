"""Complete Database Architecture (35 Entities & Seed Data)

Revision ID: 0001_complete_architecture
Revises: 
Create Date: 2026-11-12 13:00:00.000000

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001_complete_architecture'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

jsonb_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite')


def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        'organizations',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('settings_json', jsonb_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=True)
    op.create_index('ix_organizations_code', 'organizations', ['code'], unique=True)

    # 4. Permissions
    permissions_table = op.create_table(
        'permissions',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('code', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_permissions_code', 'permissions', ['code'], unique=True)
    op.create_index('ix_permissions_module', 'permissions', ['module'], unique=False)

    # 3. Roles
    roles_table = op.create_table(
        'roles',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'name', name='uq_role_org_name'),
    )
    op.create_index('ix_roles_organization_id', 'roles', ['organization_id'], unique=False)

    # Role Permissions Junction
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.UUID(), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('permission_id', sa.UUID(), sa.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    )

    # 2. Users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role_id', sa.UUID(), sa.ForeignKey('roles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'email', name='uq_user_org_email'),
    )
    op.create_index('ix_users_organization_id', 'users', ['organization_id'], unique=False)
    op.create_index('ix_users_email', 'users', ['email'], unique=False)
    op.create_index('ix_users_role_id', 'users', ['role_id'], unique=False)

    # 34. Refresh tokens
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('family_id', sa.UUID(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revocation_reason', sa.String(length=100), nullable=True),
        sa.Column('client_ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('device_name', sa.String(length=150), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'], unique=False)
    op.create_index('ix_refresh_tokens_token_hash', 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index('ix_refresh_tokens_family_id', 'refresh_tokens', ['family_id'], unique=False)
    op.create_index('ix_refresh_tokens_expires_at', 'refresh_tokens', ['expires_at'], unique=False)

    # Password reset tokens & Email OTP
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('otp_code', sa.String(length=6), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_password_reset_user_id', 'password_reset_tokens', ['user_id'], unique=False)
    op.create_index('ix_password_reset_token_hash', 'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index('ix_password_reset_otp_code', 'password_reset_tokens', ['otp_code'], unique=False)

    # Login History
    op.create_table(
        'login_history',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('is_success', sa.Boolean(), nullable=False),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('device_identifier', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_login_history_user_id', 'login_history', ['user_id'], unique=False)
    op.create_index('ix_login_history_email', 'login_history', ['email'], unique=False)
    op.create_index('ix_login_history_created_at', 'login_history', ['created_at'], unique=False)

    # 35. Idempotency keys
    op.create_table(
        'idempotency_keys',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('target_path', sa.String(length=255), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_headers', jsonb_type, nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'idempotency_key', name='uq_idempotency_key_org'),
    )
    op.create_index('ix_idempotency_keys_org_id', 'idempotency_keys', ['organization_id'], unique=False)
    op.create_index('ix_idempotency_keys_key', 'idempotency_keys', ['idempotency_key'], unique=False)

    # 33. Audit logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=100), nullable=False),
        sa.Column('entity_id', sa.String(length=100), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('diff_json', jsonb_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_audit_logs_organization_id', 'audit_logs', ['organization_id'], unique=False)
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_entity_type', 'audit_logs', ['entity_type'], unique=False)
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False)

    # 6. Departments
    op.create_table(
        'departments',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('parent_id', sa.UUID(), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'code', name='uq_department_org_code'),
    )
    op.create_index('ix_departments_organization_id', 'departments', ['organization_id'], unique=False)

    # 8. Work schedules
    op.create_table(
        'work_schedules',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('shift_start_time', sa.Time(), nullable=False),
        sa.Column('shift_end_time', sa.Time(), nullable=False),
        sa.Column('flexible_minutes', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('working_days', jsonb_type, nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_work_schedules_organization_id', 'work_schedules', ['organization_id'], unique=False)

    # 9. Holidays
    op.create_table(
        'holidays',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('holiday_date', sa.Date(), nullable=False),
        sa.Column('is_optional', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'holiday_date', name='uq_holiday_org_date'),
    )
    op.create_index('ix_holidays_organization_id', 'holidays', ['organization_id'], unique=False)
    op.create_index('ix_holidays_holiday_date', 'holidays', ['holiday_date'], unique=False)

    # 5. Employee profiles
    op.create_table(
        'employee_profiles',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_code', sa.String(length=50), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('job_title', sa.String(length=150), nullable=True),
        sa.Column('department_id', sa.UUID(), sa.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True),
        sa.Column('work_schedule_id', sa.UUID(), sa.ForeignKey('work_schedules.id', ondelete='SET NULL'), nullable=True),
        sa.Column('hire_date', sa.Date(), nullable=False),
        sa.Column('termination_date', sa.Date(), nullable=True),
        sa.Column('employment_status', sa.Enum('ACTIVE', 'ON_LEAVE', 'PROBATION', 'TERMINATED', name='employmentstatus'), nullable=False, server_default='ACTIVE'),
        sa.Column('metadata_json', jsonb_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'employee_code', name='uq_employee_code_per_org'),
        sa.UniqueConstraint('user_id', name='uq_employee_user_id'),
    )
    op.create_index('ix_employee_profiles_org_id', 'employee_profiles', ['organization_id'], unique=False)
    op.create_index('ix_employee_profiles_user_id', 'employee_profiles', ['user_id'], unique=True)
    op.create_index('ix_employee_profiles_code', 'employee_profiles', ['employee_code'], unique=False)
    op.create_index('ix_employee_profiles_dept', 'employee_profiles', ['department_id'], unique=False)

    # 7. Manager assignments
    op.create_table(
        'manager_assignments',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('manager_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('employee_id', 'manager_id', name='uq_emp_manager_assignment'),
    )
    op.create_index('ix_manager_assignments_emp', 'manager_assignments', ['employee_id'], unique=False)
    op.create_index('ix_manager_assignments_mgr', 'manager_assignments', ['manager_id'], unique=False)

    # 18. Offices
    op.create_table(
        'offices',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('address', sa.String(length=255), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='UTC'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'code', name='uq_office_org_code'),
    )
    op.create_index('ix_offices_organization_id', 'offices', ['organization_id'], unique=False)

    # 19. Office geofences
    op.create_table(
        'office_geofences',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('office_id', sa.UUID(), sa.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('radius_meters', sa.Float(), nullable=False, server_default='100.0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_office_geofences_office_id', 'office_geofences', ['office_id'], unique=False)

    # 20. Office networks
    op.create_table(
        'office_networks',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('office_id', sa.UUID(), sa.ForeignKey('offices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('subnet_cidr', sa.String(length=50), nullable=True),
        sa.Column('bssid_mac', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_office_networks_office_id', 'office_networks', ['office_id'], unique=False)

    # 21. Location events
    op.create_table(
        'location_events',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('accuracy_meters', sa.Float(), nullable=True),
        sa.Column('is_mocked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata_json', jsonb_type, nullable=True),
    )
    op.create_index('ix_location_events_emp_id', 'location_events', ['employee_id'], unique=False)
    op.create_index('ix_location_events_recorded_at', 'location_events', ['recorded_at'], unique=False)

    # 22. Location verifications
    op.create_table(
        'location_verifications',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('location_event_id', sa.UUID(), sa.ForeignKey('location_events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('office_id', sa.UUID(), sa.ForeignKey('offices.id', ondelete='SET NULL'), nullable=True),
        sa.Column('office_geofence_id', sa.UUID(), sa.ForeignKey('office_geofences.id', ondelete='SET NULL'), nullable=True),
        sa.Column('office_network_id', sa.UUID(), sa.ForeignKey('office_networks.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verification_status', sa.Enum('VERIFIED', 'OUTSIDE_GEOFENCE', 'UNRECOGNIZED_NETWORK', 'SPOOF_DETECTED', name='verificationstatus'), nullable=False),
        sa.Column('distance_meters', sa.Float(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_location_verif_loc_event', 'location_verifications', ['location_event_id'], unique=True)
    op.create_index('ix_location_verif_office', 'location_verifications', ['office_id'], unique=False)

    # 10. Devices
    op.create_table(
        'devices',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_identifier', sa.String(length=255), nullable=False),
        sa.Column('device_name', sa.String(length=150), nullable=False),
        sa.Column('os_name', sa.String(length=50), nullable=False),
        sa.Column('os_version', sa.String(length=50), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('mac_address', sa.String(length=50), nullable=True),
        sa.Column('agent_version', sa.String(length=50), nullable=False),
        sa.Column('is_trusted', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'device_identifier', name='uq_device_org_identifier'),
    )
    op.create_index('ix_devices_organization_id', 'devices', ['organization_id'], unique=False)
    op.create_index('ix_devices_identifier', 'devices', ['device_identifier'], unique=False)

    # 11. Device sessions
    op.create_table(
        'device_sessions',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('device_id', sa.UUID(), sa.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_token_hash', sa.String(length=255), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    op.create_index('ix_device_sessions_device_id', 'device_sessions', ['device_id'], unique=False)
    op.create_index('ix_device_sessions_emp_id', 'device_sessions', ['employee_id'], unique=False)
    op.create_index('ix_device_sessions_token', 'device_sessions', ['session_token_hash'], unique=True)

    # 12. OS activity events
    op.create_table(
        'os_activity_events',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('device_session_id', sa.UUID(), sa.ForeignKey('device_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('device_event_id', sa.String(length=100), nullable=False),
        sa.Column('application_name', sa.String(length=255), nullable=False),
        sa.Column('window_title', sa.String(length=500), nullable=True),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('idle_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('keystrokes_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mouse_clicks_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata_json', jsonb_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('device_session_id', 'device_event_id', name='uq_device_session_event_id'),
    )
    op.create_index('ix_os_activity_session_id', 'os_activity_events', ['device_session_id'], unique=False)
    op.create_index('ix_os_activity_app_name', 'os_activity_events', ['application_name'], unique=False)
    op.create_index('ix_os_activity_start_time', 'os_activity_events', ['start_time'], unique=False)

    # 13. Agent heartbeats
    op.create_table(
        'agent_heartbeats',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('device_session_id', sa.UUID(), sa.ForeignKey('device_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cpu_percent', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('memory_percent', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('is_idle', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('current_window', sa.String(length=500), nullable=True),
    )
    op.create_index('ix_agent_heartbeats_session', 'agent_heartbeats', ['device_session_id'], unique=False)
    op.create_index('ix_agent_heartbeats_time', 'agent_heartbeats', ['timestamp'], unique=False)

    # 14. Attendance days
    op.create_table(
        'attendance_days',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('status', sa.Enum('PRESENT', 'ABSENT', 'HALF_DAY', 'LATE', 'ON_LEAVE', 'HOLIDAY', 'WEEKEND', name='attendancestatus'), nullable=False, server_default='PRESENT'),
        sa.Column('shift_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('shift_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_work_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_break_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_idle_minutes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_overtime', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('employee_id', 'work_date', name='uq_attendance_day_per_emp_date'),
    )
    op.create_index('ix_attendance_days_org_id', 'attendance_days', ['organization_id'], unique=False)
    op.create_index('ix_attendance_days_emp_id', 'attendance_days', ['employee_id'], unique=False)
    op.create_index('ix_attendance_days_work_date', 'attendance_days', ['work_date'], unique=False)

    # 15. Attendance events
    op.create_table(
        'attendance_events',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('attendance_day_id', sa.UUID(), sa.ForeignKey('attendance_days.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.Enum('CLOCK_IN', 'CLOCK_OUT', name='attendanceeventtype'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('location_verification_id', sa.UUID(), sa.ForeignKey('location_verifications.id', ondelete='SET NULL'), nullable=True),
        sa.Column('device_session_id', sa.UUID(), sa.ForeignKey('device_sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source', sa.Enum('WEB', 'DESKTOP', 'MOBILE', 'MANUAL_ENTRY', 'SYSTEM', name='attendancesource'), nullable=False, server_default='WEB'),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_attendance_events_day_id', 'attendance_events', ['attendance_day_id'], unique=False)
    op.create_index('ix_attendance_events_time', 'attendance_events', ['timestamp'], unique=False)

    # 16. Attendance breaks
    op.create_table(
        'attendance_breaks',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('attendance_day_id', sa.UUID(), sa.ForeignKey('attendance_days.id', ondelete='CASCADE'), nullable=False),
        sa.Column('break_type', sa.Enum('LUNCH', 'COFFEE', 'PERSONAL', 'MEETING', name='breaktype'), nullable=False, server_default='LUNCH'),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_attendance_breaks_day_id', 'attendance_breaks', ['attendance_day_id'], unique=False)

    # 17. Attendance adjustments
    op.create_table(
        'attendance_adjustments',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('attendance_day_id', sa.UUID(), sa.ForeignKey('attendance_days.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requester_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('approver_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('adjustment_type', sa.Enum('MISSED_CLOCK_IN', 'MISSED_CLOCK_OUT', 'TIME_CORRECTION', 'STATUS_OVERRIDE', name='adjustmenttype'), nullable=False),
        sa.Column('requested_shift_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('requested_shift_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='adjustmentstatus'), nullable=False, server_default='PENDING'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_attendance_adjust_day_id', 'attendance_adjustments', ['attendance_day_id'], unique=False)
    op.create_index('ix_attendance_adjust_requester', 'attendance_adjustments', ['requester_id'], unique=False)

    # 23. Leave types
    op.create_table(
        'leave_types',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('category', sa.Enum('ANNUAL', 'SICK', 'CASUAL', 'MATERNITY', 'PATERNITY', 'BEREAVEMENT', 'UNPAID', 'COMP_OFF', name='leavecategory'), nullable=False),
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('annual_allowance', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('carryover_max_days', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('requires_attachment', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'code', name='uq_leave_type_org_code'),
    )
    op.create_index('ix_leave_types_org_id', 'leave_types', ['organization_id'], unique=False)

    # 24. Leave balances
    op.create_table(
        'leave_balances',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('leave_type_id', sa.UUID(), sa.ForeignKey('leave_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('allocated_days', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('used_days', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('pending_days', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('carryover_days', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('employee_id', 'leave_type_id', 'year', name='uq_leave_balance_emp_year'),
    )
    op.create_index('ix_leave_balances_org_id', 'leave_balances', ['organization_id'], unique=False)
    op.create_index('ix_leave_balances_emp_id', 'leave_balances', ['employee_id'], unique=False)

    # 25. Leave requests
    op.create_table(
        'leave_requests',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('employee_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('leave_type_id', sa.UUID(), sa.ForeignKey('leave_types.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('total_days', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED', name='leavestatus'), nullable=False, server_default='PENDING'),
        sa.Column('emergency_contact', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('end_date >= start_date', name='chk_leave_dates'),
    )
    op.create_index('ix_leave_requests_org_id', 'leave_requests', ['organization_id'], unique=False)
    op.create_index('ix_leave_requests_emp_id', 'leave_requests', ['employee_id'], unique=False)
    op.create_index('ix_leave_requests_status', 'leave_requests', ['status'], unique=False)

    # 26. Leave approvals
    op.create_table(
        'leave_approvals',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('leave_request_id', sa.UUID(), sa.ForeignKey('leave_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('approver_id', sa.UUID(), sa.ForeignKey('employee_profiles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='approvalstatus'), nullable=False, server_default='PENDING'),
        sa.Column('comments', sa.String(length=500), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_leave_approvals_req_id', 'leave_approvals', ['leave_request_id'], unique=False)
    op.create_index('ix_leave_approvals_approver', 'leave_approvals', ['approver_id'], unique=False)

    # 27. Leave documents
    op.create_table(
        'leave_documents',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('leave_request_id', sa.UUID(), sa.ForeignKey('leave_requests.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_url', sa.String(length=1000), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_leave_documents_req_id', 'leave_documents', ['leave_request_id'], unique=False)

    # 28. Report jobs
    op.create_table(
        'report_jobs',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('requester_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('report_type', sa.Enum('ATTENDANCE_SUMMARY', 'ACTIVITY_BREAKDOWN', 'LEAVE_BALANCES', 'AUDIT_TRAIL', name='reporttype'), nullable=False),
        sa.Column('status', sa.Enum('QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED', name='reportstatus'), nullable=False, server_default='QUEUED'),
        sa.Column('parameters_json', jsonb_type, nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_report_jobs_org_id', 'report_jobs', ['organization_id'], unique=False)
    op.create_index('ix_report_jobs_status', 'report_jobs', ['status'], unique=False)

    # 29. Report files
    op.create_table(
        'report_files',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('report_job_id', sa.UUID(), sa.ForeignKey('report_jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=1000), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_report_files_job_id', 'report_files', ['report_job_id'], unique=False)

    # 30. Email templates
    op.create_table(
        'email_templates',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('template_key', sa.String(length=100), nullable=False),
        sa.Column('subject_template', sa.String(length=255), nullable=False),
        sa.Column('body_html_template', sa.Text(), nullable=False),
        sa.Column('body_text_template', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('organization_id', 'template_key', name='uq_email_template_org_key'),
    )
    op.create_index('ix_email_templates_org_id', 'email_templates', ['organization_id'], unique=False)

    # 31. Email outbox
    op.create_table(
        'email_outbox',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('organization_id', sa.UUID(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('template_id', sa.UUID(), sa.ForeignKey('email_templates.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recipient_email', sa.String(length=255), nullable=False),
        sa.Column('recipient_name', sa.String(length=150), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'SENT', 'FAILED', name='outboxstatus'), nullable=False, server_default='PENDING'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_email_outbox_org_id', 'email_outbox', ['organization_id'], unique=False)
    op.create_index('ix_email_outbox_status', 'email_outbox', ['status'], unique=False)
    op.create_index('ix_email_outbox_recipient', 'email_outbox', ['recipient_email'], unique=False)

    # 32. Email delivery logs
    op.create_table(
        'email_delivery_logs',
        sa.Column('id', sa.UUID(), primary_key=True, default=uuid.uuid4),
        sa.Column('email_outbox_id', sa.UUID(), sa.ForeignKey('email_outbox.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.Enum('DELIVERED', 'BOUNCED', 'DROPPED', 'OPENED', 'CLICKED', name='deliveryeventtype'), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_email_delivery_outbox_id', 'email_delivery_logs', ['email_outbox_id'], unique=False)


def downgrade() -> None:
    # Drop all tables in reverse topological dependency order
    tables_to_drop = [
        'login_history',
        'password_reset_tokens',
        'email_delivery_logs',
        'email_outbox',
        'email_templates',
        'report_files',
        'report_jobs',
        'leave_documents',
        'leave_approvals',
        'leave_requests',
        'leave_balances',
        'leave_types',
        'attendance_adjustments',
        'attendance_breaks',
        'attendance_events',
        'attendance_days',
        'agent_heartbeats',
        'os_activity_events',
        'device_sessions',
        'devices',
        'location_verifications',
        'location_events',
        'office_networks',
        'office_geofences',
        'offices',
        'manager_assignments',
        'employee_profiles',
        'holidays',
        'work_schedules',
        'departments',
        'audit_logs',
        'idempotency_keys',
        'refresh_tokens',
        'users',
        'role_permissions',
        'roles',
        'permissions',
        'organizations',
    ]

    conn = op.get_bind()
    for table in tables_to_drop:
        if conn.dialect.has_table(conn, table):
            op.drop_table(table)

