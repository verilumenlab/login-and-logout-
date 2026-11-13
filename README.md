# Enterprise Employee Attendance, Computer Activity Tracking & Leave Management Platform

[![CI Pipeline](https://github.com/enterprise/attendance-platform/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14+-000000.svg?logo=next.js&logoColor=white)](https://nextjs.org)
[![Tauri](https://img.shields.io/badge/Tauri-2.0-24C8D8.svg?logo=tauri&logoColor=white)](https://tauri.app)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg?logo=redis&logoColor=white)](https://redis.io)

An enterprise-grade, high-concurrency workforce management platform featuring real-time attendance logging, native cross-platform desktop computer activity telemetry, multi-tier leave approval workflows, and Celery asynchronous background processing.

---

## 1. Monorepo Architecture

```
.
├── backend/                  # Python FastAPI Backend
│   ├── app/                  # Application core, models, schemas, endpoints, tasks
│   ├── alembic/              # Database migration scripts
│   ├── tests/                # Pytest unit & integration test suite
│   ├── pyproject.toml        # Ruff, mypy, pytest configuration
│   └── requirements.txt      # Production & development dependencies
├── web/                      # Next.js 14 Web Frontend
│   ├── src/app/              # Next.js App Router (Dashboard, Health, API)
│   ├── src/lib/              # Type-safe API client
│   └── package.json          # Dependencies & build scripts
├── desktop/                  # Tauri 2 Cross-Platform Desktop Agent
│   ├── src/                  # React & TypeScript desktop UI
│   ├── src-tauri/            # Rust native backend, capabilities & bindings
│   └── package.json          # Vite & Tauri CLI configuration
├── infrastructure/           # Docker & Deployment
│   ├── docker/               # Multi-stage production Dockerfiles
│   ├── init-db/              # Initial SQL schemas and extension setup
│   ├── docker-compose.yml    # Full stack production orchestration
│   └── docker-compose.dev.yml# Local development with hot reloading
├── docs/                     # Architecture & Engineering Documentation
│   ├── ARCHITECTURE.md       # High-level architecture & component diagram
│   ├── DEVELOPMENT.md        # Local environment and developer workflow
│   ├── DATABASE_SCHEMA.md    # ER diagrams, indexes, and table definitions
│   └── API_SPECIFICATION.md  # Detailed OpenAPI / REST documentation
├── .github/workflows/        # GitHub Actions CI Matrix
│   └── ci.yml
├── .env.example              # Canonical environment template
└── README.md
```

---

## 2. Quickstart & Local Setup

### Prerequisites
- Python 3.12+
- Node.js 20+ (with npm)
- Docker & Docker Compose (optional for local containerized runtime)

### 2.1 Clone and Configure Environment

```bash
cp .env.example .env
```

### 2.2 Run with Docker Compose (Recommended)

Start PostgreSQL, Redis, Backend, Celery Worker, Celery Beat, and Next.js Web:

```bash
cd infrastructure
docker compose up -d --build
```

- Web Portal: [http://localhost:3000](http://localhost:3000)
- Backend API Docs: [http://localhost:8000/api/v1/docs](http://localhost:8000/api/v1/docs)
- Health Probe: [http://localhost:8000/api/v1/health/detailed](http://localhost:8000/api/v1/health/detailed)

### 2.3 Run Locally Without Docker

#### Backend:
```bash
# Set up virtual environment
python -m venv backend/.venv
backend\.venv\Scripts\activate   # Windows
# source backend/.venv/bin/activate # Linux / macOS

# Install dependencies
pip install -r backend/requirements-dev.txt

# Run migrations (when PostgreSQL is running)
cd backend
alembic upgrade head

# Start API server
uvicorn app.main:app --reload --port 8000
```

#### Web Frontend:
```bash
cd web
npm install
npm run dev
```

#### Desktop Agent:
```bash
cd desktop
npm install
npm run dev
```

---

## 3. Health Checks & Verification

| Endpoint | Method | Purpose | Response |
| :--- | :--- | :--- | :--- |
| `/api/v1/health` | GET | Liveness probe for load balancers & orchestrators | `{"status": "ok", ...}` |
| `/api/v1/health/detailed` | GET | Readiness probe inspecting PostgreSQL, Redis & Celery | `{"status": "healthy", ...}` |
| `/api/health` | GET | Next.js internal service health probe | `{"status": "ok", ...}` |

---

## 4. Linting, Formatting, Type Checking & Tests

Run all automated checks locally:

```bash
# Backend Tests (10/10 passing)
backend\.venv\Scripts\pytest -v backend/tests

# Backend Linting & Formatting (Ruff)
backend\.venv\Scripts\ruff check backend
backend\.venv\Scripts\ruff format backend

# Backend Static Type Checking (Mypy)
backend\.venv\Scripts\mypy --config-file backend/pyproject.toml backend/app

# Web Production Build & Type Checking (Next.js)
cd web
npm run type-check
npm run build

# Desktop Build & Type Checking (Tauri / React / Vite)
cd desktop
npm run build
```

---

## 5. Phase 01 Completion Verification

- [x] Python 3.12 Virtual environment configured (`backend/.venv`)
- [x] FastAPI application configured with modular APIRouter
- [x] PostgreSQL & SQLAlchemy 2.0 Async engine configured with connection pooling
- [x] Alembic migrations configured (`alembic/versions/0001_initial_schema.py`)
- [x] Redis and Celery background task queues configured
- [x] Next.js 14 App Router, TypeScript, and TailwindCSS configured
- [x] Tauri 2 configuration created for Windows and macOS
- [x] Multi-stage Docker Compose orchestration configured
- [x] Linting (Ruff, ESLint), formatting, and type-checking (Mypy, `tsc`) configured
- [x] GitHub Actions CI workflow configured (`.github/workflows/ci.yml`)
- [x] `.env.example` created with enterprise configuration parameters
- [x] Liveness (`/api/v1/health`) and Readiness (`/api/v1/health/detailed`) health checks configured
- [x] Architectural and API documentation provided in `docs/`

