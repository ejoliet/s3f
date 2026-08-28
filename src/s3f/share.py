"""Presign + Slack Block Kit webhook POST (stdlib urllib, no slack_sdk)."""

from __future__ import annotations

import json
import os
import posixpath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from s3f import S3fSlackError, meter
from s3f.listing import env_int
from s3f.previews import FITS_EXTS, IMAGE_EXTS


def presign(client: Any, bucket: str, key: str, ttl: int) -> str:
    url: str = client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=ttl
    )
    return url


def human_ttl(ttl: int) -> str:
    if ttl % 3600 == 0:
        return f"{ttl // 3600}h"
    if ttl % 60 == 0:
        return f"{ttl // 60}m"
    return f"{ttl}s"


def build_card(
    *,
    bucket: str,
    key: str,
    size: int,
    last_modified: str,
    url: str,
    ttl: int,
    facts: dict[str, str] | None = None,
) -> dict[str, Any]:
    basename = posixpath.basename(key)
    fields = [
        {"type": "mrkdwn", "text": f"*Bucket:*\n{bucket}"},
        {"type": "mrkdwn", "text": f"*Key:*\n{key}"},
        {"type": "mrkdwn", "text": f"*Size:*\n{meter.human_bytes(size)}"},
        {"type": "mrkdwn", "text": f"*Last modified:*\n{last_modified}"},
    ]
    for name, value in (facts or {}).items():
        fields.append({"type": "mrkdwn", "text": f"*{name}:*\n{value}"})
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": basename}},
        {"type": "section", "fields": fields[:10]},  # Block Kit caps fields at 10
    ]
    if posixpath.splitext(key)[1].lower() in IMAGE_EXTS:
        blocks.append({"type": "image", "image_url": url, "alt_text": basename})
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": f"Open (presigned, {human_ttl(ttl)})",
                    },
                    "url": url,
                }
            ],
        }
    )
    label = os.environ.get("S3F_SLACK_CHANNEL_LABEL")
    if label:
        blocks.append(
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"shared via s3f → {label}"}],
            }
        )
    return {"blocks": blocks}


def _facts(client: Any, bucket: str, key: str, size: int) -> dict[str, str]:
    """Type-specific card facts (row count, TELESCOP). Best-effort, metered reads."""
    ext = posixpath.splitext(key)[1].lower()
    try:
        if ext == ".parquet":
            import pyarrow.parquet as pq

            from s3f.previews import RangedS3File

            md = pq.ParquetFile(RangedS3File(client, bucket, key, size)).metadata
            return {"Rows": f"{md.num_rows:,}", "Row groups": str(md.num_row_groups)}
        if ext in FITS_EXTS:
            from s3f.previews.fits import read_header

            header, _ = read_header(client, bucket, key, size)
            return {
                k: str(header[k])
                for k in ("TELESCOP", "INSTRUME", "DATE-OBS")
                if k in header
            }
    except Exception:  # noqa: BLE001 — facts are decoration, never block a share
        pass
    return {}


def _post(webhook: str, card: dict[str, Any], url: str) -> None:
    req = Request(
        webhook,
        data=json.dumps(card).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise S3fSlackError(f"Slack webhook returned {exc.code}: {body}", url=url) from exc
    except URLError as exc:
        raise S3fSlackError(f"Slack webhook unreachable: {exc.reason}", url=url) from exc


def share(
    bucket: str,
    key: str,
    *,
    client: Any,
    ttl: int | None = None,
    no_slack: bool = False,
) -> str:
    """Presign KEY, post a Block Kit card unless no_slack; always return the URL."""
    ttl = ttl or env_int("S3F_PRESIGN_TTL", 3600)
    head = client.head_object(Bucket=bucket, Key=key)
    size = int(head["ContentLength"])
    url = presign(client, bucket, key, ttl)
    if no_slack:
        return url
    webhook = os.environ.get("S3F_SLACK_WEBHOOK_URL")
    if not webhook:
        raise S3fSlackError(
            "S3F_SLACK_WEBHOOK_URL not set — export it or use --no-slack", url=url
        )
    card = build_card(
        bucket=bucket,
        key=key,
        size=size,
        last_modified=head["LastModified"].isoformat(),
        url=url,
        ttl=ttl,
        facts=_facts(client, bucket, key, size),
    )
    _post(webhook, card, url)
    return url
