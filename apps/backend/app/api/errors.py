from typing import NoReturn

from fastapi import HTTPException, status

from app.services.errors import (
    ConflictError,
    PersistenceError,
    ResourceNotFoundError,
    ServiceError,
)


def raise_service_http_error(error: ServiceError) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, ConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, PersistenceError):
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    raise HTTPException(status_code=status_code, detail=str(error)) from error
