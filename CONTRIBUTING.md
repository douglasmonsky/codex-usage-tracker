# Contributing

Thanks for improving Codex Usage Tracker.

## Start with the contract

Read `AGENTS.md` and [`docs/INDEX.md`](docs/INDEX.md). Work from one file under
[`docs/roadmap/tasks/`](docs/roadmap/tasks/) and its controlling documents.
Keep the branch and pull request focused on that packet, and update the
[checkbox ledger](docs/roadmap/TASK_PACKETS.md) only after every acceptance
criterion and required measurement passes.

The replacement belongs under `src/codex_usage_tracker/agent_kernel/`. Do not
import, migrate, or extend the frozen 0.28 spike under
`src/codex_usage_tracker/kernel/`.

## Local setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
```

## Checks

Run focused tests while implementing, then the smallest complete profile that
covers the changed contract:

```bash
just vp  # fast maintained checks
just v   # complete local CI profile
just vc  # release/build candidate profile
```

At minimum, documentation-only changes must pass:

```bash
python scripts/check_release.py
git diff --check
```

Never bypass hooks. Include exact commands, measurements, deviations, and
remaining risks in the pull request.

## Test data

- Use deterministic synthetic fixtures only.
- Do not commit real Codex logs, prompts, responses, reasoning, commands,
  patches, tool-output bodies, credentials, private paths, or local databases.
- Preserve missingness, provenance, and four-class token accounting in tests.
- Do not add sanitization or redaction behavior to compensate for unsafe test
  data; replace the fixture with synthetic data.

## Pull requests

Use a focused Conventional Commit and describe the user-visible contract, tests
run, performance/storage/response measurements required by the packet, and
rollback behavior. A meaningful stable diff receives at most one final
read-only reviewer.
