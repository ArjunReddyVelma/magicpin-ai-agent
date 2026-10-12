from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from backend.app.schemas.health import HealthzResponse, ReadyzResponse, ErrorResponse
from backend.app.db.session import check_database_connection

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
def readyz() -> Response:
    """
    Readiness probe executing SELECT 1 against PostgreSQL to verify connectivity.
    """
    is_db_ready = check_database_connection()
    if not is_db_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": "Required database dependency is unavailable",
                }
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready", "checks": {"database": "ok"}},
    )
