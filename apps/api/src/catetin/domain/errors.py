class DomainError(Exception):
    """Base class for all domain-level errors."""


class NotFound(DomainError):
    """Requested entity does not exist."""


class DomainValidationError(DomainError):
    """A domain invariant was violated outside of pydantic construction."""


class RateLimited(DomainError):
    """An operation was rejected because a rate limit was exceeded."""
