import json
import os
from pathlib import Path

from s3f import meter


def test_state_path_respects_xdg() -> None:
    p = meter.state_path()
    assert p == Path(os.environ["XDG_STATE_HOME"]) / "s3f" / "session.json"


def test_reset_and_load_zeroed() -> None:
    meter.reset()
    st = meter.load()
    assert (st.bytes_browsed, st.objects_browsed, st.bytes_transferred) == (0, 0, 0)


def test_record_browsed_and_transferred_persist() -> None:
    meter.reset()
    meter.record_browsed(1000, 2)
    meter.record_browsed(24, 1)
    meter.record_transferred(41)
    st = meter.load()
    assert st.bytes_browsed == 1024
    assert st.objects_browsed == 3
    assert st.bytes_transferred == 41
    # persisted on disk, not just in memory
    raw = json.loads(meter.state_path().read_text())
    assert raw["bytes_transferred"] == 41


def test_load_without_file_returns_zeroed() -> None:
    if meter.state_path().exists():
        meter.state_path().unlink()
    st = meter.load()
    assert st.bytes_browsed == 0


def test_human_bytes() -> None:
    assert meter.human_bytes(0) == "0 B"
    assert meter.human_bytes(512) == "512 B"
    assert meter.human_bytes(41 * 1024) == "41 KB"
    assert meter.human_bytes(int(23.4 * 1024)) == "23.4 KB"
    assert meter.human_bytes(int(3.2 * 1024**4)) == "3.2 TB"


def test_summary_format() -> None:
    meter.reset()
    meter.record_browsed(int(3.2 * 1024**4), 1_204_551)
    meter.record_transferred(41 * 1024)
    s = meter.summary()
    assert s == "Browsed 3.2 TB across 1,204,551 objects. Transferred 41 KB."
