# MCP-First Pivot Execution Ledger

This ledger is the durable handoff for the
[MCP-first pivot](mcp-first-pivot.md). Update the applicable entry in the same
commit as each roadmap task.

## Entry Format

```markdown
## Task N - Name
- Status: planned | active | blocked | complete
- Branch:
- Commits:
- Focused verification:
- Full verification:
- Deviations from plan:
- Follow-up risks:
```

## Task 1 - Record the pivot baseline and freeze dashboard surface growth

- Status: complete
- Branch: `pivot/1-establish-program`
- Commits: `3488d7a` (`docs: add MCP-first pivot design and roadmap`);
  `9a0d6ce` (`docs: establish MCP-first pivot program`)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md" ".agent-maintainer/change-plans/*.md"`; `git diff --check`
- Deviations from plan: Approved design and implementation roadmap were adopted
  in a preliminary documentation commit to isolate their 4,209-line reviewed
  content from the Task 1 baseline changes.
- Follow-up risks: The release sequence assumes the published baseline remains
  `0.21.0`; shift all planned minors together if that changes before execution.

## Task 2 - Make public product and storage statements internally consistent

- Status: complete
- Branch: `pivot/2-position-product`
- Commits: `docs: position MCP as the primary product` (this commit)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`; `python scripts/check_release.py`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md"`; `git diff --check`
- Deviations from plan: The local Task 2 branch is intentionally stacked on the
  reviewed Task 1 commits because pushing and merging are outside this task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after Task 1
  merges; do not drop the Task 1 baseline and review-fix commits.

## Task 3 - Introduce a declarative MCP tool catalog and profiles

- Status: complete
- Branch: `pivot/3-mcp-tool-catalog`
- Commits: `refactor: catalog MCP tools by profile` (this commit)
- Focused verification: `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_runtime.py`; `python -m ruff check src/codex_usage_tracker/interfaces/mcp tests/mcp`; `git diff --check`
- Deviations from plan: The local Task 3 branch is intentionally stacked on the
  reviewed Task 1 and Task 2 commits because pushing and merging are outside
  this task. The installed compatibility server remains the active legacy
  runtime; profile-selected server activation is deferred to its roadmap task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Core tools intentionally raise
  `CoreToolNotImplemented` until their service tasks land.

## Task 4 - Define shared MCP evidence contracts

- Status: complete
- Branch: `pivot/4-mcp-evidence-contracts`
- Commits: `feat: define MCP evidence contracts` (this commit)
- Focused verification: `python -m pytest tests/core/contracts tests/core/test_json_contracts.py -q`; `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/core/contracts`; `python -m ruff check src/codex_usage_tracker/core/contracts tests/core/contracts`; `git diff --check`
- Deviations from plan: The local Task 4 branch is intentionally stacked on the
  reviewed Tasks 1-3 commits because pushing and merging are outside this task.
  `ToolDataClass` moved to the core contract layer and is re-exported downward
  by the MCP interface model so core never imports `interfaces` and the alias
  cannot drift.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later core tools must use the registered envelope and
  evidence schemas without weakening finite-number or payload-budget checks.

## Task 5 - Add request models and shared source/accounting context builders

- Status: complete
- Branch: `pivot/5-request-context`
- Commits: `feat: build shared analysis request context`;
  `fix: harden analysis request context validation` (this commit)
- Focused verification: `python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q`
- Full verification: `python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /private/tmp/pivot-context-after-final`; `python -m pyright src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py`; `python -m ruff check src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py tests/application tests/store/test_store_dashboard_queries.py`; `git diff --check`
- Deviations from plan: The local Task 5 branch is intentionally stacked on
  the reviewed Tasks 1-4 commits because pushing and merging are outside this
  task. The shared context query opens the existing database in read-only mode
  and computes all scoped physical, canonical, coverage, revision, and freshness
  facts in one explicit transaction and one aggregate SQL statement. The route
  benchmark was not repeated for the review fix because its SQL body and every
  valid-file execution path remained byte-for-byte unchanged.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later interface adapters may accept `record` as a
  compatibility alias, but application `EvidenceRequest` remains canonical on
  `record_id`.

## Remaining Planned Tasks

Tasks 6 through 45 remain planned in the approved implementation roadmap. Add a
full entry using the format above when each task becomes active; do not mark a
task complete without its named focused and full verification evidence.
