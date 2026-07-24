"""Typed application-layer errors with stable compatibility imports."""

from codex_usage_tracker.core.errors import ApplicationError, RequestValidationError

__all__ = ["ApplicationError", "RequestContextError", "RequestValidationError"]


class RequestContextError(ApplicationError):
    """Raised when request context cannot safely read its configured source."""
