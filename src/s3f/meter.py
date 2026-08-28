"""Bytes-browsed vs bytes-transferred session counter — the viral stat.

AIDEV-NOTE: single choke point for byte accounting. Every S3 GET site calls
record_transferred(); every listing page calls record_browsed(). State is a
small JSON file so fzf-spawned preview/share subprocesses share the session.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


@dataclass
class MeterState:
    bytes_browsed: int = 0
    objects_browsed: int = 0
    bytes_transferred: int = 0


def state_path() -> Path:
    root = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(root) / "s3f" / "session.json"


def load() -> MeterState:
    try:
        raw = json.loads(state_path().read_text())
        return MeterState(
            bytes_browsed=int(raw.get("bytes_browsed", 0)),
            objects_browsed=int(raw.get("objects_browsed", 0)),
            bytes_transferred=int(raw.get("bytes_transferred", 0)),
        )
    except (OSError, ValueError):
        return MeterState()


def _save(state: MeterState) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state)))


def reset() -> None:
    _save(MeterState())


def record_browsed(nbytes: int, nobjects: int = 1) -> None:
    state = load()
    state.bytes_browsed += nbytes
    state.objects_browsed += nobjects
    _save(state)


def record_transferred(nbytes: int) -> None:
    state = load()
    state.bytes_transferred += nbytes
    _save(state)


def human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    value = float(n)
    idx = 0
    while value >= 1024.0 and idx < len(_UNITS) - 1:
        value /= 1024.0
        idx += 1
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return f"{text} {_UNITS[idx]}"


def summary() -> str:
    st = load()
    return (
        f"Browsed {human_bytes(st.bytes_browsed)} across {st.objects_browsed:,} objects. "
        f"Transferred {human_bytes(st.bytes_transferred)}."
    )
