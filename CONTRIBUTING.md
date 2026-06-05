# Contributing

Thanks for improving Codex Usage Tracker.

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
```

## Checks

Run these before opening a pull request:

```bash
python -m ruff check .
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m compileall src
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js
node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_state.js
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
git diff --check
```

## Privacy Rules

- Do not commit real Codex session logs.
- Do not add tests or docs that include prompts, assistant messages, tool output, secrets, or private data.
- Keep fixtures synthetic and aggregate-only.
- Do not make normal reports persist raw transcript content. On-demand context loading must stay explicit, local, redacted, and size-limited.

## Pull Requests

Keep changes focused and include the verification commands you ran. For user-visible behavior changes, update `README.md` and `CHANGELOG.md`.
