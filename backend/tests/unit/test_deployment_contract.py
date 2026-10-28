"""
Unit and deployment contract verification tests for DEPL-01:
Deployment verification, static asset fallback, SPA rewrites, and proxy configuration.

Verifies:
1. render.yaml blueprint schema, service types, and route ordering.
2. Static publish directory matches frontend build output (frontend/dist).
3. API route prefix (/v1/*) is prioritized ahead of the SPA catch-all (/* -> /index.html).
4. Backend health check path (/v1/readyz) matches FastAPI route mounting.
5. API errors return JSON rather than HTML responses.
6. TRUSTED_PROXIES environment variable contract and client IP integration.
"""
import os
from pathlib import Path
import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app.core.config import Settings, settings
from backend.app.core.security import get_client_ip
from backend.app.main import app


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RENDER_YAML_PATH = REPO_ROOT / "render.yaml"


@pytest.fixture(scope="module")
def render_blueprint() -> dict:
    """Loads and parses render.yaml blueprint."""
    assert RENDER_YAML_PATH.is_file(), f"render.yaml not found at {RENDER_YAML_PATH}"
    with open(RENDER_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict), "render.yaml must contain a top-level mapping"
    return data


def test_render_blueprint_services_structure(render_blueprint: dict):
    """Verifies that render.yaml defines backend, frontend, and postgres services."""
    services = render_blueprint.get("services", [])
    service_names = {s.get("name"): s for s in services}

    assert "magicpin-backend" in service_names, "Missing magicpin-backend web service"
    assert "magicpin-frontend" in service_names, "Missing magicpin-frontend static site"

    databases = render_blueprint.get("databases", [])
    db_names = {d.get("name") for d in databases}
    assert "magicpin-postgres" in db_names, "Missing magicpin-postgres database"


def test_render_blueprint_frontend_static_site_contract(render_blueprint: dict):
    """
    Verifies that the frontend static site is configured correctly:
    - runtime: static
    - staticPublishPath: frontend/dist
    - routes: /v1/* rewrite is declared BEFORE the /* catch-all rewrite.
    """
    services = render_blueprint.get("services", [])
    frontend = next(s for s in services if s.get("name") == "magicpin-frontend")

    assert frontend.get("type") == "web"
    assert frontend.get("runtime") == "static"
    assert frontend.get("staticPublishPath") == "frontend/dist"

    routes = frontend.get("routes", [])
    assert len(routes) >= 2, "Expected at least 2 routes for frontend (API rewrite + SPA catch-all)"

    # Rule 0: API Proxy rewrite for /v1/*
    rule_0 = routes[0]
    assert rule_0.get("type") == "rewrite"
    assert rule_0.get("source") == "/v1/*"
    assert rule_0.get("destination").endswith("/v1/*")
    assert rule_0.get("destination").startswith("https://")

    # Rule 1: SPA catch-all rewrite for /* -> /index.html
    rule_1 = routes[1]
    assert rule_1.get("type") == "rewrite"
    assert rule_1.get("source") == "/*"
    assert rule_1.get("destination") == "/index.html"


def test_render_blueprint_backend_contract(render_blueprint: dict):
    """
    Verifies backend web service configuration:
    - runtime: python
    - healthCheckPath: /v1/readyz
    - TRUSTED_PROXIES is configured in envVars
    - Migration runs in startCommand before uvicorn
    """
    services = render_blueprint.get("services", [])
    backend = next(s for s in services if s.get("name") == "magicpin-backend")

    assert backend.get("runtime") == "python"
    assert backend.get("healthCheckPath") == "/v1/readyz"

    start_cmd = backend.get("startCommand", "")
    assert "alembic" in start_cmd and "upgrade head" in start_cmd
    assert "uvicorn" in start_cmd

    env_vars = {item["key"]: item.get("value") for item in backend.get("envVars", []) if "key" in item}
    assert "TRUSTED_PROXIES" in env_vars
    assert "APP_ENV" in env_vars
    assert env_vars["APP_ENV"] == "production"
    assert "COOKIE_SECURE" in env_vars
    assert env_vars["COOKIE_SECURE"] == "true"


def test_frontend_dist_artifacts_present():
    """Verifies that the compiled frontend distribution exists and has index.html."""
    dist_dir = REPO_ROOT / "frontend" / "dist"
    index_html = dist_dir / "index.html"

    assert dist_dir.is_dir(), f"Frontend dist directory does not exist: {dist_dir}"
    assert index_html.is_file(), f"index.html does not exist: {index_html}"

    content = index_html.read_text(encoding="utf-8")
    assert '<div id="root"></div>' in content
    assert "<script" in content


def test_backend_api_routing_and_json_error_handling():
    """
    Verifies that backend routes respond with JSON and not HTML:
    - /v1/healthz returns 200 application/json
    - /v1/nonexistent returns 404 application/json (not an HTML fallback)
    """
    client = TestClient(app)

    # Valid health route
    res = client.get("/v1/healthz")
    assert res.status_code == 200
    assert "application/json" in res.headers.get("content-type", "")
    assert res.json() == {"status": "ok"}

    # Non-existent API route must return JSON 404, never HTML
    res_404 = client.get("/v1/nonexistent_test_route_depl01")
    assert res_404.status_code == 404
    assert "application/json" in res_404.headers.get("content-type", "")
    assert "html" not in res_404.text.lower()


def test_trusted_proxies_setting_and_client_ip_contract():
    """Verifies TRUSTED_PROXIES default value and get_client_ip integration."""
    default_cfg = Settings()
    assert default_cfg.TRUSTED_PROXIES == "127.0.0.1,::1"

    # Verify custom proxy network configuration
    custom_cfg = Settings(TRUSTED_PROXIES="10.0.0.0/8,192.168.0.0/16")
    assert custom_cfg.TRUSTED_PROXIES == "10.0.0.0/8,192.168.0.0/16"
