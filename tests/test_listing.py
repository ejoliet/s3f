from typing import Any

import pytest
from botocore import UNSIGNED

from s3f import S3fNoSuchBucket, listing, meter


def test_parse_s3uri() -> None:
    assert listing.parse_s3uri("s3://bkt/pre/fix/") == ("bkt", "pre/fix/")
    assert listing.parse_s3uri("s3://bkt") == ("bkt", "")
    with pytest.raises(ValueError):
        listing.parse_s3uri("http://nope")


def test_make_client_anonymous_is_unsigned() -> None:
    client = listing.make_client(anonymous=True)
    assert client.meta.config.signature_version is UNSIGNED


def test_make_client_env_forces_unsigned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3F_ANONYMOUS", "true")
    client = listing.make_client()
    assert client.meta.config.signature_version is UNSIGNED


def test_make_client_signed_by_default() -> None:
    client = listing.make_client()
    assert client.meta.config.signature_version is not UNSIGNED
    # adaptive retries, max 5 attempts (throttling behavior)
    assert client.meta.config.retries == {"mode": "adaptive", "total_max_attempts": 5}


def _fill(s3: Any, bucket: str, keys: dict[str, bytes]) -> None:
    s3.create_bucket(Bucket=bucket)
    for k, body in keys.items():
        s3.put_object(Bucket=bucket, Key=k, Body=body)


def test_iter_lines_streams_tab_separated(s3: Any) -> None:
    _fill(s3, "bkt", {"a/x.txt": b"12345", "a/y.txt": b"67"})
    meter.reset()
    lines = list(listing.iter_lines("bkt", "a/", client=s3))
    assert len(lines) == 2
    key, size, ts, sc = lines[0].split("\t")
    assert key == "a/x.txt"
    assert size == "5"
    assert ts  # iso timestamp
    assert sc == "STANDARD"


def test_iter_lines_records_browsed_bytes(s3: Any) -> None:
    _fill(s3, "bkt", {"x": b"123", "y": b"4567"})
    meter.reset()
    list(listing.iter_lines("bkt", "", client=s3))
    st = meter.load()
    assert st.bytes_browsed == 7
    assert st.objects_browsed == 2


def test_iter_lines_max_keys_cap(s3: Any) -> None:
    _fill(s3, "bkt", {f"k{i}": b"x" for i in range(10)})
    lines = list(listing.iter_lines("bkt", "", client=s3, max_keys=3))
    assert len(lines) == 3


def test_iter_lines_delimited_yields_prefixes(s3: Any) -> None:
    _fill(s3, "bkt", {"top.txt": b"1", "dir/a.txt": b"2", "dir/b.txt": b"3"})
    lines = list(listing.iter_lines("bkt", "", client=s3, delimiter="/"))
    assert "dir/\t-\t-\tPRE" in lines
    assert any(line.startswith("top.txt\t") for line in lines)


def test_no_such_bucket_maps_to_s3f_error(s3: Any) -> None:
    with pytest.raises(S3fNoSuchBucket):
        list(listing.iter_lines("missing-bucket", "", client=s3))
