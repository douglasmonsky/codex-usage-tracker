+++
id = "compression-mcp-progress-cache"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-07-27
allowed_paths = [
  ".agent-maintainer/change-plans/compression-mcp-progress-cache.md",
  ".agent-maintainer/change-plans/compression-parallel-ingestion.md",
  "docs/compression-lab-roadmap.md",
  "docs/mcp.md",
  "docs/cli-json-schemas.md",
  "docs/architecture/decisions/0009-compression-mcp-adapter.md",
  "src/codex_usage_tracker/compression/**",
  "src/codex_usage_tracker/store/compression_*.py",
  "src/codex_usage_tracker/store/schema.py",
  "src/codex_usage_tracker/store/content_*.py",
  "src/codex_usage_tracker/cli/mcp_compression.py",
  "src/codex_usage_tracker/cli/mcp_server.py",
  "src/codex_usage_tracker/cli/tach.domain.toml",
  "src/codex_usage_tracker/core/json_contract_server.py",
  "tests/compression/test_jobs.py",
  "tests/cli/test_mcp_compression.py",
  "tests/cli/test_cli_release.py",
  "tests/cli/test_mcp_integration.py",
  "tests/store/test_compression_runs.py",
  "tests/store/test_compression_candidates.py",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_store_migrations.py",
  "tests/core/test_json_contracts.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 30
max_changed_lines = 3400
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: compression-mcp-progress-cache

## Why this change intentionally large

PR 3 turns the existing synchronous Compression Lab builder and persistent
candidate store into one coherent asynchronous public surface. A job reservation,
worker lifecycle, compact payload envelope, API facade, MCP registration, privacy
bounds, and contract tests must agree on run identity and terminal-state behavior.
Landing only one layer would either expose a blocking MCP call, duplicate cold
work, or publish payloads whose pagination and privacy semantics are ambiguous.
Independent review also required immutable claim metadata, an additive migration,
and deterministic snapshot regressions; those corrections raised the final
reviewed diff slightly above the original 3,000-line estimate.

## Why this should not be split smaller

The registry is not useful until the API and MCP tools consume it, while those
tools are unsafe without persistent status, deduplication, restart behavior,
payload budgets, and bounded evidence modes. The modules separate those
responsibilities for review, but they form one deployable compatibility contract.
The simulator and skill/plugin routing remain separate PRs because they consume
this contract rather than defining it.

## What allowed to change

- Persistent reservation and terminal-state handling for compression runs.
- An in-process async job registry shared by API and MCP callers.
- Pure compact payload builders for status, profile, candidate pages, and detail.
- Stable SQL-backed candidate filters and paging needed by the public contract.
- Additive candidate-claim metadata and migration coverage required to keep
  historical model/thread/time filters stable after source refreshes.
- Explicit bounded evidence handles, summaries, and excerpt reads.
- The five `usage_compression_*` MCP tools and CLI domain dependency.
- Focused lifecycle, restart, deduplication, privacy, pagination, latency, and
  serialized-size tests.
- MCP/schema documentation and this roadmap's PR 3 evidence ledger.

## What must not change

- Detector ranking, estimates, default detector-set candidate identity, overlap
  allocation, or CP1-CP6 performance behavior. Non-default detector selections
  may add an identity namespace so overlapping persisted runs cannot collide.
- Existing CLI/MCP tool behavior or stable payload contracts outside the new
  Compression Lab tools.
- Default raw-content privacy behavior; default payloads remain content-free.
- Parser, dashboard, pricing, allowance, release metadata, production config,
  credentials, simulator behavior, or skill/plugin routing.
- Cross-process leasing unless a failing contract test proves that a smaller
  persistent-state extension cannot satisfy restart correctness. SQLite changes
  remain additive and limited to immutable claim metadata required by review.

## Verification plan

- Start with failing tests for immediate start, active-request deduplication,
  monotonic progress, exact completed reuse, structured failure, orphaned restart,
  stable paging, filters, default content omission, explicit excerpt bounds, and
  4/8/16/24 KiB serialized payload ceilings.
- Prove representative warm profile and candidate-list reads complete below
  500 ms without launching analysis.
- Run focused compression/store/MCP tests, Ruff, Mypy, Tach, JavaScript syntax,
  release checks, the full Python suite, and the full Agent Maintainer verifier.
- Push only after the full diff and staged paths contain no local raw usage data,
  paths, credentials, or untracked `.idea/` and `uv.lock` files.

## Rollback plan

Revert the PR 3 squash commit. Existing compression runs, candidates, profiles,
and CP1-CP6 refresh behavior remain readable because the public layer reuses the
current store and any persistent-state adjustment must be additive. Existing MCP
tools remain independent of the five new registrations.

## Follow-up ratchet work

PR 4 may consume only the reviewed API/payload contracts when adding the
overlap-aware simulator. PR 5 may route skills and dogfood workflows only after
shadow comparisons prove that compact profile-first retrieval remains actionable.
Keep registry, payload, API, and MCP modules below repository source-size limits.
