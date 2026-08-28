"""Extension -> handler dispatch, plus the shared metered ranged reader.

AIDEV-NOTE: parquet/fits handlers deliberately do NOT use pyarrow.fs.S3FileSystem
or astropy's fsspec path — those fetch bytes outside our control, breaking the
"every S3 byte flows through meter.py" constraint. RangedS3File is the single
GET site: pyarrow/astropy parse bytes it fetches. See implementation-notes.md.
"""

from __future__ import annotations

import posixpath
from typing import Any

from s3f import meter
from s3f.listing import env_int, make_client

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif"}
FITS_EXTS = {".fits", ".fit", ".fts"}


def max_preview_bytes() -> int:
    return env_int("S3F_PREVIEW_MAX_BYTES", 2 * 1024 * 1024)


def footer(fetched: int, total: int) -> str:
    return f"↓ fetched {meter.human_bytes(fetched)} of {meter.human_bytes(total)} object"


class RangedS3File:
    """Seekable read-only file over an S3 object; every read is a range GET."""

    mode = "rb"

    def __init__(self, client: Any, bucket: str, key: str, size: int) -> None:
        self._client = client
        self._bucket = bucket
        self._key = key
        self._size = size
        self._pos = 0
        self.bytes_fetched = 0
        self.closed = False

    def read(self, n: int = -1) -> bytes:
        if n == 0 or self._pos >= self._size:
            return b""
        end = self._size if n < 0 else min(self._pos + n, self._size)
        resp = self._client.get_object(
            Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end - 1}"
        )
        data: bytes = resp["Body"].read()
        meter.record_transferred(len(data))
        self.bytes_fetched += len(data)
        self._pos += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def render(bucket: str, key: str, *, client: Any = None, anonymous: bool = False) -> str:
    """Dispatch to a type handler. NEVER raises — errors render in the pane."""
    try:
        if key.endswith("/"):
            return f"{key}\n\ndirectory prefix — press ctrl-p to descend"
        if client is None:
            client = make_client(anonymous)
        head = client.head_object(Bucket=bucket, Key=key)
        size = int(head["ContentLength"])
        ext = posixpath.splitext(key)[1].lower()
        # AIDEV-NOTE: lazy handler imports avoid parent-package circular imports
        # and keep pyarrow/astropy off the hot path for text previews.
        if ext == ".parquet":
            from s3f.previews import parquet

            return parquet.render(client, bucket, key, size)
        if ext in FITS_EXTS:
            from s3f.previews import fits

            return fits.render(client, bucket, key, size)
        if ext in IMAGE_EXTS:
            from s3f.previews import image

            return image.render(client, bucket, key, size)
        from s3f.previews import generic

        return generic.render(client, bucket, key, size)
    except Exception as exc:  # noqa: BLE001 — pane must survive anything
        return f"⚠ preview error: {exc}"
