from sqlalchemy import text
from sqlalchemy.orm import Session


def check_database_connection(db: Session) -> None:
    """Run a read-only query to verify database connectivity."""

    db.execute(text("SELECT 1"))
