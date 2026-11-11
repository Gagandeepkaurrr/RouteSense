"""Centralized application settings.

Environment variables override values from the backend .env file. The .env
file is resolved relative to this module, not the shell's working directory.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    DATABASE_URL: str
    OSRM_URL: str = "http://127.0.0.1:5001"
    GEOAPIFY_API_KEY: str | None = None
    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_FORECAST_MAX_DAYS: int = 16
    WEATHER_CACHE_TTL_SECONDS: int = 3600
    OSRM_CACHE_TTL_SECONDS: int = 604800

    # Comma-separated origins keep the environment variable simple to edit.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]


settings = Settings()
