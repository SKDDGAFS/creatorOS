from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import service_error_handler
from app.api.router import api_router
from app.core.config import get_settings
from app.services.errors import ServiceError


def create_application() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.application_name,
        description="AI Operating System for Creators",
        version="0.1.0",
        debug=settings.debug,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(ServiceError, service_error_handler)

    @application.get("/")
    def home() -> dict[str, str]:
        return {"message": "CreatorOS Brain is online \U0001f9e0"}

    application.include_router(api_router)
    return application


app = create_application()
