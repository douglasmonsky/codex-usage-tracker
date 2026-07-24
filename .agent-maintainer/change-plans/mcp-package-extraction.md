+++
id = "mcp-package-extraction"
kind = "cohesive-migration"
status = "active"
base_ref = "origin/main"
expires = 2026-08-06
allowed_paths = [
  ".agent-maintainer/change-plans/mcp-package-extraction.md",
  "docs/architecture.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "src/codex_usage_tracker/cli/mcp_*.py",
  "src/codex_usage_tracker/interfaces/mcp/**",
  "tests/cli/test_cli_release.py",
  "tests/cli/test_mcp_integration.py",
  "tests/mcp/**",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 45
max_changed_lines = 4000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: MCP Package Extraction

## Why this change intentionally large

Task 29 moves one 64-tool MCP implementation surface from import-time CLI
modules into the explicit interface package. Each old implementation file
becomes a compatibility alias while the corresponding new file preserves the
same callables, so Git records both sides of each mechanical move. The server
factory, transport, serialization, registry paths, compatibility tests, and
architecture ledger must land together to keep every profile runnable.

## Why this should not be split smaller

Splitting the extraction would temporarily make either the lazy catalog point
at missing modules or leave interface modules importing implementation code
from the CLI layer. Both intermediate states violate the task's zero
import-side-effect and package-direction contracts. The public tool inventory
is deployed as one unit, so the old aliases and new factory must be reviewed
and released as one unit.

## What allowed to change

- Move MCP tool implementations and their private routing helpers under
  `interfaces/mcp/`.
- Keep `cli/mcp_*.py` import-compatible aliases.
- Add the explicit isolated FastMCP factory, transport, and JSON helpers.
- Update only the MCP catalog, profile, CLI-compatibility, release, and
  import-side-effect tests needed to prove the move.
- Record the architecture and execution-ledger result.

## What must not change

- Do not change tool names, signatures, descriptions, lifecycle metadata, or
  the 7/59/64 profile inventories.
- Do not change schemas, routes, storage, privacy behavior, dashboard assets,
  dependencies, or default profile selection.
- Do not remove historical module paths.

## Verification plan

- Run the roadmap-named factory, import-side-effect, profile, and CLI suites.
- Run all MCP and MCP-related CLI/golden compatibility tests.
- Run package-scoped Ruff, Pyright, compileall, Vulture, release readiness,
  and whitespace checks.
- Run the repository CI-equivalent verifier and full test suite.
- Use GitNexus change impact and one final independent reviewer before merge.

## Rollback plan

Revert the single Task 29 squash commit. The previous CLI modules and
decorator-compatible builder are restored together, with no data or schema
migration to reverse.

## Follow-up ratchet work

Task 30 owns repository-wide Tach boundaries and non-MCP cycles. It may tighten
the interface-to-CLI rule after this extraction lands; Task 29 must not absorb
unrelated domain-cycle work.
