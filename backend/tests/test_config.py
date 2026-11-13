"""
Unit tests for configuration and environment settings
"""

from app.core.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.PROJECT_NAME == "Enterprise Attendance & Activity Platform"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0


def test_cors_origins_parsing():
    settings = Settings(BACKEND_CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"])
    assert "http://localhost:3000" in settings.BACKEND_CORS_ORIGINS
    assert "http://localhost:8000" in settings.BACKEND_CORS_ORIGINS


def test_database_url_generation():
    settings = Settings(
        DATABASE_URL=None,
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="testpass",
        POSTGRES_SERVER="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="testdb",
    )
    async_url = settings.get_async_database_url()
    assert "postgresql+asyncpg://" in async_url
    assert "testuser:testpass@localhost:5432/testdb" in async_url
