"""
Email Template Library & Rendering Engine (Phase 12)

Provides responsive HTML and plain-text templates for:
- Employee account creation
- Password reset
- Leave submission (to Manager)
- Manager approval (to HR for second stage)
- Manager rejection (to Employee)
- HR approval (to Employee & Manager)
- HR rejection (to Employee & Manager)
- Daily attendance reports
- Weekly attendance reports
- Monthly attendance reports
"""

from __future__ import annotations

import html
from typing import Any

from app.core.config import settings

# Base HTML layout wrapping all notification emails
BASE_HTML_WRAPPER = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8fafc;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }}
    .email-container {{
      max-width: 600px;
      margin: 30px auto;
      background: #ffffff;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #e2e8f0;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
    }}
    .header {{
      background: #0f172a;
      padding: 24px 32px;
      text-align: left;
    }}
    .header h1 {{
      color: #ffffff;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin: 0;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-top: 6px;
    }}
    .badge-primary {{ background: #3b82f6; color: #ffffff; }}
    .badge-success {{ background: #10b981; color: #ffffff; }}
    .badge-warning {{ background: #f59e0b; color: #ffffff; }}
    .badge-danger {{ background: #ef4444; color: #ffffff; }}
    .content {{
      padding: 32px;
      color: #334155;
      font-size: 15px;
      line-height: 1.6;
    }}
    .content p {{
      margin: 0 0 16px;
    }}
    .info-card {{
      background: #f1f5f9;
      border-radius: 8px;
      padding: 16px 20px;
      margin: 20px 0;
      border-left: 4px solid #3b82f6;
    }}
    .info-row {{
      display: flex;
      justify-content: space-between;
      padding: 6px 0;
      font-size: 14px;
      border-bottom: 1px solid #e2e8f0;
    }}
    .info-row:last-child {{
      border-bottom: none;
    }}
    .info-label {{
      font-weight: 600;
      color: #64748b;
    }}
    .info-val {{
      font-weight: 600;
      color: #0f172a;
      text-align: right;
    }}
    .btn-container {{
      text-align: center;
      margin: 28px 0;
    }}
    .btn {{
      display: inline-block;
      background: #2563eb;
      color: #ffffff !important;
      padding: 12px 28px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 14px;
      text-decoration: none;
      box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
    }}
    .btn:hover {{
      background: #1d4ed8;
    }}
    .footer {{
      background: #f8fafc;
      padding: 20px 32px;
      border-top: 1px solid #e2e8f0;
      text-align: center;
      font-size: 12px;
      color: #94a3b8;
    }}
    .security-notice {{
      font-size: 12px;
      color: #64748b;
      margin-top: 24px;
      border-top: 1px dashed #cbd5e1;
      padding-top: 16px;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <h1>{org_name}</h1>
      <span class="badge {badge_class}">{badge_text}</span>
    </div>
    <div class="content">
      {body_content}
    </div>
    <div class="footer">
      <p style="margin: 0;">&copy; {year} {org_name}. All rights reserved.</p>
      <p style="margin: 4px 0 0;">Confidential enterprise notification. For authorized recipients only.</p>
    </div>
  </div>
</body>
</html>
"""


TEMPLATES_CONFIG: dict[str, dict[str, Any]] = {
    "employee_account_creation": {
        "subject": "Welcome to {org_name} - Your Account Credentials",
        "badge_class": "badge-primary",
        "badge_text": "Account Provisioned",
        "html": """
          <p>Hello <strong>{employee_name}</strong>,</p>
          <p>Your employee profile has been created in the <strong>{org_name}</strong> Enterprise Attendance & Activity Platform.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Employee ID:</span> <span class="info-val">{employee_code}</span></div>
            <div class="info-row"><span class="info-label">Email:</span> <span class="info-val">{email}</span></div>
            <div class="info-row"><span class="info-label">Department:</span> <span class="info-val">{department_name}</span></div>
            <div class="info-row"><span class="info-label">Designation:</span> <span class="info-val">{designation}</span></div>
            <div class="info-row"><span class="info-label">Temporary Password:</span> <span class="info-val" style="font-family: monospace; color: #2563eb;">{temporary_password}</span></div>
          </div>
          
          <p>Please log in to the web dashboard using your temporary password and set a secure password immediately.</p>
          
          <div class="btn-container">
            <a href="{dashboard_url}/login" class="btn">Sign In to Dashboard</a>
          </div>
          
          <div class="security-notice">
            <strong>Security Reminder:</strong> Never share your credentials with anyone. IT or HR will never ask for your password.
          </div>
        """,
        "text": """
Welcome to {org_name}, {employee_name}!

Your employee profile has been provisioned:
- Employee ID: {employee_code}
- Email: {email}
- Department: {department_name}
- Temporary Password: {temporary_password}

Sign in to configure your permanent password:
{dashboard_url}/login
        """.strip(),
    },
    "password_reset": {
        "subject": "Password Reset Request for {org_name}",
        "badge_class": "badge-warning",
        "badge_text": "Security Alert",
        "html": """
          <p>Hello <strong>{employee_name}</strong>,</p>
          <p>A password reset request was initiated for your enterprise account associated with <strong>{email}</strong>.</p>
          
          <p>If you made this request, please use the button below to choose a new password. This link is valid for <strong>{expires_minutes} minutes</strong>.</p>
          
          <div class="btn-container">
            <a href="{reset_url}" class="btn">Reset Your Password</a>
          </div>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Verification OTP:</span> <span class="info-val" style="font-family: monospace; font-size: 16px; color: #2563eb;">{otp_code}</span></div>
            <div class="info-row"><span class="info-label">Requested At:</span> <span class="info-val">{requested_at}</span></div>
            <div class="info-row"><span class="info-label">Expires At:</span> <span class="info-val">{expires_at}</span></div>
          </div>
          
          <div class="security-notice">
            If you did not request this password reset, please ignore this email or contact your IT security administrator immediately.
          </div>
        """,
        "text": """
Password Reset Request for {org_name}

Hello {employee_name},

A password reset was requested for {email}.
Reset link (valid for {expires_minutes} minutes):
{reset_url}

If you did not make this request, please contact your security administrator.
        """.strip(),
    },
    "leave_submission": {
        "subject": "Action Required: Leave Application Submitted by {employee_name}",
        "badge_class": "badge-primary",
        "badge_text": "Pending Manager Review",
        "html": """
          <p>Hello <strong>{manager_name}</strong>,</p>
          <p>Your team member <strong>{employee_name}</strong> has submitted a new leave application requiring your review.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Employee:</span> <span class="info-val">{employee_name} ({employee_code})</span></div>
            <div class="info-row"><span class="info-label">Leave Type:</span> <span class="info-val">{leave_type}</span></div>
            <div class="info-row"><span class="info-label">Dates:</span> <span class="info-val">{start_date} to {end_date}</span></div>
            <div class="info-row"><span class="info-label">Duration:</span> <span class="info-val">{duration_days} day(s)</span></div>
            <div class="info-row"><span class="info-label">Reason:</span> <span class="info-val">{reason}</span></div>
          </div>
          
          <p>Please sign in to your manager portal to approve or reject this request.</p>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn">Review Application</a>
          </div>
        """,
        "text": """
Action Required: Leave Application from {employee_name}

Leave details:
- Employee: {employee_name} ({employee_code})
- Leave Type: {leave_type}
- Dates: {start_date} to {end_date} ({duration_days} days)
- Reason: {reason}

Sign in to review and endorse:
{dashboard_url}/leave
        """.strip(),
    },
    "leave_manager_approval": {
        "subject": "Manager Endorsed: Leave Request #{request_code} Awaiting HR Approval",
        "badge_class": "badge-warning",
        "badge_text": "Stage 2: HR Approval Needed",
        "html": """
          <p>Dear HR Team,</p>
          <p>Manager <strong>{manager_name}</strong> has reviewed and <strong>APPROVED</strong> the leave application for <strong>{employee_name}</strong>.</p>
          <p>Per organization policy, this request now requires secondary <strong>HR Approval</strong> before final authorization.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Employee:</span> <span class="info-val">{employee_name} ({employee_code})</span></div>
            <div class="info-row"><span class="info-label">Department:</span> <span class="info-val">{department_name}</span></div>
            <div class="info-row"><span class="info-label">Manager:</span> <span class="info-val">{manager_name} (Endorsed)</span></div>
            <div class="info-row"><span class="info-label">Leave Type:</span> <span class="info-val">{leave_type}</span></div>
            <div class="info-row"><span class="info-label">Dates:</span> <span class="info-val">{start_date} to {end_date}</span></div>
            <div class="info-row"><span class="info-label">Total Days:</span> <span class="info-val">{duration_days} day(s)</span></div>
            <div class="info-row"><span class="info-label">Manager Note:</span> <span class="info-val">{manager_note}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn">Sign In to Complete HR Approval</a>
          </div>
        """,
        "text": """
Manager Approved: Leave Request #{request_code} Awaiting HR Final Approval

- Employee: {employee_name} ({employee_code})
- Department: {department_name}
- Endorsing Manager: {manager_name}
- Leave Type: {leave_type}
- Dates: {start_date} to {end_date} ({duration_days} days)

Sign in to complete final HR review:
{dashboard_url}/leave
        """.strip(),
    },
    "leave_manager_rejection": {
        "subject": "Leave Request #{request_code} Declined by Manager",
        "badge_class": "badge-danger",
        "badge_text": "Request Declined",
        "html": """
          <p>Hello <strong>{employee_name}</strong>,</p>
          <p>Your leave application for <strong>{start_date} to {end_date}</strong> has been reviewed and <strong>DECLINED</strong> by your manager <strong>{manager_name}</strong>.</p>
          
          <div class="info-card" style="border-left-color: #ef4444;">
            <div class="info-row"><span class="info-label">Leave Type:</span> <span class="info-val">{leave_type}</span></div>
            <div class="info-row"><span class="info-label">Dates:</span> <span class="info-val">{start_date} to {end_date}</span></div>
            <div class="info-row"><span class="info-label">Manager Reason:</span> <span class="info-val" style="color: #dc2626;">{rejection_reason}</span></div>
          </div>
          
          <p>If you have questions regarding this decision, please speak directly with your reporting manager.</p>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn" style="background: #475569;">View Leave History</a>
          </div>
        """,
        "text": """
Leave Request #{request_code} Declined by Manager

Hello {employee_name},
Your leave request for {start_date} to {end_date} has been declined by {manager_name}.
Reason: {rejection_reason}

View your history:
{dashboard_url}/leave
        """.strip(),
    },
    "leave_hr_approval": {
        "subject": "Final Approval: Leave Request #{request_code} Authorized",
        "badge_class": "badge-success",
        "badge_text": "Leave Authorized",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>The leave application for <strong>{employee_name}</strong> has received final <strong>HR APPROVAL</strong>.</p>
          
          <div class="info-card" style="border-left-color: #10b981;">
            <div class="info-row"><span class="info-label">Employee:</span> <span class="info-val">{employee_name} ({employee_code})</span></div>
            <div class="info-row"><span class="info-label">Leave Type:</span> <span class="info-val">{leave_type}</span></div>
            <div class="info-row"><span class="info-label">Authorized Dates:</span> <span class="info-val">{start_date} to {end_date}</span></div>
            <div class="info-row"><span class="info-label">Total Days:</span> <span class="info-val">{duration_days} day(s)</span></div>
            <div class="info-row"><span class="info-label">HR Approver:</span> <span class="info-val">{hr_name}</span></div>
            <div class="info-row"><span class="info-label">Status:</span> <span class="info-val" style="color: #059669;">CONFIRMED</span></div>
          </div>
          
          <p>Attendance records have been automatically synchronized with approved leave status for these dates.</p>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn" style="background: #059669;">View in Dashboard</a>
          </div>
        """,
        "text": """
Final Approval: Leave Request #{request_code} Authorized

- Employee: {employee_name} ({employee_code})
- Leave Type: {leave_type}
- Dates: {start_date} to {end_date} ({duration_days} days)
- Approved By: {hr_name}
- Status: CONFIRMED

View in dashboard:
{dashboard_url}/leave
        """.strip(),
    },
    "leave_hr_rejection": {
        "subject": "HR Decision: Leave Request #{request_code} Rejected",
        "badge_class": "badge-danger",
        "badge_text": "Rejected by HR",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>The leave application for <strong>{employee_name}</strong> has been <strong>REJECTED</strong> at the HR approval stage.</p>
          
          <div class="info-card" style="border-left-color: #ef4444;">
            <div class="info-row"><span class="info-label">Employee:</span> <span class="info-val">{employee_name} ({employee_code})</span></div>
            <div class="info-row"><span class="info-label">Leave Type:</span> <span class="info-val">{leave_type}</span></div>
            <div class="info-row"><span class="info-label">Dates:</span> <span class="info-val">{start_date} to {end_date}</span></div>
            <div class="info-row"><span class="info-label">HR Reason:</span> <span class="info-val" style="color: #dc2626;">{rejection_reason}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn" style="background: #475569;">View Leave History</a>
          </div>
        """,
        "text": """
HR Decision: Leave Request #{request_code} Rejected

- Employee: {employee_name} ({employee_code})
- Dates: {start_date} to {end_date}
- Rejection Reason: {rejection_reason}

View in dashboard:
{dashboard_url}/leave
        """.strip(),
    },
    "attendance_daily_report": {
        "subject": "Daily Attendance Summary - {report_date}",
        "badge_class": "badge-primary",
        "badge_text": "Daily Report",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>Here is your daily attendance and work summary for <strong>{report_date}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Target:</span> <span class="info-val">{target_scope}</span></div>
            <div class="info-row"><span class="info-label">Total Present:</span> <span class="info-val">{present_count}</span></div>
            <div class="info-row"><span class="info-label">Late Arrivals:</span> <span class="info-val">{late_count}</span></div>
            <div class="info-row"><span class="info-label">On Leave:</span> <span class="info-val">{leave_count}</span></div>
            <div class="info-row"><span class="info-label">Total Net Working Hours:</span> <span class="info-val">{total_net_hours}h</span></div>
          </div>
          
          <p>The detailed Excel report has been attached to this email or is available via your dashboard.</p>
          
          <div class="btn-container">
            <a href="{dashboard_url}/reports" class="btn">View Online Reports</a>
          </div>
        """,
        "text": """
Daily Attendance Summary - {report_date}

- Target Scope: {target_scope}
- Total Present: {present_count}
- Late Arrivals: {late_count}
- On Leave: {leave_count}
- Total Net Working Hours: {total_net_hours}h

Access reports online:
{dashboard_url}/reports
        """.strip(),
    },
    "attendance_weekly_report": {
        "subject": "Weekly Attendance Executive Digest ({week_range})",
        "badge_class": "badge-primary",
        "badge_text": "Weekly Digest",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>Attached is the consolidated weekly attendance and computer activity digest for the period <strong>{week_range}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Scope:</span> <span class="info-val">{target_scope}</span></div>
            <div class="info-row"><span class="info-label">Average Daily Attendance:</span> <span class="info-val">{attendance_rate}%</span></div>
            <div class="info-row"><span class="info-label">Total Working Hours:</span> <span class="info-val">{total_working_hours}h</span></div>
            <div class="info-row"><span class="info-label">Total Break Duration:</span> <span class="info-val">{total_break_hours}h</span></div>
            <div class="info-row"><span class="info-label">Resolved Leaves:</span> <span class="info-val">{resolved_leaves}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/reports" class="btn">Open Reports Center</a>
          </div>
        """,
        "text": """
Weekly Attendance Executive Digest ({week_range})

- Scope: {target_scope}
- Attendance Rate: {attendance_rate}%
- Working Hours: {total_working_hours}h
- Break Hours: {total_break_hours}h

Access online:
{dashboard_url}/reports
        """.strip(),
    },
    "attendance_monthly_report": {
        "subject": "Monthly Organization Attendance & Compliance Report ({month_year})",
        "badge_class": "badge-primary",
        "badge_text": "Monthly Audit",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>The monthly attendance, OS session compliance, and leave audit workbook for <strong>{month_year}</strong> has been generated.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Organization:</span> <span class="info-val">{org_name}</span></div>
            <div class="info-row"><span class="info-label">Active Headcount:</span> <span class="info-val">{active_headcount}</span></div>
            <div class="info-row"><span class="info-label">Monthly Compliance:</span> <span class="info-val">{compliance_rate}%</span></div>
            <div class="info-row"><span class="info-label">Total Overtime Hours:</span> <span class="info-val">{total_overtime_hours}h</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/reports" class="btn">Download Full Compliance Workbook</a>
          </div>
        """,
        "text": """
Monthly Attendance & Compliance Report ({month_year})

- Organization: {org_name}
- Active Headcount: {active_headcount}
- Compliance Rate: {compliance_rate}%

Download via dashboard:
{dashboard_url}/reports
        """.strip(),
    },
    "login_security_alert": {
        "subject": "Security Alert: New Sign-in Event on Your Account ({event_type})",
        "badge_class": "badge-danger",
        "badge_text": "Security Alert",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>We detected an important authentication event on your employee account at <strong>{event_time}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Event Type:</span> <span class="info-val">{event_type}</span></div>
            <div class="info-row"><span class="info-label">IP Address:</span> <span class="info-val">{ip_address}</span></div>
            <div class="info-row"><span class="info-label">Device / Client:</span> <span class="info-val">{device_info}</span></div>
            <div class="info-row"><span class="info-label">Location / Network:</span> <span class="info-val">{network_info}</span></div>
          </div>
          <p>If you did not authorize this activity, please contact your System Administrator immediately.</p>
          <div class="btn-container">
            <a href="{dashboard_url}/settings" class="btn">Review Active Sessions</a>
          </div>
        """,
        "text": """
Security Alert: New Sign-in Event ({event_type})

Hello {recipient_name},
We detected an authentication event on your account:
- Event: {event_type}
- Time: {event_time}
- IP Address: {ip_address}
- Device: {device_info}
- Network: {network_info}

Review sessions: {dashboard_url}/settings
        """.strip(),
    },
    "attendance_exception_alert": {
        "subject": "Attendance Exception Detected: {exception_title} ({work_date})",
        "badge_class": "badge-danger",
        "badge_text": "Attendance Exception",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>An attendance anomaly was flagged for employee <strong>{employee_name}</strong> ({employee_code}) on <strong>{work_date}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Anomaly:</span> <span class="info-val">{exception_title}</span></div>
            <div class="info-row"><span class="info-label">Recorded Status:</span> <span class="info-val">{recorded_status}</span></div>
            <div class="info-row"><span class="info-label">Network Verification:</span> <span class="info-val">{network_verification}</span></div>
            <div class="info-row"><span class="info-label">Details:</span> <span class="info-val">{exception_details}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/attendance" class="btn">View Attendance Record</a>
          </div>
        """,
        "text": """
Attendance Exception: {exception_title} ({work_date})
Employee: {employee_name} ({employee_code})
Status: {recorded_status}
Network Verification: {network_verification}
Details: {exception_details}

View: {dashboard_url}/attendance
        """.strip(),
    },
    "attendance_late_alert": {
        "subject": "Late Attendance Notification: {employee_name} ({work_date})",
        "badge_class": "badge-warning",
        "badge_text": "Late Arrival",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>Employee <strong>{employee_name}</strong> ({employee_code}) clocked in late on <strong>{work_date}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Scheduled Shift:</span> <span class="info-val">{scheduled_shift}</span></div>
            <div class="info-row"><span class="info-label">Actual Clock-In:</span> <span class="info-val">{actual_clock_in}</span></div>
            <div class="info-row"><span class="info-label">Late Duration:</span> <span class="info-val">{late_minutes} minutes</span></div>
            <div class="info-row"><span class="info-label">Grace Period:</span> <span class="info-val">{grace_minutes} minutes</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/attendance" class="btn">Review in Portal</a>
          </div>
        """,
        "text": """
Late Attendance Notification ({work_date})
Employee: {employee_name} ({employee_code})
Scheduled: {scheduled_shift}
Actual: {actual_clock_in}
Late: {late_minutes}m (Grace: {grace_minutes}m)

Portal: {dashboard_url}/attendance
        """.strip(),
    },
    "attendance_missing_alert": {
        "subject": "Missing Attendance Alert: {employee_name} ({work_date})",
        "badge_class": "badge-danger",
        "badge_text": "Missing Attendance",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>Employee <strong>{employee_name}</strong> ({employee_code}) has no recorded attendance for scheduled working day <strong>{work_date}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Shift:</span> <span class="info-val">{scheduled_shift}</span></div>
            <div class="info-row"><span class="info-label">Status:</span> <span class="info-val">UNEXCUSED ABSENCE</span></div>
            <div class="info-row"><span class="info-label">Department:</span> <span class="info-val">{department_name}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/attendance" class="btn">Inspect Shift Records</a>
          </div>
        """,
        "text": """
Missing Attendance Alert ({work_date})
Employee: {employee_name} ({employee_code})
Scheduled Shift: {scheduled_shift}
Status: UNEXCUSED ABSENCE
Department: {department_name}

Inspect: {dashboard_url}/attendance
        """.strip(),
    },
    "attendance_adjustment_requested": {
        "subject": "Attendance Correction Request: {employee_name} ({work_date})",
        "badge_class": "badge-warning",
        "badge_text": "Correction Pending",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>A manual attendance adjustment request has been submitted by <strong>{employee_name}</strong> for <strong>{work_date}</strong>.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Adjustment Type:</span> <span class="info-val">{adjustment_type}</span></div>
            <div class="info-row"><span class="info-label">Requested Shift:</span> <span class="info-val">{requested_shift}</span></div>
            <div class="info-row"><span class="info-label">Employee Reason:</span> <span class="info-val">{reason}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/attendance" class="btn">Review Adjustment Request</a>
          </div>
        """,
        "text": """
Attendance Correction Request ({work_date})
Employee: {employee_name}
Type: {adjustment_type}
Requested: {requested_shift}
Reason: {reason}

Review: {dashboard_url}/attendance
        """.strip(),
    },
    "attendance_adjustment_reviewed": {
        "subject": "Attendance Correction Decision: {decision_status} ({work_date})",
        "badge_class": "badge-primary",
        "badge_text": "Correction Decision",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>Your manual attendance correction request for <strong>{work_date}</strong> has been <strong>{decision_status}</strong> by {approver_name}.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Decision:</span> <span class="info-val">{decision_status}</span></div>
            <div class="info-row"><span class="info-label">Approver Remarks:</span> <span class="info-val">{remarks}</span></div>
            <div class="info-row"><span class="info-label">Updated Status:</span> <span class="info-val">{updated_status}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/attendance" class="btn">View Attendance Record</a>
          </div>
        """,
        "text": """
Attendance Correction Decision: {decision_status} ({work_date})
Decision: {decision_status}
Approver: {approver_name}
Remarks: {remarks}
Updated Status: {updated_status}

View: {dashboard_url}/attendance
        """.strip(),
    },
    "weekly_leave_report": {
        "subject": "Weekly Leave & Workforce Availability Digest ({week_range})",
        "badge_class": "badge-primary",
        "badge_text": "Weekly Leave Digest",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p>The weekly workforce leave utilization and upcoming absence digest for <strong>{week_range}</strong> is ready.</p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Total Leave Requests:</span> <span class="info-val">{total_leave_requests}</span></div>
            <div class="info-row"><span class="info-label">Approved Days:</span> <span class="info-val">{approved_leave_days}</span></div>
            <div class="info-row"><span class="info-label">Pending Approval:</span> <span class="info-val">{pending_leave_count}</span></div>
            <div class="info-row"><span class="info-label">Upcoming Absences:</span> <span class="info-val">{upcoming_absence_count}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/leave" class="btn">Open Leave Management</a>
          </div>
        """,
        "text": """
Weekly Leave Digest ({week_range})
- Requests: {total_leave_requests}
- Approved Days: {approved_leave_days}
- Pending: {pending_leave_count}
- Upcoming Absences: {upcoming_absence_count}

Portal: {dashboard_url}/leave
        """.strip(),
    },
    "system_critical_alert": {
        "subject": "CRITICAL ALERT: System Incident in {service_name} ({alert_time})",
        "badge_class": "badge-danger",
        "badge_text": "Critical Incident",
        "html": """
          <p>Hello <strong>{recipient_name}</strong>,</p>
          <p><strong style="color: #dc2626;">A critical enterprise platform event requires administrative attention.</strong></p>
          
          <div class="info-card">
            <div class="info-row"><span class="info-label">Service:</span> <span class="info-val">{service_name}</span></div>
            <div class="info-row"><span class="info-label">Severity:</span> <span class="info-val">{severity}</span></div>
            <div class="info-row"><span class="info-label">Timestamp:</span> <span class="info-val">{alert_time}</span></div>
            <div class="info-row"><span class="info-label">Error Details:</span> <span class="info-val">{error_details}</span></div>
          </div>
          
          <div class="btn-container">
            <a href="{dashboard_url}/audit-logs" class="btn">Inspect Audit Logs</a>
          </div>
        """,
        "text": """
CRITICAL ALERT: System Incident in {service_name}
Severity: {severity}
Time: {alert_time}
Details: {error_details}

Inspect: {dashboard_url}/audit-logs
        """.strip(),
    },
}


class TemplateRenderError(Exception):
    pass


def render_email_template(
    template_key: str,
    context: dict[str, Any],
) -> tuple[str, str, str]:
    """
    Renders an email template by key with provided contextual substitutions.
    Returns (subject, body_html, body_text).
    """
    if template_key not in TEMPLATES_CONFIG:
        raise TemplateRenderError(f"Email template '{template_key}' is not registered.")

    tmpl = TEMPLATES_CONFIG[template_key]

    # Defaults in context
    safe_ctx: dict[str, Any] = {
        "org_name": settings.PROJECT_NAME,
        "dashboard_url": settings.FRONTEND_BASE_URL.rstrip("/"),
        "year": "2026",
        "manager_note": "Approved per schedule",
        "rejection_reason": "Not specified",
        "temporary_password": "TempPass123!",
        "expires_minutes": 15,
        "otp_code": "N/A",
        **context,
    }

    # Sanitize string variables for HTML injection safety
    html_safe_ctx: dict[str, Any] = {}
    for k, v in safe_ctx.items():
        if isinstance(v, str):
            html_safe_ctx[k] = html.escape(v)
        else:
            html_safe_ctx[k] = v

    try:
        subject = tmpl["subject"].format(**safe_ctx)
    except KeyError as e:
        raise TemplateRenderError(f"Missing variable {e} for subject in template '{template_key}'")

    try:
        raw_body_html = tmpl["html"].format(**html_safe_ctx)
    except KeyError as e:
        raise TemplateRenderError(f"Missing variable {e} for HTML body in template '{template_key}'")

    try:
        body_text = tmpl["text"].format(**safe_ctx)
    except KeyError as e:
        raise TemplateRenderError(f"Missing variable {e} for text body in template '{template_key}'")

    body_html = BASE_HTML_WRAPPER.format(
        subject=subject,
        org_name=html_safe_ctx["org_name"],
        badge_class=tmpl["badge_class"],
        badge_text=tmpl["badge_text"],
        body_content=raw_body_html,
        year=safe_ctx["year"],
    )

    return subject, body_html, body_text
