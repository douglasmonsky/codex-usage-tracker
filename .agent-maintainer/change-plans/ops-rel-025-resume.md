# OPS-REL-025 resume checkpoint

Checkpoint: 2026-07-25, updated after the reliability acceptance checkpoint.

## Authoritative checkout

- Worktree: `/Users/Monsky/Developer/Codex/codex-usage-tracker-0.25-reliability`
- Branch: `pivot/ops-rel-025-central-product-reliability`
- Base: `8f7f2796f663142d0bae3a117c13708644eee472`
- State: reliability implementation is ready for its focused checkpoint;
  preserve every existing worktree/branch.
- The user subsequently approved moving Task 40 static-product removal into
  `0.25.0`. Task 41 remains out of scope.

## Completed at this checkpoint

- Roadmap sequence is now 0.25 reliability, 0.26 static-product removal, and
  0.27 focused-endpoint stabilization/removal.
- Plugin install/cache/runtime bundle identity is deterministic and exposed by
  setup, doctor, and `usage_status`; version is `0.25.0.dev0`.
- Normal application/MCP container startup no longer performs interrupted-job
  recovery or any other job-store write against the usage index.
- Generic job leases/progress now use `usage.jobs.sqlite3`, independent from the
  long-running usage-index writer transaction.
- Async refresh registration uses durable semantic jobs, so independent
  application containers join and poll one refresh.
- Production/default async refresh launches a detached local worker; a synthetic
  test proves the initiating process can exit and a fresh container can retrieve
  the completed result.
- Refresh progress persists phase, global percent, heartbeat, elapsed time, and
  available source/event counters; `usage_job_status` has a bounded seam for
  returning the durable details.
- Active JSONL parsing uses one fixed complete-line end-byte snapshot. Rows
  appended during refresh remain for the next incremental pass and are not
  claimed by the earlier checkpoint.
- The long derived-state phase now emits explicit start/completion progress.
- Every core MCP response includes measured server-side elapsed time.
- Job status exposes input/output generations, the fixed boundary,
  `tail_pending`, bounded tail counts, and poll guidance.
- Stale analyses return one durable refresh dependency and an exact resume
  request; completed normalized analysis is reused.
- Evidence Console and MCP refresh callers share the same durable job service.
- Evidence Console startup no longer generates the static dashboard or refreshes
  the usage index.

## Verified

- Latest focused reliability/application/MCP slice: `48 passed`.
- Earlier refresh/source/reliability slices: `33 passed`, `23 passed`, and
  `11 passed` at their respective checkpoints.
- Ruff passed on the touched reliability/MCP/store slice.
- Targeted MyPy passed with the repository's Python 3.10 import-following
  workaround.
- `git diff --check` passed.
- Installed-wheel smoke passed, including a `40`-call, three-process core MCP
  probe with a shared refresh, concurrent committed read, moving tail, exact
  evidence, analysis, durable result reuse, and coherent bundle identity.
- The 100,000-row synthetic performance gate passed: cold `15.906 s`,
  no-change `0.013 s`, 100-row append `2.213 s`, one-row tail follow-up
  `2.037 s`, and read during writer `0.0036 s`.
- Agent Perf baseline `20260725T153903Z-d5e18169` and candidate
  `20260725T155929Z-12bd83a5` were captured on identical synthetic input.
- Earlier in this branch: plugin-focused tests (`47 passed`),
  roadmap/public-doc tests (`21 passed`), and `scripts/check_release.py`
  passed.

The worktree has no local `.venv`; focused commands used the unchanged audit
environment with `PYTHONPATH=src`:

```sh
PYTHONPATH=src ../codex-usage-tracker-0.24-audit/.venv/bin/python -m pytest ...
```

## Exact next implementation step

Checkpoint the reliability slice, amend the release map so Task 40 ships in
`0.25.0`, and implement Task 40 only. Start with the explicit static-only
code/asset/entry-point inventory and failing removal/migration tests. Preserve
CSV/JSON export, the live Evidence Console and locales, exact Evidence Console
deep links, shared backend payloads, and every focused Task 41 query plan.

## Known incomplete/risk items

- A cold or parser-incompatible rebuild still holds the usage-index writer
  transaction through parsing and derived-state materialization. The 0.25
  fix prevents that lock from blocking MCP/console startup and makes repeat
  no-change refreshes near-instant, but it does not yet stage a cold rebuild
  outside writer ownership.
- The synthetic one-row append still spends about two seconds recomputing
  affected-thread derived state. This is incremental, but remains the measured
  tail hot path.
- Full suite, full type checks, final post-removal package budgets, final review,
  and publication have not run.
- No push has been made.
