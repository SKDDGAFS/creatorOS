from fastapi import APIRouter

from app.api.routes.agent_runs import router as agent_runs_router
from app.api.routes.ai import router as ai_router
from app.api.routes.analytics_sync import router as analytics_sync_router
from app.api.routes.auth import router as auth_router
from app.api.routes.channels import router as channels_router
from app.api.routes.growth_signals import router as growth_signals_router
from app.api.routes.health import router as health_router
from app.api.routes.integrations import router as integrations_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.publishing import router as publishing_router
from app.api.routes.research import router as research_router
from app.api.routes.videos import router as videos_router
from app.api.routes.workspaces import router as workspaces_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(agent_runs_router)
api_router.include_router(ai_router)
api_router.include_router(analytics_sync_router)
api_router.include_router(growth_signals_router)
api_router.include_router(jobs_router)
api_router.include_router(integrations_router)
api_router.include_router(publishing_router)
api_router.include_router(research_router)
api_router.include_router(channels_router)
api_router.include_router(videos_router)
