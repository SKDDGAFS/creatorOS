from fastapi import APIRouter

from app.api.routes.channels import router as channels_router
from app.api.routes.health import router as health_router
from app.api.routes.local import router as local_router
from app.api.routes.scheduled_posts import router as scheduled_posts_router
from app.api.routes.videos import router as videos_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(local_router)
api_router.include_router(scheduled_posts_router)
api_router.include_router(channels_router)
api_router.include_router(videos_router)
