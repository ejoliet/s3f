import json
from typing import Any

import pytest

from s3f import S3fSlackError, share
from tests.conftest import FakeSlack

WEBHOOK = "https://hooks.slack.com/services/T00/B00/XXX"


def _obj(s3: Any) -> None:
    s3.create_bucket(Bucket="bkt")
    s3.put_object(Bucket="bkt", Key="data/pic.png", Body=b"png-bytes")


def test_presign_contains_key(s3: Any) -> None:
    _obj(s3)
    url = share.presign(s3, "bkt", "data/pic.png", ttl=3600)
    assert "data/pic.png" in url
    assert url.startswith("https://")


def test_build_card_shape() -> None:
    card = share.build_card(
        bucket="bkt",
        key="data/pic.png",
        size=9,
        last_modified="2026-08-27T00:00:00",
        url="https://example.com/presigned",
        ttl=3600,
        facts={"TELESCOP": "SPHEREx"},
    )
    blocks = card["blocks"]
    assert blocks[0]["type"] == "header"
    assert blocks[0]["text"]["text"] == "pic.png"
    fields_text = json.dumps(blocks[1]["fields"])
    assert "bkt" in fields_text and "SPHEREx" in fields_text
    image_blocks = [b for b in blocks if b["type"] == "image"]
    assert image_blocks and image_blocks[0]["image_url"] == "https://example.com/presigned"
    buttons = [b for b in blocks if b["type"] == "actions"]
    assert buttons[0]["elements"][0]["url"] == "https://example.com/presigned"
    assert "1h" in buttons[0]["elements"][0]["text"]["text"]


def test_share_posts_card_and_returns_url(
    s3: Any, slack: FakeSlack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _obj(s3)
    monkeypatch.setenv("S3F_SLACK_WEBHOOK_URL", WEBHOOK)
    url = share.share("bkt", "data/pic.png", client=s3)
    assert "data/pic.png" in url
    assert slack.calls and slack.calls[0]["blocks"][0]["type"] == "header"  # type: ignore[index]


def test_share_non_200_raises_slack_error(
    s3: Any, slack: FakeSlack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _obj(s3)
    monkeypatch.setenv("S3F_SLACK_WEBHOOK_URL", WEBHOOK)
    slack.status = 400
    slack.body = b"invalid_payload"
    with pytest.raises(S3fSlackError, match="invalid_payload") as excinfo:
        share.share("bkt", "data/pic.png", client=s3)
    assert excinfo.value.url and "data/pic.png" in excinfo.value.url


def test_share_no_slack_skips_post(s3: Any, slack: FakeSlack) -> None:
    _obj(s3)
    url = share.share("bkt", "data/pic.png", client=s3, no_slack=True)
    assert "data/pic.png" in url
    assert slack.calls == []


def test_share_without_webhook_env_raises(s3: Any) -> None:
    _obj(s3)
    with pytest.raises(S3fSlackError, match="S3F_SLACK_WEBHOOK_URL"):
        share.share("bkt", "data/pic.png", client=s3)
