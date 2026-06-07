from __future__ import annotations


class EvoQuantError(Exception):
    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(message)


class TransientDataError(EvoQuantError):
    pass


class SourceUnavailableError(TransientDataError):
    pass


class ConnectionPoolExhaustedError(TransientDataError):
    pass


class FatalDataError(EvoQuantError):
    pass


class SchemaValidationError(FatalDataError):
    pass


class ConfigurationError(FatalDataError):
    pass


class CircuitOpenError(EvoQuantError):
    pass


def is_retryable(exc: Exception) -> bool:
    return isinstance(exc, TransientDataError)


def classify_exception(exc: Exception) -> str:
    if isinstance(exc, TransientDataError):
        return "transient"
    if isinstance(exc, FatalDataError):
        return "fatal"
    return "unknown"
