# Subagent Usage Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one stable MCP/CLI report that counts distinct observed subagent sessions and explains their aggregate usage, role/type mix, parent-thread distribution, and descriptive comparison with direct-agent usage.

**Architecture:** A focused store module queries canonical usage events into plain aggregate buckets. A focused report module owns validation, pricing, privacy, derived metrics, the v1 payload, and Markdown rendering; thin CLI and MCP adapters call that same report without recalculating anything.

**Tech Stack:** Python 3.10+, SQLite, MCP Python SDK, argparse, pytest, Ruff, Mypy/Pyright, Tach, existing pricing and privacy helpers.

## Global Constraints

- An observed spawn is one distinct non-empty `session_id` among rows satisfying the existing subagent predicate.
- The subagent predicate is `thread_source == "subagent"`, or non-empty `subagent_type`, or non-empty `parent_session_id`.
- Multiple calls in one subagent session count as one observed spawn.
- Rows without a usable session ID contribute to subagent totals but not observed-spawn or per-spawn denominators.
- The schema ID is exactly `codex-usage-tracker.subagent-usage.v1`.
- The default scope excludes archived sessions; `include_archived=True` opts in.
- MCP supports only `response_format="markdown"` and `response_format="json"`.
- `limit` defaults to 10 and accepts integers from 1 through 100.
- Direct-versus-subagent results are descriptive and must carry `observed_comparison_not_causal: true`.
- Do not return raw prompts, responses, context, `session_id`, `parent_session_id`, or agent nicknames.
- Use synthetic test fixtures only; never read or print the user's real usage database.
- Add no dependencies and no HTTP/dashboard surface in v1.
- Keep the implementation at or below 20 changed files and the configured change budget; do not broaden into unrelated refactors.
- Preserve the existing untracked `.idea/`, `.playwright-cli/`, `.superpowers/sdd/`, and `output/` artifacts.

---

## File Structure

**Create:**

- `src/codex_usage_tracker/store/subagent_usage_queries.py` — SQL cohort, breakdown, pricing-bucket, and coverage queries; returns plain mappings.
- `src/codex_usage_tracker/reports/subagent_usage.py` — validation, pricing, privacy, ratios, stable payload, and Markdown rendering.
- `src/codex_usage_tracker/cli/mcp_subagents.py` — one thin `subagent_usage` MCP tool.
- `tests/store/test_subagent_usage_queries.py` — distinct-session and filter semantics.
- `tests/reports/test_subagent_usage_report.py` — report schema, calculations, pricing, privacy, and edge cases.
- `tests/cli/test_subagent_usage_interfaces.py` — CLI/MCP parity and adapter behavior.

**Modify:**

- `src/codex_usage_tracker/cli/parser_reports.py` — define `subagents` CLI arguments.
- `src/codex_usage_tracker/cli/parser.py` — register the parser function.
- `src/codex_usage_tracker/cli/commands_reports.py` — add the CLI report runner.
- `src/codex_usage_tracker/cli/main.py` — register the command handler.
- `src/codex_usage_tracker/cli/mcp_server.py` — import/re-export the modular MCP tool.
- `tests/cli/test_cli_release.py` — add the public CLI command and MCP tool to release expectations.
- `docs/mcp.md` — document MCP behavior and example questions.
- `docs/cli-reference.md` — document the `subagents` command.
- `docs/cli-json-schemas.md` — document the v1 response fields.
- `docs/privacy.md` — document aggregate-only parent labels and invisible zero-usage spawns.
- `skills/codex-usage-api/SKILL.md` and packaged copy — route conversational subagent questions to the new tool.
- `skills/codex-usage-tracker/SKILL.md` and packaged copy — add the operational tool guidance.

Total planned files: 20.

---

### Task 1: Query observed subagent cohorts

**Files:**

- Create: `src/codex_usage_tracker/store/subagent_usage_queries.py`
- Create: `tests/store/test_subagent_usage_queries.py`

**Interfaces:**

- Consumes: `connect`, `init_db`, `row_to_dict`, and `usage_where_clause` from the existing store layer.
- Produces:

`query_subagent_usage_buckets(db_path: Path = DEFAULT_DB_PATH, *, since: str | None = None, parent_thread: str | None = None, agent_role: str | None = None, subagent_type: str | None = None, include_archived: bool = False, limit: int = 10) -> dict[str, Any]`

- Return shape:

```python
{
    "cohorts": {
        "direct": "UsageBucket",
        "subagent": "UsageBucket",
        "attributable_subagent": "UsageBucket",
    },
    "breakdowns": {
        "role": ["GroupedUsageBucket"],
        "type": ["GroupedUsageBucket"],
        "parent": ["GroupedUsageBucket"],
    },
    "coverage": {
        "missing_session_rows": int,
        "missing_session_tokens": int,
        "missing_role_spawns": int,
        "missing_type_spawns": int,
    },
}
```

- Every metrics mapping contains `calls`, `turns`, `observed_spawns`, all six token totals, and `latest_event`.
- Every model bucket contains `model`, `service_tier`, call/token totals, and no session identifiers.

- [ ] **Step 1: Write the failing distinct-spawn and breakdown tests**

Use the existing synthetic two-session fixture, where the subagent session contains multiple usage rows:

```python
from codex_usage_tracker.store.api import refresh_usage_index
from codex_usage_tracker.store.subagent_usage_queries import query_subagent_usage_buckets
from tests.store_dashboard_helpers import _make_codex_home


def test_query_counts_one_spawn_for_multiple_subagent_calls(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    result = query_subagent_usage_buckets(db_path)

    assert result["cohorts"]["subagent"]["metrics"]["observed_spawns"] == 1
    assert result["cohorts"]["subagent"]["metrics"]["calls"] == 2
    assert result["breakdowns"]["role"][0]["group_key"] == "test_runner"
    assert result["breakdowns"]["type"][0]["group_key"] == "thread_spawn"
    assert all("session_id" not in row for row in result["cohorts"]["subagent"]["model_buckets"])
```

Add tests named:

- `test_role_filter_keeps_direct_baseline_in_base_scope`
- `test_parent_filter_matches_parent_direct_rows_and_attached_children`
- `test_missing_session_metadata_is_coverage_not_a_spawn`
- `test_archived_rows_require_explicit_opt_in`
- `test_breakdown_limit_is_validated_before_sql`

For the role-filter assertion, require zero selected subagent calls for an unknown role while direct calls remain non-zero.

- [ ] **Step 2: Run the store tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/store/test_subagent_usage_queries.py -q
```

Expected: collection fails with `ModuleNotFoundError: codex_usage_tracker.store.subagent_usage_queries`.

- [ ] **Step 3: Implement the query module**

Start with a fixed SQL whitelist; never interpolate user values or arbitrary dimensions:

```python
SUBAGENT_PREDICATE = """(
    usage_events.thread_source = 'subagent'
    OR nullif(trim(usage_events.subagent_type), '') IS NOT NULL
    OR nullif(trim(usage_events.parent_session_id), '') IS NOT NULL
)"""

BREAKDOWN_EXPRESSIONS = {
    "role": "coalesce(nullif(trim(usage_events.agent_role), ''), 'unknown')",
    "type": "coalesce(nullif(trim(usage_events.subagent_type), ''), 'unknown')",
    "parent": "coalesce(nullif(trim(usage_events.parent_thread_name), ''), 'unknown parent')",
}
```

Build base time/archive/thread filters with the existing helper:

```python
where_sql, base_params = usage_where_clause(
    since=since,
    thread=parent_thread,
    table_alias="usage_events",
    include_archived=include_archived,
)
```

Use separate direct and subagent predicates so role/type filters never narrow the direct baseline:

```python
direct_where = _append_clause(where_sql, f"NOT {SUBAGENT_PREDICATE}")
subagent_where, subagent_params = _subagent_where(
    where_sql,
    list(base_params),
    agent_role=agent_role,
    subagent_type=subagent_type,
)
attributed_where = _append_clause(
    subagent_where,
    "nullif(trim(usage_events.session_id), '') IS NOT NULL",
)
```

Aggregate each cohort and breakdown with these exact metric expressions:

```sql
COUNT(*) AS calls,
COUNT(DISTINCT session_id || ':' || coalesce(turn_id, '')) AS turns,
COUNT(DISTINCT CASE
  WHEN nullif(trim(session_id), '') IS NOT NULL THEN session_id
END) AS observed_spawns,
coalesce(SUM(input_tokens), 0) AS input_tokens,
coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
coalesce(SUM(output_tokens), 0) AS output_tokens,
coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
coalesce(SUM(total_tokens), 0) AS total_tokens,
MAX(event_timestamp) AS latest_event
```

Run an additional aggregation by `model, service_tier` for every cohort/group and nest those rows under `model_buckets`. Validate `limit` as an integer from 1 through 100 before executing SQL. Sort breakdowns by `total_tokens DESC, group_key ASC`, then apply `limit`.

- [ ] **Step 4: Run focused tests and static checks**

Run:

```bash
.venv/bin/python -m pytest tests/store/test_subagent_usage_queries.py -q
.venv/bin/python -m ruff check src/codex_usage_tracker/store/subagent_usage_queries.py tests/store/test_subagent_usage_queries.py
.venv/bin/python -m ruff format --check src/codex_usage_tracker/store/subagent_usage_queries.py tests/store/test_subagent_usage_queries.py
```

Expected: all tests and checks pass.

- [ ] **Step 5: Commit the query slice**

```bash
git add -- src/codex_usage_tracker/store/subagent_usage_queries.py tests/store/test_subagent_usage_queries.py
git commit -m "feat: query subagent usage cohorts"
```

---

### Task 2: Build the stable report and Markdown rendering

**Files:**

- Create: `src/codex_usage_tracker/reports/subagent_usage.py`
- Create: `tests/reports/test_subagent_usage_report.py`

**Interfaces:**

- Consumes: `query_subagent_usage_buckets` from Task 1; `load_pricing_config`, `annotate_rows_with_efficiency`, and `validate_privacy_mode` from existing modules.
- Produces:

`SubagentUsageReport(data: dict[str, Any])` with `payload() -> dict[str, Any]` and `render() -> str`.

`build_subagent_usage_report(*, db_path: Path, pricing_path: Path, since: str | None = None, parent_thread: str | None = None, agent_role: str | None = None, subagent_type: str | None = None, include_archived: bool = False, limit: int = 10, privacy_mode: str = "normal") -> SubagentUsageReport`

- [ ] **Step 1: Write failing report-contract tests**

Monkeypatch `query_subagent_usage_buckets` with a compact synthetic mapping and assert the exact public shape:

```python
from tests.store_dashboard_helpers import _write_pricing


def _bucket(total_tokens: int, calls: int, turns: int, spawns: int) -> dict[str, Any]:
    metrics = {
        "calls": calls,
        "turns": turns,
        "observed_spawns": spawns,
        "input_tokens": total_tokens,
        "cached_input_tokens": total_tokens // 2,
        "uncached_input_tokens": total_tokens - (total_tokens // 2),
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "total_tokens": total_tokens,
        "latest_event": "2026-07-21T12:00:00Z",
    }
    return {
        "metrics": metrics,
        "model_buckets": [{**metrics, "model": "gpt-5.5", "service_tier": "standard"}],
    }


def query_fixture() -> dict[str, Any]:
    subagent = _bucket(300, 4, 3, 2)
    direct = _bucket(600, 5, 4, 0)
    return {
        "cohorts": {
            "direct": direct,
            "subagent": subagent,
            "attributable_subagent": subagent,
        },
        "breakdowns": {
            "role": [{"group_key": "worker", **subagent}],
            "type": [{"group_key": "thread_spawn", **subagent}],
            "parent": [{"group_key": "Synthetic parent", **subagent}],
        },
        "coverage": {
            "missing_session_rows": 0,
            "missing_session_tokens": 0,
            "missing_role_spawns": 0,
            "missing_type_spawns": 0,
        },
    }


def test_report_builds_v1_spawn_and_comparison_metrics(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(report_module, "query_subagent_usage_buckets", lambda *a, **k: query_fixture())
    pricing_path = _write_pricing(tmp_path / "pricing.json")

    report = build_subagent_usage_report(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=pricing_path,
    ).payload()

    assert report["schema_id"] == "codex-usage-tracker.subagent-usage.v1"
    assert report["definitions"]["observed_comparison_not_causal"] is True
    assert report["summary"]["observed_spawns"] == 2
    assert report["summary"]["total_tokens_per_observed_spawn"] == 150.0
    assert report["comparison"]["subagent"]["total_tokens"] == 300
    assert report["comparison"]["direct"]["total_tokens"] == 600
    assert report["summary"]["subagent_token_share"] == pytest.approx(1 / 3)
```

Add tests named:

- `test_report_uses_only_attributable_usage_for_per_spawn_metrics`
- `test_zero_denominators_render_as_none`
- `test_pricing_coverage_separates_priced_estimated_and_unpriced`
- `test_redacted_and_strict_modes_pseudonymize_parent_labels`
- `test_normal_mode_preserves_parent_labels`
- `test_empty_report_keeps_stable_v1_shape`
- `test_invalid_since_limit_and_privacy_mode_raise_value_error`
- `test_markdown_is_compact_and_states_non_causal_limit`
- `test_payload_never_contains_session_ids_or_agent_nicknames`

- [ ] **Step 2: Run report tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/reports/test_subagent_usage_report.py -q
```

Expected: collection fails because `codex_usage_tracker.reports.subagent_usage` does not exist.

- [ ] **Step 3: Implement validation and the report type**

Use the exact stable top-level shape:

```python
@dataclass(frozen=True)
class SubagentUsageReport:
    data: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return dict(self.data)

    def render(self) -> str:
        return render_subagent_usage(self.data)
```

Validate ISO dates without accepting empty strings:

```python
def _validate_since(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        raise ValueError("since must be a non-empty ISO-8601 date or datetime")
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("since must be an ISO-8601 date or datetime") from exc
    return candidate
```

Validate privacy mode through `validate_privacy_mode`; validate `limit` before calling the store.

- [ ] **Step 4: Implement pricing, privacy, and derived metrics**

Price model buckets with existing pricing logic, then sum only numeric cost values:

```python
def _price_bucket(bucket: dict[str, Any], pricing: PricingConfig) -> dict[str, Any]:
    rows = annotate_rows_with_efficiency(bucket["model_buckets"], pricing)
    covered_costs = [row["estimated_cost_usd"] for row in rows if isinstance(row["estimated_cost_usd"], int | float)]
    return {
        **bucket["metrics"],
        "estimated_cost_usd": (
            round(sum(float(value) for value in covered_costs), 6)
            if covered_costs
            else None
        ),
        "pricing_coverage": _pricing_coverage(rows),
    }
```

Compute shares and ratios with one null-safe helper:

```python
def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if denominator else None
```

Build `summary` from the priced subagent cohort, but use `attributable_subagent` for all per-spawn numerators. Build `comparison` from parallel direct and subagent metrics. For redacted and strict privacy modes, replace parent labels with a stable local digest such as `Parent <sha256(label)[:8]>`; normal mode retains the label. Never hash or return raw session IDs.

Build these exact top-level keys even for empty data:

```python
payload = {
    "schema_id": "codex-usage-tracker.subagent-usage.v1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "filters": filters,
    "definitions": definitions,
    "summary": summary,
    "comparison": comparison,
    "by_role": by_role,
    "by_type": by_type,
    "top_parent_threads": top_parent_threads,
    "coverage": coverage,
    "warnings": warnings,
}
```

- [ ] **Step 5: Implement concise Markdown rendering**

Render no more than one summary paragraph, one comparison paragraph, and the three limited breakdown lists. Include this exact caveat:

```text
Observed comparison only; it does not show that subagents caused the difference.
```

Empty results must render `No observed subagent usage matched these filters.` without raising.

- [ ] **Step 6: Run report tests and static checks**

Run:

```bash
.venv/bin/python -m pytest tests/reports/test_subagent_usage_report.py -q
.venv/bin/python -m ruff check src/codex_usage_tracker/reports/subagent_usage.py tests/reports/test_subagent_usage_report.py
.venv/bin/python -m ruff format --check src/codex_usage_tracker/reports/subagent_usage.py tests/reports/test_subagent_usage_report.py
.venv/bin/python -m mypy src/codex_usage_tracker/reports/subagent_usage.py
```

Expected: all tests and checks pass.

- [ ] **Step 7: Commit the report slice**

```bash
git add -- src/codex_usage_tracker/reports/subagent_usage.py tests/reports/test_subagent_usage_report.py
git commit -m "feat: build subagent usage report"
```

---

### Task 3: Expose one CLI command and one MCP tool

**Files:**

- Create: `src/codex_usage_tracker/cli/mcp_subagents.py`
- Create: `tests/cli/test_subagent_usage_interfaces.py`
- Modify: `src/codex_usage_tracker/cli/parser_reports.py`
- Modify: `src/codex_usage_tracker/cli/parser.py`
- Modify: `src/codex_usage_tracker/cli/commands_reports.py`
- Modify: `src/codex_usage_tracker/cli/main.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `tests/cli/test_cli_release.py`

**Interfaces:**

- Consumes: `build_subagent_usage_report` from Task 2.
- Produces: CLI `codex-usage-tracker subagents` and MCP `subagent_usage` with identical JSON payloads.

- [ ] **Step 1: Add failing public-registration and parity tests**

Add `"subagents"` to `CLI_HELP_SUBCOMMANDS` and `"subagent_usage"` to `MCP_TOOL_NAMES` in `tests/cli/test_cli_release.py`.

In the new focused test file, use a fake report to prove both adapters forward identical arguments:

```python
@dataclass(frozen=True)
class FakeReport:
    def payload(self) -> dict[str, object]:
        return {"schema_id": "codex-usage-tracker.subagent-usage.v1", "summary": {"observed_spawns": 2}}

    def render(self) -> str:
        return "2 observed subagent spawns"


def test_mcp_json_returns_shared_report_payload(monkeypatch) -> None:
    monkeypatch.setattr(mcp_subagents, "build_subagent_usage_report", lambda **kwargs: FakeReport())
    assert mcp_subagents.subagent_usage(response_format="json") == FakeReport().payload()


def test_cli_parser_defaults_match_mcp_contract() -> None:
    args = build_parser().parse_args(["subagents", "--json"])
    assert args.command == "subagents"
    assert args.limit == 10
    assert args.include_archived is False
    assert args.as_json is True
```

Also test all filters, Markdown mode, invalid MCP response format, and exact CLI/MCP JSON equality after monkeypatching both adapters to the same fake builder.

- [ ] **Step 2: Run interface tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py -q
```

Expected: failures report the missing `subagents` command and `subagent_usage` tool.

- [ ] **Step 3: Add the CLI parser and runner**

Add this parser function to `parser_reports.py`:

```python
def _add_subagents_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("subagents", help="Analyze observed subagent spawns and usage")
    parser.add_argument("--since", help="Only include calls at or after this ISO date/time")
    parser.add_argument("--parent-thread")
    parser.add_argument("--agent-role")
    parser.add_argument("--subagent-type")
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", dest="as_json")
```

Import and call `_add_subagents_parser(subparsers)` next to `_add_summary_parser` in `cli/parser.py`.

Add this runner to `commands_reports.py`:

```python
def _run_subagents(args: argparse.Namespace) -> int:
    report = build_subagent_usage_report(
        db_path=args.db,
        pricing_path=args.pricing,
        since=args.since,
        parent_thread=args.parent_thread,
        agent_role=args.agent_role,
        subagent_type=args.subagent_type,
        include_archived=args.include_archived,
        limit=args.limit,
        privacy_mode=args.privacy_mode,
    )
    if args.as_json:
        print_json(report.payload())
    else:
        print(report.render())
    return 0
```

Import `_run_subagents` and add `"subagents": _run_subagents` to `_COMMAND_HANDLERS` in `cli/main.py`.

- [ ] **Step 4: Add the modular MCP adapter**

Create `cli/mcp_subagents.py`:

```python
from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.reports.subagent_usage import build_subagent_usage_report


@mcp.tool()
def subagent_usage(
    since: str | None = None,
    parent_thread: str | None = None,
    agent_role: str | None = None,
    subagent_type: str | None = None,
    include_archived: bool = False,
    limit: int = 10,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Analyze distinct observed subagent sessions and their aggregate usage."""
    if response_format not in {"markdown", "json"}:
        raise ValueError("response_format must be markdown or json")
    report = build_subagent_usage_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        since=since,
        parent_thread=parent_thread,
        agent_role=agent_role,
        subagent_type=subagent_type,
        include_archived=include_archived,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    return report.payload() if response_format == "json" else report.render()
```

Import/re-export it in `cli/mcp_server.py`:

```python
from codex_usage_tracker.cli.mcp_subagents import subagent_usage as subagent_usage
```

Keep all tool logic out of the already-large `cli/mcp_server.py`.

- [ ] **Step 5: Run interface and regression tests**

Run:

```bash
.venv/bin/python -m pytest tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py tests/cli/test_mcp_integration.py -q
.venv/bin/python -m codex_usage_tracker subagents --help
.venv/bin/python -m ruff check src/codex_usage_tracker/cli tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py
.venv/bin/python -m ruff format --check src/codex_usage_tracker/cli tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py
```

Expected: tests/checks pass, and help lists all approved filters.

- [ ] **Step 6: Commit the interface slice**

```bash
git add -- src/codex_usage_tracker/cli/mcp_subagents.py src/codex_usage_tracker/cli/parser_reports.py src/codex_usage_tracker/cli/parser.py src/codex_usage_tracker/cli/commands_reports.py src/codex_usage_tracker/cli/main.py src/codex_usage_tracker/cli/mcp_server.py tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py
git commit -m "feat: expose subagent usage through CLI and MCP"
```

---

### Task 4: Document, package, and verify the public contract

**Files:**

- Modify: `docs/mcp.md`
- Modify: `docs/cli-reference.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/privacy.md`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md`
- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`

**Interfaces:**

- Consumes: the completed CLI/MCP contract from Task 3.
- Produces: user-facing and packaged guidance with exact tool names, definitions, limitations, and examples.

- [ ] **Step 1: Update source skill routing first and verify parity fails**

Add this exact guidance to both source skill files before syncing packaged copies:

```markdown
- Use `subagent_usage(response_format="json")` for observed subagent spawn counts, role/type mix, parent-thread fan-out, subagent usage share, per-spawn usage, and descriptive direct-versus-subagent comparisons.
- An observed spawn is a distinct persisted subagent session. Agents that produced no usage event are not visible, and comparison results are descriptive rather than causal.
```

Run:

```bash
.venv/bin/python scripts/check_release.py
```

Expected: FAIL because source and packaged skill copies differ.

- [ ] **Step 2: Apply the same edits to packaged skill copies**

Make the packaged files byte-for-byte equivalent to their source counterparts. Verify:

```bash
cmp -s skills/codex-usage-api/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md
cmp -s skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md
```

Expected: both commands exit 0.

- [ ] **Step 3: Document MCP and CLI usage**

Add the exact examples below to `docs/mcp.md` and `docs/cli-reference.md`:

```python
subagent_usage(since="2026-07-01", response_format="json")
subagent_usage(agent_role="worker", limit=5, response_format="json")
subagent_usage(parent_thread="Investigate usage spike")
```

```bash
codex-usage-tracker subagents --since 2026-07-01 --json
codex-usage-tracker subagents --agent-role worker --limit 5
codex-usage-tracker subagents --parent-thread "Investigate usage spike"
```

State beside both examples: `observed_spawns` counts distinct persisted subagent sessions; zero-usage spawns are invisible; direct comparison is non-causal.

- [ ] **Step 4: Document the JSON and privacy contracts**

In `docs/cli-json-schemas.md`, add the complete top-level v1 key list and document `summary`, `comparison`, `by_role`, `by_type`, `top_parent_threads`, `coverage`, and `warnings`, including nullable ratios.

In `docs/privacy.md`, add:

```markdown
Subagent analytics never returns raw session identifiers, agent nicknames, prompts, responses, or context. Parent-thread labels are preserved only in normal privacy mode and are pseudonymized in redacted and strict modes.
```

- [ ] **Step 5: Run focused feature verification**

Run:

```bash
.venv/bin/python -m pytest tests/store/test_subagent_usage_queries.py tests/reports/test_subagent_usage_report.py tests/cli/test_subagent_usage_interfaces.py tests/cli/test_cli_release.py -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
.venv/bin/pyright
.venv/bin/python -m mypy
.venv/bin/tach check
.venv/bin/python scripts/check_release.py
git diff --check
```

Expected: every command passes.

- [ ] **Step 6: Run the public-contract release gate**

Because this changes MCP, CLI JSON, packaged skills, and documentation, run:

```bash
just v
.venv/bin/python -m build
.venv/bin/python scripts/check_release.py --dist
.venv/bin/python scripts/smoke_installed_package.py
```

Expected: the full verifier, package build, distribution checks, and installed-package smoke test pass. If a verifier fails, read `.verify-logs/LAST_FAILURE.md` before changing code or configuration.

- [ ] **Step 7: Review the final diff for privacy and scope**

Run:

```bash
git status --short --branch
git diff --stat
git diff
git diff --check
```

Confirm exactly these conditions before staging:

- At most 20 intended files changed.
- No raw usage data, prompts, tokens, credentials, session identifiers, SQLite files, generated dashboards, or unrelated artifacts are present.
- Existing untracked IDE/SDD/output artifacts remain unstaged.
- Both skill-copy pairs are identical.

- [ ] **Step 8: Commit documentation and packaging guidance**

```bash
git add -- docs/mcp.md docs/cli-reference.md docs/cli-json-schemas.md docs/privacy.md skills/codex-usage-api/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md
git commit -m "docs: document subagent usage analytics"
```

After committing, run `git status --short --branch` once more and report the four implementation commits and all verification results.
