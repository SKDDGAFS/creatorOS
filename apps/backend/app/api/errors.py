from typing import NoReturn, cast

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.services.errors import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    PersistenceError,
    RateLimitError,
    ResourceNotFoundError,
    ServiceError,
)


def service_error_status(error: ServiceError) -> int:
    if isinstance(error, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, AuthenticationError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(error, AuthorizationError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, RateLimitError):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    elif isinstance(error, PersistenceError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    return status_code


def raise_service_http_error(error: ServiceError) -> NoReturn:
    raise HTTPException(
        status_code=service_error_status(error),
        detail=str(error),
    ) from error


def service_error_handler(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    service_error = cast(ServiceError, error)
    return JSONResponse(
        status_code=service_error_status(service_error),
        content={"detail": str(service_error)},
    )
