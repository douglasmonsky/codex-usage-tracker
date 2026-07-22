# MCP And Codex Skills

MCP is the primary analysis interface for Codex Usage Tracker. The local Codex
plugin exposes deterministic tools for usage analysis, bounded queries,
allowance diagnostics, source coverage, and explicit local content-index
investigations. Material conclusions can link to the supporting
[Evidence Console](evidence-console.md); the browser does not perform or invent
the analysis.

Normal refresh indexes aggregate counters and the existing bounded local
content/event index. Aggregate-only commands retain the older posture, and
shareable outputs follow existing behavior. See [Data Posture](data-posture.md)
and [Privacy](privacy.md) for the exact local-storage and output boundaries.

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
Suggest the clearest chart for finding token waste, then render its spec.
```

The API skill should refresh the local index, use MCP JSON tools, state scope and caveats, and recommend practical next actions. If MCP tools are unavailable, use the CLI JSON commands documented in [CLI And MCP JSON Schemas](cli-json-schemas.md).

## Agentic Investigation Tools

Use `usage_suggest_investigations(...)` when the user wants ideas, is unsure what to inspect, or asks what the tracker can help with. It returns a short menu of related goal-led investigations such as token waste, allowance change, cache failure, workflow churn, and overview. Goal-specific requests still include adjacent useful investigations instead of a one-item answer.

For broad requests such as "look through my usage for token waste" or "what should I change?", prefer the Compression Lab lifecycle: `usage_compression_start(...)`, `usage_compression_status(...)`, `usage_compression_profile(...)`, `usage_compression_candidates(...)`, selected `usage_compression_candidate_detail(...)`, and optional `usage_compression_simulate(...)`. This gives agents progress, a compact profile, ranked candidates, selected evidence, and estimated intervention impact without one cloudy nested response.

Use `usage_investigate(...)` and `usage_action_brief(...)` as compatibility routers when the caller wants one broad entrypoint. For `overview`, `token_waste`, `cache_failure`, and `workflow_churn`, compact/default calls return `content_mode="compression_lab_router"` plus `compression_lab.next` and `recommended_next_tools`. `usage_investigate(detail_mode="full")` keeps the older aggregate diagnostic rows when full legacy evidence is explicitly needed.

Use `usage_action_brief(...)` when the user wants a concise "what should I actually do next?" answer from the same router. It returns action families with evidence, likely waste pattern, recommended workflow change, existing/custom tool ideas, verification steps, and next MCP tools. It is shareable by default and does not include indexed snippets or raw fragments.

Use `usage_test_hypotheses(...)` when the user frames the task as hypotheses, wants true/false/partial decisions, or asks for the "I'd like to / I will use / I'm missing / hypothesis result" structure. It tests supplied hypotheses or built-in defaults for token waste, cache failure, repeated file rediscovery, shell churn, effort/model choice, and allowance change. It uses aggregate and local-index signals but does not include raw fragments.

Use `usage_dogfood_start(...)`, `usage_dogfood_status(job_id)`, and `usage_dogfood_result(job_id)` for maintainer dogfood checks that may run longer than a normal MCP call. Start returns a job id, status reports percent/stage/cache keys, and result returns the compact aggregate dogfood payload after completion. For repeated checks on unchanged data, call with `refresh=False` and default `use_cache=True` after one fresh run; status then reports `result_cache.hit=true` when the compact artifact is reused. Jobs are in-process and cleared when the MCP server restarts.

Use lower-level diagnostics when the investigation report recommends them:

- `usage_large_low_output_calls(...)`: high-token calls that produced little output, with cache/context clues and likely explanations.
- `usage_shell_churn(...)`: repeated shell command roots such as `sed`, `rg`, `git`, `nl`, test, and package commands.
- `usage_repeated_file_rediscovery(...)`: repeated safe file identities using hashes, basenames, extensions, and operation mixes without exposing full paths.
- `usage_investigation_walk(question=...)`: deeper local hypothesis walk over normalized content/event-index signals.
- `usage_local_evidence_export(question=...)`: strict shareable summary from the local investigation walk, omitting raw/private records.

Waste-discovery answers should not stop at "interesting." Tie recommendations to evidence and suggest verification in Calls, Threads, Call Investigator, Diagnostics Notebook, or Allowance Intelligence. Mention Headroom only when context pressure or handoff timing is relevant and the tool is available. Suggest custom local commands, scripts, repo notes, or skill updates when the same waste pattern keeps recurring.

## Visualization Tools

Use `usage_visualization_suggest(question=..., scope=...)` when the user asks
what chart would clarify a usage question. It deterministically ranks four
supported intents: token waste, weekly allowance change, cache failure, and
thread lifecycle.

Use `usage_visualization_render(kind=..., format="spec")` after choosing an
intent. It reuses the existing aggregate report, allowance, Calls, and Threads
tools and returns:

- a renderer-independent `VisualizationSpecV1`;
- the same compact rows used by the visualization table;
- a short narrative, next action, and caveats;
- explicit aggregate/raw-content flags and source schema metadata.

`source_limit=0` or `source_limit=None` scans all matching aggregate source
rows; `evidence_limit` remains intentionally bounded from 1 through 50. The
default privacy mode is `strict`. SVG and PNG are deliberately unsupported in
this experiment so the base Python package does not acquire a Node or browser
runtime dependency. Codex clients can render the semantic spec when supported,
or use its synchronized table and narrative directly.

Compact examples:

```text
usage_visualization_render(kind="token_waste", source_limit=500, evidence_limit=12)
usage_visualization_render(kind="allowance_change", source_limit=0, evidence_limit=20)
usage_visualization_render(kind="cache_failure", model="gpt-5.5", evidence_limit=10)
usage_visualization_render(kind="thread_lifecycle", thread="thread:example", source_limit=None)
```

The first and third examples use aggregate report-pack evidence, allowance
change uses the weekly detector payload, and a selected thread uses
chronological Calls data. Omitting `thread` produces a bounded comparison of
the highest-token thread summaries instead.

## Tools

The default `core` profile uses `usage_analyze` for broad diagnostic or
explanatory questions (for example, `goal="token_waste"`) and `usage_query`
for exact tabular or grouped questions (for example, tokens grouped by model
and effort). Both return bounded versioned envelopes. An asynchronous analysis
returns an analysis-job handle; poll its `job_id` with `usage_job_status`.
Raw-context compatibility tools are not part of this default flow.

- `refresh_usage_index`
- `usage_refresh_start`
- `usage_refresh_status`
- `usage_doctor`
- `usage_summary`
- `subagent_usage`
- `usage_query`
- `usage_analyze`
- `usage_status`
- `usage_dedupe_diagnostics`
- `usage_calls`
- `usage_call_detail`
- `usage_threads`
- `usage_report_pack`
- `usage_dashboard_recommendations`
- `usage_allowance_history`
- `usage_allowance_diagnostics`
- `usage_allowance_export`
- `usage_allowance_status`
- `usage_allowance_series`
- `usage_allowance_evidence`
- `usage_allowance_analysis`
- `usage_allowance_analysis_status`
- `usage_compression_start`
- `usage_compression_status`
- `usage_compression_profile`
- `usage_compression_candidates`
- `usage_compression_candidate_detail`
- `usage_compression_simulate`
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
- `usage_action_brief`
- `usage_dogfood_start`
- `usage_dogfood_status`
- `usage_dogfood_result`
- `usage_test_hypotheses`
- `usage_context_bloat_scan`
- `usage_investigation_walk`
- `usage_local_evidence_export`
- `usage_visualization_suggest`
- `usage_visualization_render`
- `generate_usage_dashboard`
- `export_usage_csv`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

## Tool Notes

`usage_doctor`, `usage_summary`, `usage_recommendations`, `session_usage`, `most_expensive_usage_calls`, `usage_pricing_coverage`, and `usage_source_coverage` accept `response_format="json"` when an agent needs stable structured output instead of markdown.

`subagent_usage` returns aggregate-only observed-subagent cohorts and role, type, and parent breakdowns in Markdown or JSON:

```python
subagent_usage(since="2026-07-01", response_format="json")
subagent_usage(agent_role="worker", limit=5, response_format="json")
subagent_usage(parent_thread="Investigate usage spike")
```

`observed_spawns` counts distinct persisted subagent sessions from canonical, deduplicated usage rows. A spawn that produced no persisted usage event is not visible, and direct-versus-subagent comparisons are descriptive rather than causal.

Subagent analytics never returns raw session identifiers, agent nicknames, prompts, responses, or context. Parent-thread labels are preserved only in normal privacy mode and are pseudonymized in redacted and strict modes.

Dashboard-shaped MCP tools return JSON dictionaries that reuse the same aggregate schemas as the local React dashboard API:

- `usage_status()` mirrors `/api/status`.
- `usage_dedupe_diagnostics(limit=100)` reports canonical versus physical rows and lists bounded aggregate/source provenance for copied clone rows excluded from totals. It never returns transcript content.
- `usage_calls(...)` mirrors `/api/calls`, including filters, pagination, `total_matched_rows`, `has_more`, and `next_offset`.
- `usage_call_detail(record_id=...)` mirrors `/api/call` for aggregate Call Investigator data without raw transcript context.
- `usage_threads(...)` mirrors `/api/threads`.
- `usage_report_pack(...)` mirrors `/api/reports/pack`.
- `usage_dashboard_recommendations(...)` returns dashboard recommendation payloads.

Selected MCP results include an additive `dashboard_target` without changing their
existing schema name, fields, row order, filters, or query semantics. `usage_status`
links to Overview; Calls rows and call detail link to Call Investigator; Threads rows
link only when their producer supplied a canonical `thread_key`; and canonical
`usage_investigate` evidence rows link to matching Call Investigator or Threads
evidence. Each finding inherits a copy of its first successfully linked evidence
target; findings do not encode an ordinal Investigator route. Thread annotation never
substitutes a display name when `thread_key` is absent. If a canonical identifier is
not valid for the selected privacy mode, that row simply omits the target.

Targets also preserve the MCP query's history scope. Calls, Threads, status, and
investigation results requested with `include_archived=true` emit `history="all"` and
an explicit `history=all` URL parameter. Active-only requests emit `history="active"`.
Call detail uses a reliable producer `is_archived` flag, when present, to keep an
archived selected record reachable in all-history scope.

Each tool checks the persistent dashboard service once. A reachable service produces
a loopback `absolute_url`; an unreachable service or a local status-inspection error
keeps the MCP result successful and returns a relative target with
`codex-usage-tracker serve-dashboard --open` fallback guidance. These links are
navigation metadata only: target presence does not upgrade conversational readiness,
index freshness, MCP discovery, current-task tool exposure, or access to raw context.
Use the existing readiness and recovery fields from `usage_status` for those claims.

Clients should present **Open evidence** with `dashboard_target.absolute_url` when
that value is present. Otherwise they should show `relative_url` together with the
exact `fallback_instruction`; they must not invent a host or infer that a dashboard
service is running. A target, installed skill, or healthy persistent service never
proves task-level MCP tool exposure. Inspect the current task's tool inventory before
claiming MCP availability.

`refresh_usage_index()` indexes aggregate usage rows plus the local content index by default. Use `refresh_usage_index(aggregate_only=True)` when the user wants the older aggregate-only SQLite posture. Use `include_archived=True` only when the user explicitly wants all history; the dashboard defaults to active sessions so older work does not inflate current usage.

## Allowance Intelligence

- `usage_allowance_status(...)` is the default polling entry point. It reads a
  constant-size canonical snapshot, reports copied clone rows excluded, and
  directs stale or empty indexes through `usage_refresh_start` and
  `usage_refresh_status` without running full diagnostics. Pass the last
  `revision` as `since_revision`; an unchanged response stays compact.
- `usage_allowance_series(...)` returns canonical observed context plus weekly
  completed-cycle `credits / 1%` capacity history, robust rolling summaries,
  regimes, and every supported boundary. It accepts bounded presets, bounded
  custom ranges, or `all` aggregate cycles without scanning raw transcripts.
- `usage_allowance_evidence(...)` returns latest-first canonical transitions in
  pages of at most 500 rows; 50 is the normal first page. Pass `next_cursor` back
  as `cursor`. Strict and normal modes return aggregate provenance; local mode
  explicitly opts into bounded physical record identifiers for debugging.
- `usage_allowance_analysis(...)` reads the exact persisted multi-change result
  for the current source/model/rate-card key or starts one deduplicated background job.
  Poll active work with `usage_allowance_analysis_status(job_id)`, then reload
  `usage_allowance_analysis(...)` after completion.
- `usage_allowance_history(...)` returns normalized observed weekly and 5-hour allowance snapshots.
- `usage_allowance_diagnostics(...)` returns evidence grades comparing observed usage movement against estimated local credits. Weekly windows are the primary long-range signal; 5-hour windows are noisy rolling-window context.
- `usage_allowance_export(...)` returns strict-privacy evidence bundles for manual sharing.

The v2 status, series, evidence, and analysis tools are the normal MCP/plugin
surface. History, diagnostics, and export remain compatibility and explicit
offline-diagnostic tools. Use allowance tools when users ask whether limits
changed, whether weekly allowance behavior shifted, why the 5-hour counter
looks noisy, or how to share aggregate allowance evidence safely. The tracker
cannot read the user's logged-in Codex account plan, native remaining
allowance, or usage from other agentic surfaces. Remaining allowance context is
only as accurate as values manually copied into
`~/.codex-usage-tracker/allowance.json`.

Recommended polling flow:

```text
usage_allowance_status()
usage_allowance_status(since_revision="r-example")
usage_allowance_series(range_preset="8w", granularity="cycle")
usage_allowance_evidence(limit=50)
usage_allowance_analysis()
usage_allowance_analysis_status(job_id="allowance-analysis-example")
```

Poll status after the returned interval (30 seconds for fresh/aging data, 60
seconds for stale/empty/unchanged data). Poll an analysis job every 500
milliseconds only while it is pending, queued, or running. Do not pass `limit=0`
to v2 evidence. See
[Allowance Intelligence](allowance-intelligence.md) for model gates and
[CLI, MCP, and Dashboard JSON Schemas](cli-json-schemas.md) for synthetic payloads.

## Compression Lab

Compression Lab is the profile-first MCP workflow for finding context and token
waste without returning one cloudy nested report:

```text
usage_compression_start(include_archived=false)
usage_compression_status(run_id="compression_...")
usage_compression_profile(run_id="compression_...")
usage_compression_candidates(run_id="compression_...", limit=20)
usage_compression_candidate_detail(candidate_id="cmp_...", evidence_mode="handles")
usage_compression_simulate(run_id="compression_...", candidate_ids=["cmp_..."])
```

Broad compatibility routers use this same sequence. They start or reuse a run,
return polling instructions when the run is active, then read the profile,
candidate page, one selected candidate detail by default, and a small simulation
when a completed profile is available. Agents should not expand every candidate
detail unless the user asks for exhaustive evidence.

- `usage_compression_start(...)` returns immediately. It reuses an exact
  completed profile or identical active request and otherwise launches one
  daemon worker. `refresh=true` forces a new analysis; it does not rescan source
  logs.
- `usage_compression_status(run_id=...)` returns monotonic percent, stage,
  detector counts, records examined, candidate count, cache state, and exact
  next-poll arguments. A pending/running row not owned by the current MCP process
  reports `status="interrupted"` instead of pretending that work is progressing.
- `usage_compression_profile(...)` reads only a completed profile. Supplying no
  run ID looks up the current exact scope/detector cache; it never silently starts
  analysis.
- `usage_compression_candidates(...)` supports family, confidence, model,
  thread/session, time, exposure, savings, sort, limit, and offset filters.
  `limit=0` or `limit=null` requests the complete local result set, while the MCP
  response still honors its byte budget and returns `next_offset` when another
  page is required.
- `usage_compression_candidate_detail(...)` defaults to content-free evidence
  handles. `evidence_mode="summaries"` returns bounded claim summaries.
  `evidence_mode="excerpts"` is the explicit opt-in that may return raw local
  indexed text; `evidence_limit` and `max_excerpt_chars` remain bounded.
- `usage_compression_simulate(...)` recalculates overlap allocation for up to 50
  explicitly selected candidates. It returns deterministic portfolio totals, a
  bounded record/component calculation trace, and verification plans without
  persisting state or returning indexed content. Unknown or foreign candidates
  fail as one structured selection error. Stale runs return a structured error
  with refresh arguments that preserve the original scope and detector set.

The localhost dashboard routes `/api/compression/start`,
`/api/compression/status`, and `/api/compression/profile` use the same
application services and exact `codex-usage-tracker-compression-api-v1`
payloads. Browser navigation may stop polling, but it does not cancel the
persistent server worker.

All six tools use `codex-usage-tracker-compression-api-v1`. Common fields disclose run,
scope, versions, coverage, cache/timing state, warnings/caveats, pagination,
recommended next-tool arguments, `content_mode`, `includes_indexed_content`, and
`includes_raw_fragments`. Default status, profile, candidate-page, and detail
targets are 4 KiB, 8 KiB, 16 KiB, and 24 KiB respectively. Candidate pages never
embed claims or excerpts. Simulation responses target 16 KiB and trim trace or
verification rows before portfolio totals.

## Local Content And Raw Context

`usage_content_search(query=...)` searches the explicit local content index and can return indexed snippets. Use it only when the user asks for local content exploration, pattern hunting, or diagnostics that need transcript-level evidence. Its payload marks `content_mode="local_content_index"`, `includes_indexed_content=true`, and `includes_raw_fragments=true`.

`usage_thread_trace(...)` returns a paged call timeline for one thread/session/seed record and may include local indexed fragments. Treat it as an explicit local content-index surface, not a default shareable report.

`usage_call_context` is disabled by default in MCP server processes. Enable it explicitly only when the user asks to inspect raw local log context:

```bash
CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1
```

Normal aggregate tools do not need that variable. When raw context is enabled, `usage_call_context` accepts `max_entries`, `max_chars`, `include_tool_output`, and `include_compaction_history`. Use `0` limits only when the user explicitly asks for all matching entries or no character cap on local context.
