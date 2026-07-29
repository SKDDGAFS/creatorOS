import json
import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.models.channel import Platform
from app.models.platform_integration import (
    ConnectionStatus,
    PlatformConnection,
    PlatformOperation,
    PlatformOperationStatus,
    PlatformQuotaUsage,
    PlatformRequestLog,
    PlatformSyncCursor,
    RequestOutcome,
)
from app.platforms.redaction import safe_request_metadata
from app.services.errors import (
    ConflictError,
    InvalidRequestError,
    PersistenceError,
    ResourceNotFoundError,
)

IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _aware_utc(value: datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise InvalidRequestError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError(message) from exc


def _normalize_identifier(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise InvalidRequestError(
            f"{field} must start with a letter and contain only lowercase "
            "letters, numbers, dots, underscores, or hyphens"
        )
    return normalized


def _canonical_json(value: dict[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidRequestError("Operation request must be a JSON object") from exc


def _normalize_scopes(scopes: tuple[str, ...]) -> list[str]:
    if len(scopes) > 100:
        raise InvalidRequestError("A connection cannot contain more than 100 scopes")
    normalized = sorted({scope.strip() for scope in scopes if scope.strip()})
    if any(len(scope) > 500 for scope in normalized):
        raise InvalidRequestError("Each scope cannot exceed 500 characters")
    return normalized


def create_connection(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    platform: Platform,
    external_account_id: str,
    display_name: str | None,
    credential_reference: str,
    scopes: tuple[str, ...],
    token_expires_at: datetime | None,
) -> PlatformConnection:
    account_id = external_account_id.strip()
    reference = credential_reference.strip()
    if not account_id or len(account_id) > 255:
        raise InvalidRequestError(
            "external_account_id must contain 1 through 255 characters"
        )
    if not reference or len(reference) > 500:
        raise InvalidRequestError(
            "credential_reference must contain 1 through 500 characters"
        )
    connection = PlatformConnection(
        workspace_id=workspace_id,
        created_by_user_id=user_id,
        platform=platform.value,
        external_account_id=account_id,
        display_name=display_name,
        credential_reference=reference,
        scopes=_normalize_scopes(scopes),
        token_expires_at=_aware_utc(token_expires_at, "token_expires_at"),
    )
    db.add(connection)
    _commit(db, "Platform account is already connected")
    db.refresh(connection)
    return connection


def get_connection(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    lock: bool = False,
) -> PlatformConnection:
    statement = select(PlatformConnection).where(
        PlatformConnection.id == connection_id,
        PlatformConnection.workspace_id == workspace_id,
    )
    if lock:
        statement = statement.with_for_update()
    connection = db.scalar(statement)
    if connection is None:
        raise ResourceNotFoundError("Platform connection not found")
    return connection


def list_connections(
    db: Session,
    *,
    workspace_id: UUID,
    platform: Platform | None,
    include_disconnected: bool,
) -> list[PlatformConnection]:
    statement: Select[tuple[PlatformConnection]] = select(
        PlatformConnection
    ).where(PlatformConnection.workspace_id == workspace_id)
    if platform is not None:
        statement = statement.where(
            PlatformConnection.platform == platform.value
        )
    if not include_disconnected:
        statement = statement.where(
            PlatformConnection.status != ConnectionStatus.DISCONNECTED.value
        )
    statement = statement.order_by(
        PlatformConnection.created_at,
        PlatformConnection.id,
    )
    return list(db.scalars(statement).all())


def replace_credential_reference(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    credential_reference: str,
    scopes: tuple[str, ...],
    token_expires_at: datetime | None,
) -> PlatformConnection:
    reference = credential_reference.strip()
    if not reference or len(reference) > 500:
        raise InvalidRequestError(
            "credential_reference must contain 1 through 500 characters"
        )
    connection = get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        lock=True,
    )
    connection.credential_reference = reference
    connection.scopes = _normalize_scopes(scopes)
    connection.token_expires_at = _aware_utc(
        token_expires_at,
        "token_expires_at",
    )
    connection.last_refreshed_at = _utc_now()
    connection.status = ConnectionStatus.CONNECTED.value
    connection.disconnected_at = None
    _commit(db, "Unable to update platform credential reference")
    return connection


def mark_connection_status(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    status: ConnectionStatus,
) -> PlatformConnection:
    connection = get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        lock=True,
    )
    if connection.status == status.value:
        db.rollback()
        return connection
    if connection.status == ConnectionStatus.DISCONNECTED.value:
        db.rollback()
        raise ConflictError("Disconnected platform connections are terminal")
    connection.status = status.value
    if status is ConnectionStatus.DISCONNECTED:
        connection.disconnected_at = _utc_now()
    _commit(db, "Unable to update platform connection status")
    return connection


def get_cursor(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    resource_type: str,
) -> PlatformSyncCursor | None:
    resource = _normalize_identifier(resource_type, "resource_type")
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    return db.scalar(
        select(PlatformSyncCursor).where(
            PlatformSyncCursor.connection_id == connection_id,
            PlatformSyncCursor.resource_type == resource,
        )
    )


def save_cursor(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    resource_type: str,
    cursor: str | None,
    synced_at: datetime | None = None,
) -> PlatformSyncCursor:
    resource = _normalize_identifier(resource_type, "resource_type")
    if cursor is not None and len(cursor) > 2000:
        raise InvalidRequestError("cursor cannot exceed 2000 characters")
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
        lock=True,
    )
    record = db.scalar(
        select(PlatformSyncCursor).where(
            PlatformSyncCursor.connection_id == connection_id,
            PlatformSyncCursor.resource_type == resource,
        )
    )
    if record is None:
        record = PlatformSyncCursor(
            connection_id=connection_id,
            resource_type=resource,
        )
        db.add(record)
    record.cursor = cursor
    record.last_synced_at = (
        _aware_utc(synced_at, "synced_at") if synced_at else _utc_now()
    )
    _commit(db, "Unable to save platform sync cursor")
    db.refresh(record)
    return record


def begin_operation(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    operation_type: str,
    idempotency_key: str,
    request: dict[str, Any],
) -> tuple[PlatformOperation, bool]:
    operation_name = _normalize_identifier(operation_type, "operation_type")
    if len(idempotency_key) < 8 or len(idempotency_key) > 256:
        raise InvalidRequestError(
            "idempotency_key must contain 8 through 256 characters"
        )
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    key_hash = hash_token(idempotency_key)
    fingerprint = hash_token(_canonical_json(request))
    existing = db.scalar(
        select(PlatformOperation).where(
            PlatformOperation.connection_id == connection_id,
            PlatformOperation.operation_type == operation_name,
            PlatformOperation.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise ConflictError(
                "Idempotency key was already used with another request"
            )
        return existing, False

    operation = PlatformOperation(
        connection_id=connection_id,
        operation_type=operation_name,
        idempotency_key_hash=key_hash,
        request_fingerprint=fingerprint,
    )
    db.add(operation)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        concurrent = db.scalar(
            select(PlatformOperation).where(
                PlatformOperation.connection_id == connection_id,
                PlatformOperation.operation_type == operation_name,
                PlatformOperation.idempotency_key_hash == key_hash,
            )
        )
        if concurrent is not None and concurrent.request_fingerprint == fingerprint:
            return concurrent, False
        raise ConflictError("Unable to start platform operation") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise PersistenceError("Unable to start platform operation") from exc
    db.refresh(operation)
    return operation, True


def _get_operation(
    db: Session,
    *,
    workspace_id: UUID,
    operation_id: UUID,
    lock: bool,
) -> PlatformOperation:
    statement = (
        select(PlatformOperation)
        .join(PlatformConnection)
        .where(
            PlatformOperation.id == operation_id,
            PlatformConnection.workspace_id == workspace_id,
        )
    )
    if lock:
        statement = statement.with_for_update()
    operation = db.scalar(statement)
    if operation is None:
        raise ResourceNotFoundError("Platform operation not found")
    return operation


def complete_operation(
    db: Session,
    *,
    workspace_id: UUID,
    operation_id: UUID,
    external_resource_id: str | None,
) -> PlatformOperation:
    operation = _get_operation(
        db,
        workspace_id=workspace_id,
        operation_id=operation_id,
        lock=True,
    )
    if operation.status == PlatformOperationStatus.SUCCEEDED.value:
        db.rollback()
        return operation
    if operation.status == PlatformOperationStatus.FAILED.value:
        db.rollback()
        raise ConflictError("Failed platform operations cannot complete")
    operation.status = PlatformOperationStatus.SUCCEEDED.value
    operation.external_resource_id = external_resource_id
    operation.completed_at = _utc_now()
    _commit(db, "Unable to complete platform operation")
    return operation


def fail_operation(
    db: Session,
    *,
    workspace_id: UUID,
    operation_id: UUID,
    error_code: str,
    safe_message: str,
) -> PlatformOperation:
    operation = _get_operation(
        db,
        workspace_id=workspace_id,
        operation_id=operation_id,
        lock=True,
    )
    if operation.status != PlatformOperationStatus.IN_PROGRESS.value:
        db.rollback()
        raise ConflictError("Platform operation is already terminal")
    operation.status = PlatformOperationStatus.FAILED.value
    operation.last_error_code = error_code.strip()[:100] or "platform_error"
    operation.last_error_message = (
        safe_message.strip()[:500] or "Platform operation failed"
    )
    operation.completed_at = _utc_now()
    _commit(db, "Unable to fail platform operation")
    return operation


def record_request_log(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    operation_id: UUID | None,
    method: str,
    url: str,
    headers: dict[str, Any] | None,
    body: Any,
    status_code: int | None,
    duration_ms: int,
    outcome: RequestOutcome,
    provider_request_id: str | None = None,
) -> PlatformRequestLog:
    if duration_ms < 0:
        raise InvalidRequestError("duration_ms cannot be negative")
    if status_code is not None and not 100 <= status_code <= 599:
        raise InvalidRequestError("status_code must be between 100 and 599")
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    if operation_id is not None:
        operation = _get_operation(
            db,
            workspace_id=workspace_id,
            operation_id=operation_id,
            lock=False,
        )
        if operation.connection_id != connection_id:
            db.rollback()
            raise ConflictError("Request log operation belongs to another connection")
    metadata = safe_request_metadata(
        method=method,
        url=url,
        headers=headers,
        body=body,
    )
    log = PlatformRequestLog(
        connection_id=connection_id,
        operation_id=operation_id,
        method=metadata["method"],
        host=metadata["host"],
        path=metadata["path"],
        status_code=status_code,
        duration_ms=duration_ms,
        outcome=outcome.value,
        provider_request_id=provider_request_id,
        request_metadata={
            "headers": metadata["headers"],
            "body": metadata["body"],
        },
    )
    db.add(log)
    _commit(db, "Unable to record platform request log")
    db.refresh(log)
    return log


def record_quota_usage(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    quota_bucket: str,
    units: int,
    request_count: int = 1,
    usage_date: date | None = None,
) -> PlatformQuotaUsage:
    bucket = _normalize_identifier(quota_bucket, "quota_bucket")
    if units < 0:
        raise InvalidRequestError("units cannot be negative")
    if request_count < 1:
        raise InvalidRequestError("request_count must be positive")
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    day = usage_date or _utc_now().date()
    statement = (
        select(PlatformQuotaUsage)
        .where(
            PlatformQuotaUsage.connection_id == connection_id,
            PlatformQuotaUsage.usage_date == day,
            PlatformQuotaUsage.quota_bucket == bucket,
        )
        .with_for_update()
    )
    record = db.scalar(statement)
    if record is None:
        record = PlatformQuotaUsage(
            connection_id=connection_id,
            usage_date=day,
            quota_bucket=bucket,
            units=units,
            request_count=request_count,
        )
        db.add(record)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            record = db.scalar(statement)
            if record is None:
                raise ConflictError(
                    "Unable to record platform quota usage"
                ) from None
            record.units += units
            record.request_count += request_count
            _commit(db, "Unable to record platform quota usage")
        except SQLAlchemyError as exc:
            db.rollback()
            raise PersistenceError(
                "Unable to record platform quota usage"
            ) from exc
    else:
        record.units += units
        record.request_count += request_count
        _commit(db, "Unable to record platform quota usage")
    db.refresh(record)
    return record


def list_quota_usage(
    db: Session,
    *,
    workspace_id: UUID,
    connection_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[PlatformQuotaUsage]:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise InvalidRequestError("start_date cannot be after end_date")
    get_connection(
        db,
        workspace_id=workspace_id,
        connection_id=connection_id,
    )
    statement: Select[tuple[PlatformQuotaUsage]] = select(
        PlatformQuotaUsage
    ).where(PlatformQuotaUsage.connection_id == connection_id)
    if start_date is not None:
        statement = statement.where(
            PlatformQuotaUsage.usage_date >= start_date
        )
    if end_date is not None:
        statement = statement.where(
            PlatformQuotaUsage.usage_date <= end_date
        )
    statement = statement.order_by(
        PlatformQuotaUsage.usage_date,
        PlatformQuotaUsage.quota_bucket,
    )
    return list(db.scalars(statement).all())
