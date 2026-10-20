import os
import urllib.parse
from typing import List
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(v: str) -> str:
    """Normalizes Postgres connection URLs to the psycopg driver dialect (postgresql+psycopg://)."""
    if isinstance(v, str):
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+psycopg://"):
            return v.replace("postgresql://", "postgresql+psycopg://", 1)
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_NAME: str = "Magicpin AI Agent"
    API_V1_STR: str = "/v1"
    SECRET_KEY: str = "insecure-development-secret-key-change-in-production"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent"
    DATABASE_URL_TEST: str = "postgresql+psycopg://reddy@localhost:5432/magicpin_ai_agent_test"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        return normalize_database_url(v)

    # LLM Settings
    LLM_PROVIDER: str = "groq"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_MAX_RETRIES: int = 2

    # Frontend & CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    @classmethod
    def _normalize_single_origin(cls, origin: str) -> str:
        s = origin.strip().rstrip("/")
        if not s:
            return ""
        if not s.startswith(("http://", "https://")):
            if s.startswith("localhost") or s.startswith("127.0.0.1"):
                s = f"http://{s}"
            else:
                s = f"https://{s}"
        parsed = urllib.parse.urlparse(s)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return s

    @field_validator("FRONTEND_ORIGIN", mode="before")
    @classmethod
    def normalize_frontend_origin(cls, v: str) -> str:
        if isinstance(v, str):
            parts = [cls._normalize_single_origin(part) for part in v.split(",") if part.strip()]
            valid_parts = [p for p in parts if p]
            return ",".join(valid_parts) if valid_parts else "http://localhost:5173"
        return v

    # Sessions & Cookies
    SESSION_TTL_MINUTES: int = 10080  # 7 days
    CSRF_SECRET: str = "insecure-development-csrf-secret-change-in-production"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_NAME: str = "mp_session"
    RATE_LIMIT_LOGIN_MAX_ATTEMPTS: int = 5
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 900

    # Observability
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins(self) -> List[str]:
        origins = [o.strip() for o in self.FRONTEND_ORIGIN.split(",") if o.strip()]
        if self.APP_ENV == "development":
            origins.extend([
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
            ])
        return list(dict.fromkeys(origins))

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "Settings":
        if self.APP_ENV == "production":
            insecure_markers = [
                "insecure",
                "change-in-production",
                "change-this-in-production",
            ]
            if (
                not self.SECRET_KEY
                or len(self.SECRET_KEY) < 32
                or any(m in self.SECRET_KEY.lower() for m in insecure_markers)
            ):
                raise ValueError(
                    "SECRET_KEY must be a cryptographically secure string of at least 32 characters in production."
                )

            if (
                not self.CSRF_SECRET
                or len(self.CSRF_SECRET) < 32
                or any(m in self.CSRF_SECRET.lower() for m in insecure_markers)
            ):
                raise ValueError(
                    "CSRF_SECRET must be a cryptographically secure string of at least 32 characters in production."
                )

            if self.LLM_PROVIDER != "mock":
                if not self.LLM_API_KEY or self.LLM_API_KEY.strip() in ("", "your_groq_api_key_here"):
                    raise ValueError(
                        f"LLM_API_KEY is required in production when LLM_PROVIDER is '{self.LLM_PROVIDER}'."
                    )
        return self


settings = Settings()
