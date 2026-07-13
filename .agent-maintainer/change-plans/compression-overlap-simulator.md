+++
id = "compression-overlap-simulator"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-07-27
allowed_paths = [
  ".agent-maintainer/change-plans/compression-overlap-simulator.md",
  "docs/compression-lab-roadmap.md",
  "docs/mcp.md",
  "docs/cli-json-schemas.md",
  "src/codex_usage_tracker/compression/attribution.py",
  "src/codex_usage_tracker/compression/payloads.py",
  "src/codex_usage_tracker/compression/simulator.py",
  "src/codex_usage_tracker/compression/simulation_api.py",
  "src/codex_usage_tracker/compression/simulation_payloads.py",
  "src/codex_usage_tracker/store/compression_capacities.py",
  "src/codex_usage_tracker/cli/mcp_compression.py",
  "tests/compression/test_simulator.py",
  "tests/cli/test_mcp_simulation.py",
  "tests/cli/test_mcp_integration.py",
  "tests/cli/test_cli_release.py",
]
forbidden_paths = ["src/codex_usage_tracker/store/schema.py", "config/prod/**", ".env", ".env.*"]
max_changed_files = 15
max_changed_lines = 1800
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: compression-overlap-simulator

## Why this change intentionally large

PR 4 adds one read-only what-if workflow across the pure overlap allocator,
typed candidate hydration, compact payload construction, shared API validation,
MCP registration, contract tests, and user documentation. Those layers must
agree on deterministic selection ordering, capacity bounds, stale-run behavior,
privacy flags, and serialized-size limits.

## Why this should not be split smaller

The simulator is unsafe to expose without capacity and determinism tests, while
the pure calculation has no user-facing value until the API and MCP adapter can
validate persisted run/candidate identity. The implementation remains one
reviewable vertical slice; skill routing and dogfood workflows stay in PR 5.

## What allowed to change

- Hydrate persisted candidates into existing typed compression contracts.
- Recalculate overlap allocation for an explicit bounded candidate selection.
- Add compact portfolio, calculation-trace, and verification-plan payloads.
- Add `usage_compression_simulate` and structured selection/staleness errors.
- Add focused determinism, capacity, privacy, payload-budget, and MCP tests.
- Update Compression Lab roadmap and public MCP/schema documentation.

## What must not change

- Compression persistence tables, migrations, refresh/index behavior, or jobs.
  PR 4 may read existing detector-ready record capacities through one bounded
  query module; it must not write or reinterpret those facts.
- Detector ranking, estimates, default candidate identities, or cached profiles.
- Existing MCP tool names, behavior, or stable payload contracts.
- Default raw-content privacy behavior; simulation remains aggregate-only.
- Dashboard, parser, pricing, allowance, release metadata, or plugin routing.

## Verification plan

- Start with failing pure tests for order independence, shared/disjoint capacity,
  subset reallocation, and deterministic trace ordering.
- Add API/MCP tests for empty, duplicate, over-limit, unknown, foreign,
  incomplete, and stale selections plus the serialized payload ceiling.
- Run focused compression/MCP tests, Ruff, Pyright, Tach, Xenon, Bandit,
  Markdown lint, release checks, the full Python suite, and the full Agent
  Maintainer verifier.
- Run one independent correctness/privacy review before publication.

## Rollback plan

Revert the PR 4 squash commit. PR 3 run, candidate, payload, and MCP contracts
remain unchanged because simulation is derived and does not persist state.

## Follow-up ratchet work

PR 5 may route skills and dogfood workflows to the simulator only after this
contract passes local and GitHub CI. Keep each new simulator module below the
repository source-size and complexity limits.
