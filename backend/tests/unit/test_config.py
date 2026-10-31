import pytest
from backend.app.core.config import Settings, normalize_database_url
from backend.app.db.session import engine


def test_default_settings():
    settings = Settings(_env_file=None)
    assert settings.APP_NAME == "Magicpin AI Agent"
    assert settings.API_V1_STR == "/v1"
    assert settings.LLM_PROVIDER == "groq"
    assert settings.SESSION_TTL_MINUTES > 0
    assert "http://localhost:5173" in settings.cors_origins


def test_cors_origins_includes_frontend():
    custom = Settings(FRONTEND_ORIGIN="http://merchant.magicpin.com")
    assert "http://merchant.magicpin.com" in custom.cors_origins


def test_database_url_normalization():
    # Render postgres:// format
    render_style = Settings(DATABASE_URL="postgres://user:pass@host:5432/db")
    assert render_style.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db"

    # Standard postgresql:// format without dialect
    standard = Settings(DATABASE_URL="postgresql://user:pass@host:5432/db")
    assert standard.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db"

    # Explicit psycopg dialect preserved
    explicit = Settings(DATABASE_URL="postgresql+psycopg://user:pass@host:5432/db")
    assert explicit.DATABASE_URL == "postgresql+psycopg://user:pass@host:5432/db"


def test_frontend_origin_normalization_bare_hostname():
    cfg = Settings(FRONTEND_ORIGIN="magicpin-frontend.onrender.com")
    assert "https://magicpin-frontend.onrender.com" in cfg.cors_origins


def test_frontend_origin_normalization_trailing_slash():
    cfg = Settings(FRONTEND_ORIGIN="https://merchant.magicpin.com/")
    assert "https://merchant.magicpin.com" in cfg.cors_origins


def test_frontend_origin_normalization_localhost():
    cfg = Settings(FRONTEND_ORIGIN="localhost:3000")
    assert "http://localhost:3000" in cfg.cors_origins


def test_frontend_origin_multiple_comma_separated():
    cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="a" * 32,
        CSRF_SECRET="b" * 32,
        LLM_PROVIDER="mock",
        FRONTEND_ORIGIN="magicpin-frontend.onrender.com, https://custom-merchant.com/",
    )
    assert cfg.cors_origins == [
        "https://magicpin-frontend.onrender.com",
        "https://custom-merchant.com",
    ]


def test_production_configuration_valid():
    cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="c" * 32,
        CSRF_SECRET="d" * 32,
        LLM_PROVIDER="groq",
        LLM_API_KEY="gsk_valid_api_key_for_production",
    )
    assert cfg.APP_ENV == "production"
    assert cfg.SECRET_KEY == "c" * 32


def test_production_configuration_mock_provider_allows_empty_key():
    cfg = Settings(
        APP_ENV="production",
        SECRET_KEY="e" * 32,
        CSRF_SECRET="f" * 32,
        LLM_PROVIDER="mock",
        LLM_API_KEY="",
    )
    assert cfg.APP_ENV == "production"
    assert cfg.LLM_PROVIDER == "mock"


def test_production_configuration_rejects_insecure_secret_key():
    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure string"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="insecure-development-secret-key-change-in-production",
            CSRF_SECRET="g" * 32,
            LLM_PROVIDER="mock",
        )

    with pytest.raises(ValueError, match="SECRET_KEY must be a cryptographically secure string"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="short-secret",
            CSRF_SECRET="g" * 32,
            LLM_PROVIDER="mock",
        )


def test_production_configuration_rejects_insecure_csrf_secret():
    with pytest.raises(ValueError, match="CSRF_SECRET must be a cryptographically secure string"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="h" * 32,
            CSRF_SECRET="insecure-development-csrf-secret-change-in-production",
            LLM_PROVIDER="mock",
        )


def test_production_configuration_rejects_missing_llm_key_for_groq():
    with pytest.raises(ValueError, match="LLM_API_KEY is required in production"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="i" * 32,
            CSRF_SECRET="j" * 32,
            LLM_PROVIDER="groq",
            LLM_API_KEY="",
        )


def test_database_engine_pool_recycle_configured():
    assert engine.pool._recycle == 300


def test_alembic_normalize_db_url():
    assert normalize_database_url("postgres://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url("postgresql://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url("postgresql+psycopg://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"


def test_llm_api_key_alias_support(monkeypatch):
    """Verifies that GROQ_API_KEY is accepted as a backward-compatible alias when LLM_API_KEY is unset."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_from_groq_alias_env")
    cfg = Settings(_env_file=None)
    assert cfg.LLM_API_KEY == "gsk_from_groq_alias_env"

    # Direct LLM_API_KEY takes precedence
    monkeypatch.setenv("LLM_API_KEY", "gsk_direct_canonical_env")
    cfg2 = Settings(_env_file=None)
    assert cfg2.LLM_API_KEY == "gsk_direct_canonical_env"
