+++
id = "mcp-first-product-pivot"
kind = "program-baseline"
status = "complete"
base_ref = "origin/main"
expires = 2026-12-31
allowed_paths = [
  "AGENTS.md",
  "CHANGELOG.md",
  "docs/architecture.md",
  "docs/deprecations.md",
  "docs/roadmap/mcp-first-pivot.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "docs/superpowers/plans/2026-07-21-mcp-first-product-pivot.md",
  "docs/superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md",
  ".agent-maintainer/change-plans/mcp-first-product-pivot.md",
  "tests/cli/test_cli_release.py",
  "tests/packaging/test_public_docs.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 11
max_changed_lines = 4600
+++

# MCP-First Product Pivot Change Plan

## Reason

The approved design and implementation roadmap contain 4,209 reviewed lines,
so adopting them and establishing the normative baseline intentionally exceeds
the repository's normal 800-line change budget. The exception covers documents,
guidance, and focused public-document tests only; it does not authorize runtime
or product-surface changes.

## Scope

- Adopt the approved design and implementation roadmap without adding features.
- Record releases `0.22.0` through `0.26.0`, bounded compatibility dates, and
  the surface-growth freeze.
- Establish the execution and deprecation ledgers consumed by later tasks.
- Add focused tests for the public program contracts.

## Verification

```bash
/Users/Monsky/Developer/Codex/codex-usage-tracker-subagent-pr/.venv/bin/python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q
npx markdownlint-cli2 README.md "docs/**/*.md" ".agent-maintainer/change-plans/*.md"
git diff --check
```

Fixtures and examples remain synthetic, and no private session content or local
database output is included.
