from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="Magicpin AI Agent",
    version="1.0.0"
)

app.include_router(router)


@app.get("/")
def home():
    return {
        "message": "Magicpin AI Agent is running!"
    }


@app.get("/v1/healthz")
def health():
    return {
        "status": "healthy"
    }