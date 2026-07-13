+++
id = "compression-candidate-persistence"
kind = "cohesive-migration"
status = "active"
base_ref = "origin/main"
expires = 2026-07-27
allowed_paths = [".agent-maintainer/change-plans/compression-candidate-persistence.md", "src/codex_usage_tracker/compression/**", "src/codex_usage_tracker/store/compression_*.py", "tests/compression/**", "tests/store/test_compression_runs.py", "tests/store/test_compression_publication.py", "tests/cli/test_cli_benchmarks.py", "scripts/benchmark_compression_lab.py", "scripts/compression_*.py", "docs/compression-lab-roadmap.md", "docs/architecture/decisions/**", "src/codex_usage_tracker/compression/tach.domain.toml"]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 15
max_changed_lines = 1800
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: compression-candidate-persistence

## Why this change intentionally large

CP5 replaces the candidate hot path from domain allocation through SQLite
publication. The typed write contract, transaction boundary, run builder,
rollback tests, benchmark, and roadmap evidence must change together so a
completed profile can never reference a partial candidate generation.

## Why this should not be split smaller

The domain adapter contract and atomic writer are unsafe to land independently:
without the writer the contract is unused, while without the contract the writer
would retain the mapping round trip. The rollback tests and benchmark validate
the same transaction boundary and must ship with it.

## What allowed to change

- Internal typed candidate and claim persistence rows.
- Candidate replacement and completed-profile publication transactions.
- Compression run construction at the persistence boundary.
- Candidate-heavy benchmark timing and focused store/run-builder tests.
- Compression roadmap status and measured evidence.
- Tach policy and its ADR only if the implementation changes a domain boundary.

## What must not change

- Public candidate and profile payloads, fingerprints, IDs, ranking, and overlap
  allocation.
- Existing generic mapping-based store APIs used by compatibility callers.
- MCP, CLI, dashboard, parser, pricing, privacy, and release behavior.
- Revision-vector cache identity established by CP4.

## Verification plan

- Start with rollback tests that inject failures between candidate, claim, and
  profile writes and prove no cacheable mixed-generation run is visible.
- Compare typed and mapping persistence results and canonical fingerprints.
- Measure a candidate-heavy persistence workload against the CP1-compatible
  path and require at least a 40 percent improvement.
- Run focused tests, Ruff, Mypy, Tach, the full Python suite, release checks,
  and the full Agent Maintainer verifier before opening the PR.

## Rollback plan

Revert the CP5 squash commit. The schema remains compatible and the retained
mapping API can continue writing the existing candidate and claim rows.

## Follow-up ratchet work

Keep publication and benchmark responsibilities in separate modules. CP6 must
not expand this plan to cover parallel parsing, MCP contracts, or dashboard work.
