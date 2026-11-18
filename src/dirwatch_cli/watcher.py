"""Filesystem snapshotting and change aggregation for dirwatch-cli.

The module is deliberately dependency free: it walks a directory tree with
:func:`os.walk`, records each file's ``(mtime_ns, size)`` state and compares two
snapshots to classify *added*, *modified* and *deleted* relative paths.

A small :class:`Debouncer` helper coalesces bursts of events so the CLI only
fires an editor command once a quiet window has elapsed.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

#: A file's identity for change detection: ``(mtime_ns, size)``.
FileState = Tuple[int, int]

#: Directory names / globs ignored by default.
DEFAULT_IGNORE: Tuple[str, ...] = (".git", "__pycache__", "node_modules", ".venv")


def match_any(name: str, relpath: str, patterns: Iterable[str]) -> bool:
    """Return ``True`` if ``name`` or ``relpath`` matches any ``pattern``.

    Patterns use :mod:`fnmatch` semantics and are tested against both the bare
    file name (``foo.py``) and the slash-normalised relative path
    (``src/foo.py``) so that ``*.py`` and ``src/*.py`` both behave intuitively.
    """
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(relpath, pattern):
            return True
    return False


@dataclass(frozen=True)
class Diff:
    """The result of comparing two snapshots."""

    added: Tuple[str, ...] = ()
    modified: Tuple[str, ...] = ()
    deleted: Tuple[str, ...] = ()

    def __bool__(self) -> bool:
        """A ``Diff`` is truthy when it carries at least one change."""
        return bool(self.added or self.modified or self.deleted)

    def as_events(self) -> List[Tuple[str, str]]:
        """Flatten the diff into ``(kind, path)`` pairs for printing/aggregation."""
        events: List[Tuple[str, str]] = []
        events.extend(("added", path) for path in self.added)
        events.extend(("modified", path) for path in self.modified)
        events.extend(("deleted", path) for path in self.deleted)
        return events


def diff(old: Dict[str, FileState], new: Dict[str, FileState]) -> Diff:
    """Compare two ``{path: (mtime_ns, size)}`` mappings.

    Parameters
    ----------
    old, new:
        Snapshots produced by :meth:`Snapshot.scan`.

    Returns
    -------
    Diff
        Sorted tuples of relative paths grouped into added / modified / deleted.
    """
    added = tuple(sorted(path for path in new if path not in old))
    deleted = tuple(sorted(path for path in old if path not in new))
    modified = tuple(
        sorted(path for path in new if path in old and new[path] != old[path])
    )
    return Diff(added=added, modified=modified, deleted=deleted)


class Snapshot:
    """A point-in-time view of one or more directory trees.

    Parameters
    ----------
    roots:
        One or more directory paths to watch. Relative paths are resolved to
        absolute paths. With multiple roots each key is prefixed by the root's
        basename to keep the keys unique.
    patterns:
        fnmatch glob patterns used as an include filter (default ``("*",)``).
    ignore:
        Directory names or glob patterns to skip. Matching entries are pruned
        during the walk and also filter individual files.
    """

    def __init__(
        self,
        roots: Sequence[str | os.PathLike[str]],
        patterns: Sequence[str] = ("*",),
        ignore: Sequence[str] = DEFAULT_IGNORE,
    ) -> None:
        if not roots:
            raise ValueError("at least one root path is required")
        self.roots: List[str] = [os.path.abspath(os.fspath(root)) for root in roots]
        self.patterns: Tuple[str, ...] = tuple(patterns)
        self.ignore: Tuple[str, ...] = tuple(ignore)

    def _rel(self, root: str, dirpath: str, name: str) -> str:
        full = os.path.join(dirpath, name)
        return os.path.relpath(full, root).replace(os.sep, "/")

    def _ignored(self, name: str, relpath: str) -> bool:
        if name in self.ignore:
            return True
        return match_any(name, relpath, self.ignore)

    def _included(self, name: str, relpath: str) -> bool:
        return match_any(name, relpath, self.patterns)

    def scan(self) -> Dict[str, FileState]:
        """Walk the roots and return ``{relative_path: (mtime_ns, size)}``."""
        result: Dict[str, FileState] = {}
        multi = len(self.roots) > 1
        for root in self.roots:
            prefix = os.path.basename(root) if multi else ""
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(
                    name
                    for name in dirnames
                    if not self._ignored(name, self._rel(root, dirpath, name))
                )
                for name in filenames:
                    relpath = self._rel(root, dirpath, name)
                    if self._ignored(name, relpath):
                        continue
                    if not self._included(name, relpath):
                        continue
                    full = os.path.join(dirpath, name)
                    try:
                        stat = os.stat(full)
                    except OSError:
                        # File vanished or is unreadable between listing and stat.
                        continue
                    key = f"{prefix}/{relpath}" if prefix else relpath
                    result[key] = (stat.st_mtime_ns, stat.st_size)
        return result


class Debouncer:
    """Coalesce a stream of events, releasing them after a quiet period.

    ``add`` timestamps the latest change with the caller supplied clock value;
    ``ready`` reports whether ``delay`` seconds have elapsed since that change;
    ``drain`` returns the merged events and resets the buffer.

    When the same path is touched multiple times within a window, the most
    significant event wins in the order added > deleted > modified.
    """

    _PRECEDENCE = {"added": 0, "deleted": 1, "modified": 2}

    def __init__(self, delay: float) -> None:
        if delay < 0:
            raise ValueError("debounce delay must be non-negative")
        self.delay = float(delay)
        self._events: List[Tuple[str, str]] = []
        self._last_change: Optional[float] = None

    @property
    def pending(self) -> int:
        """Number of raw events currently buffered."""
        return len(self._events)

    def add(self, events: Iterable[Tuple[str, str]], now: float) -> None:
        """Record ``(kind, path)`` events observed at ``now``."""
        events = list(events)
        if not events:
            return
        self._events.extend(events)
        self._last_change = now

    def ready(self, now: float) -> bool:
        """Return ``True`` when the buffer is non-empty and the window elapsed."""
        if not self._events or self._last_change is None:
            return False
        # Small tolerance so exact decimal boundaries (0.3 - 0.0) do not fail
        # because of binary floating point representation.
        return (now - self._last_change) >= self.delay - 1e-9

    def drain(self) -> List[Tuple[str, str]]:
        """Return merged events (sorted by path) and clear the buffer."""
        best: Dict[str, str] = {}
        for kind, path in self._events:
            current = best.get(path)
            if current is None or self._PRECEDENCE[kind] < self._PRECEDENCE[current]:
                best[path] = kind
        self._events = []
        self._last_change = None
        return [(best[path], path) for path in sorted(best)]
