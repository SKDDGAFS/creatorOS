from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.init_db import check_database_connection
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def application_health() -> dict[str, str]:
    return {"status": "ok", "service": "CreatorOS API"}


@router.get("/database")
def database_health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        check_database_connection(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {"status": "ok", "database": "reachable"}
