from __future__ import annotations


class SteamError(Exception):
    """Base class for Steam API errors."""


class RateLimitError(SteamError):
    """Raised when Steam returns HTTP 429 (Too Many Requests)."""


class SourceError(SteamError):
    """Raised on a non-retryable Steam API error response."""


class ParseError(SteamError):
    """Raised when a Steam XML or JSON response cannot be parsed."""
