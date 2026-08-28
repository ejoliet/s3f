"""boto3 paginator -> tab-separated line stream, with anonymous-mode detection."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError

from s3f import S3fAccessDenied, S3fError, S3fNoSuchBucket, meter


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, ""))
    except ValueError:
        return default


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def parse_s3uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("s3://"):
        raise ValueError(f"not an s3:// URI: {uri!r}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"missing bucket in {uri!r}")
    return bucket, prefix


def make_client(anonymous: bool = False) -> Any:
    """S3 client with adaptive retries; unsigned when anonymous or no credentials.

    AIDEV-NOTE: anonymous-mode detection — public Open Data buckets must work
    with zero AWS config, so missing credentials silently fall back to UNSIGNED.
    """
    anonymous = anonymous or env_bool("S3F_ANONYMOUS")
    session = boto3.session.Session()
    if not anonymous and session.get_credentials() is None:
        anonymous = True
    kwargs: dict[str, Any] = {"retries": {"mode": "adaptive", "total_max_attempts": 5}}
    if anonymous:
        kwargs["signature_version"] = UNSIGNED
    return session.client("s3", config=Config(**kwargs))


def _map_client_error(exc: ClientError, bucket: str) -> S3fError:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    if code in {"NoSuchBucket", "404"}:
        return S3fNoSuchBucket(f"no such bucket: {bucket}")
    if code in {"AccessDenied", "403", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
        return S3fAccessDenied(
            f"access denied on s3://{bucket} — try --anonymous (public bucket) "
            "or set AWS_PROFILE"
        )
    return S3fError(str(exc))


def iter_lines(
    bucket: str,
    prefix: str,
    *,
    client: Any = None,
    anonymous: bool = False,
    page_size: int | None = None,
    max_keys: int | None = None,
    delimiter: str | None = None,
) -> Iterator[str]:
    """Yield `key<TAB>size<TAB>last_modified<TAB>storage_class` per object, lazily.

    Never accumulates keys in memory — fzf holds the list. Directory prefixes
    (delimited mode) are yielded as `prefix/<TAB>-<TAB>-<TAB>PRE`.
    """
    client = client if client is not None else make_client(anonymous)
    page_size = page_size or env_int("S3F_LIST_PAGE_SIZE", 1000)
    max_keys = max_keys or env_int("S3F_LIST_MAX_KEYS", 2_000_000)
    paginate_kwargs: dict[str, Any] = {
        "Bucket": bucket,
        "Prefix": prefix,
        "PaginationConfig": {"PageSize": page_size},
    }
    if delimiter:
        paginate_kwargs["Delimiter"] = delimiter
    yielded = 0
    try:
        for page in client.get_paginator("list_objects_v2").paginate(**paginate_kwargs):
            page_bytes = 0
            page_objects = 0
            for cp in page.get("CommonPrefixes") or []:
                if yielded >= max_keys:
                    break
                yield f"{cp['Prefix']}\t-\t-\tPRE"
                yielded += 1
            for obj in page.get("Contents") or []:
                if yielded >= max_keys:
                    break
                storage = obj.get("StorageClass", "STANDARD")
                yield f"{obj['Key']}\t{obj['Size']}\t{obj['LastModified'].isoformat()}\t{storage}"
                yielded += 1
                page_bytes += int(obj["Size"])
                page_objects += 1
            if page_objects:
                meter.record_browsed(page_bytes, page_objects)
            if yielded >= max_keys:
                return
    except ClientError as exc:
        raise _map_client_error(exc, bucket) from exc
