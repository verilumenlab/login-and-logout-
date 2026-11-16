"""
Core Application Configuration
Uses pydantic-settings to load environment variables and provide type-safe settings.
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _with_driver(url: str, driver: str) -> str:
    """Render/Heroku give postgres:// or postgresql:// URLs; SQLAlchemy needs an explicit driver."""
    for prefix in ("postgres://", "postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return f"postgresql+{driver}://" + url[len(prefix):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Project Info
    PROJECT_NAME: str = "Enterprise Attendance & Activity Platform"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = "default-insecure-secret-key-change-me-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "attendance_db"
    DATABASE_URL: str | None = None
    SYNC_DATABASE_URL: str | None = None

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_URL: str | None = None

    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ]
    # Optional regex for extra browser origins, e.g. Netlify deploy previews:
    # ^https://([a-z0-9-]+--)?my-site\.netlify\.app$
    BACKEND_CORS_ORIGIN_REGEX: str | None = None

    # Email & Notification Settings (Phase 12)
    EMAIL_PROVIDER: str = "console"  # "console", "smtp", "resend"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False
    SMTP_SSL: bool = False
    RESEND_API_KEY: str = ""
    DEFAULT_FROM_EMAIL: str = "noreply@enterprise.corp"
    DEFAULT_FROM_NAME: str = "Enterprise Platform Notifications"
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    EMAIL_MAX_RETRIES: int = 3
    EMAIL_RETRY_BACKOFF_SECONDS: int = 60
    # Fixed weekly digest recipients (comma-separated). Both get the full org Excel.
    WEEKLY_REPORT_HR_EMAILS: str = "satish@verilumen.ai"
    WEEKLY_REPORT_MANAGER_EMAILS: str = "kp@verilumen.ai"

    # Employee Application Release Management (Electron / Windows)
    RELEASE_STORAGE_DIR: str = "storage/releases"
    RELEASE_CI_TOKEN: str = "change-me-release-ci-token-min-32-chars"
    RELEASE_DEFAULT_CHANNEL: str = "staging"
    RELEASE_MAX_UPLOAD_BYTES: int = 262144000  # 250 MB
    FRONTEND_UPDATE_FEED_BASE_URL: str = "http://localhost:8000/api/v1/updates/windows"

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            import json

            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return v if isinstance(v, list) else []

    def get_async_database_url(self) -> str:
        """Returns the async database URL, defaulting to postgresql+asyncpg or sqlite+aiosqlite."""
        if self.DATABASE_URL:
            return _with_driver(self.DATABASE_URL, "asyncpg")
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_sync_database_url(self) -> str:
        """Returns sync database URL for migrations."""
        if self.SYNC_DATABASE_URL:
            return self.SYNC_DATABASE_URL
        if self.DATABASE_URL and self.DATABASE_URL.startswith("sqlite"):
            return self.DATABASE_URL.replace("sqlite+aiosqlite://", "sqlite://")
        if self.DATABASE_URL:
            return _with_driver(self.DATABASE_URL, "psycopg2")
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def get_cors_origins(self) -> list[str]:
        """CORS allowlist: explicit origins plus FRONTEND_BASE_URL (portal host)."""
        origins = list(self.BACKEND_CORS_ORIGINS or [])
        frontend = (self.FRONTEND_BASE_URL or "").strip().rstrip("/")
        if frontend and frontend not in origins:
            origins.append(frontend)
        return origins


settings = Settings()
