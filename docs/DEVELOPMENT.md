# Developer Setup & Contribution Guide

This guide covers setting up and running all services locally for development.

---

## 1. Prerequisites

Ensure the following tools are installed:
- **Python**: 3.12+
- **Node.js**: 20+ (with npm)
- **Rust & Cargo**: (For desktop Tauri 2 development)
- **Docker & Docker Compose**: (For PostgreSQL and Redis container runtime)

---

## 2. Environment Configuration

Copy the example configuration to `.env`:

```bash
cp .env.example .env
```

Review `.env` and configure your local parameters. By default, credentials and ports match local container defaults.

---

## 3. Backend Setup (FastAPI & Celery)

### 3.1 Create and Activate Virtual Environment

```bash
# Windows (PowerShell)
python -m venv backend/.venv
backend\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv backend/.venv
source backend/.venv/bin/activate
```

### 3.2 Install Dependencies

```bash
pip install -r backend/requirements-dev.txt
```

### 3.3 Database Migrations

Run Alembic migrations to apply the initial schema:

```bash
cd backend
alembic upgrade head
```

### 3.4 Run the Backend Server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API Base URL: `http://localhost:8000/api/v1`
- Swagger Docs: `http://localhost:8000/api/v1/docs`
- Health Probe: `http://localhost:8000/api/v1/health`

### 3.5 Run Celery Worker

```bash
cd backend
celery -A app.core.celery_app.celery_app worker --loglevel=info
```

---

## 4. Web Frontend Setup (Next.js)

```bash
cd web
npm install
npm run dev
```

- Web Dashboard: `http://localhost:3000`
- System Health Page: `http://localhost:3000/health`

---

## 5. Desktop Client Setup (Tauri 2 + React)

```bash
cd desktop
npm install
npm run dev      # Runs React frontend in Vite dev mode
npm run tauri dev # Runs Tauri 2 native desktop client
```

---

## 6. Docker Compose Orchestration

To run PostgreSQL, Redis, Backend, Celery, and Web simultaneously:

```bash
cd infrastructure
docker compose up -d --build
```

To stop containers:

```bash
cd infrastructure
docker compose down
```

---

## 7. Testing, Linting & Type Checking

### Backend Tests
```bash
backend\.venv\Scripts\pytest -v backend/tests
```

### Backend Linting and Formatting (Ruff)
```bash
backend\.venv\Scripts\ruff check backend
backend\.venv\Scripts\ruff format backend
```

### Backend Type Checking (Mypy)
```bash
backend\.venv\Scripts\mypy --config-file backend/pyproject.toml backend/app
```

### Web Type Checking & Build
```bash
cd web
npm run type-check
npm run build
```

### Desktop Type Checking & Build
```bash
cd desktop
npm run build
```

