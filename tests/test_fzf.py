from s3f import fzf


def test_command_shape() -> None:
    cmd, env = fzf.build_fzf_command("bkt", "pre/", anonymous=True, delimited=False)
    assert cmd[0] == "fzf"
    joined = " ".join(cmd)
    assert "--delimiter" in joined
    assert "s3f preview {1}" in joined
    assert "start:reload:" in joined
    assert "ctrl-r:reload" in joined
    assert "ctrl-p:reload" in joined
    assert "enter:become(s3f share {1})" in joined
    assert "ctrl-s:execute" in joined
    assert "ctrl-y:execute-silent" in joined
    assert env["S3F_BUCKET"] == "bkt"
    assert env["S3F_ANONYMOUS"] == "true"


def test_list_cmd_carries_prefix_and_flags() -> None:
    cmd, _ = fzf.build_fzf_command("bkt", "pre/", anonymous=True, delimited=True)
    joined = " ".join(cmd)
    assert "s3f list s3://bkt/pre/" in joined
    assert "--anonymous" in joined
    assert "--delimited" in joined


def test_clipboard_cmd_known_tool() -> None:
    assert fzf.clipboard_cmd() in {"pbcopy", "xclip -selection clipboard", "xsel -ib"}
