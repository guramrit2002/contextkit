"""Custom exceptions for contextkit."""


class ContextKitError(Exception):
    """Base exception for all contextkit errors."""

    pass


class ProjectNotFoundError(ContextKitError):
    """Raised when a project cannot be found."""

    pass


class InvalidProjectIdError(ContextKitError):
    """Raised when a project ID is invalid."""

    pass


class StorageError(ContextKitError):
    """Raised when a storage operation fails."""

    pass


class BriefingError(ContextKitError):
    """Raised when briefing retrieval fails."""

    pass


class ValidationError(ContextKitError):
    """Raised when input validation fails."""

    pass
