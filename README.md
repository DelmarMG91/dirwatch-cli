# dirwatch-cli

Watch directories for changes and run a command after each burst — a tiny, dependency-free alternative to `entr` and `watchexec`.

[![CI](https://github.com/DelmarMG91/dirwatch-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/DelmarMG91/dirwatch-cli/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/dirwatch-cli.svg)](https://pypi.org/project/dirwatch-cli/)

## Features

- **Zero dependencies** — pure Python standard library, works anywhere Python 3.9+ runs.
- **Polling snapshots** — compares `(mtime_ns, size)` per file, so it works on network shares, containers and editors that do not emit filesystem events.
- **Include patterns** — watch only the files you care about with repeatable `--pattern` globs.
- **Ignore rules** — skips `.git`, `__pycache__`, `node_modules` and `.venv` by default; add your own names or globs with `--ignore`.
- **Debounced execution** — a burst of saves triggers the command once, after a configurable quiet period.
- **`--once` warm start** — run the command immediately at startup (handy for test watchers), then keep watching.
- **Readable event log** — every run prints a timestamped list of added (`+`), modified (`~`) and deleted (`-`) paths, plus the command's exit code.
- **Graceful shutdown** — `Ctrl-C` prints the total watch time and the number of triggered runs.

## Install

```bash
pip install dirwatch-cli
```

Or from a checkout, in editable mode:

```bash
git clone https://github.com/DelmarMG91/dirwatch-cli.git
cd dirwatch-cli
pip install -e .
```

Requires Python 3.9 or newer. No runtime dependencies.

## Quick Start

Watch `src/`, react only to Python files, and run the test suite after each save:

```bash
dirwatch src --pattern '*.py' --cmd 'pytest -q'
```

Example output:

```text
$ dirwatch src --pattern '*.py' --cmd 'pytest -q'
dirwatch 0.1.0 — watching /home/dev/demo/src
pattern: *.py | interval: 0.5s | debounce: 0.3s
[14:22:07] 2 change(s):
  ~ app.py
  + tests/test_app.py
.....                                                                    [100%]
5 passed in 0.08s
[14:22:08] exit code 0
^C
Watched for 0:00:18.4 (1 trigger(s))
```

Only the event log is printed by `dirwatch`; the command's own output streams to the same terminal, so test results and compiler errors stay visible.

## Usage

```text
dirwatch [PATHS...] [--pattern GLOB]... [--ignore GLOB]...
          [--debounce 0.3] [--interval 0.5] [--cmd CMD]
          [--clear] [--once] [--quiet] [--version]
```

Watch several directories at once:

```bash
dirwatch src tests --pattern '*.py' --cmd 'python -m pytest -q'
```

Run a build after any change in the current directory, clearing the screen first:

```bash
dirwatch . --cmd 'make' --clear
```

Watch events only, without executing anything:

```bash
dirwatch src --pattern '*.js'
```

Example output:

```text
$ dirwatch src --pattern '*.js'
dirwatch 0.1.0 — watching /home/dev/web/src
pattern: *.js | interval: 0.5s | debounce: 0.3s
no --cmd given: printing events only
[09:41:12] 1 change(s):
  ~ components/Button.js
[09:41:19] 2 change(s):
  + components/Modal.js
  - components/Legacy.js
^C
Watched for 0:00:31.8 (2 trigger(s))
```

Run once before watching — useful when you want the first test run to happen even before the first edit:

```bash
dirwatch src --once --cmd 'pytest -q'
```

Ignore noisy artifacts and slow-changing directories:

```bash
dirwatch . --ignore '*.log' --ignore 'dist' --pattern '*.ts' --cmd 'npm test'
```

## Options

| Option | Default | Description |
| --- | --- | --- |
| `PATHS...` | `.` | One or more directories to watch. With multiple roots, event paths are prefixed with the root directory name. |
| `--pattern GLOB` | `*` | Include only files whose name or relative path matches `GLOB`. Repeat the flag to add more patterns. |
| `--ignore GLOB` | `.git`, `__pycache__`, `node_modules`, `.venv` | Additional directory names or globs to skip. Repeatable; default ignores always apply. |
| `--debounce SECONDS` | `0.3` | Quiet period used to aggregate a burst of changes into a single run. `0` fires on the next poll. |
| `--interval SECONDS` | `0.5` | Time between directory scans. Lower values react faster at the cost of more `stat` calls. |
| `--cmd CMD` | — | Command executed through the platform shell after each burst. Without it, `dirwatch` only prints events. |
| `--clear` | off | Clear the terminal before each command execution. |
| `--once` | off | Execute `--cmd` once immediately at startup, then continue watching. |
| `--quiet` | off | Suppress startup banner, event lines and exit-code lines (command output is untouched). |
| `--version` | — | Print `dirwatch 0.1.0` and exit. |
| `--help` | — | Show the full option reference and examples. |

### Cross-platform notes

`dirwatch` uses polling rather than native OS notifications, which makes behaviour identical on Windows, macOS and Linux — including WSL, Docker bind mounts and most network filesystems where inotify events are unreliable. String commands are executed with `shell=True` (``cmd.exe`` on Windows, `/bin/sh` elsewhere), so pipes, quotes and redirections behave as they do in your terminal. Pass an argv-style command from Python's `CommandRunner` API when you want to bypass the shell.

The event path separator in output is always `/`, even on Windows, so logs and scripts stay portable.

## Development

```bash
git clone https://github.com/DelmarMG91/dirwatch-cli.git
cd dirwatch-cli
python -m pip install -e ".[dev]"
python -m pytest -q
```

The test suite uses `tmp_path` fixtures and fake clocks, so it runs in well under a second and never waits on real debounce intervals.

Project layout:

```text
src/dirwatch_cli/
├── __init__.py     # version
├── __main__.py     # python -m dirwatch_cli
├── cli.py          # argument parsing, watch loop, output
├── runner.py       # CommandRunner
└── watcher.py      # Snapshot, diff, Debouncer
tests/
├── test_cli.py
├── test_runner.py
└── test_watcher.py
```

## Contributing

Issues and pull requests are welcome. Please keep the tool dependency-free, add tests for behaviour changes, and run `python -m pytest -q` before opening a PR.

## License

MIT — see [LICENSE](LICENSE).
