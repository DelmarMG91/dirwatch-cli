# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nothing yet.

## [0.1.0] - 2025-01-01

### Added

- `Snapshot` directory scanner with `(mtime_ns, size)` change detection and include/ignore glob filtering.
- `diff()` helper classifying added, modified and deleted relative paths.
- `Debouncer` event aggregation with configurable quiet period.
- `CommandRunner` executing shell strings or argv sequences and returning exit codes.
- `dirwatch` CLI with `--pattern`, `--ignore`, `--debounce`, `--interval`, `--cmd`, `--clear`, `--once`, `--quiet` and `--version`.
- Graceful `Ctrl-C` shutdown reporting watch duration and trigger count.
- Test suite covering snapshots, diffing, debounce logic, command execution and CLI helpers.

[Unreleased]: https://github.com/DelmarMG91/dirwatch-cli/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DelmarMG91/dirwatch-cli/releases/tag/v0.1.0
