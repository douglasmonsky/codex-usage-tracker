+++
id = "product-kernel-reset"
kind = "program-baseline"
status = "active"
base_ref = "origin/main"
expires = 2027-01-31
allowed_paths = [
  "AGENTS.md",
  "CHANGELOG.md",
  "README.md",
  ".agent-maintainer/change-plans/product-kernel-reset.md",
  ".agent-maintainer/change-plans/mcp-first-product-pivot.md",
  ".agent-maintainer/change-plans/archive/mcp-first-product-pivot.md",
  "docs/architecture.md",
  "docs/deprecations.md",
  "docs/release-checklist.md",
  "docs/roadmap/product-kernel-reset.md",
  "docs/roadmap/product-kernel-reset-execution.md",
  "docs/roadmap/mcp-first-pivot.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "docs/roadmap/archive/2026-07-21-mcp-first-pivot/**",
  "docs/superpowers/plans/2026-07-26-product-kernel-reset.md",
  "docs/superpowers/plans/2026-07-21-mcp-first-product-pivot.md",
  "docs/superpowers/plans/archive/2026-07-21-mcp-first-product-pivot.md",
  "docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md",
  "docs/superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md",
  "docs/superpowers/specs/archive/2026-07-21-mcp-first-product-pivot-design.md",
  "tests/packaging/test_public_docs.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 24
max_changed_lines = 20000
allow_source_without_test_change = true
requires_tests = true
requires_full_verify = false
ratchet_targets = []
+++

# Program Baseline: Product Kernel Reset

## Purpose

Archive the completed MCP-first roadmap and establish the approved post-0.25
program around a lean factual data kernel, model-driven inference, exact
evidence, and live local observability.

## Why this change is intentionally large

The change establishes one coherent authority across the public roadmap,
architecture, detailed design, implementation sequence, execution ledger,
deprecation contract, repository guidance, and public-document tests. Splitting
those documents would leave contradictory active instructions. The mechanical
line count also includes complete historical roadmap, plan, design, ledger, and
deprecation copies moved under archive paths; copy-aware review leaves roughly
2,900 lines of substantive documentation change.

## Allowed behavior change

None. This is documentation and governance only. It must not alter runtime
source, package version, generated plugin assets, installed software, database
state, or release artifacts.

## Decisions established

- Tracker owns exact facts, bounded calculations, freshness, and evidence.
- Codex owns inference, explanation, and recommendations.
- The kernel has exactly six default MCP tools.
- Queries and browser opens never trigger refresh.
- Normal ingestion excludes content FTS, analysis, compression,
  recommendations, diagnostics, and usage-drain work.
- Release 0.26 cuts over side by side and removes beta compatibility runtime.
- Release 0.27 adds guided exploration and optional separate content evidence.
- Release 0.28 is feature-free stabilization and contract freeze.

## Verification

```bash
python -m pytest tests/packaging/test_public_docs.py -q
python scripts/check_release.py
npx markdownlint-cli2 README.md "docs/**/*.md" \
  ".agent-maintainer/change-plans/*.md"
git diff --check
```

## Rollback

Revert this documentation changeset. The archived documents remain complete,
and this task does not touch runtime or user data.
