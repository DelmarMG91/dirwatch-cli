"""Tests for CommandRunner."""
from __future__ import annotations

import io
import sys

import pytest

from dirwatch_cli.runner import CommandRunner


def test_runner_success_exit_code():
    runner = CommandRunner([sys.executable, "-c", "print('ok')"])
    assert runner.run() == 0


def test_runner_failure_exit_code():
    runner = CommandRunner([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert runner.run() == 3


def test_runner_shell_string_command():
    runner = CommandRunner(f'"{sys.executable}" -c "print(42)"')
    assert runner.run() == 0


def test_runner_clear_writes_escape_sequence():
    stream = io.StringIO()
    runner = CommandRunner([sys.executable, "-c", "pass"], clear=True, stream=stream)
    assert runner.run() == 0
    assert stream.getvalue() == "\033[2J\033[H"


def test_runner_rejects_empty_command():
    with pytest.raises(ValueError):
        CommandRunner("")
    with pytest.raises(ValueError):
        CommandRunner([])


def test_runner_missing_executable_raises():
    runner = CommandRunner(["definitely-not-a-real-executable-xyz"])
    with pytest.raises(OSError):
        runner.run()
