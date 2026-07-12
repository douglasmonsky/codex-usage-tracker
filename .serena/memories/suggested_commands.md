# Common commands
- Sync: `uv sync --all-extras`
- Focused tests: `.venv/bin/python -m pytest <paths> -q`
- Python lint/format: `.venv/bin/python -m ruff check .`; `.venv/bin/python -m ruff format --check .`
- Types: `.venv/bin/pyright`; `.venv/bin/python -m mypy`
- Architecture: `.venv/bin/tach check`
- Release sanity: `.venv/bin/python scripts/check_release.py`
- Named repo gates: `/Users/Monsky/.codex/bin/codex-task <name> --json` when `.codex/tasks.toml` defines them.