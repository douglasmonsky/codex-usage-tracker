"""Stable errors shared by request contracts and application orchestration."""


class ApplicationError(Exception):
    """Base error for application orchestration failures."""


class RequestValidationError(ApplicationError, ValueError):
    """Raised when a typed request violates its contract."""
