from fastapi import APIRouter

from app.api.routes.channels import router as channels_router
from app.api.routes.health import router as health_router
from app.api.routes.videos import router as videos_router


api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(channels_router)
api_router.include_router(videos_router)
