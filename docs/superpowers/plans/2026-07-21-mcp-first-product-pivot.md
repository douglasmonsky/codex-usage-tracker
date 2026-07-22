# Codex Usage Tracker MCP-First Product Pivot Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this roadmap task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not combine tasks unless the roadmap explicitly permits it.

**Goal:** Make MCP the primary analysis product, reduce the live dashboard to a focused Evidence Console, simplify public CLI and API surfaces, strengthen architectural and release guarantees, and remove expired compatibility code before 1.0.

**Architecture:** Introduce a typed application layer and seven-tool core MCP profile over existing deterministic analytics. Migrate the live frontend to Home, Explore, Limits, Settings, and contextual Evidence routes. Preserve old tools, commands, routes, and static output only through bounded compatibility adapters, then remove them after two minor releases.

**Tech Stack:** Python 3.10-3.14, FastMCP, SQLite, stdlib HTTP server, React 19, TypeScript, TanStack Query/Router/Table/Virtual, Vitest, Playwright, pytest, coverage.py, Pyright, Mypy, Ruff, Tach, Dependency Cruiser, GitHub Actions, setuptools, PyPI Trusted Publishing.

**Approved design:** `docs/superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md`

## Global Constraints

- Baseline repository state is `main` at `bf383e1f4d9e206f3ba8cb004075bc3e87bc3fa6` and published package `0.21.0`.
- If `0.22.0` is published before execution begins, shift every planned minor version upward by the same amount without changing task order, compatibility duration, or acceptance criteria.
- No new dashboard workspace, top-level MCP concept, top-level CLI command, runtime dependency, or SQLite table may be added unless specified in this roadmap.
- Deterministic backend code performs calculations, ranking, identity, pricing, allowance, and statistical decisions. Agents do not calculate from raw rows.
- The installed plugin defaults to MCP profile `core`.
- The `core` profile contains exactly seven tools: `usage_status`, `usage_refresh`, `usage_analyze`, `usage_query`, `usage_evidence`, `usage_allowance`, and `usage_job_status`.
- Existing public MCP tools remain available in profile `full` through the compatibility window.
- Developer and dogfood tools are profile `developer` only.
- The first Evidence Console release defaults to Home, Explore, and Limits. Settings is a shell action. Evidence is contextual.
- Existing analytical pages remain direct-link compatibility routes for one minor release, notice-only routes for one further minor release, then are deleted.
- The legacy static dashboard follows the same two-release compatibility window.
- Existing raw-context controls and loopback server request guards remain behaviorally unchanged unless a task explicitly modifies them.
- Public documentation must accurately describe current local storage behavior. This roadmap does not redesign privacy behavior.
- External validation programs are outside scope.
- All new core tool outputs use `codex-usage-tracker.mcp-envelope.v1`.
- All new dashboard targets use `codex-usage-tracker-dashboard-target-v2`.
- Every material analytical finding includes claim type, confidence, evidence identifiers, and limitations.
- Every behavior task begins with a failing focused test and ends with focused verification plus the applicable repository gate.
- Normal PR limit is 25 non-generated files and 1,500 changed non-generated lines. Generated dashboard assets must be isolated in a separate commit.
- Schema, public contract, release, or compatibility changes require a named non-author review before merge.
- Do not weaken test thresholds, broaden allowlists, add broad suppressions, or mark a task complete with known failing acceptance tests.
- Source fixtures, screenshots, and documentation examples use synthetic data only.

---

## Program release map

| Planned release | Program outcome | Required compatibility state |
| --- | --- | --- |
| `0.22.0` | Stable MCP core profile, shared contracts, truthful product positioning, generic job facade | Existing dashboard and old tools still function; old tools are `full` profile |
| `0.23.0` | Evidence Console becomes default; CLI and HTTP v2 ship | Old dashboard pages are direct-link compatibility routes; old CLI names remain aliases |
| `0.24.0` | Python architecture refit, database integrity, context offsets, infrastructure hardening | Old pages are notice-only; old APIs and aliases remain supported |
| `0.25.0` | Expired dashboard, static, MCP, CLI, and HTTP compatibility removed | Only documented stable and advanced surfaces remain |
| `0.26.0` | Feature-free stabilization release for pre-1.0 contract hardening | No new public surface; migration and package gates prove final state |

## Program dependency graph

```text
Task 1-2  Product and execution baseline
   |
Task 3-5  MCP catalog and shared contracts
   |
Task 6-14 Core application services and tools
   |
Task 15-17 Compatibility isolation and 0.22 release
   |
Task 18-27 Evidence Console, CLI, HTTP v2, and 0.23 release
   |
Task 28-39 Architecture, integrity, CI/release, and 0.24 release
   |
Task 40-43 Compatibility deletion and 0.25 release
   |
Task 44-45 Stabilization and final acceptance
```

## Execution protocol

For each task:

1. Create a branch named `pivot/<task-number>-<slug>` from current `main`.
2. Create or update one cohesive change plan under `.agent-maintainer/change-plans/` when the task exceeds repository change budgets.
3. Read the design sections referenced by the task.
4. Write the exact failing tests named in the task.
5. Run the focused test command and record the expected failure.
6. Implement only the task's interfaces.
7. Run focused tests, static checks, and release checks named in the task.
8. Update `docs/roadmap/mcp-first-pivot-execution.md` with branch, commit, tests, deviations, and remaining risks.
9. Commit with the exact conventional prefix shown in the task.
10. Open a PR; do not merge until required checks and review are complete.

---

## Release 0.22.0 - MCP core and product contract

### Task 1: Record the pivot baseline and freeze dashboard surface growth

**Files:**

- Create: `docs/roadmap/mcp-first-pivot.md`
- Create: `docs/roadmap/mcp-first-pivot-execution.md`
- Create: `docs/deprecations.md`
- Create: `.agent-maintainer/change-plans/mcp-first-product-pivot.md`
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md`
- Modify: `CHANGELOG.md`
- Test: `tests/packaging/test_public_docs.py`
- Test: `tests/cli/test_cli_release.py`

**Interfaces:**

- Produces the normative release sequence, compatibility release windows, execution ledger format, and prohibition on unplanned product-surface growth.
- Later tasks consume `docs/deprecations.md` and `docs/roadmap/mcp-first-pivot-execution.md`.

**Required execution-ledger entry:**

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

- [ ] **Step 1: Add failing public-document tests.** Assert that the roadmap names releases `0.22.0` through `0.26.0`, the deprecation document contains required columns, and the architecture document declares MCP primary and Evidence Console supporting.

Run:

```bash
python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q
```

Expected: FAIL because the new documents and assertions do not exist.

- [ ] **Step 2: Write the baseline documents.** Copy the approved design decisions without adding new features. Mark the previously merged `2026-07-19` foundation as completed input, not the active roadmap.

- [ ] **Step 3: Add the agent execution rule to `AGENTS.md`.** Require tasks to follow this roadmap, use focused branches, and update the execution ledger.

- [ ] **Step 4: Verify documentation.**

```bash
python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q
npx markdownlint-cli2 README.md "docs/**/*.md" ".agent-maintainer/change-plans/*.md"
git diff --check
```

Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add AGENTS.md CHANGELOG.md docs/roadmap/mcp-first-pivot.md docs/roadmap/mcp-first-pivot-execution.md docs/deprecations.md docs/architecture.md .agent-maintainer/change-plans/mcp-first-product-pivot.md tests/packaging/test_public_docs.py tests/cli/test_cli_release.py
git commit -m "docs: establish MCP-first pivot program"
```

### Task 2: Make public product and storage statements internally consistent

**Files:**

- Modify: `README.md`
- Modify: `docs/first-five-minutes.md`
- Modify: `docs/dashboard-guide.md`
- Create: `docs/evidence-console.md`
- Create: `docs/data-posture.md`
- Modify: `docs/mcp.md`
- Modify: `docs/privacy.md`
- Modify: `pyproject.toml`
- Modify: `tests/packaging/test_public_docs.py`
- Modify: `tests/release_catalog.py`

**Interfaces:**

- Produces the stable public positioning used by package metadata and bundled documentation.
- Does not change runtime storage or privacy behavior.

**Required positioning:**

- Package description: `Local, evidence-backed Codex usage analyst with MCP tools and an Evidence Console.`
- README title paragraph: MCP conversational analysis first, Evidence Console second.
- Data posture: normal refresh indexes aggregate counters and the existing bounded local content/event index; aggregate-only commands retain the older posture; shareable outputs follow existing behavior.

- [ ] **Step 1: Write failing consistency tests.** Add assertions that public docs do not contain `The dashboard is the core product surface`, do not claim that SQLite stores aggregate metrics only, and do contain the canonical package description and data-posture summary.

- [ ] **Step 2: Rewrite the README front door.** The quick workflow becomes install, setup, restart/open fresh task, ask a starter question, and optionally open evidence. Move screenshot-heavy dashboard material below the conversational workflow or replace it with one Evidence Console overview image.

- [ ] **Step 3: Split dashboard documentation.** `docs/evidence-console.md` documents only Home, Explore, Limits, Settings, and Evidence target behavior. `docs/dashboard-guide.md` becomes a compatibility pointer during the migration window.

- [ ] **Step 4: Update package metadata.** Change `[project].description` without changing the distribution name, console command, dependencies, or version in this task.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q
python scripts/check_release.py
npx markdownlint-cli2 README.md "docs/**/*.md"
git diff --check
```

Expected: PASS with no contradictory storage statement.

- [ ] **Step 6: Commit.**

```bash
git add README.md docs/first-five-minutes.md docs/dashboard-guide.md docs/evidence-console.md docs/data-posture.md docs/mcp.md docs/privacy.md pyproject.toml tests/packaging/test_public_docs.py tests/release_catalog.py
git commit -m "docs: position MCP as the primary product"
```

### Task 3: Introduce a declarative MCP tool catalog and profiles

**Files:**

- Create: `src/codex_usage_tracker/interfaces/mcp/__init__.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/models.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/profiles.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/runtime.py`
- Create: `tests/mcp/test_tool_registry.py`
- Create: `tests/mcp/test_tool_profiles.py`
- Modify: `src/codex_usage_tracker/cli/mcp_runtime.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `tests/release_catalog.py`

**Interfaces:**

- Produces:

```python
McpProfile = Literal["core", "full", "developer"]
ToolMaturity = Literal["stable", "beta", "experimental"]
ToolLifecycle = Literal["active", "deprecated"]
ToolDataClass = Literal["aggregate", "local_index", "raw_context", "administrative"]

@dataclass(frozen=True)
class ToolSpec:
    name: str
    minimum_profile: McpProfile
    maturity: ToolMaturity
    lifecycle: ToolLifecycle
    data_class: ToolDataClass
    handler: Callable[..., object]
    replacement: str | None = None
    deprecated_since: str | None = None
    remove_after: str | None = None
```

- Produces `tool_specs()`, `tools_for_profile(profile)`, and `build_mcp_server(profile)`. A tool is included in its minimum profile and every more permissive profile.
- Does not yet change the installed plugin default.

- [ ] **Step 1: Write failing profile tests.** Assert exact core names and order:

```python
assert [tool.name for tool in tools_for_profile("core")] == [
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
]
```

Assert `full` is a strict superset and `developer` is a strict superset of `full`. Assert names are unique and every deprecated tool has replacement and removal release.

- [ ] **Step 2: Implement immutable models and catalog validation.** Catalog validation raises a specific `ToolCatalogError` for duplicate names, missing replacements, invalid minimum-profile order, or removal release earlier than deprecation release.

- [ ] **Step 3: Register existing handlers with minimum profile `full` or `developer`.** Core handlers may initially be stubs that raise `CoreToolNotImplemented` so tests can build the server before later tasks implement behavior. Existing public tool names remain registered in `full`; dogfood and visualization experiments become `developer`.

- [ ] **Step 4: Keep `cli/mcp_runtime.py` as a compatibility import.** It re-exports the server instance used by old modules until Task 29 moves adapters.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_runtime.py
python -m ruff check src/codex_usage_tracker/interfaces/mcp tests/mcp
```

Expected: PASS; current full-profile tool names remain available.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_runtime.py src/codex_usage_tracker/cli/mcp_server.py tests/mcp tests/cli/test_mcp_integration.py tests/release_catalog.py
git commit -m "refactor: catalog MCP tools by profile"
```

### Task 4: Define the shared MCP envelope, scope, message, claim, and evidence contracts

**Files:**

- Create: `src/codex_usage_tracker/core/contracts/__init__.py`
- Create: `src/codex_usage_tracker/core/contracts/common.py`
- Create: `src/codex_usage_tracker/core/contracts/claims.py`
- Create: `src/codex_usage_tracker/core/contracts/evidence.py`
- Create: `src/codex_usage_tracker/core/contracts/envelope.py`
- Create: `src/codex_usage_tracker/core/contracts/serialization.py`
- Create: `tests/core/contracts/test_common.py`
- Create: `tests/core/contracts/test_envelope.py`
- Create: `tests/core/contracts/test_claims.py`
- Modify: `src/codex_usage_tracker/core/json_contracts.py`
- Modify: `src/codex_usage_tracker/core/json_contract_validation.py`
- Modify: `tests/core/test_json_contracts.py`
- Create: `docs/contracts.md`

**Interfaces:**

- Produces frozen dataclasses or TypedDict-compatible serializers for `ScopeV1`, `FreshnessV1`, `AccountingContextV1`, `MessageV1`, `RecommendationV1`, `FindingV1`, `EvidenceV1`, `NextActionV1`, and `McpEnvelopeV1`.
- Produces:

```python
def envelope_payload(
    *,
    tool: str,
    result_schema: str,
    result: object,
    scope: ScopeV1,
    freshness: FreshnessV1,
    accounting: AccountingContextV1,
    data_class: ToolDataClass,
    warnings: Sequence[MessageV1] = (),
    limitations: Sequence[MessageV1] = (),
    dashboard_targets: Sequence[Mapping[str, object]] = (),
    next_actions: Sequence[NextActionV1] = (),
    request_id: str | None = None,
) -> dict[str, object]:
```

- [ ] **Step 1: Write failing serialization tests.** Require sorted deterministic mappings, UTC timestamps, generated request IDs matching `req-[0-9a-f]{32}`, finite numeric values, stable message codes, and rejection of recommendations with no supporting claim.

- [ ] **Step 2: Implement contracts without importing reports, store, CLI, MCP, or server packages.** `core/contracts` may import standard library and other `core` modules only.

- [ ] **Step 3: Register schemas.** Add the envelope and nested schema names to the JSON contract registry and documentation equality tests.

- [ ] **Step 4: Add size helpers.** `serialized_size(payload)` returns UTF-8 JSON byte count and `enforce_payload_budget(payload, maximum, name)` raises `PayloadBudgetError` with actual and maximum bytes.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/core/contracts tests/core/test_json_contracts.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/core/contracts
python -m ruff check src/codex_usage_tracker/core/contracts tests/core/contracts
```

Expected: PASS and no import from interfaces or persistence.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/core/contracts tests/core/contracts src/codex_usage_tracker/core/json_contracts.py src/codex_usage_tracker/core/json_contract_validation.py tests/core/test_json_contracts.py docs/contracts.md
git commit -m "feat: define MCP evidence contracts"
```

### Task 5: Add request models and shared source/accounting context builders

**Files:**

- Create: `src/codex_usage_tracker/application/__init__.py`
- Create: `src/codex_usage_tracker/application/requests.py`
- Create: `src/codex_usage_tracker/application/context.py`
- Create: `src/codex_usage_tracker/application/errors.py`
- Create: `tests/application/test_requests.py`
- Create: `tests/application/test_context.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `tests/store/test_store_dashboard_queries.py`

**Interfaces:**

- Produces `StatusRequest`, `RefreshRequest`, `AnalysisRequest`, `QueryRequest`, `EvidenceRequest`, `AllowanceRequest`, and `JobStatusRequest`.
- Produces:

```python
@dataclass(frozen=True)
class RequestScope:
    since: str | None = None
    until: str | None = None
    history: Literal["active", "all"] = "active"
    privacy_mode: Literal["normal", "redacted", "strict"] = "normal"
    project: str | None = None
    thread_key: str | None = None
    model: str | None = None
    effort: str | None = None


def build_request_context(
    *, db_path: Path, pricing_path: Path, scope: RequestScope
) -> RequestContext:
    ...
```

`RequestContext` contains source revision, freshness, physical/canonical counts, copied rows excluded, pricing coverage, credit coverage, and tier coverage.

- [ ] **Step 1: Write failing validation tests.** Cover invalid date order, unsupported history/privacy values, nonfinite thresholds, unsafe thread identifiers, limits above contract maximum, and deterministic normalized scope serialization.

- [ ] **Step 2: Add one bounded store query for context facts.** It returns all required counts and coverage in one transaction. It must use canonical rows for canonical totals and physical rows only for physical/excluded counts.

- [ ] **Step 3: Implement request context.** Do not call a full report builder. Missing database state returns explicit empty/unknown fields rather than creating hidden side effects.

- [ ] **Step 4: Verify query plan and behavior.**

```bash
python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/pivot-context-budget
```

Expected: PASS within the current route-budget thresholds.

- [ ] **Step 5: Commit.**

```bash
git add src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py tests/application tests/store/test_store_dashboard_queries.py
git commit -m "feat: build shared analysis request context"
```

### Task 6: Implement stable status and capabilities use case

**Files:**

- Create: `src/codex_usage_tracker/application/status.py`
- Create: `tests/application/test_status.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/core_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Modify: `src/codex_usage_tracker/cli/mcp_dashboard.py`
- Modify: `tests/mcp/test_tool_profiles.py`
- Modify: `tests/cli/test_mcp_integration.py`

**Interfaces:**

- Produces:

```python
def get_status(request: StatusRequest) -> dict[str, object]:
    """Return codex-usage-tracker.status.v2."""


def usage_status() -> dict[str, object]:
    """Return McpEnvelopeV1 containing status.v2."""
```

- Result contains index freshness, parser/source coverage, pricing/accounting coverage, conversational readiness, active MCP profile, exact core tool names, persistent service status, and next action.

- [ ] **Step 1: Write failing application tests.** Cover empty install, fresh index, stale index, unavailable pricing, restart-required MCP, core profile, and a malformed local configuration. Assert the result never claims current-task tool exposure.

- [ ] **Step 2: Implement `get_status`.** Reuse bounded doctor/readiness helpers and shared request context. No refresh, report generation, source scan, or analysis job may start.

- [ ] **Step 3: Implement the core MCP adapter.** Wrap result in `McpEnvelopeV1`, use data class `administrative`, and enforce a 16 KiB budget.

- [ ] **Step 4: Convert old `usage_status` into a full-profile compatibility wrapper.** It preserves its existing result schema and delegates to existing dashboard status behavior until removal.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/application/test_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/core/test_conversational_readiness.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/status.py src/codex_usage_tracker/interfaces/mcp/core_tools.py
```

Expected: PASS; core `usage_status` is envelope v1, full compatibility status remains available under its catalog entry.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/application/status.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py src/codex_usage_tracker/cli/mcp_dashboard.py tests/application/test_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py
git commit -m "feat: add stable MCP usage status"
```

### Task 7: Introduce the generic job facade over existing registries

**Files:**

- Create: `src/codex_usage_tracker/jobs/__init__.py`
- Create: `src/codex_usage_tracker/jobs/models.py`
- Create: `src/codex_usage_tracker/jobs/adapters.py`
- Create: `src/codex_usage_tracker/jobs/service.py`
- Create: `tests/jobs/test_models.py`
- Create: `tests/jobs/test_service.py`
- Modify: `src/codex_usage_tracker/server/usage_refresh.py`
- Modify: `src/codex_usage_tracker/server/analysis_jobs.py`
- Modify: `src/codex_usage_tracker/server/compression_routes.py`
- Modify: `src/codex_usage_tracker/cli/mcp_dogfood.py`

**Interfaces:**

- Produces `JobKind`, `JobState`, `JobStatusV1`, `JobHandle`, and:

```python
class JobAdapter(Protocol):
    def status(self, job_id: str, *, include_result: bool = False) -> Mapping[str, object]: ...

class JobService:
    def register(self, *, kind: JobKind, job_id: str, adapter: JobAdapter) -> None: ...
    def status(self, job_id: str, *, include_result: bool = False) -> JobStatusV1: ...
```

- No persistence migration occurs in this task.

- [ ] **Step 1: Write failing adapter tests.** Build synthetic refresh, allowance, compression, analysis, and dogfood payloads and assert all normalize into one monotonic status contract. Cover unknown job, failed job, completed job, missing result, and oversized result.

- [ ] **Step 2: Implement pure normalization.** Map subsystem-specific stages and errors to stable values without mutating existing registries.

- [ ] **Step 3: Add registration at job creation points.** Existing public job functions continue returning historical payloads. New application services can register handles and poll through `JobService`.

- [ ] **Step 4: Enforce result budgets.** Status without result is at most 16 KiB. Completed result inclusion uses the originating tool's budget.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/jobs tests/server/test_analysis_jobs.py tests/server/test_usage_refresh.py tests/compression/test_jobs.py -q
python -m ruff check src/codex_usage_tracker/jobs tests/jobs
```

Expected: PASS with no schema or migration change.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/jobs src/codex_usage_tracker/server/usage_refresh.py src/codex_usage_tracker/server/analysis_jobs.py src/codex_usage_tracker/server/compression_routes.py src/codex_usage_tracker/cli/mcp_dogfood.py tests/jobs
git commit -m "refactor: unify usage job status"
```

### Task 8: Implement core refresh and generic job-status tools

**Files:**

- Create: `src/codex_usage_tracker/application/refresh.py`
- Create: `src/codex_usage_tracker/application/job_status.py`
- Create: `tests/application/test_refresh.py`
- Create: `tests/application/test_job_status.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/core_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Modify: `tests/mcp/test_tool_profiles.py`
- Modify: `tests/cli/test_mcp_integration.py`

**Interfaces:**

- Produces:

```python
def refresh_usage(request: RefreshRequest) -> CompletedOrJob[dict[str, object]]: ...
def get_job_status(request: JobStatusRequest) -> JobStatusV1: ...
```

`usage_refresh` accepts `history`, `aggregate_only`, and `execution="auto|sync|async"`. `auto` completes synchronously only when the bounded refresh planner determines that the current incremental work is safe for one MCP call; otherwise it starts a job.

- [ ] **Step 1: Write failing refresh tests.** Cover no changes, append-only small refresh, large/multiple-source async selection, archived scope, aggregate-only mode, active-job reuse, failed job, and exact accounting metadata.

- [ ] **Step 2: Implement the refresh planner.** Base the decision on stored source metadata and bounded file facts, not wall-clock guesses. Define `MAX_SYNC_SOURCE_FILES = 4` and `MAX_SYNC_ADDED_BYTES = 4_194_304`.

- [ ] **Step 3: Implement core adapters.** `usage_refresh` returns envelope v1 with result schema `codex-usage-tracker.refresh.v2` or a job result. `usage_job_status` polls any registered job.

- [ ] **Step 4: Keep old refresh tools in full profile.** `refresh_usage_index`, `usage_refresh_start`, and `usage_refresh_status` remain unchanged for compatibility.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/application/test_refresh.py tests/application/test_job_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/store/test_store_large_batches.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/refresh.py src/codex_usage_tracker/application/job_status.py
```

Expected: PASS; core tool count remains seven.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/application/refresh.py src/codex_usage_tracker/application/job_status.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py tests/application/test_refresh.py tests/application/test_job_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py
git commit -m "feat: add core refresh and job tools"
```

### Task 9: Implement the canonical query request and application service

**Files:**

- Create: `src/codex_usage_tracker/application/query.py`
- Create: `src/codex_usage_tracker/application/query_models.py`
- Create: `src/codex_usage_tracker/application/query_validation.py`
- Create: `tests/application/test_query.py`
- Create: `tests/application/test_query_validation.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `src/codex_usage_tracker/store/dashboard_queries.py`
- Modify: `src/codex_usage_tracker/reports/api.py`
- Modify: `src/codex_usage_tracker/core/json_contracts.py`
- Modify: `tests/core/test_json_contracts.py`

**Interfaces:**

- Consumes `QueryRequest`, `RequestContext`, `McpEnvelopeV1`, and canonical usage rows.
- Produces:

```python
QueryEntity = Literal["call", "thread", "project", "model", "effort", "origin", "service_tier", "subagent"]
QueryMeasure = Literal[
    "tokens", "uncached_tokens", "cached_tokens", "output_tokens",
    "reasoning_tokens", "estimated_cost", "estimated_credits", "call_count",
    "duration", "cache_ratio", "context_pressure",
]
QueryOrder = Literal["asc", "desc"]

@dataclass(frozen=True)
class QueryRequest:
    entity: QueryEntity
    measures: tuple[QueryMeasure, ...]
    filters: QueryFilters
    group_by: tuple[str, ...] = ()
    order_by: str | None = None
    order: QueryOrder = "desc"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"

@dataclass(frozen=True)
class QueryResult:
    schema: Literal["codex-usage-tracker.query.v2"]
    entity: QueryEntity
    columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]
    next_cursor: str | None
    total_matched: int | None
    dashboard_target: DashboardTargetV2 | None
```

**Normative behavior:**

- All default totals read canonical usage rows.
- A query never accepts free-form SQL, arbitrary column names, arbitrary sort expressions, or unlimited interactive results.
- `limit` is `1..200`; `cursor` is an opaque signed or deterministic bounded token owned by the query adapter.
- `group_by` values are entity-specific allowlisted dimensions.
- Cost and credit measures preserve pricing coverage and estimation fields.
- The service does not duplicate report calculations; it uses repository query functions or established report builders.

- [ ] **Step 1: Write validation tests.** Cover each supported entity, invalid measures, measure/entity mismatches, unsupported groupings, negative limits, limits above 200, malformed cursor, ambiguous time windows, and contradictory filters.

Example:

```python
def test_query_rejects_arbitrary_measure() -> None:
    with pytest.raises(QueryValidationError, match="unsupported measure"):
        validate_query_request(
            QueryRequest(entity="thread", measures=(cast(QueryMeasure, "raw_prompt"),), filters=QueryFilters())
        )
```

- [ ] **Step 2: Run validation tests and verify RED.**

```bash
python -m pytest tests/application/test_query_validation.py -q
```

Expected: collection fails because the query application modules do not exist.

- [ ] **Step 3: Implement the allowlist and request normalization.** Keep all entity/measure/grouping compatibility in one immutable table named `QUERY_ENTITY_CAPABILITIES`. Return a normalized request; do not silently discard an invalid field.

- [ ] **Step 4: Write service tests with synthetic SQLite fixtures.** Cover canonical duplicate exclusion, active/all-history scope, thread and subagent grouping, unpriced rows, stable ordering, cursor continuation, and a result with no matches.

- [ ] **Step 5: Implement repository adapters.** Add only narrowly named query functions to `store/api.py`; SQL remains in `store/dashboard_queries.py` or a new focused module selected during implementation. Every SQL query must use parameters and deterministic tie-break ordering.

- [ ] **Step 6: Add `codex-usage-tracker.query.v2` to the JSON contract registry.** Assert exact schema equality between runtime sources and docs.

- [ ] **Step 7: Verify.**

```bash
python -m pytest tests/application/test_query.py tests/application/test_query_validation.py tests/core/test_json_contracts.py tests/store/test_store_dashboard_queries.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/query.py src/codex_usage_tracker/application/query_models.py src/codex_usage_tracker/application/query_validation.py
python -m ruff check src/codex_usage_tracker/application/query*.py tests/application/test_query*.py
```

Expected: PASS with deterministic row ordering and no physical duplicate in ordinary results.

- [ ] **Step 8: Commit.**

```bash
git add src/codex_usage_tracker/application/query.py src/codex_usage_tracker/application/query_models.py src/codex_usage_tracker/application/query_validation.py src/codex_usage_tracker/store/api.py src/codex_usage_tracker/store/dashboard_queries.py src/codex_usage_tracker/reports/api.py src/codex_usage_tracker/core/json_contracts.py tests/application/test_query.py tests/application/test_query_validation.py tests/core/test_json_contracts.py tests/store/test_store_dashboard_queries.py
git commit -m "feat: add canonical usage query service"
```

### Task 10: Define the analysis-goal catalog and strategy protocol

**Files:**

- Create: `src/codex_usage_tracker/analytics/analysis_catalog.py`
- Create: `src/codex_usage_tracker/analytics/analysis_models.py`
- Create: `src/codex_usage_tracker/analytics/strategies/__init__.py`
- Create: `src/codex_usage_tracker/analytics/strategies/protocol.py`
- Create: `tests/analytics/test_analysis_catalog.py`
- Create: `tests/analytics/test_strategy_protocol.py`
- Modify: `src/codex_usage_tracker/reports/agentic.py`
- Modify: `src/codex_usage_tracker/recommendation_engine/api.py`
- Modify: `docs/architecture.md`

**Interfaces:**

```python
AnalysisGoal = Literal[
    "usage_spike", "token_waste", "context_bloat", "cache_failure",
    "subagent_cost", "fast_usage", "pricing_gaps", "thread_comparison",
    "model_effort_mix", "workflow_churn",
]

@dataclass(frozen=True)
class AnalysisRequest:
    goal: AnalysisGoal
    filters: QueryFilters
    history: HistoryScope = "active"
    evidence_limit: int = 8
    comparison: ComparisonWindow | None = None
    execution: ExecutionMode = "auto"

class AnalysisStrategy(Protocol):
    goal: AnalysisGoal
    strategy_version: str
    def estimate(self, request: AnalysisRequest, context: RequestContext) -> WorkEstimate: ...
    def analyze(self, request: AnalysisRequest, context: RequestContext) -> AnalysisReportV2: ...
```

**Catalog requirements:**

- One strategy per goal.
- Strategy IDs and versions are stable strings and appear in result provenance.
- Each goal declares required facts, optional facts, maximum evidence records, synchronous-work ceiling, and supported dashboard evidence destinations.
- Catalog registration is import-explicit; no entry-point or filesystem magic.
- The catalog is exhaustive and duplicate goals fail at startup tests.

- [ ] **Step 1: Write failing catalog tests.** Require exactly the ten goals above, unique names, unique strategy IDs, positive evidence bounds, and a documented fallback message for missing facts.

- [ ] **Step 2: Implement immutable catalog metadata and the strategy protocol.** Do not move existing algorithms in this task.

- [ ] **Step 3: Add compatibility adapters for current report builders.** Define private adapter classes that delegate to current report/recommendation APIs while satisfying the protocol. Mark adapters with `implementation_status="compatibility"`.

- [ ] **Step 4: Test that adapters produce deterministic `WorkEstimate` values and never execute analysis during estimation.**

- [ ] **Step 5: Document ownership.** `analytics/` owns calculation and strategy selection; `application/` owns orchestration; `interfaces/` owns transport.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/analytics/test_analysis_catalog.py tests/analytics/test_strategy_protocol.py tests/reports/test_agentic.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/analytics
python -m ruff check src/codex_usage_tracker/analytics tests/analytics
```

Expected: PASS; existing public report behavior remains unchanged.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/analytics/analysis_catalog.py src/codex_usage_tracker/analytics/analysis_models.py src/codex_usage_tracker/analytics/strategies src/codex_usage_tracker/reports/agentic.py src/codex_usage_tracker/recommendation_engine/api.py tests/analytics docs/architecture.md
git commit -m "refactor: catalog usage analysis strategies"
```

### Task 11: Implement the canonical analysis application service

**Files:**

- Create: `src/codex_usage_tracker/application/analyze.py`
- Create: `tests/application/test_analyze.py`
- Create: `tests/application/fixtures/analysis_cases.py`
- Modify: `src/codex_usage_tracker/analytics/analysis_catalog.py`
- Modify: `src/codex_usage_tracker/jobs/service.py`
- Modify: `src/codex_usage_tracker/core/json_contracts.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `docs/cli-json-schemas.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class AnalyzeResult:
    completed: AnalysisReportV2 | None
    job: JobStatusV1 | None


def analyze_usage(request: AnalysisRequest, context: RequestContext) -> AnalyzeResult: ...
```

**Decision rules:**

- `execution="sync"` rejects a strategy whose estimate exceeds its synchronous ceiling.
- `execution="async"` always starts or reuses a job.
- `execution="auto"` uses `WorkEstimate` to choose.
- Identical jobs reuse an active or compatible completed result using a semantic key built from source revision, goal, normalized request, pricing/rate-card/threshold versions, and strategy version.
- An analysis response is bounded to eight findings and eight evidence records by default; hard maximum is twenty.
- Empty evidence is not converted into a finding.
- A strategy error becomes a structured error message with no fabricated conclusion.

- [ ] **Step 1: Write failing orchestration tests.** Cover synchronous completion, forced async, auto async, job reuse, stale source revision, strategy exception, no evidence, partial pricing, comparison-window validation, and deterministic semantic keys.

- [ ] **Step 2: Implement semantic-key generation as a pure function.** Use canonical JSON and SHA-256. Include every payload-changing input and no irrelevant local path.

- [ ] **Step 3: Implement the application service.** Inject the strategy catalog and job service through `RequestContext`; do not import the FastMCP runtime.

- [ ] **Step 4: Register `codex-usage-tracker.analysis.v2` and `codex-usage-tracker.analysis-job.v1` contracts.** Include finding kinds, evidence relationships, source revision, accounting context, strategy metadata, limitations, and dashboard targets.

- [ ] **Step 5: Add contract fixtures for each goal.** Fixtures are synthetic and small enough for exact equality tests.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/application/test_analyze.py tests/analytics tests/core/test_json_contracts.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/analyze.py
python scripts/check_release.py
```

Expected: PASS and no response above the configured envelope budget.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/application/analyze.py src/codex_usage_tracker/analytics/analysis_catalog.py src/codex_usage_tracker/jobs/service.py src/codex_usage_tracker/core/json_contracts.py tests/application/test_analyze.py tests/application/fixtures/analysis_cases.py tests/core/test_json_contracts.py docs/cli-json-schemas.md
git commit -m "feat: orchestrate evidence-backed usage analysis"
```

### Task 12: Add the core `usage_query` and `usage_analyze` MCP tools

**Files:**

- Modify: `src/codex_usage_tracker/application/query.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/core_tools.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/query_analysis_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Create: `tests/mcp/test_core_query_tool.py`
- Create: `tests/mcp/test_core_analyze_tool.py`
- Modify: `tests/mcp/test_tool_profiles.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `docs/mcp.md`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md`

**Tool signatures:**

```python
@mcp.tool(name="usage_query")
def usage_query_tool(
    entity: str,
    measures: list[str],
    filters: dict[str, object] | None = None,
    group_by: list[str] | None = None,
    order_by: str | None = None,
    order: str = "desc",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
) -> dict[str, object]: ...

@mcp.tool(name="usage_analyze")
def usage_analyze_tool(
    goal: str,
    filters: dict[str, object] | None = None,
    history: str = "active",
    evidence_limit: int = 8,
    comparison: dict[str, object] | None = None,
    execution: str = "auto",
) -> dict[str, object]: ...
```

**Normative tool behavior:**

- Both always return JSON envelopes; no Markdown mode.
- Invalid requests return MCP tool errors with concise, field-specific messages rather than success payloads carrying an error string.
- The tool descriptions contain examples and explain when to choose query versus analyze.
- No tool accepts arbitrary text intended to be interpreted as a query language.

- [x] **Step 1: Write failing tool-profile tests.** Assert both names exist in `core`, each has a single registration, and compatibility imports cannot register a duplicate.

- [x] **Step 2: Write tool contract tests.** Use the application layer with injected temporary paths. Cover a completed analysis and an asynchronous job response.

- [x] **Step 3: Implement thin transport adapters.** Parse transport values into request dataclasses, call application services, and serialize typed results. Keep functions under 60 physical lines.

- [x] **Step 4: Rewrite the API skill's routing guidance.** Broad diagnostic questions use `usage_analyze`; precise tabular questions use `usage_query`; raw-context tools are not part of the default flow.

- [x] **Step 5: Synchronize packaged skill bytes.** `scripts/check_release.py` must verify exact equality.

- [x] **Step 6: Verify.**

```bash
python -m pytest tests/mcp/test_core_query_tool.py tests/mcp/test_core_analyze_tool.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q
python scripts/check_release.py
```

Expected: PASS with exactly seven default tools.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py tests/mcp/test_core_query_tool.py tests/mcp/test_core_analyze_tool.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py docs/mcp.md skills/codex-usage-api/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md
git commit -m "feat: expose core query and analysis tools"
```

### Task 13: Implement the canonical evidence service and `usage_evidence`

**Files:**

- Create: `src/codex_usage_tracker/evidence/__init__.py`
- Create: `src/codex_usage_tracker/evidence/models.py`
- Create: `src/codex_usage_tracker/evidence/service.py`
- Create: `src/codex_usage_tracker/evidence/selectors.py`
- Create: `src/codex_usage_tracker/application/evidence.py`
- Modify: `src/codex_usage_tracker/application/requests.py`
- Modify: `src/codex_usage_tracker/jobs/service.py`
- Modify: `src/codex_usage_tracker/store/usage_record_queries.py`
- Modify: `src/codex_usage_tracker/store/thread_summaries.py`
- Modify: `src/codex_usage_tracker/store/query_sql.py`
- Modify: `src/codex_usage_tracker/store/allowance_intelligence.py`
- Create: `tests/evidence/test_service.py`
- Create: `tests/evidence/test_selectors.py`
- Create: `tests/application/test_evidence.py`
- Modify: `src/codex_usage_tracker/core/dashboard_targets.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/core_tools.py`
- Modify: `src/codex_usage_tracker/core/json_contracts.py`
- Modify: `tests/core/test_dashboard_targets.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `tests/application/test_query.py`
- Modify: `tests/application/test_requests.py`
- Modify: `tests/application/fixtures/analysis_cases.py`
- Modify: `tests/jobs/test_service.py`
- Modify: `tests/mcp/test_tool_profiles.py`
- Modify: `docs/cli-json-schemas.md`

**Interfaces:**

```python
EvidenceSelectorKind = Literal["finding", "call", "thread", "allowance", "analysis"]

@dataclass(frozen=True)
class EvidenceRequest:
    selector_kind: EvidenceSelectorKind
    selector_id: str
    section: str = "summary"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"

@dataclass(frozen=True)
class EvidenceResult:
    schema: Literal["codex-usage-tracker.evidence-result.v1"]
    selector: dict[str, str]
    records: tuple[EvidenceV1, ...]
    next_cursor: str | None
    dashboard_target: DashboardTargetV2
```

**Evidence rules:**

- Finding IDs resolve only against a compatible completed in-process analysis result.
- Call and thread selectors use canonical IDs.
- Allowance selectors point to persisted analysis/evidence keys.
- `section="summary"` is aggregate only. Other sections are allowlisted and must already exist in current application services.
- No section returns raw transcript fragments by default.
- Missing selectors produce a typed not-found error, not an empty successful result.
- Evidence ordering is stable and pagination is keyset-based where the repository already supports it.

- [x] **Step 1: Write failing selector tests.** Cover valid and invalid record IDs, thread keys, finding IDs, analysis IDs, history mismatches, stale analysis revisions, and malformed cursors.

- [x] **Step 2: Implement typed selectors and repository reads.** Reuse call detail, thread calls, allowance evidence, and compatible completed analysis results; do not create duplicate analytical calculations or persistence.

- [x] **Step 3: Upgrade dashboard target schema to v2.** Add `target_id`, `evidence_kind`, optional `analysis_id`, and `expires_at=None` while preserving a v1 compatibility builder. All URLs remain deterministic and allowlisted.

- [x] **Step 4: Add the core tool.**

```python
@mcp.tool(name="usage_evidence")
def usage_evidence_tool(
    selector_kind: str,
    selector_id: str,
    section: str = "summary",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
) -> dict[str, object]: ...
```

- [x] **Step 5: Verify.**

```bash
python -m pytest tests/evidence tests/application/test_evidence.py tests/core/test_dashboard_targets.py tests/core/test_json_contracts.py tests/mcp/test_tool_profiles.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/evidence src/codex_usage_tracker/application/evidence.py
```

Expected: PASS; every finding in the synthetic analysis fixtures opens at least one exact evidence selector.

- [x] **Step 6: Commit in focused hook-safe commits.**

```bash
git add src/codex_usage_tracker/evidence src/codex_usage_tracker/application/evidence.py src/codex_usage_tracker/core/dashboard_targets.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/core/json_contracts.py tests/evidence tests/application/test_evidence.py tests/core/test_dashboard_targets.py tests/core/test_json_contracts.py
git commit -m "feat: add canonical evidence retrieval"
```

### Task 14: Consolidate allowance operations behind `usage_allowance`

**Files:**

- Create: `src/codex_usage_tracker/application/allowance.py`
- Create: `src/codex_usage_tracker/application/allowance_models.py`
- Modify: `src/codex_usage_tracker/application/requests.py`
- Create: `tests/application/test_allowance.py`
- Create: `tests/application/test_allowance_models.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/core_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Modify: `src/codex_usage_tracker/core/dashboard_targets.py`
- Modify: `src/codex_usage_tracker/cli/mcp_allowance.py`
- Modify: `tests/cli/test_mcp_allowance.py`
- Create: `tests/mcp/test_core_allowance_tool.py`
- Modify: `tests/mcp/test_tool_profiles.py`
- Modify: `tests/mcp/test_tool_registry.py`
- Modify: `tests/core/test_dashboard_targets.py`
- Modify: `docs/allowance-intelligence.md`
- Modify: `docs/mcp.md`
- Modify: `skills/codex-usage-tracker/SKILL.md` and packaged mirror
- Modify: `skills/codex-usage-api/SKILL.md` and packaged mirror

**Interfaces:**

```python
AllowanceOperation = Literal["status", "series", "evidence", "analysis"]

@dataclass(frozen=True)
class AllowanceRequest:
    operation: AllowanceOperation
    window: Literal["weekly", "five_hour"] = "weekly"
    range: str = "8w"
    cursor: str | None = None
    limit: int = 50
    analysis_id: str | None = None
    execution: ExecutionMode = "auto"
```

- `status` returns constant-size current state.
- `series` returns finite canonical capacity/observation series.
- `evidence` returns a paginated page.
- `analysis` returns a compatible completed result or a generic job handle.
- Existing allowance tools remain full-profile compatibility tools through 0.24.

- [x] **Step 1: Write failing application tests for every operation.** Cover empty index, stale status, finite ranges, invalid `all` use in interactive evidence, cursor conflicts, analysis reuse, insufficient evidence, and multiple supported changes.

- [x] **Step 2: Implement the application facade.** Delegate to existing allowance v2 services and generic jobs. Remove no old code in this task.

- [x] **Step 3: Add the core tool.** Return one envelope schema whose `result_schema` varies by operation. Include a Limits dashboard target for each successful result.

- [x] **Step 4: Add compatibility equivalence tests.** For identical fixtures, old `usage_allowance_status/series/evidence/analysis` payload semantics must equal the corresponding new operation after envelope removal.

- [x] **Step 5: Update docs and skills to prefer the consolidated tool.**

- [x] **Step 6: Verify.**

```bash
python -m pytest tests/application/test_allowance.py tests/cli/test_mcp_allowance.py tests/mcp/test_tool_profiles.py tests/allowance_intelligence -q
python scripts/check_release.py
```

Expected: PASS; allowance calculations are unchanged.

- [x] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/application/allowance.py src/codex_usage_tracker/application/allowance_models.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py src/codex_usage_tracker/cli/mcp_allowance.py tests/application/test_allowance.py tests/cli/test_mcp_allowance.py tests/mcp/test_tool_profiles.py docs/allowance-intelligence.md docs/mcp.md
git commit -m "feat: consolidate allowance MCP operations"
```

### Task 15: Move legacy MCP tools into explicit compatibility and developer profiles

**Files:**

- Create: `src/codex_usage_tracker/interfaces/mcp/compatibility_tools.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/developer_tools.py`
- Create: `tests/mcp/test_compatibility_tools.py`
- Create: `tests/mcp/test_developer_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `src/codex_usage_tracker/cli/mcp_runtime.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `tests/release_catalog.py`
- Modify: `docs/deprecations.md`
- Modify: `docs/mcp.md`

**Profile disposition:**

- `core`: exactly seven stable tools.
- `full`: core plus supported compatibility tools required for existing clients.
- `developer`: full plus dogfood, visualization experiments, local export experiments, and maintainer-only tools.

**Compatibility requirements:**

- No public tool is deleted in 0.22.
- Every non-core tool has a catalog disposition: `compatibility`, `advanced`, `developer`, or `deprecated`.
- A deprecated tool description names the replacement and earliest removal release.
- Compatibility tool schemas and names remain unchanged.
- A process exposes one selected profile only; it does not register all profiles and hide them through documentation.

- [ ] **Step 1: Build a complete expected-name fixture from the 0.21/PR290 baseline.** Store it in `tests/mcp/fixtures/tool_names_021.json`. The test must fail if a tool disappears unintentionally.

- [ ] **Step 2: Classify every current tool in `MCP_TOOL_CATALOG`.** The catalog must cover all names found by FastMCP registration and reject uncataloged tools.

- [ ] **Step 3: Refactor registration.** `cli/mcp_server.py` becomes a temporary import-compatible module that calls `codex_usage_tracker.interfaces.mcp.server.main()`. Tool implementation modules no longer register themselves as an import side effect; registry code registers selected callables.

- [ ] **Step 4: Add profile-isolation tests.** Start the MCP server in-process or inspect its tool registry for each profile. Verify exactly seven core names and complete legacy names in full/developer.

- [ ] **Step 5: Update deprecations.** Record replacement, warning start, direct removal release, and retained CLI/HTTP alternatives.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/mcp/test_compatibility_tools.py tests/mcp/test_developer_tools.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/cli/test_cli_release.py -q
python scripts/check_release.py
```

Expected: PASS; default profile exposes seven tools and full profile preserves baseline tools.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_server.py src/codex_usage_tracker/cli/mcp_runtime.py tests/mcp tests/cli/test_mcp_integration.py tests/cli/test_cli_release.py tests/release_catalog.py docs/deprecations.md docs/mcp.md
git commit -m "refactor: profile the MCP tool surface"
```

### Task 16: Make the installed plugin launch the core MCP profile by default

**Files:**

- Modify: `skills/codex-usage-tracker/scripts/run_mcp.py`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py`
- Modify: `.mcp.json`
- Modify: `src/codex_usage_tracker/plugin_installer.py`
- Modify: `src/codex_usage_tracker/core/conversational_readiness.py`
- Modify: `tests/cli/test_mcp_launcher.py`
- Modify: `tests/cli/test_plugin_installer.py`
- Modify: `tests/core/test_conversational_readiness.py`
- Modify: `scripts/smoke_installed_package.py`
- Modify: `docs/install.md`
- Modify: `docs/mcp.md`

**Launcher contract:**

- `CODEX_USAGE_TRACKER_MCP_PROFILE` accepts `core`, `full`, or `developer`.
- Installed generated plugin wrappers set `core` explicitly.
- Source-checkout maintainers may select `developer`.
- Unknown values fail before starting FastMCP.
- Readiness reports the configured profile and whether the runtime version matches the wrapper's package spec.
- Existing runtime bootstrap cache behavior remains.

- [ ] **Step 1: Write failing launcher tests.** Cover default core, explicit full/developer, invalid profile, generated wrapper environment, cached runtime, local `.venv`, Windows path construction, and readiness output.

- [ ] **Step 2: Pass profile through the exec environment.** Keep `MODULE_ARGS` stable except for using the new `codex_usage_tracker.interfaces.mcp.server` module internally; retain `codex_usage_tracker.mcp_server` as a compatibility module.

- [ ] **Step 3: Update installer templates and readiness checks.** A healthy wrapper with the core profile reports it exactly; do not claim current-task tool discovery.

- [ ] **Step 4: Update installed-wheel smoke.** Launch an isolated MCP subprocess, list tools through the SDK or registry probe, and assert exactly the seven core names.

- [ ] **Step 5: Synchronize source and packaged launcher files byte-for-byte.**

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/cli/test_mcp_launcher.py tests/cli/test_plugin_installer.py tests/core/test_conversational_readiness.py -q
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
```

Expected: PASS; clean installation starts the core profile.

- [ ] **Step 7: Commit.**

```bash
git add skills/codex-usage-tracker/scripts/run_mcp.py src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py .mcp.json src/codex_usage_tracker/plugin_installer.py src/codex_usage_tracker/core/conversational_readiness.py tests/cli/test_mcp_launcher.py tests/cli/test_plugin_installer.py tests/core/test_conversational_readiness.py scripts/smoke_installed_package.py docs/install.md docs/mcp.md
git commit -m "feat: default the plugin to core MCP tools"
```

### Task 17: Gate and publish Release 0.22.0

**Files:**

- Create: `docs/releases/0.22.0.md`
- Create: `docs/upgrading-to-0.22.0.md`
- Create: `tests/golden_questions/cases/*.json`
- Create: `tests/golden_questions/test_core_tools.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `docs/roadmap/mcp-first-pivot-execution.md`
- Modify: `scripts/check_release.py`
- Modify: `tests/release_catalog.py`

**Release acceptance:**

- Installed plugin exposes exactly seven tools by default.
- Full profile preserves the 0.21/PR290 tool-name set.
- All seven core tools return the shared envelope.
- Ten golden questions route to the expected core tool in at most three calls, excluding refresh/job polling.
- Existing calculations for canonical totals, tier pricing, allowance, and subagent reports have equivalence tests.
- Public documentation no longer calls the dashboard the core product.
- No dashboard navigation change ships in this release.

- [ ] **Step 1: Add ten deterministic golden-question cases.** Include usage spike, token waste, precise model query, subagent comparison, Fast usage, pricing gaps, thread comparison, allowance status, allowance evidence, and evidence follow-up. Each fixture declares expected tool sequence and result schema.

- [ ] **Step 2: Implement a test-only routing evaluator.** It validates skill guidance and tool metadata; it does not invoke a live model or require network access.

- [ ] **Step 3: Run the complete 0.22 gate.**

```bash
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
python -m mypy
npm run dashboard:verify
npm run dashboard:assets:check
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
python scripts/check_release.py
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 4: Record exact outputs in the execution ledger and release note.** Include test count, coverage, tool counts by profile, wheel/sdist hashes, package sizes, and schema inventory.

- [ ] **Step 5: Commit the release candidate.**

```bash
git add README.md CHANGELOG.md pyproject.toml docs/releases/0.22.0.md docs/upgrading-to-0.22.0.md docs/roadmap/mcp-first-pivot-execution.md tests/golden_questions tests/release_catalog.py scripts/check_release.py
git commit -m "chore: prepare 0.22.0 MCP core release"
```

- [ ] **Step 6: Publish and qualify.** Publish to TestPyPI first, install the exact artifact in a clean Python 3.10 and 3.14 environment, run tool inventory and all seven tool help/contract smokes, then publish the same candidate according to the current release workflow. Artifact-promotion hardening is implemented later in Task 36.

---

## Release 0.23.0 - Evidence Console and default product simplification

### Task 18: Introduce the Evidence Console route model and URL compatibility layer

**Files:**

- Create: `frontend/dashboard/src/app/evidenceConsoleRoutes.ts`
- Create: `frontend/dashboard/src/app/evidenceConsoleRoutes.test.ts`
- Create: `frontend/dashboard/src/routes/legacyRouteAliases.ts`
- Create: `frontend/dashboard/src/routes/legacyRouteAliases.test.ts`
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `frontend/dashboard/src/app/navigation.ts`
- Modify: `frontend/dashboard/src/routes/dashboardSearch.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/app/shellUrl.ts`
- Modify: `frontend/dashboard/src/app/shellUrl.test.ts`
- Modify: `frontend/dashboard/src/app/currentViewExport.ts`
- Modify: `frontend/dashboard/src/App.shell.test.tsx`
- Modify: `src/codex_usage_tracker/core/dashboard_targets.py`
- Modify: `tests/core/test_dashboard_targets.py`

**Target routes:**

```ts
type EvidenceConsoleRouteId = 'home' | 'explore' | 'limits' | 'evidence' | 'settings';

type ExploreMode = 'calls' | 'threads';
```

**Compatibility mapping:**

| Existing view | Target route |
| --- | --- |
| `overview` | `home` |
| `calls` | `explore&mode=calls` |
| `threads` | `explore&mode=threads` |
| `call` | `evidence&kind=call` |
| `usage-drain` | `limits` |
| `settings` | `settings` |
| `investigator` | legacy direct route, no primary replacement |
| `compression-lab` | legacy direct route, no primary replacement |
| `diagnostics` | legacy direct route, replacement is conversational analysis plus evidence |
| `cache-context` | legacy direct route, replacement is `usage_analyze(goal="cache_failure")` |
| `reports` | legacy direct route, replacement is `usage_analyze`/`usage_query` |

**Normative behavior:**

- New links emit only target route IDs.
- Old URLs remain accepted and normalize to the corresponding target route when there is direct parity.
- Old workbench routes without direct parity remain renderable by their old ID during 0.23 but never appear in primary navigation.
- URL normalization uses `history.replaceState`, not a full reload.
- The default shell exposes Home, Explore, and Limits as primary analytical navigation plus Settings as a visually separate utility action.
- Evidence is contextual and absent from persistent primary navigation.
- The experimental navigation preference no longer adds workbench pages to primary navigation; it exposes a Labs link inside Settings only.

- [ ] **Step 1: Write failing exhaustive route tests.** Assert exact target IDs, unique labels, exhaustive rendering, deterministic aliases, no deprecated secondary aliases, and exactly three analytical navigation items plus the Settings utility action.

- [ ] **Step 2: Implement the new catalog separately from compatibility aliases.** Do not overload maturity/placement fields to represent aliases. `evidenceConsoleRoutes.ts` owns target routes; `legacyRouteAliases.ts` owns old input normalization.

- [ ] **Step 3: Update dashboard targets to emit v2 routes.** V1 targets remain parseable through aliases. V2 call targets use `view=evidence&kind=call&record=...`; thread targets use `view=evidence&kind=thread&thread_key=...` or `view=explore&mode=threads&thread_key=...` according to target purpose.

- [ ] **Step 4: Update shell consumers.** Navigation, return labels, export labels, keyboard shortcuts, and copy-link capabilities use the new route catalog. Legacy route labels come only from the alias catalog.

- [ ] **Step 5: Verify.**

```bash
npm --workspace frontend/dashboard test -- evidenceConsoleRoutes.test.ts legacyRouteAliases.test.ts routeCatalog.test.ts shellUrl.test.ts App.shell.test.tsx dashboardTargets.test.ts
npm run dashboard:typecheck
npm run dashboard:lint
python -m pytest tests/core/test_dashboard_targets.py -q
```

Expected: PASS; new navigation has exactly four persistent destinations and all old stable URLs resolve.

- [ ] **Step 6: Commit.**

```bash
git add frontend/dashboard/src/app/evidenceConsoleRoutes.ts frontend/dashboard/src/app/evidenceConsoleRoutes.test.ts frontend/dashboard/src/routes/legacyRouteAliases.ts frontend/dashboard/src/routes/legacyRouteAliases.test.ts frontend/dashboard/src/app/routeCatalog.ts frontend/dashboard/src/app/navigation.ts frontend/dashboard/src/routes/dashboardSearch.ts frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/app/shellUrl.ts frontend/dashboard/src/app/shellUrl.test.ts frontend/dashboard/src/app/currentViewExport.ts frontend/dashboard/src/App.shell.test.tsx src/codex_usage_tracker/core/dashboard_targets.py tests/core/test_dashboard_targets.py
git commit -m "refactor: define Evidence Console routes"
```

### Task 19: Replace Overview with a focused Home status and evidence-launch page

**Files:**

- Create: `frontend/dashboard/src/features/home/HomePage.tsx`
- Create: `frontend/dashboard/src/features/home/HomePage.module.css`
- Create: `frontend/dashboard/src/features/home/homeModel.ts`
- Create: `frontend/dashboard/src/features/home/HomePage.test.tsx`
- Create: `frontend/dashboard/src/features/home/homeModel.test.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `frontend/dashboard/src/app/useConversationalReadiness.ts`
- Modify: `src/codex_usage_tracker/server/status.py`
- Modify: `src/codex_usage_tracker/server/dashboard_shell.py`
- Modify: `tests/server/test_server_status.py`
- Modify: `tests/server/test_server_dashboard_shell.py`

**Home content contract:**

1. Index freshness and source revision.
2. Conversational-analysis readiness and configured MCP profile.
3. Accounting status: canonical/physical/excluded rows and pricing coverage.
4. Current allowance summary when available.
5. At most three deterministic high-confidence findings from a bounded home-summary endpoint.
6. Recent evidence: at most five calls or threads.
7. Primary actions: copy a starter investigation prompt, open Explore, open Limits, refresh.

**Explicit removals from Home:**

- 3D Usage Constellation.
- broad diagnostic cards.
- report-library tiles.
- multiple competing charts.
- manual report configuration.
- hidden all-history scans during initial hydration.

- [ ] **Step 1: Write failing model tests.** Cover fresh, stale, empty, pricing-partial, copied-row, MCP-ready, MCP-unavailable, allowance-missing, and bounded-findings states. Assert at most five top-level status cards and at most three findings.

- [ ] **Step 2: Add a bounded home-summary response.** Extend `/api/status` or add `/api/v2/home` only if status would become semantically overloaded. The endpoint must execute constant-size metadata reads plus bounded persisted recommendation/finding reads; no full-history detector runs.

- [ ] **Step 3: Implement Home.** Use existing design tokens and accessibility primitives. Each finding has an `Open evidence` target and a copyable conversational follow-up. No finding is generated in React.

- [ ] **Step 4: Route `overview` compatibility URLs to Home.** Preserve old bookmark behavior.

- [ ] **Step 5: Verify.**

```bash
npm --workspace frontend/dashboard test -- HomePage.test.tsx homeModel.test.ts ConversationalAnalysisStatus.test.tsx App.shell.test.tsx
npm run dashboard:typecheck
npm run dashboard:stylelint
python -m pytest tests/server/test_server_status.py tests/server/test_server_dashboard_shell.py -q
```

Expected: PASS; initial Home data is bounded and no heavy-analysis route executes.

- [ ] **Step 6: Commit.**

```bash
git add frontend/dashboard/src/features/home frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/api/types.ts frontend/dashboard/src/api/client.ts frontend/dashboard/src/app/useConversationalReadiness.ts src/codex_usage_tracker/server/status.py src/codex_usage_tracker/server/dashboard_shell.py tests/server/test_server_status.py tests/server/test_server_dashboard_shell.py
git commit -m "feat: add focused Evidence Console home"
```

### Task 20: Consolidate Calls and Threads into Explore

**Files:**

- Create: `frontend/dashboard/src/features/explore/ExplorePage.tsx`
- Create: `frontend/dashboard/src/features/explore/ExplorePage.module.css`
- Create: `frontend/dashboard/src/features/explore/exploreState.ts`
- Create: `frontend/dashboard/src/features/explore/exploreState.test.ts`
- Create: `frontend/dashboard/src/features/explore/ExplorePage.test.tsx`
- Modify: `frontend/dashboard/src/features/calls/CallsPage.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx`
- Modify: `frontend/dashboard/src/features/threads/threadsUrlState.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `tests/playwright/dashboard-react.spec.mjs`

**Explore contract:**

- One page with a two-option accessible mode switch: Calls and Threads.
- Calls mode retains current table, filters, sorting, pagination, selected-row summary, export, and Evidence navigation.
- Threads mode retains ranking, grouping, bounded call expansion, pagination, and Evidence navigation.
- Shared filters have one owner. Mode-specific filters are preserved in URL state but ignored outside their mode.
- Switching modes does not refetch unrelated data until that mode becomes active.
- Old `view=calls` and `view=threads` URLs normalize to Explore with the corresponding mode.
- No cross-mode calculation is implemented in the frontend.

- [ ] **Step 1: Write failing state tests.** Cover default mode, old URL normalization, deep-linked call/thread, mode switching, browser back/forward, shared time/history scope, incompatible filter cleanup, and preserved pagination per mode.

- [ ] **Step 2: Extract embeddable views.** Refactor `CallsPage` and `ThreadsPage` into view components that accept shell-owned scope and navigation callbacks. Do not duplicate queries or business calculations.

- [ ] **Step 3: Implement Explore shell and URL state.** The mode switch uses a tablist or equivalent accessible control and has keyboard coverage.

- [ ] **Step 4: Add live browser tests.** Prove Calls → Evidence → return, Threads → Evidence → return, mode back/forward, mobile rendering, and no duplicate network request on same-source return.

- [ ] **Step 5: Verify.**

```bash
npm --workspace frontend/dashboard test -- ExplorePage.test.tsx exploreState.test.ts CallsPage.test.tsx ThreadsPage.test.tsx threadsUrlState.test.ts
npm run dashboard:typecheck
npm run dashboard:lint
npm run dashboard:smoke
```

Expected: PASS; Explore is the only primary evidence browser.

- [ ] **Step 6: Commit.**

```bash
git add frontend/dashboard/src/features/explore frontend/dashboard/src/features/calls/CallsPage.tsx frontend/dashboard/src/features/threads/ThreadsPage.tsx frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx frontend/dashboard/src/features/threads/threadsUrlState.ts frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/api/client.ts frontend/dashboard/src/api/types.ts tests/playwright/dashboard-react.spec.mjs
git commit -m "feat: unify calls and threads in Explore"
```

### Task 21: Build one contextual Evidence route for calls, threads, findings, and allowance claims

**Files:**

- Create: `frontend/dashboard/src/features/evidence/EvidencePage.tsx`
- Create: `frontend/dashboard/src/features/evidence/EvidencePage.module.css`
- Create: `frontend/dashboard/src/features/evidence/evidenceRouteState.ts`
- Create: `frontend/dashboard/src/features/evidence/evidenceRouteState.test.ts`
- Create: `frontend/dashboard/src/features/evidence/EvidencePage.test.tsx`
- Create: `frontend/dashboard/src/features/evidence/CallEvidence.tsx`
- Create: `frontend/dashboard/src/features/evidence/ThreadEvidence.tsx`
- Create: `frontend/dashboard/src/features/evidence/FindingEvidence.tsx`
- Create: `frontend/dashboard/src/features/evidence/AllowanceEvidence.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Modify: `tests/server/test_server_open_investigator.py`
- Create: `tests/server/test_server_evidence.py`

**Evidence route contract:**

```text
?view=evidence&kind=call&record=<canonical-record-id>
?view=evidence&kind=thread&thread_key=<canonical-thread-key>
?view=evidence&kind=finding&analysis=<analysis-id>&finding=<finding-id>
?view=evidence&kind=allowance&analysis=<analysis-id>&evidence=<evidence-id>
```

- Call evidence reuses current aggregate Call Investigator readouts and explicit context controls.
- Thread evidence shows bounded thread summary and paginated calls.
- Finding evidence shows claim, scope, confidence, limitations, and linked evidence.
- Allowance evidence shows the selected persisted claim and supporting transitions.
- The route never appears in primary navigation.
- Every evidence type has a canonical return target and copy-link action.
- Unsupported or stale selectors render a recoverable not-found state with no automatic fallback to a similarly named record.

- [ ] **Step 1: Write failing URL and component tests.** Cover each kind, malformed selectors, stale analysis, archived scope, return navigation, context disabled, and browser reload.

- [ ] **Step 2: Add `/api/v2/evidence`.** It delegates to the evidence application service and returns the shared envelope. Register it as an interactive/bounded route in `route_inventory.py`.

- [ ] **Step 3: Refactor Call Investigator.** Move reusable call readouts into `CallEvidence`; retain old component as a compatibility route wrapper through 0.23.

- [ ] **Step 4: Implement remaining evidence renderers.** They render server facts; no inference occurs in React.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/server/test_server_evidence.py tests/server/test_server_open_investigator.py tests/application/test_evidence.py -q
npm --workspace frontend/dashboard test -- EvidencePage.test.tsx evidenceRouteState.test.ts CallInvestigatorPage.test.tsx
npm run dashboard:typecheck
npm run dashboard:release-candidate
```

Expected: PASS for every canonical target and recoverable stale state.

- [ ] **Step 6: Commit.**

```bash
git add frontend/dashboard/src/features/evidence frontend/dashboard/src/features/investigator/InvestigatorPage.tsx frontend/dashboard/src/api/client.ts frontend/dashboard/src/api/types.ts frontend/dashboard/src/routes/DashboardRouteView.tsx src/codex_usage_tracker/server/routes.py src/codex_usage_tracker/server/handler.py src/codex_usage_tracker/server/route_inventory.py tests/server/test_server_evidence.py tests/server/test_server_open_investigator.py
git commit -m "feat: add contextual evidence route"
```

### Task 22: Refocus Limits and Settings for the Evidence Console

**Files:**

- Modify: `frontend/dashboard/src/features/usage-drain/UsageDrainPage.tsx`
- Modify: `frontend/dashboard/src/features/usage-drain/UsageDrainPage.test.tsx`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.test.tsx`
- Modify: `frontend/dashboard/src/features/settings/useSettingsSection.ts`
- Modify: `frontend/dashboard/src/app/useExperimentalDashboardFeatures.ts`
- Modify: `frontend/dashboard/src/app/useExperimentalDashboardFeatures.test.tsx`
- Modify: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx`
- Modify: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.test.tsx`
- Modify: `docs/evidence-console.md`

**Limits changes:**

- Rename route label only; keep established allowance calculations and APIs.
- Lead with observed status and reset information.
- Show estimates and change claims with explicit type labels.
- Each supported change/evidence row opens the Evidence route.
- Hide compatibility v1 controls and unlimited technical query controls under an Advanced disclosure.
- Do not add a new statistical method.

**Settings changes:**

- Show installation/runtime readiness, configured MCP profile, source/data paths, pricing/rate-card status, language, history defaults, and service status.
- Replace `Show experimental dashboard features` with `Show compatibility and Labs links` under Advanced.
- Labs are links, not primary navigation items.
- Do not claim current-task MCP exposure; retain exact readiness wording.

- [ ] **Step 1: Write failing behavior tests.** Cover finding type labels, evidence links, Labs default off, Labs immediate toggle, malformed storage value, restricted localStorage, and exact readiness wording.

- [ ] **Step 2: Implement the refocus without changing backend mathematics.** Use existing allowance v2 payloads.

- [ ] **Step 3: Add Labs link inventory from legacy route catalog.** Each item includes maturity, lifecycle, replacement MCP operation, and direct link. No item appears outside Settings when the preference is off.

- [ ] **Step 4: Verify.**

```bash
npm --workspace frontend/dashboard test -- UsageDrainPage.test.tsx SettingsPage.test.tsx useExperimentalDashboardFeatures.test.tsx ConversationalAnalysisStatus.test.tsx
npm run dashboard:typecheck
npm run dashboard:stylelint
```

Expected: PASS; Limits remains a core route and Settings is the sole Labs discovery point.

- [ ] **Step 5: Commit.**

```bash
git add frontend/dashboard/src/features/usage-drain/UsageDrainPage.tsx frontend/dashboard/src/features/usage-drain/UsageDrainPage.test.tsx frontend/dashboard/src/features/settings/SettingsPage.tsx frontend/dashboard/src/features/settings/SettingsPage.test.tsx frontend/dashboard/src/features/settings/useSettingsSection.ts frontend/dashboard/src/app/useExperimentalDashboardFeatures.ts frontend/dashboard/src/app/useExperimentalDashboardFeatures.test.tsx frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.test.tsx docs/evidence-console.md
git commit -m "refactor: focus Limits and Settings"
```

### Task 23: Prove job parity and hide legacy workbenches from default navigation

**Files:**

- Create: `docs/dashboard-sunset-job-parity-v2.md`
- Create: `tests/application/test_dashboard_sunset_parity.py`
- Modify: `frontend/dashboard/src/app/navigation.ts`
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Modify: `frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`
- Modify: `frontend/dashboard/src/components/FeatureMaturityBanner.tsx`
- Modify: `frontend/dashboard/src/components/FeatureMaturityBanner.test.tsx`
- Modify: `docs/deprecations.md`
- Modify: `docs/mcp.md`

**Required parity rows:**

| Legacy job | Core replacement | Evidence destination |
| --- | --- | --- |
| Diagnose usage drivers | `usage_analyze(goal="usage_spike")` | Finding/Call/Thread Evidence |
| Broad token waste | `usage_analyze(goal="token_waste")` | Finding Evidence + Explore |
| Context/cache analysis | `usage_analyze(goal="context_bloat")` or `usage_analyze(goal="cache_failure")` | Call/Thread Evidence |
| Repeated command/file churn | `usage_analyze(goal="workflow_churn")` | Finding Evidence |
| Report selection and explanation | `usage_analyze` or `usage_query` | Evidence/Explore |
| Compression candidate ranking | compatibility full-profile tools through 0.24 | direct Labs route during transition |
| Diagnostic fact browsing | `usage_query` plus `usage_evidence` | Evidence/Explore |
| Subagent analysis | `usage_query(entity="subagent")` or `usage_analyze(goal="subagent_cost")` | Explore/Evidence |

- [ ] **Step 1: Write failing parity tests over synthetic fixtures.** For every row, assert same canonical evidence IDs, same history scope, same accounting context, and equivalent caveats. Intentional omissions require an explicit decision row.

- [ ] **Step 2: Fill only missing parity fields.** Add additive evidence fields or strategy mappings; do not recreate old dashboard visuals.

- [ ] **Step 3: Switch primary navigation.** Home, Explore, Limits, Settings only. Remove Files/Commands/Models aliases. Evidence remains contextual. Legacy workbench direct routes remain operational and show a transition banner with their core replacement.

- [ ] **Step 4: Add direct-route tests.** Old bookmarks load, show lifecycle notice, and offer a core prompt or link. They do not reappear in navigation.

- [ ] **Step 5: Sign the parity record.** Every row records fixture, replacement tool/request, expected evidence IDs, actual evidence IDs, result, and owner. Any non-PASS row blocks release.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/application/test_dashboard_sunset_parity.py tests/application/test_analyze.py tests/application/test_query.py tests/application/test_evidence.py -q
npm --workspace frontend/dashboard test -- App.shell.test.tsx routeCatalog.test.ts FeatureMaturityBanner.test.tsx DiagnosticsPage.query.test.tsx
npm run dashboard:release-candidate
```

Expected: PASS and exactly three analytical navigation items plus the Settings utility action.

- [ ] **Step 7: Commit.**

```bash
git add docs/dashboard-sunset-job-parity-v2.md tests/application/test_dashboard_sunset_parity.py frontend/dashboard/src/app/navigation.ts frontend/dashboard/src/app/routeCatalog.ts frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx frontend/dashboard/src/features/investigator/InvestigatorPage.tsx frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx frontend/dashboard/src/features/cache-context/CacheContextPage.tsx frontend/dashboard/src/features/reports/ReportsPage.tsx frontend/dashboard/src/components/FeatureMaturityBanner.tsx frontend/dashboard/src/components/FeatureMaturityBanner.test.tsx docs/deprecations.md docs/mcp.md
git commit -m "feat: simplify the default dashboard surface"
```

### Task 24: Remove the Usage Constellation and unnecessary frontend dependencies

**Files:**

- Delete: `frontend/dashboard/src/features/overview/UsageConstellation.tsx` or its current source equivalent
- Delete: corresponding constellation tests and fixtures that exist only for that feature
- Delete: `tests/playwright/dashboard-constellation.spec.mjs` if present
- Delete: packaged constellation JavaScript assets
- Modify: `frontend/dashboard/package.json`
- Modify: `package-lock.json`
- Modify: `package.json`
- Modify: `scripts/check-visualization-renderer-bundle.mjs`
- Modify: `scripts/check-dashboard-bundles.mjs`
- Modify: `scripts/check_release.py`
- Modify: `tests/release_catalog.py`
- Modify: `docs/deprecations.md`

**Removal rule:**

- Remove `three` and `@types/three` if no remaining runtime source imports them.
- Retain D3/ECharts only for evidence/allowance visualizations that remain in Home, Explore, Limits, or Evidence.
- Bundle budgets ratchet downward; do not merely raise or preserve existing thresholds.
- No static or packaged asset may reference a deleted chunk.

- [ ] **Step 1: Add failing dependency and asset tests.** Assert no import of `three`, no constellation route/component, no packaged asset, and a lower main-bundle ceiling based on the current measured artifact minus the removed chunk with 10% allowance.

- [ ] **Step 2: Remove source and dependency entries.** Rebuild the lockfile using the repository's normal npm version.

- [ ] **Step 3: Rebuild packaged assets and verify no stale chunk.**

- [ ] **Step 4: Verify.**

```bash
npm ci
npm run dashboard:verify
npm run dashboard:assets:check
npm run dashboard:release-candidate
python scripts/check_release.py
```

Expected: PASS; `npm ls three` returns no production dependency.

- [ ] **Step 5: Commit.**

```bash
git add -A frontend/dashboard package.json package-lock.json scripts/check-visualization-renderer-bundle.mjs scripts/check-dashboard-bundles.mjs scripts/check_release.py tests/release_catalog.py docs/deprecations.md src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "refactor: remove non-core dashboard visualization"
```

### Task 25: Add the versioned HTTP API v2 application facade

**Files:**

- Create: `src/codex_usage_tracker/interfaces/http/__init__.py`
- Create: `src/codex_usage_tracker/interfaces/http/v2.py`
- Create: `src/codex_usage_tracker/interfaces/http/serialization.py`
- Create: `tests/interfaces/http/test_v2.py`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Modify: `src/codex_usage_tracker/server/request_guards.py`
- Modify: `tests/server/test_route_inventory.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/architecture.md`

**Stable v2 endpoints:**

```text
GET  /api/v2/status
POST /api/v2/refresh
GET  /api/v2/jobs/{job_id}
POST /api/v2/analyze
POST /api/v2/query
POST /api/v2/evidence
POST /api/v2/allowance
GET  /api/v2/capabilities
```

**Rules:**

- Endpoints call application services used by MCP; they do not call MCP functions.
- Requests and responses use the same typed contracts as the core MCP tools.
- POST bodies have explicit maximum byte sizes and reject unknown top-level fields.
- Existing dashboard GET routes remain through compatibility but new Evidence Console code prefers v2.
- Mutating/expensive endpoints retain token and local-origin guards.
- Route inventory declares execution type, input limit, output limit, cache behavior, and all-history behavior.

- [ ] **Step 1: Write failing route and serialization tests.** Cover exact paths, methods, content type, malformed JSON, oversized body, unknown fields, token failures, status codes, job polling, and schema equality with MCP results.

- [ ] **Step 2: Implement pure request decoders and response serialization.** Keep HTTP details out of application modules.

- [ ] **Step 3: Register routes and route profiles.** Do not remove v1 routes.

- [ ] **Step 4: Switch Evidence Console API client to v2 where parity exists.** Add temporary fallback only for an explicitly documented old-server compatibility case.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/interfaces/http/test_v2.py tests/server/test_route_inventory.py tests/core/test_json_contracts.py tests/dashboard/test_dashboard_server.py -q
npm --workspace frontend/dashboard test -- client.test.ts HomePage.test.tsx ExplorePage.test.tsx EvidencePage.test.tsx
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
```

Expected: PASS with bounded v2 routes.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/interfaces/http src/codex_usage_tracker/server/routes.py src/codex_usage_tracker/server/handler.py src/codex_usage_tracker/server/route_inventory.py src/codex_usage_tracker/server/request_guards.py tests/interfaces/http/test_v2.py tests/server/test_route_inventory.py tests/core/test_json_contracts.py docs/cli-json-schemas.md docs/architecture.md frontend/dashboard/src/api
git commit -m "feat: add Evidence Console HTTP API v2"
```

### Task 26: Introduce the simplified CLI hierarchy without deleting legacy commands

**Files:**

- Create: `src/codex_usage_tracker/interfaces/cli/__init__.py`
- Create: `src/codex_usage_tracker/interfaces/cli/parser.py`
- Create: `src/codex_usage_tracker/interfaces/cli/commands.py`
- Create: `src/codex_usage_tracker/interfaces/cli/namespaces.py`
- Create: `tests/interfaces/cli/test_parser.py`
- Create: `tests/interfaces/cli/test_commands.py`
- Modify: `src/codex_usage_tracker/cli/parser.py`
- Modify: `src/codex_usage_tracker/cli/main.py`
- Modify: `src/codex_usage_tracker/cli/commands_reports.py`
- Modify: `tests/cli/test_cli_release.py`
- Modify: `docs/cli-reference.md`
- Modify: `docs/deprecations.md`

**Stable top-level commands after this task:**

```text
setup
status
doctor
refresh
analyze
query
open
export
config
service
admin
```

**Namespace mapping:**

- `analyze` invokes the analysis application service.
- `query` invokes the query service.
- `open` opens the Evidence Console or an exact dashboard target.
- `config pricing|allowance|rate-card|projects|thresholds` owns configuration commands.
- `service install|status|uninstall|serve` owns persistent/live service commands.
- `admin inspect-log|rebuild-index|reset-db|dedupe-diagnostics|source-coverage|support-bundle|dogfood|mcp` owns operational and manual MCP-server commands.
- Existing top-level commands remain aliases through 0.24 and print one concise deprecation line to stderr only when invoked interactively; JSON output remains valid and warnings go to stderr.

- [ ] **Step 1: Write failing parser inventory tests.** Assert exact stable top-level names, namespace subcommands, old aliases, help formatting, Python 3.10 behavior, and translated help compatibility.

- [ ] **Step 2: Build new parser as the canonical parser.** Old `cli/parser.py` imports and returns it for compatibility. Do not duplicate option definitions; helper functions build shared option groups.

- [ ] **Step 3: Implement application command handlers.** `analyze` and `query` serialize the same contracts as MCP/HTTP. `open` accepts target JSON, target ID, call ID, thread key, or the default Home route.

- [ ] **Step 4: Add warning policy.** Machine-readable commands never contaminate stdout. Tests inspect stdout and stderr separately.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/interfaces/cli/test_parser.py tests/interfaces/cli/test_commands.py tests/cli/test_cli_release.py tests/core/test_i18n.py -q
python -m compileall src
python scripts/check_release.py
```

Expected: PASS; old scripts keep working and the primary help is substantially shorter.

- [ ] **Step 6: Commit.**

```bash
git add src/codex_usage_tracker/interfaces/cli src/codex_usage_tracker/cli/parser.py src/codex_usage_tracker/cli/main.py src/codex_usage_tracker/cli/commands_reports.py tests/interfaces/cli tests/cli/test_cli_release.py docs/cli-reference.md docs/deprecations.md
git commit -m "feat: simplify the tracker CLI hierarchy"
```

### Task 27: Gate and publish Release 0.23.0

**Files:**

- Create: `docs/releases/0.23.0.md`
- Create: `docs/upgrading-to-0.23.0.md`
- Create: `docs/evidence-console-route-migration.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `docs/first-five-minutes.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/evidence-console.md`
- Modify: `docs/roadmap/mcp-first-pivot-execution.md`
- Modify: `tests/playwright/dashboard-release-candidate.spec.mjs`
- Modify: `scripts/capture_dashboard_screenshots.mjs`
- Modify: `docs/assets/*`

**Release acceptance:**

- Primary analytical navigation is Home, Explore, and Limits; Settings is a separate shell utility action.
- Evidence route is contextual and supports all four selector kinds.
- Old stable URLs normalize correctly.
- Legacy workbenches are direct-only and clearly transitioning.
- Calls and Threads parity tests pass inside Explore.
- Home does no hidden heavy scan.
- README and first-run guide begin with conversational analysis and use the Evidence Console for verification.
- Removed constellation dependencies and assets are absent.
- CLI primary help shows the new hierarchy.

- [ ] **Step 1: Capture synthetic desktop, tablet, mobile, 200%-zoom, reduced-motion, and keyboard evidence.** Include Home, Explore Calls, Explore Threads, Limits, Evidence, Settings, and one legacy direct route.

- [ ] **Step 2: Run focused acceptance.**

```bash
python -m pytest tests/application/test_dashboard_sunset_parity.py tests/interfaces/http/test_v2.py tests/interfaces/cli tests/core/test_dashboard_targets.py -q
npm --workspace frontend/dashboard test -- HomePage.test.tsx ExplorePage.test.tsx EvidencePage.test.tsx UsageDrainPage.test.tsx SettingsPage.test.tsx App.shell.test.tsx
npm run dashboard:release-candidate
```

- [ ] **Step 3: Run complete release gates.**

```bash
python -m pytest
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
python -m mypy
npm run dashboard:verify
npm run dashboard:assets:check
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
python scripts/check_release.py
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 4: Record release evidence.** Include exact route inventory, default nav, old URL tests, core/full/developer tool counts, CLI command counts, bundle sizes, package sizes, test counts, and coverage.

- [ ] **Step 5: Commit.**

```bash
git add README.md CHANGELOG.md pyproject.toml docs/releases/0.23.0.md docs/upgrading-to-0.23.0.md docs/evidence-console-route-migration.md docs/first-five-minutes.md docs/dashboard-guide.md docs/evidence-console.md docs/roadmap/mcp-first-pivot-execution.md tests/playwright/dashboard-release-candidate.spec.mjs scripts/capture_dashboard_screenshots.mjs docs/assets src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "chore: prepare 0.23.0 Evidence Console release"
```

---

## Release 0.24.0 - Architecture, integrity, and delivery hardening

### Task 28: Add an application composition root and dependency protocols

**Files:**

- Create: `src/codex_usage_tracker/application/container.py`
- Create: `src/codex_usage_tracker/application/protocols.py`
- Create: `src/codex_usage_tracker/application/paths.py`
- Create: `tests/application/test_container.py`
- Create: `tests/application/test_protocols.py`
- Modify: `src/codex_usage_tracker/application/context.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/server.py`
- Modify: `src/codex_usage_tracker/interfaces/http/v2.py`
- Modify: `src/codex_usage_tracker/interfaces/cli/commands.py`
- Modify: `docs/architecture.md`

**Interfaces:**

```python
@dataclass(frozen=True)
class ApplicationPaths:
    codex_home: Path
    db_path: Path
    pricing_path: Path
    allowance_path: Path
    rate_card_path: Path
    thresholds_path: Path
    projects_path: Path

@dataclass(frozen=True)
class ApplicationContainer:
    paths: ApplicationPaths
    clock: Clock
    repositories: RepositorySet
    jobs: JobService
    analyses: AnalysisCatalog
    dashboard_targets: DashboardTargetResolver


def build_application_container(paths: ApplicationPaths) -> ApplicationContainer: ...
```

**Protocols:**

- `Clock`
- `UsageRepository`
- `SourceRepository`
- `AnalysisResultRepository`
- `JobRepository`
- `DashboardTargetResolver`
- `PricingProvider`

**Rules:**

- Interfaces build a container once and pass it to application services.
- Application and analytics modules do not import default global paths.
- Default paths remain only in CLI/plugin composition code.
- Tests can construct a container against temporary paths without monkeypatching module globals.
- No dependency-injection framework is added.

- [ ] **Step 1: Write failing protocol and container tests.** Assert frozen configuration, custom paths, deterministic clock injection, repository sharing within one container, and no default-home access in application tests.

- [ ] **Step 2: Define minimal protocols from actual service needs.** Do not create speculative generic CRUD interfaces. Each protocol method must be consumed by a current application service.

- [ ] **Step 3: Build the composition root.** Use concrete store/report/job implementations. Avoid service locators: services receive the container or exact dependencies explicitly.

- [ ] **Step 4: Convert core MCP, HTTP v2, and new CLI handlers.** Compatibility modules may continue using historical globals until their sunset tasks.

- [ ] **Step 5: Add an import rule test.** Application modules may import `application.protocols`, models, and domain packages; they may not import `core.paths.DEFAULT_*`.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/application/test_container.py tests/application/test_protocols.py tests/mcp tests/interfaces -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application
python -m ruff check src/codex_usage_tracker/application tests/application
```

Expected: PASS with no application test reading the developer's home directory.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/application/container.py src/codex_usage_tracker/application/protocols.py src/codex_usage_tracker/application/paths.py src/codex_usage_tracker/application/context.py src/codex_usage_tracker/interfaces/mcp/server.py src/codex_usage_tracker/interfaces/http/v2.py src/codex_usage_tracker/interfaces/cli/commands.py tests/application/test_container.py tests/application/test_protocols.py docs/architecture.md
git commit -m "refactor: compose tracker application services"
```

### Task 29: Complete the MCP package extraction and eliminate import-side-effect registration

**Files:**

- Create or complete: `src/codex_usage_tracker/interfaces/mcp/server.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/transports.py`
- Create: `src/codex_usage_tracker/interfaces/mcp/serialization.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_dashboard.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_discovery.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_allowance.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_subagents.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_compression.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_investigations.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_visualization.py`
- Move/refactor from: `src/codex_usage_tracker/cli/mcp_dogfood.py`
- Retain compatibility shims at the old paths
- Create: `tests/mcp/test_server.py`
- Create: `tests/mcp/test_no_import_registration.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `config/vulture-whitelist.py`
- Modify: `docs/architecture.md`

**Required shape:**

```python
def create_mcp_server(*, profile: McpProfile, container: ApplicationContainer) -> FastMCP:
    server = FastMCP("codex-usage-tracker")
    for definition in tools_for_profile(profile):
        server.add_tool(definition.callable, name=definition.name, description=definition.description)
    return server


def main() -> None:
    profile = profile_from_environment()
    create_mcp_server(profile=profile, container=build_default_container()).run()
```

**Rules:**

- Importing any MCP implementation module registers zero tools globally.
- Tool registration occurs only inside `create_mcp_server`.
- Old module functions remain importable through shims during compatibility.
- The public `python -m codex_usage_tracker.mcp_server` entry continues to work.
- The server factory accepts a test container and does not inspect user paths at import time.

- [ ] **Step 1: Write a failing import-side-effect test.** Import every `codex_usage_tracker.interfaces.mcp.*` and compatibility `cli.mcp_*` module in a fresh interpreter; assert no global FastMCP registry changes.

- [ ] **Step 2: Move implementation functions by concern.** Keep core tools in `interfaces/mcp/core_tools.py`; compatibility tool adapters in `interfaces/mcp/compatibility_tools.py`; developer tools in `interfaces/mcp/developer_tools.py`. Split further only when a file would exceed 450 source lines.

- [ ] **Step 3: Replace decorators with explicit definitions.** Preserve names, parameters, descriptions, and schemas.

- [ ] **Step 4: Add server-factory tests.** Create two servers with different profiles in one process and prove their tool inventories remain isolated.

- [ ] **Step 5: Add compatibility shims.** Shims re-export functions and emit no warning at import time.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/mcp/test_server.py tests/mcp/test_no_import_registration.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/interfaces/mcp
python -m ruff check src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_*.py tests/mcp
python scripts/check_release.py
```

Expected: PASS; two independently constructed servers have no cross-registration.

- [ ] **Step 7: Commit.**

```bash
git add -A src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_*.py src/codex_usage_tracker/mcp_server.py tests/mcp tests/cli/test_mcp_integration.py config/vulture-whitelist.py docs/architecture.md
git commit -m "refactor: extract the MCP interface package"
```

### Task 30: Enforce Python architecture with Tach domain boundaries

**Files:**

- Modify: `tach.toml`
- Create: `src/codex_usage_tracker/core/tach.domain.toml`
- Create: `src/codex_usage_tracker/ingest/tach.domain.toml`
- Create: `src/codex_usage_tracker/store/tach.domain.toml`
- Create: `src/codex_usage_tracker/analytics/tach.domain.toml`
- Create: `src/codex_usage_tracker/evidence/tach.domain.toml`
- Create: `src/codex_usage_tracker/jobs/tach.domain.toml`
- Create: `src/codex_usage_tracker/application/tach.domain.toml`
- Create: `src/codex_usage_tracker/interfaces/tach.domain.toml`
- Create: `src/codex_usage_tracker/dashboard/tach.domain.toml`
- Create: `src/codex_usage_tracker/plugin/tach.domain.toml`
- Create: `src/codex_usage_tracker/compatibility/tach.domain.toml`
- Create: `tests/architecture/test_dependency_directions.py`
- Create: `tests/architecture/test_public_package_boundaries.py`
- Modify: `docs/architecture.md`
- Modify: `.github/workflows/ci.yml`

**Target dependency direction:**

```text
interfaces -> application -> analytics/evidence/jobs -> store/ingest/core
server compatibility -> interfaces/http + application
plugin -> interfaces/mcp + interfaces/cli composition
compatibility -> application + historical adapters
frontend build assets -> no Python imports
```

**Forbidden directions:**

- `core` imports no higher layer.
- `store` imports no `application`, `interfaces`, or MCP modules.
- `analytics` imports no transport modules.
- `application` imports no `cli`, `mcp`, or `server` transport implementation.
- `interfaces/mcp` does not import `interfaces/http` or CLI handlers.
- `interfaces/http` does not call MCP functions.
- compatibility code cannot be imported by stable domain packages.

- [ ] **Step 1: Add a diagnostic baseline test.** Run current Tach and record every violation grouped by target domain. Do not create a broad ignore baseline.

- [ ] **Step 2: Move or invert dependencies in focused commits within this task branch.** Extract shared models downward, pass callbacks/protocols upward, and remove private cross-package imports. Do not add façade modules solely to fool the graph.

- [ ] **Step 3: Enable:**

```toml
root_module = "forbid"
forbid_circular_dependencies = true
layers_explicit_depends_on = true
```

- [ ] **Step 4: Add secondary import regression tests.** Parse Python imports and assert transport/domain restrictions even when Tach config changes accidentally.

- [ ] **Step 5: Make Tach a named CI step in hardening Python.** It must run before dead-code checks so architecture failures are obvious.

- [ ] **Step 6: Verify.**

```bash
tach check
python -m pytest tests/architecture -q
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check src tests/architecture
```

Expected: PASS with zero cycles and every source module owned.

- [ ] **Step 7: Commit.**

```bash
git add tach.toml src/codex_usage_tracker/**/tach.domain.toml tests/architecture docs/architecture.md .github/workflows/ci.yml src/codex_usage_tracker
git commit -m "refactor: enforce tracker architecture boundaries"
```

### Task 31: Enforce SQLite foreign keys and integrity checks

**Files:**

- Modify: `src/codex_usage_tracker/store/connection.py`
- Create: `src/codex_usage_tracker/store/integrity.py`
- Create: `tests/store/test_connection_integrity.py`
- Create: `tests/store/test_foreign_key_cascades.py`
- Create: `tests/store/test_integrity_report.py`
- Modify: `src/codex_usage_tracker/diagnostics/api.py`
- Modify: `src/codex_usage_tracker/diagnostics/models.py`
- Modify: `src/codex_usage_tracker/interfaces/cli/commands.py`
- Modify: `src/codex_usage_tracker/application/status.py`
- Modify: `docs/data-posture.md`
- Modify: `docs/architecture.md`

**Connection requirements:**

```python
conn.execute("PRAGMA foreign_keys = ON")
if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
    raise DatabaseIntegrityError("SQLite foreign-key enforcement is unavailable")
```

- Every read/write connection uses the shared helper or an explicitly tested equivalent.
- `PRAGMA foreign_key_check` and `PRAGMA integrity_check` are available through a read-only integrity service.
- Doctor/status report pass/fail/unknown without silently repairing data.
- Cascades and cleanup ordering are tested for usage events, content rows, compression facts, recommendation facts, allowance observations, OTel mappings, and analysis/job rows.
- Existing valid databases migrate without a forced rebuild.

- [ ] **Step 1: Write failing connection tests.** Assert foreign keys enabled for every shared connection, rollback on exception, WAL behavior retained, and an intentional orphan insert fails.

- [ ] **Step 2: Inventory all foreign keys.** Add a test that parses `PRAGMA foreign_key_list` for every table and records expected parent/child relationships.

- [ ] **Step 3: Implement integrity service.** Return structured counts and bounded table names; never dump row content.

- [ ] **Step 4: Add doctor and `admin integrity` surfaces.** The CLI exits 1 on integrity findings and 2 on invalid/unreadable database.

- [ ] **Step 5: Run migration fixtures from supported historical schemas.** Use current migration tests plus at least schema versions 13, 24, 27, 30, and current-minus-one.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/store/test_connection_integrity.py tests/store/test_foreign_key_cascades.py tests/store/test_integrity_report.py tests/store/test_store_migrations.py tests/diagnostics -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/store/integrity.py
```

Expected: PASS and no orphan survives a cascade fixture.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/store/connection.py src/codex_usage_tracker/store/integrity.py src/codex_usage_tracker/diagnostics src/codex_usage_tracker/interfaces/cli/commands.py src/codex_usage_tracker/application/status.py tests/store/test_connection_integrity.py tests/store/test_foreign_key_cascades.py tests/store/test_integrity_report.py tests/store/test_store_migrations.py docs/data-posture.md docs/architecture.md
git commit -m "fix: enforce SQLite relational integrity"
```

### Task 32: Add indexed byte offsets for bounded context retrieval

**Files:**

- Modify: `src/codex_usage_tracker/core/schema.py`
- Modify: `src/codex_usage_tracker/store/schema.py`
- Create: `src/codex_usage_tracker/store/context_offsets.py`
- Modify: `src/codex_usage_tracker/source_records.py`
- Modify: parser/ingest modules that create `UsageEvent`
- Modify: `src/codex_usage_tracker/context/loader.py`
- Modify: `src/codex_usage_tracker/context/reader.py`
- Create: `tests/context/test_byte_offset_reads.py`
- Create: `tests/store/test_context_offsets.py`
- Modify: `tests/store/test_store_migrations.py`
- Modify: `scripts/benchmark_synthetic_history.py`
- Modify: `docs/architecture.md`

**Schema change:**

- Add nullable `source_byte_offset INTEGER` to usage records or a focused lookup table keyed by `record_id`.
- Increment schema version exactly once.
- New parses record the byte offset of the target event line.
- Existing rows remain null and use sequential fallback until reindexed.

**Read algorithm:**

1. Validate source-file provenance against stored file identity/size metadata.
2. If a validated byte offset exists, seek to a bounded pre-target anchor or exact target and reconstruct only the required turn window.
3. If offset is absent or stale, use the current sequential scan.
4. Never trust an offset after source replacement without provenance validation.
5. Return diagnostics identifying `offset_seek` or `sequential_fallback`.

- [ ] **Step 1: Write failing parser/store tests.** Assert exact byte offsets for UTF-8 ASCII and multibyte lines, append-only refresh, rewritten file, cloned file, and Windows newline fixtures.

- [ ] **Step 2: Add migration and writer support.** Preserve old constructors with a default `None` field.

- [ ] **Step 3: Write context-read equivalence tests.** Offset and sequential algorithms must return byte-for-byte equivalent normalized payloads for quick/full modes, tool-output options, compaction history, malformed JSON lines, and target turns near file boundaries.

- [ ] **Step 4: Implement seek path and fallback.** Never scan beyond the target event. Add a configurable maximum backward scan window and fall back when the selected turn begins before that window.

- [ ] **Step 5: Add a synthetic performance ratchet.** For a 100,000-line source with a target in the final 5%, offset mode must inspect fewer than 5% of file bytes and be at least 5x faster than forced sequential mode on median of five runs. Keep timing threshold generous enough for CI variance and also assert inspected-byte ratio, which is deterministic.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/context/test_byte_offset_reads.py tests/store/test_context_offsets.py tests/store/test_store_migrations.py tests/context -q
python scripts/benchmark_synthetic_history.py --rows 1000 --with-source-logs --json --enforce-thresholds
```

Expected: PASS with payload equivalence and bounded-byte evidence.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/core/schema.py src/codex_usage_tracker/store/schema.py src/codex_usage_tracker/store/context_offsets.py src/codex_usage_tracker/source_records.py src/codex_usage_tracker/parser src/codex_usage_tracker/context/loader.py src/codex_usage_tracker/context/reader.py tests/context/test_byte_offset_reads.py tests/store/test_context_offsets.py tests/store/test_store_migrations.py scripts/benchmark_synthetic_history.py docs/architecture.md
git commit -m "perf: seek directly to indexed call context"
```

### Task 33: Persist generic analysis jobs and reusable results

**Files:**

- Modify: `src/codex_usage_tracker/store/schema.py`
- Create: `src/codex_usage_tracker/store/analysis_job_schema.py`
- Create: `src/codex_usage_tracker/store/analysis_job_repository.py`
- Modify: `src/codex_usage_tracker/jobs/service.py`
- Modify: `src/codex_usage_tracker/jobs/models.py`
- Modify: `src/codex_usage_tracker/application/analyze.py`
- Modify: `src/codex_usage_tracker/application/allowance.py`
- Modify: `src/codex_usage_tracker/application/refresh.py`
- Create: `tests/store/test_analysis_job_repository.py`
- Create: `tests/jobs/test_persisted_jobs.py`
- Modify: `tests/store/test_store_migrations.py`
- Modify: `docs/architecture.md`

**Tables:**

```sql
CREATE TABLE analysis_jobs (
    job_id TEXT PRIMARY KEY,
    job_kind TEXT NOT NULL,
    semantic_key TEXT NOT NULL,
    status TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    request_schema TEXT NOT NULL,
    request_json TEXT NOT NULL,
    progress_json TEXT NOT NULL,
    result_schema TEXT,
    result_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    last_accessed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX ... ON analysis_jobs(job_kind, semantic_key, status) ...;
```

The exact index may use a partial unique index for active states if supported by existing migration conventions.

**Rules:**

- Persist compact normalized requests and bounded results only.
- Do not persist raw context in generic jobs.
- Active in-process execution is recoverable as `interrupted` after process restart; completed compatible results remain reusable.
- Job retention is count/time bounded and cleanup runs transactionally.
- Existing allowance/compression tables remain until compatibility removal; adapters can mirror or migrate completed results without deleting historical rows.

- [ ] **Step 1: Write migration/repository tests.** Cover create, active deduplication, completion, failure, interrupted recovery, result compatibility, stale revision, retention pruning, and concurrent readers.

- [ ] **Step 2: Implement repository and recovery.** On startup, mark `queued|running` rows from previous process as `interrupted`; do not resume unknown code automatically.

- [ ] **Step 3: Upgrade `JobService`.** Use persisted state as source of truth, with in-memory worker handles only for active execution.

- [ ] **Step 4: Route new analysis and allowance jobs through the repository.** Refresh may remain a transient job if its result is not semantically reusable; it still exposes generic status.

- [ ] **Step 5: Add cleanup and doctor diagnostics.** Report active, interrupted, failed, completed, and pruned counts.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/store/test_analysis_job_repository.py tests/jobs/test_persisted_jobs.py tests/application/test_analyze.py tests/application/test_allowance.py tests/store/test_store_migrations.py -q
python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/jobs src/codex_usage_tracker/store/analysis_job_repository.py
```

Expected: PASS; completed result survives a new application container.

- [ ] **Step 7: Commit.**

```bash
git add src/codex_usage_tracker/store/schema.py src/codex_usage_tracker/store/analysis_job_schema.py src/codex_usage_tracker/store/analysis_job_repository.py src/codex_usage_tracker/jobs src/codex_usage_tracker/application/analyze.py src/codex_usage_tracker/application/allowance.py src/codex_usage_tracker/application/refresh.py tests/store/test_analysis_job_repository.py tests/jobs/test_persisted_jobs.py tests/store/test_store_migrations.py docs/architecture.md
git commit -m "feat: persist reusable analysis jobs"
```

### Task 34: Make coverage, schema, parity, and work-proof gates directly blocking

**Files:**

- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Create: `tests/quality/test_tool_work_proof.py`
- Create: `tests/quality/test_schema_inventory.py`
- Create: `tests/quality/test_compatibility_inventory.py`
- Modify: `scripts/check_release.py`
- Modify: `tests/release_catalog.py`
- Modify: `docs/development.md`

**Blocking thresholds:**

```toml
[tool.coverage.report]
fail_under = 85
```

- Overall branch coverage must be at least 85%.
- Changed Python source lines must be at least 90% covered, enforced by the existing Agent Maintainer/diff-cover path or an explicit CI step.
- Every MCP tool must declare expected work proof: result count, processed source count, matched row count, or constant-size status semantics.
- Successful tool executions that unexpectedly process zero units when relevant inputs exist fail a contract test.
- Every emitted schema appears in the runtime registry, documentation, and release inventory.
- Every compatibility alias appears in `docs/deprecations.md` and tests.

- [ ] **Step 1: Add direct coverage threshold and verify current suite.** If current coverage is below 85%, add focused tests for uncovered stable/core/application paths. Do not exclude files solely to meet the number.

- [ ] **Step 2: Add work-proof metadata to tool catalog.** Define:

```python
@dataclass(frozen=True)
class WorkProofContract:
    kind: Literal["constant", "rows", "sources", "evidence", "job"]
    minimum_when_applicable: int
    applicability_field: str | None
    processed_field: str | None
```

- [ ] **Step 3: Write synthetic tool tests.** A query over known rows cannot return success with `processed_rows=0`; refresh over one changed file cannot claim no inspected source; status is allowed constant work.

- [ ] **Step 4: Add schema and compatibility inventory checks to `check_release.py`.** Fail on undocumented or orphaned entries.

- [ ] **Step 5: Update CI commands.** Use `--cov-fail-under=85` or config-driven equivalent. Add changed-line coverage on pull requests.

- [ ] **Step 6: Verify.**

```bash
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pytest tests/quality -q
python scripts/check_release.py
```

Expected: PASS at or above 85% branch coverage.

- [ ] **Step 7: Commit.**

```bash
git add pyproject.toml .github/workflows/ci.yml tests/quality scripts/check_release.py tests/release_catalog.py docs/development.md src/codex_usage_tracker/interfaces/mcp
git commit -m "test: block false-green and coverage regressions"
```

### Task 35: Pin GitHub Actions and release dependencies to immutable revisions

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/publish.yml`
- Modify: `.github/workflows/pricing-compat.yml`
- Modify: `.github/workflows/allowance-statistical-calibration.yml`
- Modify: `.github/dependabot.yml`
- Modify: `scripts/check_release.py`
- Create: `tests/ci/test_immutable_action_pins.py`
- Modify: `docs/development.md`
- Modify: `docs/release-checklist.md`

**Rules:**

- Every third-party `uses:` reference is a full 40-character commit SHA.
- A trailing comment records the reviewed release tag, for example:

```yaml
uses: actions/checkout@<40-char-sha> # v7.0.0
```

- Local actions remain relative paths.
- Docker image references used in release smokes use immutable digests where practical.
- Dependabot action updates must update the SHA and reviewed comment together.
- `scripts/check_release.py` rejects mutable tags and mismatched/missing comments.

- [ ] **Step 1: Write failing workflow parser tests.** Parse YAML as text or a YAML AST that preserves the reference/comment relationship. Cover tags, branches, abbreviated SHAs, local actions, and valid full SHAs.

- [ ] **Step 2: Resolve current official SHAs.** Record the source release and update every workflow. Do not infer a SHA; retrieve it from the official action repository/release record during implementation.

- [ ] **Step 3: Update Dependabot and release process.** Document review requirements for major action changes.

- [ ] **Step 4: Verify.**

```bash
python -m pytest tests/ci/test_immutable_action_pins.py tests/ci -q
actionlint .github/workflows/*.yml
zizmor --offline --no-progress .github/workflows
python scripts/check_release.py
```

Expected: PASS with no mutable action reference.

- [ ] **Step 5: Commit.**

```bash
git add .github/workflows .github/dependabot.yml scripts/check_release.py tests/ci/test_immutable_action_pins.py docs/development.md docs/release-checklist.md
git commit -m "ci: pin workflow actions immutably"
```

### Task 36: Build once and promote identical artifacts through TestPyPI, PyPI, and GitHub Release

**Files:**

- Modify: `.github/workflows/publish.yml`
- Create: `src/codex_usage_tracker/release/artifact_manifest.py`
- Create: `src/codex_usage_tracker/release/promotion_evidence.py`
- Create: `tests/release/test_artifact_manifest.py`
- Create: `tests/release/test_promotion_evidence.py`
- Modify: `scripts/check_release.py`
- Modify: `scripts/smoke_installed_package.py`
- Modify: `docs/release-checklist.md`
- Modify: `docs/architecture.md`

**Release graph:**

```text
exact tag/commit
    -> build wheel + sdist once
    -> manifest with hashes/source SHA/schema inventory/bundle hashes
    -> full verification and installed-artifact smokes
    -> publish exact bytes to TestPyPI
    -> install exact TestPyPI version and verify hashes/version/contracts
    -> environment approval
    -> publish downloaded verified artifact bundle unchanged to PyPI
    -> attach same bytes and manifest to GitHub Release
    -> verify all three public locations have identical hashes
```

**Rules:**

- The PyPI job does not rebuild.
- TestPyPI and PyPI publication in one release workflow use one uploaded `python-dist` artifact whose manifest hash is passed as a job output.
- Manual `pypi` dispatch either requires a previously qualified artifact/workflow run identifier or is removed in favor of release publication.
- Trusted Publishing remains.
- Release evidence records exact Git SHA, action run, artifact SHA-256 values, schema version, MCP tool inventory, Evidence Console bundle hashes, and installed-smoke results.

- [ ] **Step 1: Write failing manifest tests.** Cover missing file, altered artifact, wrong source SHA, wrong version, multiple versions, stale frontend asset, and manifest canonicalization.

- [ ] **Step 2: Implement manifest create/verify commands.** Keep them shell-friendly and deterministic.

- [ ] **Step 3: Rewrite workflow dependencies.** Build job uploads the bundle once; all publication and attachment jobs download and verify it. Add a TestPyPI smoke/qualification job that blocks production publication.

- [ ] **Step 4: Add exact-byte tests to release checks.** Test fixture manifests and workflow ordering.

- [ ] **Step 5: Exercise a dry-run or TestPyPI candidate.** Record artifact hashes before and after upload/download.

- [ ] **Step 6: Verify locally.**

```bash
python -m pytest tests/release/test_artifact_manifest.py tests/release/test_promotion_evidence.py tests/packaging -q
python -m build
python -m codex_usage_tracker.release.artifact_manifest create --source dist --output /tmp/cut-dist-manifest.json --expected-sha "$(git rev-parse HEAD)"
python -m codex_usage_tracker.release.artifact_manifest verify --source dist --manifest /tmp/cut-dist-manifest.json --expected-sha "$(git rev-parse HEAD)"
python scripts/smoke_installed_package.py
python scripts/check_release.py --dist
```

Expected: PASS.

- [ ] **Step 7: Commit.**

```bash
git add .github/workflows/publish.yml src/codex_usage_tracker/release tests/release scripts/check_release.py scripts/smoke_installed_package.py docs/release-checklist.md docs/architecture.md
git commit -m "build: promote one verified release artifact"
```

### Task 37: Add system-complexity, package-size, and public-surface budgets

**Files:**

- Create: `config/product-complexity-budget.json`
- Create: `scripts/check_product_complexity.py`
- Create: `tests/quality/test_product_complexity_budget.py`
- Modify: `scripts/check-dashboard-bundles.mjs`
- Modify: `scripts/check_release.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Modify: `docs/development.md`
- Modify: `docs/architecture.md`

**Initial budgets for 0.24:**

| Metric | Maximum |
| --- | ---: |
| Default MCP tools | 7 |
| Full-profile MCP tools | current 0.22 baseline; may only decrease without explicit decision |
| Stable CLI top-level commands | 11 |
| Primary analytical dashboard routes | 3 |
| Shell utility routes | 1 |
| Contextual dashboard routes | 1 |
| Python files over 600 physical lines | 0 |
| Frontend source files over 500 physical lines | 0 |
| Wheel size | current 0.23 size rounded up by 5%; target decreases later |
| Source distribution size | current 0.23 size rounded up by 5% |
| Main initial React JS | measured 0.23 baseline minus removed constellation, rounded up by 10% |
| Number of emitted stable JSON schemas | baseline plus only explicitly approved additions |
| Number of SQLite schema increments per release | 1 |

**Rules:**

- The budget file records baseline commit, measurement command, and rationale.
- A budget increase requires an architecture decision and changed test fixture.
- Generated assets are measured separately from authored source.
- Removed compatibility surfaces ratchet counts downward in 0.25.

- [ ] **Step 1: Implement a deterministic measurement script.** Read parser/catalog/route/schema registries rather than grepping ambiguous text. Inspect built artifacts when package sizes are requested.

- [ ] **Step 2: Write failing budget tests against intentionally reduced test fixtures.** Prove each metric blocks.

- [ ] **Step 3: Establish 0.23 measured baselines and set initial ceilings.** Do not guess package or bundle bytes in the committed file.

- [ ] **Step 4: Add CI and release checks.** Dashboard bundle checks and product-complexity checks run in separate named steps.

- [ ] **Step 5: Verify.**

```bash
python scripts/check_product_complexity.py --config config/product-complexity-budget.json
python -m pytest tests/quality/test_product_complexity_budget.py -q
npm run dashboard:bundle-report
python -m build
python scripts/check_product_complexity.py --config config/product-complexity-budget.json --dist dist
```

Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add config/product-complexity-budget.json scripts/check_product_complexity.py tests/quality/test_product_complexity_budget.py scripts/check-dashboard-bundles.mjs scripts/check_release.py .github/workflows/ci.yml pyproject.toml docs/development.md docs/architecture.md
git commit -m "test: budget product and package complexity"
```

### Task 38: Convert legacy dashboard workbenches to notice-only compatibility routes

**Files:**

- Create: `frontend/dashboard/src/features/compatibility/LegacyWorkbenchNotice.tsx`
- Create: `frontend/dashboard/src/features/compatibility/LegacyWorkbenchNotice.module.css`
- Create: `frontend/dashboard/src/features/compatibility/LegacyWorkbenchNotice.test.tsx`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Modify: `frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Modify: `docs/deprecations.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `tests/playwright/dashboard-release-candidate.spec.mjs`

**Notice-only behavior:**

- Old direct URLs render a small compatibility page.
- The page names the prior feature, its replacement core request, deprecation/removal release, and actions to copy the replacement prompt or open Evidence/Explore/Limits.
- It does not load old workbench queries, start background jobs, or import heavy page modules.
- Old exports that remain supported are linked as CLI or full-profile MCP compatibility operations.
- The old feature implementation source may remain temporarily for deletion in Task 40/41, but it is no longer reachable from the production route tree.

- [ ] **Step 1: Write failing route/network tests.** Each old route must render the notice and make zero calls to its historical API endpoints.

- [ ] **Step 2: Implement one shared notice component and static route descriptors.** Copy is localized through the stable shell catalog.

- [ ] **Step 3: Remove lazy imports from `DashboardRouteView`.** This ensures old chunks are not included in production route bundles.

- [ ] **Step 4: Update route inventory and docs.** Mark historical endpoints compatibility-only; do not remove them yet.

- [ ] **Step 5: Verify.**

```bash
npm --workspace frontend/dashboard test -- LegacyWorkbenchNotice.test.tsx dashboardRouter.test.tsx App.shell.test.tsx
npm run dashboard:verify
npm run dashboard:release-candidate
node scripts/check-dashboard-bundles.mjs
```

Expected: PASS; old workbench chunks are absent from the production manifest or unreachable according to bundle analysis.

- [ ] **Step 6: Commit.**

```bash
git add frontend/dashboard/src/features/compatibility frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/app/routeCatalog.ts frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx frontend/dashboard/src/features/investigator/InvestigatorPage.tsx frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx frontend/dashboard/src/features/cache-context/CacheContextPage.tsx frontend/dashboard/src/features/reports/ReportsPage.tsx frontend/dashboard/src/api/client.ts src/codex_usage_tracker/server/route_inventory.py docs/deprecations.md docs/dashboard-guide.md tests/playwright/dashboard-release-candidate.spec.mjs src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "refactor: retire legacy dashboard workbenches"
```

### Task 39: Gate and publish Release 0.24.0

**Files:**

- Create: `docs/releases/0.24.0.md`
- Create: `docs/upgrading-to-0.24.0.md`
- Create: `docs/releases/0.24.0-artifact-manifest-example.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `docs/roadmap/mcp-first-pivot-execution.md`
- Modify: `docs/release-checklist.md`
- Modify: `tests/golden_questions/test_core_tools.py`

**Release acceptance:**

- Python architecture has zero Tach cycles and `root_module="forbid"`.
- Application services run from custom temporary paths without global defaults.
- Default MCP server is explicitly constructed and has no import-registration side effects.
- SQLite foreign keys and integrity checks are enforced.
- Context offset reads pass equivalence/performance gates.
- Generic analysis jobs persist and recover interrupted state.
- Coverage is directly blocked at 85%; changed lines at 90%.
- Workflow actions are immutable.
- Release workflow builds once and promotes identical artifacts.
- Complexity budgets pass.
- Legacy dashboard workbenches are notice-only and make no old API calls.

- [ ] **Step 1: Run architecture/integrity focused gates.**

```bash
tach check
python -m pytest tests/architecture tests/store/test_connection_integrity.py tests/store/test_foreign_key_cascades.py tests/jobs/test_persisted_jobs.py tests/context/test_byte_offset_reads.py -q
```

- [ ] **Step 2: Run complete quality and product gates.**

```bash
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
python -m mypy
python scripts/check_product_complexity.py --config config/product-complexity-budget.json
npm run dashboard:verify
npm run dashboard:assets:check
npm run dashboard:release-candidate
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
python scripts/benchmark_synthetic_history.py --rows 1000 --with-source-logs --json --enforce-thresholds
python scripts/check_release.py
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 3: Run one TestPyPI promotion rehearsal using the new artifact workflow.** Verify downloaded TestPyPI hashes equal the build manifest before enabling the production environment.

- [ ] **Step 4: Record release evidence.** Include architecture graph summary, integrity check output, schema version/migration, offset performance evidence, coverage, complexity budgets, action pin inventory, and artifact hashes.

- [ ] **Step 5: Commit.**

```bash
git add README.md CHANGELOG.md pyproject.toml docs/releases/0.24.0.md docs/upgrading-to-0.24.0.md docs/releases/0.24.0-artifact-manifest-example.json docs/roadmap/mcp-first-pivot-execution.md docs/release-checklist.md tests/golden_questions/test_core_tools.py
git commit -m "chore: prepare 0.24.0 hardened architecture release"
```

---

## Release 0.25.0 - Compatibility removal and footprint reduction

### Task 40: Remove the legacy static dashboard product and entry points

**Files:**

- Delete: legacy static dashboard source modules under `src/codex_usage_tracker/dashboard/` that are not used by the live Evidence Console
- Delete: legacy static HTML/JavaScript/CSS package assets under `src/codex_usage_tracker/plugin_data/dashboard/` except current React assets and locale assets still used by React
- Delete or refactor: static dashboard generation helpers in `src/codex_usage_tracker/dashboard.py` and related compatibility modules
- Modify: `src/codex_usage_tracker/interfaces/cli/parser.py`
- Modify: `src/codex_usage_tracker/interfaces/cli/commands.py`
- Modify: `src/codex_usage_tracker/interfaces/http/v2.py`
- Modify: `src/codex_usage_tracker/server/dashboard_pages.py`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/compatibility_tools.py`
- Modify: `scripts/check_release.py`
- Modify: `scripts/smoke_installed_package.py`
- Modify: `tests/release_catalog.py`
- Delete or replace: tests that assert static dashboard generation
- Create: `tests/compatibility/test_removed_static_dashboard.py`
- Modify: `docs/deprecations.md`
- Modify: `docs/upgrading-to-0.25.0.md`

**Removal scope:**

- Remove CLI `dashboard` and `open-dashboard` aliases.
- Remove MCP `generate_usage_dashboard`.
- Remove `/dashboard.html` and configured static-filename serving.
- Make `/` issue an HTTP redirect to `/react-dashboard.html` when the live server is running.
- Remove generated static dashboard package data and screenshots that exist only for that surface.
- Retain CSV/JSON exports through stable CLI/application services.
- Retain exact Evidence Console deep links.

**Compatibility behavior:**

- Removed CLI commands exit `2`, print the exact replacement `codex-usage-tracker open`, and link to the upgrade guide.
- Removed MCP tools are absent rather than returning fake compatibility responses; release notes provide replacement tools.
- Requests to `/dashboard.html` return `410 Gone` with a short local HTML page pointing to `/react-dashboard.html` for one release. No usage data is embedded in the 410 response.
- `/` redirects with `302` during 0.25; the redirect may become permanent after 1.0.

- [ ] **Step 1: Add failing removal and migration tests.** Assert command absence from primary/alias parser, tool absence from full profile, `410` static path, `/` redirect, no static package files, and exact replacement text.

- [ ] **Step 2: Inventory static-only code and assets.** Produce a checked list in the task execution ledger. Do not delete modules also used by React payload construction; relocate shared backend functions before deletion.

- [ ] **Step 3: Remove the surface and compatibility registration.** Update package-data declarations so stale assets cannot enter a wheel.

- [ ] **Step 4: Update installed-package smoke.** Serve the wheel, assert React Home/Explore/Evidence/Limits assets, assert `/dashboard.html` returns 410, and assert no static generator command/tool exists.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/compatibility/test_removed_static_dashboard.py tests/packaging tests/dashboard tests/server -q
npm run dashboard:verify
npm run dashboard:assets:check
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
python scripts/smoke_installed_package.py
python scripts/check_product_complexity.py --config config/product-complexity-budget.json --dist dist
```

Expected: PASS and wheel/source distribution sizes decrease.

- [ ] **Step 6: Ratchet budgets.** Set new package/bundle ceilings to the measured 0.25 candidate rounded up by no more than 3%.

- [ ] **Step 7: Commit.**

```bash
git add -A src/codex_usage_tracker frontend/dashboard tests scripts pyproject.toml config/product-complexity-budget.json docs/deprecations.md docs/upgrading-to-0.25.0.md
git commit -m "refactor: remove the legacy static dashboard"
```

### Task 41: Remove expired dashboard workbenches, legacy API routes, MCP tools, and CLI aliases

**Files:**

- Delete: `frontend/dashboard/src/features/diagnostics/` except any components migrated into Evidence
- Delete: `frontend/dashboard/src/features/investigator/` legacy workbench code not used by Evidence
- Delete: `frontend/dashboard/src/features/compression-lab/`
- Delete: `frontend/dashboard/src/features/cache-context/`
- Delete: `frontend/dashboard/src/features/reports/`
- Delete: `frontend/dashboard/src/features/compatibility/LegacyWorkbenchNotice.tsx` after route removal
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `frontend/dashboard/src/routes/legacyRouteAliases.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `src/codex_usage_tracker/server/routes.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/server/route_inventory.py`
- Delete/refactor: server route modules used only by removed workbench pages
- Modify: `src/codex_usage_tracker/interfaces/mcp/compatibility_tools.py`
- Modify: `src/codex_usage_tracker/interfaces/mcp/registry.py`
- Modify: `src/codex_usage_tracker/interfaces/cli/parser.py`
- Modify: `src/codex_usage_tracker/interfaces/cli/commands.py`
- Delete/refactor: historical `cli/mcp_*` compatibility shims no longer imported by supported code
- Modify: `tests/mcp/fixtures/tool_names_021.json` only by moving it to historical fixture storage; do not rewrite history
- Create: `tests/compatibility/test_025_removed_surfaces.py`
- Modify: `docs/deprecations.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/mcp.md`
- Modify: `docs/evidence-console.md`

**Removal rule:**

A surface can be deleted only when its row in `docs/dashboard-sunset-job-parity-v2.md` is PASS and its `remove_in` value is `0.25.0` or earlier.

**Backend retention rule:**

- Deterministic analytics used by core strategies stay under `analytics/`, even if their old UI/API route disappears.
- Stable query and export behavior remains under application services.
- Developer-only experiments explicitly retained by design may remain in the `developer` MCP profile only if they have a named owner, bounded contract, and no dashboard route.
- Old broad diagnostic HTTP endpoints return `410` for one release only when a known external bookmark path exists; otherwise remove them.

**Target public counts:**

- Default MCP tools: 7.
- Full MCP profile: core plus only advanced operations that lack one-call core parity and remain explicitly supported. Target maximum: 15.
- Developer profile: no fixed maximum, but every tool is cataloged and excluded from installed default skills.
- Primary analytical dashboard routes: 3.
- Shell utility routes: 1.
- Contextual routes: 1.
- Stable top-level CLI commands: 11.
- Legacy top-level aliases: 0.

- [ ] **Step 1: Add a failing deletion inventory test.** The test reads deprecation records and asserts every due surface is absent from route, CLI, MCP, HTTP, package, and docs inventories.

- [ ] **Step 2: Remove frontend routes and source.** Old URLs without a direct stable alias return a not-found page that names the Evidence Console and does not retain the full legacy feature name as an active capability.

- [ ] **Step 3: Remove HTTP handlers and API client methods.** Keep application services used by core. Update route inventory and route-budget fixtures.

- [ ] **Step 4: Remove expired MCP tools and CLI aliases.** Update catalog counts and skills. Preserve historical JSON schema docs in an archived compatibility appendix rather than current tool reference.

- [ ] **Step 5: Run dead-code and dependency cleanup.** Remove unused packages, modules, CSS, locales, tests, and generated assets. Run Knip, Vulture, Deptry, and bundle analysis before adding any whitelist.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/compatibility/test_025_removed_surfaces.py tests/application/test_dashboard_sunset_parity.py tests/mcp tests/interfaces -q
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
deptry .
vulture src tests config/vulture-whitelist.py
npm run dashboard:verify
npm run dashboard:assets:check
python scripts/check_product_complexity.py --config config/product-complexity-budget.json
python scripts/check_release.py
```

Expected: PASS at the target public counts.

- [ ] **Step 7: Ratchet inventories and budgets downward.** Record exact removed routes, tools, commands, modules, package bytes, and frontend chunks.

- [ ] **Step 8: Commit.**

```bash
git add -A src frontend tests docs skills scripts config pyproject.toml package.json package-lock.json
git commit -m "refactor: remove expired analysis surfaces"
```

### Task 42: Finalize public contracts, migrations, and package footprint after removal

**Files:**

- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `docs/architecture.md`
- Modify: `docs/mcp.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/evidence-console.md`
- Modify: `docs/first-five-minutes.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/deprecations.md`
- Create: `docs/compatibility/0.21-0.24-tool-and-route-reference.md`
- Create: `docs/compatibility/0.25-removal-map.md`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: packaged skill copies
- Modify: `tests/packaging/test_public_docs.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `scripts/check_release.py`
- Modify: `config/product-complexity-budget.json`

**Documentation contract:**

The first screenful of README must communicate:

1. Codex Usage Tracker is a local, evidence-backed usage analyst.
2. Conversation through the Codex plugin/MCP is the primary analysis path.
3. Evidence Console is the visual verification and exact-record browser.
4. The backend performs deterministic accounting/statistics; the agent explains results.
5. The tracker indexes the data types it actually stores; no obsolete aggregate-only promise appears.
6. Install/setup/restart/question/open-evidence instructions are concise and correct.

**Schema contract:**

- Current docs list only stable core MCP, HTTP v2, CLI, and dashboard target schemas.
- Historical schemas remain in the compatibility appendix with last-supported release.
- No runtime schema is undocumented.
- No removed schema is presented as active.

- [ ] **Step 1: Add failing public-doc and schema-lifecycle tests.** Search exact required positioning and forbidden obsolete claims. Compare active/historical schema registries to docs.

- [ ] **Step 2: Rewrite the public journey.** Replace dashboard-tour-first sections with question-first examples and exact evidence follow-ups. Keep a small Evidence Console screenshot set.

- [ ] **Step 3: Archive historical reference.** Move removed tool/route documentation without deleting migration knowledge.

- [ ] **Step 4: Synchronize skills.** The API skill should solve broad questions with no more than three core calls in ordinary cases. The operational skill owns setup/status/open/export/admin tasks.

- [ ] **Step 5: Rebuild packages and set final 0.25 budgets.** Remove unused docs assets from package data where the installed skill does not need them.

- [ ] **Step 6: Verify.**

```bash
python -m pytest tests/packaging/test_public_docs.py tests/core/test_json_contracts.py tests/cli/test_cli_release.py -q
npx markdownlint-cli2 README.md "docs/**/*.md" "skills/**/*.md"
python scripts/check_release.py
python -m build
python scripts/check_release.py --dist
python scripts/check_product_complexity.py --config config/product-complexity-budget.json --dist dist
```

Expected: PASS with no active documentation for a removed surface.

- [ ] **Step 7: Commit.**

```bash
git add README.md pyproject.toml docs skills src/codex_usage_tracker/plugin_data/skills tests/packaging/test_public_docs.py tests/core/test_json_contracts.py scripts/check_release.py config/product-complexity-budget.json
git commit -m "docs: finalize the MCP-first product contract"
```

### Task 43: Gate and publish Release 0.25.0

**Files:**

- Create: `docs/releases/0.25.0.md`
- Complete: `docs/upgrading-to-0.25.0.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `docs/roadmap/mcp-first-pivot-execution.md`
- Modify: `tests/golden_questions/cases/*.json`
- Modify: `tests/golden_questions/test_core_tools.py`

**Release acceptance:**

- Legacy static dashboard is removed.
- Legacy workbench source/routes are removed.
- Expired MCP tools and CLI aliases are removed according to deprecation records.
- Core calculations and exact evidence remain.
- Public counts meet Task 41 targets.
- Golden questions use only core tools.
- Wheel, sdist, and initial React bundle are smaller than 0.24 and within ratcheted budgets.
- Upgrade guide contains exact command/tool/URL replacements.
- No new feature is introduced in this release beyond removal/migration support.

- [ ] **Step 1: Run removal and compatibility tests.**

```bash
python -m pytest tests/compatibility tests/golden_questions tests/packaging/test_public_docs.py -q
```

- [ ] **Step 2: Run full release gates.**

```bash
tach check
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
python -m mypy
deptry .
vulture src tests config/vulture-whitelist.py
npm run dashboard:verify
npm run dashboard:assets:check
npm run dashboard:release-candidate
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
python scripts/benchmark_synthetic_history.py --rows 1000 10000 100000 --json --enforce-thresholds
python scripts/check_product_complexity.py --config config/product-complexity-budget.json
python scripts/check_release.py
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/check_product_complexity.py --config config/product-complexity-budget.json --dist dist
python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 3: Publish through build-once promotion.** TestPyPI, PyPI, and GitHub release artifact hashes must be identical to the manifest.

- [ ] **Step 4: Record before/after footprint.** Compare 0.21, 0.24, and 0.25 tool count, route count, CLI count, Python module count, JS chunks, wheel/sdist bytes, initial bundle bytes, and test runtime.

- [ ] **Step 5: Commit.**

```bash
git add CHANGELOG.md pyproject.toml docs/releases/0.25.0.md docs/upgrading-to-0.25.0.md docs/roadmap/mcp-first-pivot-execution.md tests/golden_questions
git commit -m "chore: prepare 0.25.0 product simplification release"
```

---

## Release 0.26.0 - Feature-free stabilization and contract freeze

### Task 44: Build the deterministic golden-question, fault-injection, and recovery suite

**Files:**

- Create: `tests/golden_questions/runner.py`
- Expand: `tests/golden_questions/cases/*.json`
- Create: `tests/reliability/test_core_tool_failures.py`
- Create: `tests/reliability/test_job_recovery.py`
- Create: `tests/reliability/test_database_failure_modes.py`
- Create: `tests/reliability/test_evidence_target_recovery.py`
- Create: `tests/reliability/test_partial_configuration.py`
- Create: `scripts/run_core_acceptance.py`
- Create: `docs/core-acceptance-suite.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/development.md`

**Golden-question cases:**

At minimum, include:

1. What drove usage today?
2. Why was yesterday higher than the comparison window?
3. Which threads consumed the most credits?
4. Which model/effort mix was most expensive?
5. Did subagents materially affect usage?
6. Are any calls exact Fast/Priority observations?
7. Which costs are unpriced or estimated?
8. Which calls show context bloat?
9. Which calls show poor cache reuse?
10. What repeated workflow churn is visible?
11. What is my latest weekly allowance state?
12. Is a supported allowance-capacity change present?
13. Show the exact evidence behind finding X.
14. Query calls for one model and period.
15. Query threads with the highest uncached input.
16. Open the heaviest thread in the Evidence Console.
17. Refresh stale data and continue the original analysis.
18. Recover when MCP setup is unavailable.
19. Recover when pricing is missing.
20. Recover when no relevant evidence exists.

**Fault cases:**

- stale source revision during follow-up;
- deleted source file;
- interrupted analysis job;
- malformed/corrupt cursor;
- SQLite locked within busy timeout and beyond it;
- foreign-key/integrity failure;
- missing pricing/rate-card/allowance configuration;
- persistent dashboard service unavailable;
- Evidence target with removed compatibility route;
- plugin core profile configured but current task exposure unknown;
- zero canonical rows with physical duplicates present;
- unsupported strategy goal or query field.

**Acceptance:**

- Every golden question declares expected first tool, maximum tool calls, allowed fallback tools, required result schema, required claim type, and evidence selector.
- Ordinary cases use no more than three core calls excluding refresh/job polling.
- No failure case produces a confident fabricated finding.
- Every recoverable case returns one exact next action.
- The suite is deterministic and network-free.

- [ ] **Step 1: Implement the fixture schema and validator.** Invalid cases fail before execution.

- [ ] **Step 2: Implement a deterministic orchestration simulator.** It consumes skill routing rules and tool metadata; it does not pretend to evaluate natural-language quality with a live model.

- [ ] **Step 3: Add application fault injection.** Use protocols/fakes for clock, repository, pricing, job service, dashboard target resolver, and source reader.

- [ ] **Step 4: Add a single CI acceptance command.**

```bash
python scripts/run_core_acceptance.py --json /tmp/core-acceptance.json
```

It exits nonzero on any failed case and emits bounded diagnostics.

- [ ] **Step 5: Verify.**

```bash
python -m pytest tests/golden_questions tests/reliability -q
python scripts/run_core_acceptance.py --json /tmp/core-acceptance.json
```

Expected: every case PASS, ordinary median core calls <= 2, maximum <= 3.

- [ ] **Step 6: Commit.**

```bash
git add tests/golden_questions tests/reliability scripts/run_core_acceptance.py docs/core-acceptance-suite.md .github/workflows/ci.yml docs/development.md
git commit -m "test: validate core conversational workflows"
```

### Task 45: Freeze stable contracts, complete final documentation, and publish Release 0.26.0

**Files:**

- Create: `docs/releases/0.26.0.md`
- Create: `docs/upgrading-to-0.26.0.md`
- Create: `docs/stable-contracts.md`
- Create: `docs/mcp-core-tool-reference.md`
- Create: `docs/evidence-model.md`
- Create: `docs/operations-and-recovery.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `docs/architecture.md`
- Modify: `docs/roadmap/mcp-first-pivot-execution.md`
- Modify: `docs/deprecations.md`
- Modify: `scripts/check_release.py`
- Modify: `tests/release_catalog.py`
- Modify: `config/product-complexity-budget.json`

**Contract freeze:**

The following become the supported pre-1.0 stable surface:

- seven core MCP tool names and top-level request fields;
- shared envelope, finding, evidence, job, and dashboard-target schemas;
- HTTP API v2 paths and methods;
- stable CLI top-level command names and namespace names;
- Evidence Console route IDs and canonical selector parameters;
- canonical usage-accounting semantics;
- release artifact manifest schema;
- SQLite forward-migration support from all public 0.21+ versions.

Pre-1.0 evolution remains possible, but a breaking change requires:

- schema/contract revision;
- migration or compatibility adapter;
- upgrade guide;
- changed deprecation record;
- exact tests;
- sufficient package-version movement under the repository's compatibility policy.

**Feature-free rule:**

- This release contains no new analytical goal, no new default MCP tool, no new dashboard route, no new CLI namespace, and no new statistical method.
- Changes are limited to defects, documentation, compatibility, performance, accessibility, recovery, and release hardening.

- [ ] **Step 1: Add contract snapshot tests.** Generate canonical manifests for MCP, HTTP, CLI, dashboard routes, schemas, database version, and release artifact schema. Snapshot updates require a changed contract version and upgrade entry.

- [ ] **Step 2: Complete user and maintainer documentation.** Keep public docs short and question-oriented; put exhaustive details in reference docs.

- [ ] **Step 3: Close all deprecation rows.** Each is `removed`, `retained`, or `superseded`; none remains ambiguously active.

- [ ] **Step 4: Run final acceptance.**

```bash
tach check
python scripts/run_core_acceptance.py --json /tmp/core-acceptance.json
python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
python -m pyright --pythonpath "$(command -v python)" src
python -m ruff check .
python -m mypy
deptry .
vulture src tests config/vulture-whitelist.py
npm run dashboard:verify
npm run dashboard:assets:check
npm run dashboard:release-candidate
python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 5 --skip-compression --enforce-thresholds --output-dir /tmp/dashboard-route-budget
python scripts/benchmark_synthetic_history.py --rows 1000 10000 100000 500000 --json --enforce-thresholds
python scripts/check_product_complexity.py --config config/product-complexity-budget.json
python scripts/check_release.py
python -m build
python -m twine check dist/*
python scripts/check_release.py --dist
python scripts/check_product_complexity.py --config config/product-complexity-budget.json --dist dist
python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS.

- [ ] **Step 5: Perform two clean upgrade smokes.**

1. Install public `0.21.0`, create and populate a synthetic database, then upgrade to the 0.26 candidate and run status/query/analyze/evidence/allowance.
2. Install public `0.24.0`, create a persisted analysis job/result fixture, upgrade to the 0.26 candidate, and verify recovery/compatibility.

No real user data is used.

- [ ] **Step 6: Publish through exact-byte promotion.** Verify identical TestPyPI/PyPI/GitHub hashes and retain immutable evidence.

- [ ] **Step 7: Record final program results.** Include:

- baseline and final public-surface counts;
- route/tool/command/schema removals;
- package and bundle size changes;
- source/module/test counts;
- coverage and architecture status;
- query/refresh/context performance;
- golden-question results and call budgets;
- known retained limitations;
- exact follow-up policy.

- [ ] **Step 8: Commit.**

```bash
git add README.md CHANGELOG.md pyproject.toml docs/releases/0.26.0.md docs/upgrading-to-0.26.0.md docs/stable-contracts.md docs/mcp-core-tool-reference.md docs/evidence-model.md docs/operations-and-recovery.md docs/architecture.md docs/roadmap/mcp-first-pivot-execution.md docs/deprecations.md scripts/check_release.py tests/release_catalog.py config/product-complexity-budget.json
git commit -m "chore: prepare 0.26.0 contract-stabilization release"
```

---

## Design-to-task traceability

| Design concern | Primary tasks | Release proof |
| --- | --- | --- |
| MCP-first product positioning and accurate public claims | 1-2, 17, 27, 42, 45 | Public-doc tests, package metadata, release notes |
| Seven-tool default profile and compatibility isolation | 3, 12-16, 41, 45 | Tool inventory snapshots and installed-plugin smoke |
| Shared envelope, scope, messages, findings, and evidence | 4-5, 9-14, 25, 45 | JSON contract registry and exact fixtures |
| Generic job lifecycle | 7-8, 11, 14, 33, 44 | Job adapter, persistence, recovery, and fault tests |
| Evidence Console route model | 18-23, 27 | Route catalog, URL aliases, browser acceptance |
| Dashboard feature sunset | 23-24, 38, 40-43 | Parity record, zero-network notices, removed-source inventory |
| CLI simplification | 26, 41-43, 45 | Parser inventories, alias lifecycle, help snapshots |
| HTTP API v2 | 25, 28-30, 41, 45 | Route inventory, schema equality, architecture gates |
| Application architecture and dependency direction | 28-30 | Container tests, Tach, secondary import regression |
| SQLite integrity and migration safety | 31-33, 39, 45 | Foreign-key checks, migration fixtures, upgrade smokes |
| Context-read performance | 32, 39, 45 | Payload equivalence and inspected-byte performance ratchet |
| Coverage and false-green prevention | 34, 39, 43-45 | 85% branch coverage, 90% changed lines, work-proof contracts |
| Immutable CI and release promotion | 35-36, 39, 43, 45 | Action-pin tests and identical public artifact hashes |
| Product/package complexity reduction | 24, 37-43, 45 | Blocking budgets and baseline/final comparison |
| Internal synthetic acceptance | 17, 27, 44-45 | Golden questions, fault injection, clean upgrade smokes |

## Safe parallelization map

Tasks may run in parallel only when they do not edit the same contracts or depend on an unmerged interface. The preferred execution remains sequential; this map exists for a coordinator using isolated worktrees.

| After completion of | Tasks that may run concurrently | Merge order constraint |
| --- | --- | --- |
| 5 | 6 and 7 | Merge 6 before 8; merge 7 before 8 and 11 |
| 9 and 10 | 11 and preparatory tests for 13 | Merge 11 before 12; merge 13 after 11 contract fixtures stabilize |
| 14 | 15 and documentation preparation for 16 | Merge 15 before 16 |
| 18 | 19 and 20 | Merge both before 21 and 23 |
| 21 | 22 and 24 | Merge both before 27; 23 depends on 19-22 |
| 28 | 31 and 32 | Merge both before 30 only when domain paths are stable; otherwise 30 merges first and both rebase |
| 30 | 34 and 35 | Merge independently; 36 depends on 35 and current release checks |
| 31-33 | 37 and 38 | Merge 38 before 39; 37 must remeasure after 38 |
| 40 | 42 documentation preparation and 41 removal | Merge 41 before finalizing 42 budgets/docs |
| 43 | 44 and draft reference documentation for 45 | Merge 44 before final contract snapshots in 45 |

A coordinating agent must not merge parallel branches without rerunning focused cross-branch tests and the release's complete gate.

## Cross-program completion checklist

The pivot is complete only when all statements below are true:

- [ ] `main` contains the approved design, roadmap, execution ledger, and closed deprecation inventory.
- [ ] Clean plugin installs expose exactly seven core tools.
- [ ] Core tool implementations are thin adapters over application services.
- [ ] All deterministic calculations remain outside the model-facing transport layer.
- [ ] Every material finding links to exact evidence.
- [ ] Home, Explore, Limits, the Settings utility, and contextual Evidence are the only live dashboard routes.
- [ ] Legacy static dashboard and workbench source are absent from distributions.
- [ ] Stable CLI help contains only the simplified hierarchy.
- [ ] HTTP API v2, MCP, and CLI share request/response models.
- [ ] Tach blocks cycles and upward dependencies.
- [ ] SQLite foreign keys and integrity checks are enabled and tested.
- [ ] Context reads use validated byte offsets with a correct fallback.
- [ ] Generic jobs persist reusable analysis and recover interrupted state explicitly.
- [ ] Coverage, work-proof, schema, compatibility, route, package, and complexity gates are directly blocking.
- [ ] GitHub Actions are pinned immutably.
- [ ] Release artifacts are built once and promoted unchanged.
- [ ] Public descriptions accurately state what the tracker indexes and what each interface does.
- [ ] Internal golden-question and fault-injection suites pass without network or real user data.
- [ ] No release after 0.21 has silently changed canonical accounting, pricing, allowance, or evidence semantics.

## Rollback policy

Each release is independently revertible at the product layer:

- `0.22.0`: set installed plugin profile to `full` and restore 0.21 skill guidance; no database rollback.
- `0.23.0`: switch route exposure back to the 0.22 foundation catalog; v2 API and core tools remain additive.
- `0.24.0`: application/architecture refactors preserve public contracts; rollback code while retaining additive database migrations.
- `0.25.0`: users requiring removed surfaces must reinstall `0.24.x`; current database remains forward-compatible, but removed code is not reintroduced through flags.
- `0.26.0`: feature-free stabilization can be reverted to `0.25.x` without a reverse migration when no new schema is added.

Database rollback is never performed by decrementing `PRAGMA user_version` or deleting migration records. Correct forward or restore a pre-migration database backup.

## Autonomous-agent stop conditions

An implementing agent must stop the active task and report a blocker when any of these occurs:

1. A named file or interface no longer exists and no unambiguous current equivalent is found after repository search.
2. A task requires changing canonical accounting, pricing, allowance mathematics, or identity semantics not explicitly authorized here.
3. A parity test shows different canonical evidence between a sunset surface and its replacement.
4. A schema migration fails against a supported historical fixture.
5. A release task would require weakening a threshold or suppressing a new diagnostic.
6. A proposed package/complexity budget increase lacks an architecture decision.
7. An external dependency or action revision cannot be verified from an authoritative source.
8. A core response cannot fit its specified payload budget without discarding required evidence or caveats.
9. A compatibility removal is not listed as due in `docs/deprecations.md`.
10. Full verification reveals a pre-existing failure that makes the task's success claim ambiguous; record it separately rather than silently proceeding.

For ordinary implementation differences that do not affect public behavior, choose the smallest design-consistent solution, record it in the execution ledger, and continue.
