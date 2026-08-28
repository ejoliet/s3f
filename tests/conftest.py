from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    for var in ("S3F_ANONYMOUS", "S3F_SLACK_WEBHOOK_URL", "S3F_LIST_MAX_KEYS"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def s3() -> Iterator["boto3.client"]:  # type: ignore[type-arg]
    with mock_aws():
        yield boto3.client("s3", region_name="us-east-1")


class FakeSlack:
    def __init__(self) -> None:
        self.status = 200
        self.body = b"ok"
        self.calls: list[dict[str, object]] = []


@pytest.fixture()
def slack(monkeypatch: pytest.MonkeyPatch) -> FakeSlack:
    """Stub s3f.share.urlopen — the spec mandates stdlib urllib for the webhook."""
    import io
    import json
    import urllib.error
    from typing import Any

    fake = FakeSlack()

    class _Resp:
        def read(self) -> bytes:
            return fake.body

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(req: Any, timeout: float = 10) -> _Resp:
        fake.calls.append(json.loads(req.data.decode()))
        if fake.status >= 300:
            raise urllib.error.HTTPError(
                req.full_url, fake.status, "error", None, io.BytesIO(fake.body)
            )
        return _Resp()

    monkeypatch.setattr("s3f.share.urlopen", fake_urlopen)
    return fake
