"""Command execution for dirwatch-cli."""
from __future__ import annotations

import subprocess
import sys
from typing import IO, List, Optional, Sequence, Union

Command = Union[str, Sequence[str]]

_CLEAR_SEQUENCE = "\033[2J\033[H"


class CommandRunner:
    """Run a shell command and report its exit code.

    A string command is executed through the platform shell (``shell=True``),
    matching the behaviour of ``entr`` style watchers and keeping pipes,
    redirections and quoted arguments working. A list command is executed
    directly without a shell, which is handy on Windows and for tests.

    Parameters
    ----------
    command:
        Shell string or argv sequence to execute.
    clear:
        When true, clear the terminal before each run.
    stream:
        Output stream used for the clear escape sequence (defaults to stdout).
    """

    def __init__(
        self,
        command: Command,
        *,
        clear: bool = False,
        stream: Optional[IO[str]] = None,
    ) -> None:
        if isinstance(command, str) and not command.strip():
            raise ValueError("command must not be empty")
        if not isinstance(command, str) and not list(command):
            raise ValueError("command must not be empty")
        self.command: Command = command
        self.clear = bool(clear)
        self.stream: IO[str] = stream if stream is not None else sys.stdout

    def _clear_screen(self) -> None:
        try:
            self.stream.write(_CLEAR_SEQUENCE)
            self.stream.flush()
        except (OSError, ValueError):
            # A closed or non-tty stream must not break the watch loop.
            pass

    def run(self) -> int:
        """Execute the command and return its exit status.

        Raises
        ------
        FileNotFoundError
            If an argv-style command references a missing executable.
        OSError
            If the process cannot be started for any other reason.
        """
        if self.clear:
            self._clear_screen()
        if isinstance(self.command, str):
            completed = subprocess.run(self.command, shell=True)
        else:
            argv: List[str] = [str(part) for part in self.command]
            completed = subprocess.run(argv)
        return int(completed.returncode)
