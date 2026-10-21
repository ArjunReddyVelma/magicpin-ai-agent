from fastapi import APIRouter
from backend.app.api.v1.routes import health, auth, merchant, context, conversations, actions, whatsapp

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(merchant.router)
api_router.include_router(context.router)
api_router.include_router(conversations.router)
api_router.include_router(actions.router)
api_router.include_router(whatsapp.router)


