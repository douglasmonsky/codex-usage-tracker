+++
id = "persisted-analysis-jobs"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-08-07
allowed_paths = [
  ".agent-maintainer/change-plans/persisted-analysis-jobs.md",
  "docs/architecture.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "src/codex_usage_tracker/application/allowance.py",
  "src/codex_usage_tracker/application/analyze.py",
  "src/codex_usage_tracker/application/container.py",
  "src/codex_usage_tracker/diagnostics/api.py",
  "src/codex_usage_tracker/jobs/models.py",
  "src/codex_usage_tracker/jobs/persistence.py",
  "src/codex_usage_tracker/jobs/service.py",
  "src/codex_usage_tracker/store/analysis_job_codec.py",
  "src/codex_usage_tracker/store/analysis_job_lifecycle.py",
  "src/codex_usage_tracker/store/analysis_job_repository.py",
  "src/codex_usage_tracker/store/analysis_job_schema.py",
  "src/codex_usage_tracker/store/schema.py",
  "tests/jobs/test_persisted_jobs.py",
  "tests/store/test_analysis_job_repository.py",
  "tests/store/test_otel_schema.py",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_store_migrations.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 20
max_changed_lines = 2500
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: Persisted Analysis Jobs

- Status: complete
- Roadmap task: 33
- Branch: `pivot/33-persisted-analysis-jobs`

## Purpose

Persist generic analysis and allowance job lifecycle state and bounded reusable
results in SQLite so completed work survives application restarts and orphaned
active work is reported as interrupted.

## Why this change intentionally large

The additive migration, transactional repository, generic job facade, analysis
and allowance worker checkpoints, startup recovery, diagnostics, retention,
privacy bounds, compatibility tests, and migration fixtures form one durable
lifecycle contract. Most of the line count is the explicit repository and
restart/concurrency coverage required by Task 33.

## Why this should not be split smaller

Landing the table without its sole writer would create unused schema. Landing
the writer without the application checkpoints would persist permanently
queued rows. Landing recovery without compatible-result and privacy tests could
discard useful work or store unsafe content. These pieces therefore ship as one
cohesive additive migration.

## What allowed to change

- Schema version 36, `analysis_jobs`, its bounded cleanup counter, and indexes.
- Repository create/reuse, lifecycle, recovery, retention, and diagnostic reads.
- `JobService` persistence boundary and normalized analysis/allowance
  checkpoints while refresh remains transient.
- Synthetic tests, architecture documentation, and Task 33 execution evidence.

## What must not change

- Raw context or unbounded payloads must not enter generic job storage.
- Unknown worker code must not resume after restart.
- Existing allowance/compression history, refresh behavior, public MCP names,
  stable result schemas, and compatibility routes must remain intact.
- No unrelated dashboard, release, or Task 34 work is included.

## Verification plan

- Focused repository, jobs, application, migration, concurrency, restart,
  retention, doctor, HTTP, and container tests.
- Ruff, MyPy, targeted Pyright, Tach, Xenon, Vulture, release sanity,
  `git diff --check`, package build, and Twine validation.
- Full pytest, whole-project coverage, at least 90% diff coverage, and one final
  read-only reviewer after the diff is stable.

## Rollback plan

Revert the Task 33 commit. Schema v36 is additive; retained `analysis_jobs` and
`analysis_job_stats` tables are ignored by v35 code, and transient generic job
behavior resumes without deleting historical allowance or compression rows.

## Follow-up ratchet work

Task 34 should make the already-passing diff-coverage and schema inventory
checks directly blocking. Later tasks must reuse this persistence boundary
without expanding it to raw context, refresh results, or unknown worker-code
resumption.
