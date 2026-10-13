from backend.app.core.config import Settings


def test_default_settings():
    settings = Settings()
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

