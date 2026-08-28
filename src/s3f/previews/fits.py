"""FITS primary-HDU header preview via 2880-byte block range reads.

AIDEV-NOTE: astropy parses, but WE fetch — astropy's use_fsspec path would
bypass the byte meter and drag in aiobotocore. Hand-rolled block reads are
README-blessed as the fallback; here they are the primary path.
"""

from __future__ import annotations

from typing import Any

from astropy.io.fits import Header

from s3f import S3fPreviewError
from s3f.meter import human_bytes
from s3f.previews import RangedS3File, footer, max_preview_bytes

BLOCK = 2880
CARD = 80
CURATED = ("TELESCOP", "INSTRUME", "DATE-OBS", "RA_TARG", "DEC_TARG", "NAXIS")


def _has_end_card(block: bytes) -> bool:
    return any(block[i : i + CARD].rstrip() == b"END" for i in range(0, len(block), CARD))


def read_header(client: Any, bucket: str, key: str, size: int) -> tuple[Header, int]:
    """Fetch primary header blocks only; return (header, bytes_fetched)."""
    f = RangedS3File(client, bucket, key, size)
    raw = b""
    cap = min(size, max_preview_bytes())
    found_end = False
    while len(raw) < cap:
        block = f.read(BLOCK)
        if not block:
            break
        raw += block
        if _has_end_card(block):
            found_end = True
            break
    if not raw:
        raise S3fPreviewError("empty object")
    if not found_end:
        raise S3fPreviewError(f"no END card in first {human_bytes(len(raw))} — corrupt FITS?")
    return Header.fromstring(raw.decode("ascii", errors="replace")), f.bytes_fetched


def render(client: Any, bucket: str, key: str, size: int) -> str:
    header, fetched = read_header(client, bucket, key, size)
    lines = [key, ""]
    for card in header.cards:
        if str(card.keyword).startswith(CURATED):
            lines.append(f"  {card.keyword:<8} = {card.value!r:<24} / {card.comment}")
    lines += ["", f"cards: {len(header)} total", "", footer(fetched, size)]
    return "\n".join(lines)
