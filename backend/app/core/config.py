import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # LLM Settings
    LLM_PROVIDER: str = "groq"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_MAX_RETRIES: int = 2

    # Frontend & CORS
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    # Sessions & Cookies
    SESSION_TTL_MINUTES: int = 1440
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_NAME: str = "mp_session"

    # Observability
    LOG_LEVEL: str = "INFO"

    @property
    def cors_origins(self) -> List[str]:
        origins = [self.FRONTEND_ORIGIN]
        if self.APP_ENV == "development":
            origins.extend([
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
            ])
        return list(set(origins))


settings = Settings()
