from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import AuthContext, get_auth_context, require_csrf
from app.api.errors import raise_service_http_error
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services import auth_service
from app.services.errors import ServiceError

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_hours * 60 * 60
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    try:
        user, _workspace = auth_service.register_user(db, payload)
        issued = auth_service.issue_session(db, user)
        _set_auth_cookies(response, issued.session_token, issued.csrf_token)
        return AuthResponse(
            user=UserResponse.model_validate(user),
            csrf_token=issued.csrf_token,
        )
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> AuthResponse:
    try:
        user = auth_service.authenticate(db, str(payload.email), payload.password)
        issued = auth_service.issue_session(db, user)
        _set_auth_cookies(response, issued.session_token, issued.csrf_token)
        return AuthResponse(
            user=UserResponse.model_validate(user),
            csrf_token=issued.csrf_token,
        )
    except ServiceError as exc:
        raise_service_http_error(exc)


@router.get("/me", response_model=UserResponse)
def me(auth: Annotated[AuthContext, Depends(get_auth_context)]) -> User:
    return auth.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    auth: Annotated[AuthContext, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    auth_service.revoke_session(db, auth.session)
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
