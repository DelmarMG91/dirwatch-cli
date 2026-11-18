"""Tests for snapshotting, diffing and debounce aggregation."""
from __future__ import annotations

import pytest

from dirwatch_cli.watcher import (
    DEFAULT_IGNORE,
    Debouncer,
    Diff,
    Snapshot,
    diff,
    match_any,
)


def _write(path, content="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_snapshot_empty_directory(tmp_path):
    snapshot = Snapshot([str(tmp_path)])
    assert snapshot.scan() == {}


def test_snapshot_detects_added_file(tmp_path):
    _write(tmp_path / "a.txt", "one")
    before = Snapshot([str(tmp_path)]).scan()
    _write(tmp_path / "b.txt", "two")
    after = Snapshot([str(tmp_path)]).scan()

    changes = diff(before, after)
    assert changes.added == ("b.txt",)
    assert changes.modified == ()
    assert changes.deleted == ()


def test_snapshot_detects_modified_file(tmp_path):
    target = tmp_path / "a.txt"
    _write(target, "one")
    before = Snapshot([str(tmp_path)]).scan()
    _write(target, "two-two-two")
    after = Snapshot([str(tmp_path)]).scan()

    changes = diff(before, after)
    assert changes.modified == ("a.txt",)
    assert changes.added == ()
    assert changes.deleted == ()


def test_snapshot_detects_deleted_file(tmp_path):
    target = tmp_path / "gone.txt"
    _write(target, "bye")
    before = Snapshot([str(tmp_path)]).scan()
    target.unlink()
    after = Snapshot([str(tmp_path)]).scan()

    changes = diff(before, after)
    assert changes.deleted == ("gone.txt",)


def test_snapshot_ignores_default_directories(tmp_path):
    _write(tmp_path / ".git" / "config", "[core]")
    _write(tmp_path / "__pycache__" / "mod.cpython-311.pyc", "bytecode")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "module")
    _write(tmp_path / ".venv" / "pyvenv.cfg", "home = /usr")
    _write(tmp_path / "src" / "main.py", "print(1)")

    files = Snapshot([str(tmp_path)]).scan()
    assert list(files) == ["src/main.py"]
    for ignored in DEFAULT_IGNORE:
        assert not any(part == ignored for path in files for part in path.split("/"))


def test_snapshot_custom_ignore_glob(tmp_path):
    _write(tmp_path / "keep.py", "keep")
    _write(tmp_path / "skip.log", "noise")
    _write(tmp_path / "logs" / "debug.log", "noise")

    files = Snapshot([str(tmp_path)], ignore=("*.log", "logs")).scan()
    assert files == {"keep.py": files["keep.py"]}


def test_snapshot_pattern_filter(tmp_path):
    _write(tmp_path / "a.py", "a")
    _write(tmp_path / "b.txt", "b")
    _write(tmp_path / "pkg" / "c.py", "c")

    files = Snapshot([str(tmp_path)], patterns=("*.py",)).scan()
    assert set(files) == {"a.py", "pkg/c.py"}


def test_snapshot_multiple_roots_are_prefixed(tmp_path):
    _write(tmp_path / "one" / "a.txt", "a")
    _write(tmp_path / "two" / "b.txt", "b")

    files = Snapshot([str(tmp_path / "one"), str(tmp_path / "two")]).scan()
    assert set(files) == {"one/a.txt", "two/b.txt"}


def test_snapshot_requires_a_root():
    with pytest.raises(ValueError):
        Snapshot([])


def test_diff_reports_all_three_groups(tmp_path):
    _write(tmp_path / "stay.txt", "same")
    _write(tmp_path / "change.txt", "before")
    _write(tmp_path / "remove.txt", "bye")
    before = Snapshot([str(tmp_path)]).scan()

    _write(tmp_path / "change.txt", "after-after")
    (tmp_path / "remove.txt").unlink()
    _write(tmp_path / "fresh.txt", "new")
    after = Snapshot([str(tmp_path)]).scan()

    changes = diff(before, after)
    assert isinstance(changes, Diff)
    assert changes.added == ("fresh.txt",)
    assert changes.modified == ("change.txt",)
    assert changes.deleted == ("remove.txt",)
    assert bool(changes) is True


def test_diff_unchanged_is_empty(tmp_path):
    _write(tmp_path / "a.txt", "stable")
    before = Snapshot([str(tmp_path)]).scan()
    after = Snapshot([str(tmp_path)]).scan()

    changes = diff(before, after)
    assert not changes
    assert changes.as_events() == []


def test_diff_as_events_order():
    changes = Diff(added=("a.txt",), modified=("b.txt",), deleted=("c.txt",))
    assert changes.as_events() == [
        ("added", "a.txt"),
        ("modified", "b.txt"),
        ("deleted", "c.txt"),
    ]


def test_match_any_checks_name_and_path():
    assert match_any("main.py", "src/main.py", ("*.py",))
    assert match_any("main.py", "src/main.py", ("src/*.py",))
    assert not match_any("main.py", "src/main.py", ("*.js",))


def test_debouncer_waits_for_quiet_period():
    debouncer = Debouncer(0.3)
    debouncer.add([("modified", "a.txt")], now=100.0)
    assert debouncer.ready(100.29) is False
    assert debouncer.ready(100.3) is True


def test_debouncer_aggregates_burst():
    debouncer = Debouncer(0.2)
    debouncer.add([("modified", "a.txt")], now=0.0)
    debouncer.add([("added", "b.txt")], now=0.1)
    assert debouncer.pending == 2
    assert debouncer.ready(0.25) is False
    assert debouncer.ready(0.3) is True

    events = debouncer.drain()
    assert events == [("modified", "a.txt"), ("added", "b.txt")]
    assert debouncer.pending == 0
    assert debouncer.ready(999.0) is False


def test_debouncer_merges_duplicate_paths_by_precedence():
    debouncer = Debouncer(0.0)
    debouncer.add([("modified", "a.txt")], now=0.0)
    debouncer.add([("deleted", "a.txt")], now=0.0)
    assert debouncer.drain() == [("deleted", "a.txt")]

    debouncer.add([("deleted", "b.txt")], now=1.0)
    debouncer.add([("added", "b.txt")], now=1.0)
    assert debouncer.drain() == [("added", "b.txt")]


def test_debouncer_rejects_negative_delay():
    with pytest.raises(ValueError):
        Debouncer(-1)


def test_debouncer_ignores_empty_add():
    debouncer = Debouncer(0.0)
    debouncer.add([], now=0.0)
    assert debouncer.pending == 0
    assert debouncer.ready(1.0) is False
