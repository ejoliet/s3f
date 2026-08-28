"""fzf invocation builder: binds, preview command, colors."""

from __future__ import annotations

import shutil


def clipboard_cmd() -> str:
    if shutil.which("pbcopy"):
        return "pbcopy"
    if shutil.which("xclip"):
        return "xclip -selection clipboard"
    return "xsel -ib"


def build_fzf_command(
    bucket: str,
    prefix: str,
    *,
    anonymous: bool,
    delimited: bool,
    query: str = "",
) -> tuple[list[str], dict[str, str]]:
    """Return (argv, extra_env) for the fzf UI over `s3f list` reloads.

    AIDEV-NOTE: fzf holds the (potentially multi-million line) list; `reload`
    restarts the feeder without restarting fzf — that is how prefix pivoting
    works. Bucket travels via S3F_BUCKET env, not per-line.
    """
    flags = ""
    if anonymous:
        flags += " --anonymous"
    if delimited:
        flags += " --delimited"

    def list_cmd(pfx: str) -> str:
        return f"s3f list s3://{bucket}/{pfx}{flags}"

    clip = clipboard_cmd()
    argv = [
        "fzf",
        "--ansi",
        "--delimiter",
        "\t",
        "--nth",
        "1",
        "--query",
        query,
        "--preview",
        "s3f preview {1}",
        "--preview-window",
        "right:60%:wrap",
        "--header",
        (
            f"s3://{bucket}/{prefix}  "
            "enter=share+exit  ctrl-s=share  ctrl-y=copy URL  "
            "ctrl-r=reload {q}  ctrl-p=descend"
        ),
        "--color",
        "header:italic:dim,hl:cyan,hl+:bright-cyan",
        "--bind",
        f"start:reload:{list_cmd(prefix)}",
        "--bind",
        f"ctrl-r:reload({list_cmd('{q}')})",
        "--bind",
        f"ctrl-p:reload({list_cmd('{1}')})",
        "--bind",
        "enter:become(s3f share {1})",
        "--bind",
        "ctrl-s:execute(s3f share {1})",
        "--bind",
        f"ctrl-y:execute-silent(s3f share {{1}} --no-slack | tail -n1 | {clip})",
    ]
    env = {
        "S3F_BUCKET": bucket,
        "S3F_ANONYMOUS": "true" if anonymous else "false",
    }
    return argv, env
