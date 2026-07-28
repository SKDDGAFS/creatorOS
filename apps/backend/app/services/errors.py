class ServiceError(Exception):
    """Base exception for safe errors raised by the service layer."""


class ResourceNotFoundError(ServiceError):
    """Raised when a requested record or required parent does not exist."""


class ConflictError(ServiceError):
    """Raised when a write conflicts with an existing record."""


class PersistenceError(ServiceError):
    """Raised when a database write fails for a non-conflict reason."""
