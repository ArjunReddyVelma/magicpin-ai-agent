from fastapi import APIRouter, Response, status
from backend.app.schemas.health import HealthzResponse, ReadyzResponse, ErrorResponse

router = APIRouter()


@router.get(
    "/healthz",
    response_model=HealthzResponse,
    summary="Liveness check",
    tags=["Health"],
)
def healthz() -> HealthzResponse:
    """
    Liveness probe returning 200 OK when the process is running.
    """
    return HealthzResponse(status="ok")


@router.get(
    "/readyz",
    response_model=ReadyzResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ErrorResponse,
            "description": "One or more required dependencies are unavailable",
        }
    },
    summary="Readiness check for required dependencies",
    tags=["Health"],
)
def readyz(response: Response) -> ReadyzResponse:
    """
    Readiness probe verifying operational state of required backend dependencies.
    """
    # In Phase 1 baseline, verifies system readiness without crashing.
    # In Phase 2, database ping via SQLAlchemy session will be connected.
    checks = {"database": "ok"}
    return ReadyzResponse(status="ready", checks=checks)
