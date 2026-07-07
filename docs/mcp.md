# MCP And Codex Skills

Codex Usage Tracker can be installed as a local Codex plugin and exposes MCP tools for local usage analysis, aggregate reports, allowance diagnostics, source coverage, and future content-index investigation.

## Local Plugin

After installing the Python package, register the plugin:

```bash
codex-usage-tracker install-plugin
```

For a source checkout:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python
```

Restart Codex after registration so it can discover the plugin.

Marketplace installs use the bundled MCP launcher at `skills/codex-usage-tracker/scripts/run_mcp.py`. On first MCP startup it creates a cached runtime under `~/.cache/codex-usage-tracker/mcp-runtime/` and installs the exact pinned Python package, so it does not require a `.venv` inside the plugin directory.

This is intentional: normal user installs come from the PyPI distribution `codex-usage-tracking`, and the plugin bootstrapper pins an exact reviewed package version so MCP startup does not accidentally track `main`.

The launcher stores the package spec used for that runtime and reinstalls when the bundled package pin changes. Set `CODEX_USAGE_TRACKER_PACKAGE_SPEC` to test a different package version or Git ref, or set `CODEX_USAGE_TRACKER_RUNTIME_DIR` to use a separate cache while debugging plugin startup.

## Companion Skills

The plugin installs two companion skills. They are local instruction files that help Codex use this package; they do not create another hosted service or send usage data outside the machine.

- `codex-usage-tracker`: operational setup and direct tracker work, including refresh, dashboards, CSV export, doctor checks, and MCP tools.
- `codex-usage-api`: conversational usage analysis using stable usage APIs first, with content-index tools treated as explicit local investigation tools when they are available.

Good prompts for the API companion skill:

```text
Open dashboard.
Use my Codex Usage Tracker data to explain what drove usage this week.
Heaviest thread?
Thread leaderboard.
Look through my usage for token waste and recommend fixes.
Find low-cache or high-context calls from today and suggest what to inspect next.
Look through my usage for token waste.
Find calls where context got bloated.
Show me where caching failed.
Find expensive calls worth opening in the investigator.
Compare usage by project for the last 7 days.
Show me what is estimated or unpriced before I trust the cost numbers.
```

The API skill should refresh the local index, call stable tools such as `usage_status`, `usage_calls`, `usage_call_detail`, `usage_threads`, `usage_report_pack`, `usage_summary`, `usage_query`, `session_usage`, `usage_recommendations`, `most_expensive_usage_calls`, `usage_pricing_coverage`, or `usage_source_coverage`, then explain the answer with the data scope and estimate caveats. Content-aware tools should be used only when the user asks for local content exploration or a diagnostic clearly needs indexed snippets.

If MCP tools are not available, the same questions can be answered through CLI JSON commands documented in [CLI And MCP JSON Schemas](cli-json-schemas.md).

Waste-discovery answers should include remediation ideas when evidence supports them: dashboard rows to inspect, Headroom if available for context/headroom checks, workflow changes such as thread splitting or lower effort for routine work, and small custom local commands or skill updates Codex can build when the same waste pattern keeps recurring.

The companion skill cannot read your logged-in Codex account plan, native remaining allowance, or usage from other agentic surfaces. Remaining allowance context is only as accurate as the values you manually copy into `~/.codex-usage-tracker/allowance.json`.

## Tools

- `refresh_usage_index`
- `usage_doctor`
- `usage_summary`
- `usage_query`
- `usage_status`
- `usage_calls`
- `usage_call_detail`
- `usage_threads`
- `usage_report_pack`
- `usage_dashboard_recommendations`
- `usage_recommendations`
- `session_usage`
- `usage_call_context`
- `most_expensive_usage_calls`
- `usage_pricing_coverage`
- `usage_source_coverage`
- `usage_content_search`
- `usage_thread_trace`
- `usage_repetition_scan`
- `usage_command_loop_scan`
- `usage_file_churn_scan`
- `usage_context_bloat_scan`
- `usage_allowance_history`
- `usage_allowance_diagnostics`
- `usage_allowance_export`
- `generate_usage_dashboard`
- `export_usage_csv`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

`usage_doctor`, `usage_summary`, `usage_recommendations`, `session_usage`, `most_expensive_usage_calls`, `usage_pricing_coverage`, and `usage_source_coverage` accept `response_format="json"` when an agent needs stable structured output instead of markdown.

Dashboard-shaped MCP tools return JSON dictionaries directly and reuse the same aggregate schemas as the local React dashboard API:

Status: `usage_status()` returns `/api/status` freshness, row counts, parser diagnostics, and observed allowance windows.

Calls: `usage_calls(...)` returns `/api/calls` rows with filters, pagination, `total_matched_rows`, `has_more`, and `next_offset`.

Call detail: `usage_call_detail(record_id=...)` returns `/api/call` data for the Call Investigator without raw transcript context.

Threads: `usage_threads(...)` returns `/api/threads` aggregate thread rows.

Report pack: `usage_report_pack(...)` returns `/api/reports/pack` report cards and compact evidence rows.

Dashboard recommendations: `usage_dashboard_recommendations(...)` returns the dashboard recommendation payload.

`refresh_usage_index`, `usage_query`, `generate_usage_dashboard`, `export_usage_csv`, and config-writing MCP tools return JSON dictionaries directly.

`refresh_usage_index()` indexes aggregate usage rows and the local content index by default. Use `refresh_usage_index(aggregate_only=True)` when the user wants the older aggregate-only SQLite posture.

`refresh_usage_index(include_archived=True)` and `generate_usage_dashboard(include_archived=True)` are explicit all-history opt-ins. The default dashboard view excludes archived session rows so older work does not inflate the current usage picture.

`usage_content_search(query=...)` searches the explicit local content index and can return indexed snippets. Use it only when the user asks for local content exploration, pattern hunting, or diagnostics that need transcript-level evidence. Its payload marks `content_mode="local_content_index"`, `includes_indexed_content=true`, and `includes_raw_fragments=true`.

`usage_thread_trace(...)` returns a paged call timeline for one thread, thread key, session id, or seed record id, with local indexed fragments attached when present. It is also an explicit local content-index surface and carries the same indexed-content flags.

`usage_repetition_scan(...)`, `usage_command_loop_scan(...)`, `usage_file_churn_scan(...)`, and `usage_context_bloat_scan(...)` run explicit local content/event-index diagnostics over normalized fragment hashes, command roots/labels, file hashes/basenames, and aggregate token rows. These payloads set `includes_indexed_content=true` and `includes_raw_fragments=false`.

## Allowance Intelligence MCP Tools

- `usage_allowance_history(...)` returns normalized observed weekly and 5-hour allowance snapshots.
- `usage_allowance_diagnostics(...)` returns evidence grades comparing observed usage movement against estimated local credits. Weekly candidates include `nonparametric-v1` statistical evidence plus `summary.research_readiness`; weekly windows are primary and 5-hour windows are noisy rolling-window context.
- `usage_allowance_export(...)` returns a strict-privacy evidence bundle for manual sharing.

Use these when users ask whether limits changed, whether weekly allowance behavior shifted, why the 5-hour counter looks noisy, or how to share aggregate allowance evidence safely.

## Raw Context Guard

`usage_call_context` is disabled by default in MCP server processes. To enable it explicitly:

```bash
CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1
```

Normal aggregate tools do not need this variable. Keep raw context disabled unless the user specifically asks to inspect local log context.

When raw context is enabled, `usage_call_context` accepts `max_entries`, `max_chars`, `include_tool_output`, and `include_compaction_history`. Use `0` for either limit only when the user explicitly asks for all matching entries or no character cap for that local context request. Compacted replacement history is transcript-like content; request it only for a specific call investigation, and keep the aggregate tools as the default path.
