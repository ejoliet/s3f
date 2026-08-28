"""Head-bytes preview for everything else: UTF-8 text as-is, else xxd-style hexdump."""

from __future__ import annotations

from typing import Any

from s3f.previews import RangedS3File, footer

HEAD_BYTES = 4096


def hexdump(data: bytes) -> str:
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off : off + 16]
        hexes = " ".join(f"{b:02x}" for b in chunk)
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:08x}: {hexes:<47}  {text}")
    return "\n".join(lines)


def render(client: Any, bucket: str, key: str, size: int) -> str:
    f = RangedS3File(client, bucket, key, size)
    data = f.read(min(size, HEAD_BYTES))
    try:
        body = data.decode("utf-8")
    except UnicodeDecodeError:
        body = hexdump(data)
    return f"{body}\n{footer(f.bytes_fetched, size)}"
