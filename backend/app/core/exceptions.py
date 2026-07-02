"""Custom application exceptions.

Domain exceptions (price-floor violation, insufficient stock, ...) will be
added alongside the service layer. They all inherit from AppError so the API
layer can map them to HTTP responses in a single exception handler.
"""


class AppError(Exception):
    """Base class for every business/domain error raised by services."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
