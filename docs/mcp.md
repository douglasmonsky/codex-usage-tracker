# MCP And Codex Skills

Codex Usage Tracker can be installed as a local Codex plugin. It exposes MCP tools for local usage analysis, dashboard-shaped aggregate payloads, allowance diagnostics, source coverage, and opt-in local content-index investigations.

## Local Plugin

After installing the Python package, register the plugin:

```bash
codex-usage-tracker install-plugin
```

For a source checkout:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python
```

Restart Codex after registration so the plugin and skills are discovered.

Marketplace installs use the bundled MCP launcher at `skills/codex-usage-tracker/scripts/run_mcp.py`. On first MCP startup it creates a cached runtime under `~/.cache/codex-usage-tracker/mcp-runtime/` and installs the exact pinned Python package, so the plugin does not need a `.venv` inside its directory.

The launcher intentionally pins a reviewed package version instead of tracking `main`. Set `CODEX_USAGE_TRACKER_PACKAGE_SPEC` to test another package version or Git ref, and set `CODEX_USAGE_TRACKER_RUNTIME_DIR` to use a separate cache while debugging plugin startup.

## Companion Skills

The plugin installs two companion skills:

- `codex-usage-tracker`: operational setup, dashboard launch, refresh, CSV export, doctor checks, and direct tracker commands.
- `codex-usage-api`: conversational usage analysis using stable MCP/API payloads first, with content-index tools reserved for explicit local investigation.

Good starter prompts:

```text
Open dashboard.
Suggest usage investigations.
Look through my usage for token waste.
Find high-context, low-cache calls worth opening in investigator.
Which threads are draining the most, and what would reduce that next time?
Check whether my weekly allowance changed.
Explain why the 5-hour counter looks noisy.
Compare usage by model and effort, then suggest safer defaults.
Show me what is estimated or unpriced before I trust cost numbers.
```

The API skill should refresh the local index, use MCP JSON tools, state scope and caveats, and recommend practical next actions. If MCP tools are unavailable, use the CLI JSON commands documented in [CLI And MCP JSON Schemas](cli-json-schemas.md).

## Agentic Investigation Tools

Use `usage_suggest_investigations(...)` when the user wants ideas, is unsure what to inspect, or asks what the tracker can help with. It returns goal-led investigation options such as token waste, allowance change, cache failure, workflow churn, and overview.

Use `usage_investigate(...)` as the first stop for broad requests such as "look through my usage for token waste" or "what should I change?" It returns normalized findings, evidence, confidence, recommended actions, verification tools, and caveats.

Use lower-level diagnostics when the investigation report recommends them:

- `usage_large_low_output_calls(...)`: high-token calls that produced little output, with cache/context clues and likely explanations.
- `usage_shell_churn(...)`: repeated shell command roots such as `sed`, `rg`, `git`, `nl`, test, and package commands.
- `usage_repeated_file_rediscovery(...)`: repeated safe file identities using hashes, basenames, extensions, and operation mixes without exposing full paths.
- `usage_investigation_walk(question=...)`: deeper local hypothesis walk over normalized content/event-index signals.
- `usage_local_evidence_export(question=...)`: strict shareable summary from the local investigation walk, omitting raw/private records.

Waste-discovery answers should not stop at "interesting." Tie recommendations to evidence and suggest verification in Calls, Threads, Call Investigator, Diagnostics Notebook, or Allowance Intelligence. Mention Headroom only when context pressure or handoff timing is relevant and the tool is available. Suggest custom local commands, scripts, repo notes, or skill updates when the same waste pattern keeps recurring.

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
- `usage_allowance_history`
- `usage_allowance_diagnostics`
- `usage_allowance_export`
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
- `usage_repeated_file_rediscovery`
- `usage_shell_churn`
- `usage_large_low_output_calls`
- `usage_suggest_investigations`
- `usage_investigate`
- `usage_context_bloat_scan`
- `usage_investigation_walk`
- `usage_local_evidence_export`
- `generate_usage_dashboard`
- `export_usage_csv`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

## Tool Notes

`usage_doctor`, `usage_summary`, `usage_recommendations`, `session_usage`, `most_expensive_usage_calls`, `usage_pricing_coverage`, and `usage_source_coverage` accept `response_format="json"` when an agent needs stable structured output instead of markdown.

Dashboard-shaped MCP tools return JSON dictionaries that reuse the same aggregate schemas as the local React dashboard API:

- `usage_status()` mirrors `/api/status`.
- `usage_calls(...)` mirrors `/api/calls`, including filters, pagination, `total_matched_rows`, `has_more`, and `next_offset`.
- `usage_call_detail(record_id=...)` mirrors `/api/call` for aggregate Call Investigator data without raw transcript context.
- `usage_threads(...)` mirrors `/api/threads`.
- `usage_report_pack(...)` mirrors `/api/reports/pack`.
- `usage_dashboard_recommendations(...)` returns dashboard recommendation payloads.

`refresh_usage_index()` indexes aggregate usage rows plus the local content index by default. Use `refresh_usage_index(aggregate_only=True)` when the user wants the older aggregate-only SQLite posture. Use `include_archived=True` only when the user explicitly wants all history; the dashboard defaults to active sessions so older work does not inflate current usage.

## Allowance Intelligence

- `usage_allowance_history(...)` returns normalized observed weekly and 5-hour allowance snapshots.
- `usage_allowance_diagnostics(...)` returns evidence grades comparing observed usage movement against estimated local credits. Weekly windows are the primary long-range signal; 5-hour windows are noisy rolling-window context.
- `usage_allowance_export(...)` returns strict-privacy evidence bundles for manual sharing.

Use allowance tools when users ask whether limits changed, whether weekly allowance behavior shifted, why the 5-hour counter looks noisy, or how to share aggregate allowance evidence safely. The tracker cannot read the user's logged-in Codex account plan, native remaining allowance, or usage from other agentic surfaces. Remaining allowance context is only as accurate as values manually copied into `~/.codex-usage-tracker/allowance.json`.

## Local Content And Raw Context

`usage_content_search(query=...)` searches the explicit local content index and can return indexed snippets. Use it only when the user asks for local content exploration, pattern hunting, or diagnostics that need transcript-level evidence. Its payload marks `content_mode="local_content_index"`, `includes_indexed_content=true`, and `includes_raw_fragments=true`.

`usage_thread_trace(...)` returns a paged call timeline for one thread/session/seed record and may include local indexed fragments. Treat it as an explicit local content-index surface, not a default shareable report.

`usage_call_context` is disabled by default in MCP server processes. Enable it explicitly only when the user asks to inspect raw local log context:

```bash
CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1
```

Normal aggregate tools do not need that variable. When raw context is enabled, `usage_call_context` accepts `max_entries`, `max_chars`, `include_tool_output`, and `include_compaction_history`. Use `0` limits only when the user explicitly asks for all matching entries or no character cap on local context.
