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
python -m pytest
python -m compileall src
python -m build
git diff --check
```

## Privacy Rules

- Do not commit real Codex session logs.
- Do not add tests or docs that include prompts, assistant messages, tool output, secrets, or private data.
- Keep fixtures synthetic and aggregate-only.
- Do not make normal reports persist raw transcript content. On-demand context loading must stay explicit, local, redacted, and size-limited.

## Pull Requests

Keep changes focused and include the verification commands you ran. For user-visible behavior changes, update `README.md` and `CHANGELOG.md`.
