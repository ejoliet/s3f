"""click entrypoint: browse, list, preview, share, stats."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import click

from s3f import S3fError, S3fSlackError, listing, meter, previews
from s3f import share as share_mod
from s3f.fzf import build_fzf_command
from s3f.listing import env_bool


def _die(exc: S3fError) -> None:
    click.echo(f"error: {exc}", err=True)
    sys.exit(exc.exit_code)


def _parse(s3uri: str) -> tuple[str, str]:
    try:
        return listing.parse_s3uri(s3uri)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc


@click.group()
@click.version_option()
def main() -> None:
    """fzf over a billion S3 objects — preview terabytes, download kilobytes."""


@main.command("list")
@click.argument("s3uri")
@click.option("--anonymous", is_flag=True, help="Unsigned requests (public buckets).")
@click.option("--delimited", is_flag=True, help="Treat '/' prefixes as directories.")
def list_cmd(s3uri: str, anonymous: bool, delimited: bool) -> None:
    """Stream `key<TAB>size<TAB>last_modified<TAB>storage_class` lines (fzf feeder)."""
    bucket, prefix = _parse(s3uri)
    try:
        for line in listing.iter_lines(
            bucket,
            prefix,
            anonymous=anonymous,
            delimiter="/" if delimited else None,
        ):
            click.echo(line)
    except S3fError as exc:
        _die(exc)
    except BrokenPipeError:  # fzf closed the pipe (reload/quit) — normal
        pass


@main.command()
@click.argument("s3uri")
@click.option("--anonymous", is_flag=True, help="Unsigned requests (public buckets).")
@click.option("--delimited", is_flag=True, help="Treat '/' prefixes as directories.")
@click.option("--filter", "filter_", default="", help="Initial fuzzy query.")
def browse(s3uri: str, anonymous: bool, delimited: bool, filter_: str) -> None:
    """Spawn fzf over S3URI; previews are ranged GETs, enter shares to Slack."""
    if shutil.which("fzf") is None:
        click.echo("fzf not found — install fzf >= 0.44 (brew/apt install fzf)")
        sys.exit(1)
    bucket, prefix = _parse(s3uri)
    meter.reset()
    argv, extra_env = build_fzf_command(
        bucket, prefix, anonymous=anonymous, delimited=delimited, query=filter_
    )
    subprocess.run(argv, env={**os.environ, **extra_env})
    click.echo(meter.summary())


@main.command()
@click.argument("key")
def preview(key: str) -> None:
    """Render a ranged-GET preview of KEY (bucket via S3F_BUCKET).

    Never exits non-zero — errors render in the pane so fzf survives.
    """
    bucket = os.environ.get("S3F_BUCKET")
    if not bucket:
        click.echo("⚠ preview error: S3F_BUCKET not set")
        return
    click.echo(previews.render(bucket, key, anonymous=env_bool("S3F_ANONYMOUS")))


@main.command("share")
@click.argument("key")
@click.option("--ttl", type=int, default=None, help="Presigned URL lifetime (seconds).")
@click.option("--no-slack", is_flag=True, help="Presign only; skip the webhook.")
def share_cmd(key: str, ttl: int | None, no_slack: bool) -> None:
    """Presign KEY, post a Block Kit card to Slack, print the URL."""
    bucket = os.environ.get("S3F_BUCKET")
    if not bucket:
        click.echo("error: S3F_BUCKET not set (share runs inside `s3f browse`)")
        sys.exit(2)
    client = listing.make_client(env_bool("S3F_ANONYMOUS"))
    try:
        url = share_mod.share(bucket, key, client=client, ttl=ttl, no_slack=no_slack)
        click.echo(url)
    except S3fSlackError as exc:
        if exc.url:
            click.echo(exc.url)  # share never loses the URL
        click.echo(f"slack error: {exc}")
        sys.exit(exc.exit_code)
    except S3fError as exc:
        _die(exc)


@main.command()
def stats() -> None:
    """Print the session byte meter."""
    click.echo(meter.summary())
