# Agent & Developer Guidelines

## Development Workflow
- Package Management: Always use `uv` for environment setup and dependency management (`uv sync`, `uv run`).
- Code Formatting & Linting: Run `uv run ruff check .` and `uv run ruff format .` before submitting code. All commits must pass cleanly.
- Testing: Run `uv run pytest`. Coverage must remain >= 80% across the Python codebase.
- Use strict typing and check for linting/typing issues before submitting code.

## System Architecture Conventions
- File Operations: State persistence MUST use POSIX atomic writes (write to `.tmp` -> `fsync()` -> `rename()`) with `fcntl.flock` where concurrent writes can occur.
- Directory Structure: Respect XDG Base Specifications (`XDG_DATA_HOME`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`).
- Logging: Structured JSON line entries emitted to `~/.local/state/sfw/logs/<service>.log.jsonl`.
