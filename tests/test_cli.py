from typing import Any

import pytest
from click.testing import CliRunner

from s3f import meter
from s3f.cli import main
from tests.conftest import FakeSlack

WEBHOOK = "https://hooks.slack.com/services/T00/B00/XXX"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _fill(s3: Any) -> None:
    s3.create_bucket(Bucket="bkt")
    s3.put_object(Bucket="bkt", Key="a/one.txt", Body=b"hello")
    s3.put_object(Bucket="bkt", Key="a/two.txt", Body=b"world!")


def test_list_streams_lines(s3: Any, runner: CliRunner) -> None:
    _fill(s3)
    res = runner.invoke(main, ["list", "s3://bkt/a/"])
    assert res.exit_code == 0
    lines = res.output.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].split("\t")[0] == "a/one.txt"


def test_list_no_such_bucket_exit_4(s3: Any, runner: CliRunner) -> None:
    res = runner.invoke(main, ["list", "s3://missing-bkt/"])
    assert res.exit_code == 4


def test_list_bad_uri_fails(runner: CliRunner) -> None:
    res = runner.invoke(main, ["list", "http://nope"])
    assert res.exit_code != 0


def test_preview_requires_bucket_env_but_exits_zero(runner: CliRunner) -> None:
    res = runner.invoke(main, ["preview", "a/one.txt"])
    assert res.exit_code == 0  # never blank the fzf pane
    assert "S3F_BUCKET" in res.output


def test_preview_renders(s3: Any, runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _fill(s3)
    monkeypatch.setenv("S3F_BUCKET", "bkt")
    res = runner.invoke(main, ["preview", "a/one.txt"])
    assert res.exit_code == 0
    assert "hello" in res.output


def test_share_prints_url(
    s3: Any, runner: CliRunner, slack: FakeSlack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fill(s3)
    monkeypatch.setenv("S3F_BUCKET", "bkt")
    monkeypatch.setenv("S3F_SLACK_WEBHOOK_URL", WEBHOOK)
    res = runner.invoke(main, ["share", "a/one.txt"])
    assert res.exit_code == 0
    assert "https://" in res.output


def test_share_slack_failure_still_prints_url_exit_5(
    s3: Any, runner: CliRunner, slack: FakeSlack, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fill(s3)
    monkeypatch.setenv("S3F_BUCKET", "bkt")
    monkeypatch.setenv("S3F_SLACK_WEBHOOK_URL", WEBHOOK)
    slack.status = 404
    slack.body = b"channel_not_found"
    res = runner.invoke(main, ["share", "a/one.txt"])
    assert res.exit_code == 5
    assert "https://" in res.output  # share never loses the URL
    assert "channel_not_found" in res.output


def test_stats_prints_summary(runner: CliRunner) -> None:
    meter.reset()
    res = runner.invoke(main, ["stats"])
    assert res.exit_code == 0
    assert res.output.startswith("Browsed ")


def test_browse_requires_fzf(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    res = runner.invoke(main, ["browse", "s3://bkt/"])
    assert res.exit_code != 0
    assert "fzf" in res.output


def test_browse_spawns_fzf_and_prints_summary(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    class FakeProc:
        returncode = 0

    def fake_run(cmd: list[str], **kwargs: object) -> FakeProc:
        calls.append(cmd)
        return FakeProc()

    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("subprocess.run", fake_run)
    res = runner.invoke(main, ["browse", "s3://bkt/pre/", "--anonymous"])
    assert res.exit_code == 0
    assert calls and calls[0][0] == "fzf"
    assert "Browsed" in res.output
