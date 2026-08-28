import io
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from astropy.io import fits as afits

from s3f import meter, previews
from s3f.previews import RangedS3File, footer

# 1x1 red pixel PNG
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc000000301010018dd8db00000000049"
    "454e44ae426082"
)


def _put(s3: Any, key: str, body: bytes) -> None:
    s3.create_bucket(Bucket="bkt")
    s3.put_object(Bucket="bkt", Key=key, Body=body)


def _parquet_bytes() -> bytes:
    n = 100_000
    table = pa.table({"ra": np.arange(n, dtype=np.float64), "flux": np.arange(n)})
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _fits_bytes() -> bytes:
    hdu = afits.PrimaryHDU(data=np.zeros((16, 16), dtype=np.float32))
    hdu.header["TELESCOP"] = "SPHEREx"
    hdu.header["DATE-OBS"] = "2026-08-27"
    buf = io.BytesIO()
    hdu.writeto(buf)
    return buf.getvalue()


def test_footer_format() -> None:
    line = footer(int(23.4 * 1024), int(1.2 * 1024**3))
    assert line == "↓ fetched 23.4 KB of 1.2 GB object"


def test_ranged_file_reads_and_meters(s3: Any) -> None:
    _put(s3, "x.bin", b"0123456789")
    meter.reset()
    f = RangedS3File(s3, "bkt", "x.bin", 10)
    f.seek(2)
    assert f.read(3) == b"234"
    assert f.tell() == 5
    assert f.read() == b"56789"
    assert f.read(4) == b""  # EOF
    assert meter.load().bytes_transferred == 8


def test_parquet_preview_schema_and_byte_cap(s3: Any) -> None:
    body = _parquet_bytes()
    _put(s3, "data/t.parquet", body)
    meter.reset()
    out = previews.render("bkt", "data/t.parquet", client=s3)
    assert "ra" in out and "flux" in out
    assert "num_rows: 100000" in out
    assert "num_row_groups: 1" in out
    fetched = meter.load().bytes_transferred
    assert 0 < fetched < len(body)  # core invariant: footer only
    assert "↓ fetched" in out


def test_fits_preview_header_and_byte_cap(s3: Any) -> None:
    body = _fits_bytes()
    _put(s3, "img/f.fits", body)
    meter.reset()
    out = previews.render("bkt", "img/f.fits", client=s3)
    assert "TELESCOP" in out and "SPHEREx" in out
    assert "NAXIS" in out
    fetched = meter.load().bytes_transferred
    assert 0 < fetched < len(body)
    assert "↓ fetched" in out


def test_image_preview_falls_back_without_chafa(
    s3: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _put(s3, "pic.png", PNG_1PX)
    monkeypatch.setattr("shutil.which", lambda _: None)
    out = previews.render("bkt", "pic.png", client=s3)
    assert "chafa" in out.lower()  # explains fallback, never crashes
    assert "↓ fetched" in out


def test_generic_text_preview(s3: Any) -> None:
    _put(s3, "notes.txt", b"hello s3f\nline two\n")
    out = previews.render("bkt", "notes.txt", client=s3)
    assert "hello s3f" in out


def test_generic_binary_hexdump_and_4k_cap(s3: Any) -> None:
    body = b"\x00\x01\x02\xff" * 4096  # 16 KB binary
    _put(s3, "blob.dat", body)
    meter.reset()
    out = previews.render("bkt", "blob.dat", client=s3)
    assert "00000000" in out  # xxd-style offset
    assert meter.load().bytes_transferred <= 4096


def test_corrupt_parquet_renders_error_in_pane(s3: Any) -> None:
    _put(s3, "bad.parquet", b"PAR1 this is not really parquet PAR1")
    out = previews.render("bkt", "bad.parquet", client=s3)  # must not raise
    assert "preview error" in out.lower()


def test_missing_key_renders_error_in_pane(s3: Any) -> None:
    s3.create_bucket(Bucket="bkt")
    out = previews.render("bkt", "nope.txt", client=s3)
    assert "preview error" in out.lower()
