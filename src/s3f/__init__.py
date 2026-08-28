"""s3f — fzf over a billion S3 objects: preview terabytes, download kilobytes."""

__all__ = [
    "S3fAccessDenied",
    "S3fError",
    "S3fNoSuchBucket",
    "S3fPreviewError",
    "S3fSlackError",
]


class S3fError(Exception):
    """Base class for s3f errors; carries a process exit code."""

    exit_code = 1


class S3fAccessDenied(S3fError):
    exit_code = 3


class S3fNoSuchBucket(S3fError):
    exit_code = 4


class S3fSlackError(S3fError):
    """Webhook failure; carries the presigned URL so it is never lost."""

    exit_code = 5

    def __init__(self, message: str, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class S3fPreviewError(S3fError):
    """Preview failures are rendered in-pane and never kill fzf."""

    exit_code = 1
