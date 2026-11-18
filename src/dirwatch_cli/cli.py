"""Command line interface for dirwatch-cli."""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from typing import IO, Iterable, List, Optional, Sequence, Tuple

from . import __version__
from .runner import CommandRunner
from .watcher import DEFAULT_IGNORE, Debouncer, Diff, Snapshot, diff

_EVENT_MARKERS = {"added": "+", "modified": "~", "deleted": "-"}


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser used by :func:`main`."""
    parser = argparse.ArgumentParser(
        prog="dirwatch",
        description=(
            "Watch directories for changes and run a command after each burst. "
            "A lightweight, dependency-free alternative to entr and watchexec."
        ),
        epilog=(
            "examples:\n"
            "  dirwatch src --pattern '*.py' --cmd 'pytest -q'\n"
            "  dirwatch . --ignore '*.log' --cmd 'make' --debounce 0.5\n"
            "  dirwatch src tests --once --cmd 'python -m pytest -q'\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATHS",
        help="directories to watch (default: the current directory)",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        metavar="GLOB",
        help="include only files matching GLOB; repeatable (default: *)",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        metavar="GLOB",
        help=(
            "additional directory name or glob to ignore; repeatable "
            "(default ignores: .git, __pycache__, node_modules, .venv)"
        ),
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=0.3,
        metavar="SECONDS",
        help="quiet period used to aggregate change events (default: 0.3)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="polling interval between directory scans (default: 0.5)",
    )
    parser.add_argument(
        "--cmd",
        metavar="CMD",
        help="command to execute after each change burst (run through the shell)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="clear the terminal before executing the command",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="run the command once immediately at startup, then keep watching",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress event banners and status lines",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show the version number and exit",
    )
    return parser


def format_events(events: Iterable[Tuple[str, str]]) -> List[str]:
    """Render ``(kind, path)`` events as indented, marked display lines."""
    lines: List[str] = []
    for kind, path in events:
        lines.append(f"  {_EVENT_MARKERS.get(kind, '?')} {path}")
    return lines


def run_initial(runner: CommandRunner, *, quiet: bool = False, stream: IO[str] = sys.stdout) -> int:
    """Execute the command once for ``--once`` and return its exit code."""
    if not quiet:
        stamp = datetime.now().strftime("%H:%M:%S")
        stream.write(f"[{stamp}] initial run\n")
        stream.flush()
    code = runner.run()
    if not quiet:
        stamp = datetime.now().strftime("%H:%M:%S")
        stream.write(f"[{stamp}] exit code {code}\n")
        stream.flush()
    return code


def _describe_roots(roots: Sequence[str]) -> str:
    if len(roots) == 1:
        return roots[0]
    return ", ".join(roots)


def watch_loop(
    snapshot: Snapshot,
    runner: Optional[CommandRunner],
    *,
    debounce: float,
    interval: float,
    quiet: bool = False,
    stream: IO[str] = sys.stdout,
    sleep=time.sleep,
    clock=time.monotonic,
) -> int:
    """Poll ``snapshot`` until interrupted and run ``runner`` on change bursts."""
    debouncer = Debouncer(debounce)
    previous = snapshot.scan()
    triggers = 0
    started = clock()
    try:
        while True:
            sleep(interval)
            current = snapshot.scan()
            changes: Diff = diff(previous, current)
            previous = current
            now = clock()
            events = changes.as_events()
            if events:
                debouncer.add(events, now)
            if not debouncer.ready(now):
                continue
            batch = debouncer.drain()
            triggers += 1
            if not quiet:
                stamp = datetime.now().strftime("%H:%M:%S")
                stream.write(f"[{stamp}] {len(batch)} change(s):\n")
                for line in format_events(batch):
                    stream.write(line + "\n")
                stream.flush()
            if runner is not None:
                code = runner.run()
                if not quiet:
                    stamp = datetime.now().strftime("%H:%M:%S")
                    stream.write(f"[{stamp}] exit code {code}\n")
                    stream.flush()
    except KeyboardInterrupt:
        elapsed = clock() - started
        if not quiet:
            minutes, seconds = divmod(elapsed, 60.0)
            stream.write(
                f"\nWatched for {int(minutes):d}:{seconds:04.1f} "
                f"({triggers} trigger(s))\n"
            )
            stream.flush()
        return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for the ``dirwatch`` console script."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.interval <= 0:
        parser.error("--interval must be greater than zero")
    if args.debounce < 0:
        parser.error("--debounce must be zero or greater")

    roots: List[str] = list(args.paths) or ["."]
    missing = [path for path in roots if not os.path.isdir(path)]
    if missing:
        for path in missing:
            sys.stderr.write(f"dirwatch: not a directory: {path}\n")
        return 2

    patterns: Tuple[str, ...] = tuple(args.pattern) if args.pattern else ("*",)
    ignore: Tuple[str, ...] = tuple(DEFAULT_IGNORE) + tuple(args.ignore or ())
    snapshot = Snapshot(roots, patterns=patterns, ignore=ignore)
    runner = CommandRunner(args.cmd, clear=args.clear) if args.cmd else None

    if not args.quiet:
        sys.stdout.write(
            f"dirwatch {__version__} — watching {_describe_roots(snapshot.roots)}\n"
        )
        sys.stdout.write(
            f"pattern: {', '.join(patterns)} | interval: {args.interval}s | "
            f"debounce: {args.debounce}s\n"
        )
        if runner is None:
            sys.stdout.write("no --cmd given: printing events only\n")
        sys.stdout.flush()

    if args.once and runner is not None:
        run_initial(runner, quiet=args.quiet, stream=sys.stdout)

    return watch_loop(
        snapshot,
        runner,
        debounce=args.debounce,
        interval=args.interval,
        quiet=args.quiet,
        stream=sys.stdout,
    )


if __name__ == "__main__":  # pragma: no cover - exercised via __main__.py
    raise SystemExit(main())
