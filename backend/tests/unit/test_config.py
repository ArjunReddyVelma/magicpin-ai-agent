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
