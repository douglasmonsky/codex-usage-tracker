"""Typed application-layer request errors."""


class ApplicationError(Exception):
    """Base error for application orchestration failures."""


class RequestValidationError(ApplicationError, ValueError):
    """Raised when a typed application request violates its contract."""


class RequestContextError(ApplicationError):
    """Raised when request context cannot safely read its configured source."""
