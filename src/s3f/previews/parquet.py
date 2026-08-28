"""Parquet footer preview: schema, row count, compression — no data pages fetched."""

from __future__ import annotations

from typing import Any

import pyarrow.parquet as pq

from s3f import meter
from s3f.previews import RangedS3File, footer


def render(client: Any, bucket: str, key: str, size: int) -> str:
    f = RangedS3File(client, bucket, key, size)
    pf = pq.ParquetFile(f)
    md = pf.metadata
    compression = (
        md.row_group(0).column(0).compression if md.num_row_groups else "n/a"
    )
    lines = [key, ""]
    lines += [f"  {field.name}: {field.type}" for field in pf.schema_arrow]
    lines += [
        "",
        f"num_rows: {md.num_rows}",
        f"num_row_groups: {md.num_row_groups}",
        f"file size: {meter.human_bytes(size)}",
        f"compression: {compression}",
        f"created by: {md.created_by}",
        "",
        footer(f.bytes_fetched, size),
    ]
    return "\n".join(lines)
