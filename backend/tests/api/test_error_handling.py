import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from backend.app.main import app


# Router to trigger intentional unexpected exceptions
error_test_router = APIRouter()


@error_test_router.get("/v1/test/unhandled-error")
def trigger_unhandled_error():
    raise RuntimeError("Intentional secret database crash failure details should not leak")


# Register route for testing
app.include_router(error_test_router)


def test_unhandled_exception_returns_clean_500():
    """
    Verifies that an unhandled Exception produces a structured 500 JSON response
    conforming to the API standard without leaking stack traces or internal messages.
    """
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/v1/test/unhandled-error")
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert data["error"]["message"] == "An unexpected server error occurred. Please try again later."
    # Ensure sensitive runtime error message is not in response body
    assert "Intentional secret database crash" not in response.text
    assert "Traceback" not in response.text


def test_http_exceptions_still_handled_normally(client: TestClient):
    """
    Verifies that normal HTTPExceptions are handled and not swallowed by the global Exception handler.
    """
    # Calling unauthenticated endpoint raises 401 HTTPException
    response = client.get("/v1/merchant/profile")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_validation_errors_still_handled_normally(client: TestClient):
    """
    Verifies that RequestValidationErrors (422) continue to return structured VALIDATION_ERROR.
    """
    response = client.post("/v1/auth/register", json={"invalid": "payload"})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_cors_preflight_and_origin_handling(client: TestClient):
    """
    Verifies that CORS headers respond correctly to normalized frontend origins.
    """
    response = client.options(
        "/v1/healthz",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
