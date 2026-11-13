# API Specification (v1)

## Overview
All API endpoints are prefixed with `/api/v1`. Authentication is conducted via standard OAuth2 Bearer Tokens (JWT).

Interactive Swagger documentation is available at `/api/v1/docs` when running the backend.

---

## 1. System Health

### 1.1 Liveness Probe
- **Method**: `GET /api/v1/health`
- **Auth**: None
- **Response**: `200 OK`
```json
{
  "status": "ok",
  "environment": "development",
  "version": "0.1.0",
  "timestamp": "2026-11-12T12:00:00.000Z"
}
```

### 1.2 Detailed Readiness Probe
- **Method**: `GET /api/v1/health/detailed`
- **Auth**: None
- **Response**: `200 OK` (or `503 Service Unavailable` if critical dependency is down)
```json
{
  "status": "healthy",
  "environment": "development",
  "version": "0.1.0",
  "timestamp": "2026-11-12T12:00:00.000Z",
  "uptime_seconds": 124.5,
  "database": {
    "status": "healthy",
    "latency_ms": 1.45,
    "database": "postgresql"
  },
  "redis": {
    "status": "healthy",
    "latency_ms": 0.82,
    "message": "PONG"
  },
  "celery": {
    "status": "healthy",
    "broker_status": "connected",
    "active_workers": 2
  }
}
```

---

## 2. Authentication

### 2.1 Register User
- **Method**: `POST /api/v1/auth/register`
- **Auth**: Bearer token for an Administrator. Non-superusers may only create users in their own organization and cannot set `is_superuser`.
- **Body**:
```json
{
  "email": "employee@example.com",
  "password": "Password123!",
  "full_name": "Jane Doe",
  "role": "employee",
  "department": "Engineering"
}
```

### 2.2 Token Exchange (OAuth2 Form)
- **Method**: `POST /api/v1/auth/token`
- **Content-Type**: `application/x-www-form-urlencoded`
- **Body**: `username=employee@example.com&password=Password123!`
- **Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer"
}
```

### 2.3 Current User Info
- **Method**: `GET /api/v1/auth/me`
- **Header**: `Authorization: Bearer <token>`

---

## 3. Attendance Management

### 3.1 Clock In
- **Method**: `POST /api/v1/attendance/clock-in`
- **Header**: `Authorization: Bearer <token>`
- **Body**: `{"notes": "Starting shift from remote office"}`

### 3.2 Clock Out
- **Method**: `POST /api/v1/attendance/clock-out`
- **Header**: `Authorization: Bearer <token>`
- **Body**: `{"notes": "End of shift"}`

### 3.3 Shift History
- **Method**: `GET /api/v1/attendance/history?limit=30`
- **Header**: `Authorization: Bearer <token>`

---

## 4. Computer Activity Telemetry

### 4.1 Sync Activity Batch
- **Method**: `POST /api/v1/activity/sync`
- **Header**: `Authorization: Bearer <token>`
- **Body**:
```json
{
  "logs": [
    {
      "timestamp": "2026-11-12T12:00:00.000Z",
      "application_name": "Visual Studio Code",
      "window_title": "app.py - enterprise",
      "duration_seconds": 60,
      "idle_seconds": 0,
      "keystrokes_count": 85,
      "mouse_clicks_count": 22
    }
  ]
}
```

---

## 5. Leave Management

### 5.1 Submit Leave Request
- **Method**: `POST /api/v1/leave/`
- **Header**: `Authorization: Bearer <token>`
- **Body**:
```json
{
  "leave_type": "annual",
  "start_date": "2026-12-20",
  "end_date": "2026-12-24",
  "days_count": 5,
  "reason": "Annual family vacation"
}
```

### 5.2 List My Leave Requests
- **Method**: `GET /api/v1/leave/`
- **Header**: `Authorization: Bearer <token>`

