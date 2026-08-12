from fastapi import FastAPI
from api.routes import router
from config import GROQ_API_KEY


app = FastAPI(
    title="Magicpin AI Agent",
    version="1.0.0",
)

app.include_router(router)


@app.get("/")
def home():
    return {
        "message": "Magicpin AI Agent is running!"
    }


@app.get("/v1/healthz")
def health():
    """
    Liveness check.

    Confirms that the application process is running.
    """
    return {
        "status": "healthy"
    }


@app.get("/v1/readyz")
def readiness():
    """
    Readiness check.

    Confirms that required runtime configuration is available.
    """
    if not GROQ_API_KEY:
        return {
            "status": "not_ready",
            "reason": "LLM configuration is missing.",
        }

    return {
        "status": "ready"
    }