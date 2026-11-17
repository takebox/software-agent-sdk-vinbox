class TrackError(Exception):
    """Base exception for all track errors."""

    pass


class TrackValidationError(TrackError):
    """Raised when there's a validation error in track metadata."""

    def __init__(self, message: str = "Track validation failed") -> None:
        super().__init__(message)
