"""Ranged image bytes -> chafa thumbnail; text metadata fallback, never crash."""

from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import tempfile
from typing import Any

from s3f import meter
from s3f.previews import RangedS3File, footer, max_preview_bytes


def _pane_size() -> tuple[str, str]:
    cols = os.environ.get("FZF_PREVIEW_COLUMNS") or os.environ.get("COLUMNS") or "80"
    rows = os.environ.get("FZF_PREVIEW_LINES") or os.environ.get("LINES") or "24"
    return cols, rows


def render(client: Any, bucket: str, key: str, size: int) -> str:
    f = RangedS3File(client, bucket, key, size)
    data = f.read(min(size, max_preview_bytes()))
    truncated = size > len(data)
    body = _chafa(data, posixpath.splitext(key)[1]) or (
        f"[image] {key}\n"
        f"size: {meter.human_bytes(size)}\n"
        "install chafa for in-terminal thumbnails"
    )
    if truncated:
        body += f"\n(truncated to first {meter.human_bytes(len(data))})"
    return f"{body}\n{footer(f.bytes_fetched, size)}"


def _chafa(data: bytes, suffix: str) -> str | None:
    chafa = shutil.which("chafa")
    if chafa is None:
        return None
    cols, rows = _pane_size()
    with tempfile.NamedTemporaryFile(suffix=suffix or ".img") as tmp:
        tmp.write(data)
        tmp.flush()
        proc = subprocess.run(
            [chafa, f"--size={cols}x{rows}", "-f", "auto", tmp.name],
            capture_output=True,
            timeout=10,
        )
    if proc.returncode != 0:
        return None  # e.g. truncated image chafa can't decode -> metadata fallback
    return proc.stdout.decode("utf-8", errors="replace")
