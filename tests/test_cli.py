"""Tests for the CLI layer."""
from __future__ import annotations

import io

import pytest

from dirwatch_cli import __version__, cli
from dirwatch_cli.watcher import Snapshot


class FakeRunner:
    """Minimal stand-in for :class:`CommandRunner`."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls = 0

    def run(self) -> int:
        self.calls += 1
        return self.code


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_help_mentions_options(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--pattern", "--ignore", "--debounce", "--interval", "--cmd", "--once", "--clear", "--quiet"):
        assert flag in out


def test_cli_missing_directory_returns_2(capsys):
    assert cli.main(["/definitely/not/a/real/directory"]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.paths == []
    assert args.debounce == 0.3
    assert args.interval == 0.5
    assert args.pattern is None
    assert args.ignore is None
    assert args.cmd is None
    assert args.once is False
    assert args.quiet is False


def test_format_events_markers():
    lines = cli.format_events([("added", "a.py"), ("modified", "b.py"), ("deleted", "c.py")])
    assert lines == ["  + a.py", "  ~ b.py", "  - c.py"]


def test_run_initial_executes_command_once():
    runner = FakeRunner(code=7)
    stream = io.StringIO()
    code = cli.run_initial(runner, quiet=False, stream=stream)
    assert runner.calls == 1
    assert code == 7
    output = stream.getvalue()
    assert "initial run" in output
    assert "exit code 7" in output


def test_run_initial_quiet_has_no_output():
    runner = FakeRunner()
    stream = io.StringIO()
    assert cli.run_initial(runner, quiet=True, stream=stream) == 0
    assert runner.calls == 1
    assert stream.getvalue() == ""


def test_watch_loop_runs_command_after_change(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("one", encoding="utf-8")
    snapshot = Snapshot([str(tmp_path)])
    runner = FakeRunner()
    state = {"ticks": 0}

    def fake_sleep(_seconds: float) -> None:
        state["ticks"] += 1
        if state["ticks"] == 2:
            target.write_text("two-two-two", encoding="utf-8")
        if state["ticks"] > 8:
            raise KeyboardInterrupt

    result = cli.watch_loop(
        snapshot,
        runner,
        debounce=0.0,
        interval=0.01,
        quiet=True,
        stream=io.StringIO(),
        sleep=fake_sleep,
        clock=lambda: float(state["ticks"]),
    )

    assert result == 0
    assert runner.calls >= 1


def test_watch_loop_without_command_only_reports(tmp_path):
    snapshot = Snapshot([str(tmp_path)])
    state = {"ticks": 0}

    def fake_sleep(_seconds: float) -> None:
        state["ticks"] += 1
        raise KeyboardInterrupt

    stream = io.StringIO()
    result = cli.watch_loop(
        snapshot,
        None,
        debounce=0.0,
        interval=0.01,
        quiet=False,
        stream=stream,
        sleep=fake_sleep,
        clock=lambda: float(state["ticks"]),
    )

    assert result == 0
    assert "Watched for" in stream.getvalue()
