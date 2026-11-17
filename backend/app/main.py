"""
FastAPI Main Application Entrypoint
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.redis import close_redis_client
from app.middleware.security_headers import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Keep org leave policy and trusted office Wi-Fi SSIDs in sync.
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.core.seeds import seed_organization_leave_types, seed_organization_office_wifi
        from app.models.organization import Organization

        async with AsyncSessionLocal() as db:
            orgs = (await db.execute(select(Organization))).scalars().all()
            for org in orgs:
                await seed_organization_leave_types(db, org.id)
                await seed_organization_office_wifi(db, org.id)
            await db.commit()
    except Exception:
        # Never block API startup if policy sync fails (e.g. migrations pending).
        pass

    yield
    await close_redis_client()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# Security Headers
app.add_middleware(SecurityHeadersMiddleware)

# Set CORS middleware (FRONTEND_BASE_URL is always included so portal host stays allowed)
_cors_origins = settings.get_cors_origins()
if _cors_origins or settings.BACKEND_CORS_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=settings.BACKEND_CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs_url": f"{settings.API_V1_STR}/docs",
        "health_url": f"{settings.API_V1_STR}/health",
    }


@app.get("/health", tags=["Root"])
async def top_level_health():
    from app.api.v1.endpoints.health import liveness_probe
    return await liveness_probe()
