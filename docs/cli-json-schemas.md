# CLI, MCP, and Dashboard JSON Schemas

Codex Usage Tracker exposes JSON for automation through CLI `--json` flags, MCP tools, and the local dashboard server API. Default shareable payloads are aggregate-first and do not include prompts, assistant messages, tool output, or raw transcript snippets. `usage_content_search` is the explicit local content-index exception and marks that it can include indexed snippets.

## Companion Skill Usage

The installed `codex-usage-api` skill is the recommended conversational entrypoint when a user wants to discuss usage instead of manually choosing commands. It should refresh aggregate data first, prefer JSON MCP tools, and fall back to these CLI JSON surfaces when MCP tools are unavailable.

| Question | Preferred JSON surface |
| --- | --- |
| What used the most? | `most_expensive_usage_calls(response_format="json")`, then `usage_summary(group_by="thread", response_format="json")` |
| Which project, thread, or model is driving usage? | `usage_summary(group_by="project" \| "thread" \| "model", response_format="json")` |
| Why did usage spike? | `usage_query(...)` with `since`, `project`, `thread`, `model`, `effort`, `min_tokens`, or `min_credits` filters |
| What should I inspect next? | `usage_recommendations(response_format="json")` |
| What is estimated or unpriced? | `usage_pricing_coverage(response_format="json")`, `usage_query(pricing_status="unpriced")`, or `usage_query(credit_confidence="estimated")` |
| How does this affect my allowance? | `usage_query(...)` rows with `usage_credits`, `usage_credit_confidence`, and allowance annotations |
| What happened in one session? | `session_usage(session_id=..., response_format="json")` |

The skill should separate exact facts from estimates. Remaining allowance is not native account data; it is only copied local state from `~/.codex-usage-tracker/allowance.json` when configured.

Use the global `--privacy-mode redacted` or `--privacy-mode strict` option, or the MCP `privacy_mode` argument, when project metadata should be hidden from JSON answers. The CLI option goes before the subcommand.

## Contract Validation

Stable payload contracts are tracked in `codex_usage_tracker.json_contracts` and covered by tests. Every stable payload includes a top-level `schema` string so agents can distinguish compatible responses from markdown, disabled-context responses, or future versions.

Compatibility rules before 1.0:

- Additive fields are allowed when they do not change documented field types or privacy semantics.
- Removing a documented schema, removing a required field, changing a required field type, or changing privacy behavior requires either a new schema id or an explicit pre-1.0 migration note.
- After 1.0, breaking payload changes require a new schema id.
- Config-file schemas such as pricing, allowance, and rate-card JSON are tracked separately from runtime CLI/MCP/dashboard payload schemas.

Tracked schema ids:

| Schema | Surface |
| --- | --- |
| `codex-usage-tracker-setup-v1` | CLI `setup --json` |
| `codex-usage-tracker-doctor-v1` | CLI `doctor --json`, MCP `usage_doctor(response_format="json")` |
| | Includes an `environment` object with package and Python versions, important local paths, lightweight Codex log discovery counts, and packaged dashboard asset health. Support bundles sanitize this payload according to the selected privacy mode. |
| `codex-usage-tracker-plugin-install-v1` | CLI `install-plugin --json`, setup plugin payload |
| `codex-usage-tracker-plugin-upgrade-v1` | CLI `upgrade-plugin --json` |
| `codex-usage-tracker-plugin-uninstall-v1` | CLI `uninstall-plugin --json` |
| `codex-usage-tracker-refresh-v1` | CLI `refresh --json`, MCP `refresh_usage_index()` |
| `codex-usage-tracker-rebuild-index-v1` | CLI `rebuild-index --json` |
| `codex-usage-tracker-reset-db-v1` | CLI `reset-db --yes --json` |
| `codex-usage-tracker-summary-v1` | CLI `summary --json`, CLI `expensive --json`, MCP summary/expensive JSON |
| `codex-usage-tracker-query-v1` | CLI `query`, MCP `usage_query(...)` |
| `codex-usage-tracker-recommendations-v1` | CLI `recommendations --json`, MCP `usage_recommendations(response_format="json")`, MCP `usage_dashboard_recommendations(...)` |
| `codex-usage-tracker-action-brief-v1` | CLI `action-brief --json`, MCP `usage_action_brief(...)`; compact aggregate remediation brief |
| `codex-usage-tracker-async-job-status-v1` | MCP `usage_dogfood_start(...)`, `usage_dogfood_status(...)`; async in-process job progress/status payload |
| `codex-usage-tracker-allowance-history-v1` | CLI `allowance-history --json`, MCP `usage_allowance_history(...)`, dashboard server `/api/allowance/history` |
| `codex-usage-tracker-allowance-diagnostics-v1` | CLI `allowance-diagnostics --json`, MCP `usage_allowance_diagnostics(...)`, dashboard server `/api/allowance/diagnostics` |
| `codex-usage-tracker-allowance-evidence-export-v1` | CLI `allowance-export --json`, MCP `usage_allowance_export(...)`, dashboard server `/api/allowance/export` |
| `codex-usage-tracker-reports-pack-v1` | Dashboard server `/api/reports/pack` response, MCP `usage_report_pack(...)` |
| `codex-usage-tracker-diagnostics-v1` | CLI `diagnostics ... --json`, dashboard server `/api/diagnostics/*` |
| `codex-usage-tracker-diagnostic-overview-v1` | CLI `diagnostics overview --json`, dashboard server `/api/diagnostics/overview` |
| `codex-usage-tracker-diagnostic-tool-output-v1` | CLI `diagnostics tool-output --json`, dashboard server `/api/diagnostics/tool-output` |
| `codex-usage-tracker-diagnostic-commands-v1` | CLI `diagnostics commands --json`, dashboard server `/api/diagnostics/commands` |
| `codex-usage-tracker-diagnostic-git-interactions-v1` | CLI `diagnostics git-interactions --json`, dashboard server `/api/diagnostics/git-interactions` |
| `codex-usage-tracker-diagnostic-file-reads-v1` | CLI `diagnostics file-reads --json`, dashboard server `/api/diagnostics/file-reads` |
| `codex-usage-tracker-diagnostic-file-modifications-v1` | CLI `diagnostics file-modifications --json`, dashboard server `/api/diagnostics/file-modifications` |
| `codex-usage-tracker-diagnostic-read-productivity-v1` | CLI `diagnostics read-productivity --json`, dashboard server `/api/diagnostics/read-productivity` |
| `codex-usage-tracker-diagnostic-concentration-v1` | CLI `diagnostics concentration --json`, dashboard server `/api/diagnostics/concentration` |
| `codex-usage-tracker-diagnostic-guided-summary-v1` | CLI `diagnostics guided-summary --json`, dashboard server `/api/diagnostics/guided-summary` |
| `codex-usage-tracker-diagnostic-usage-drain-v1` | CLI `diagnostics usage-drain --json`, dashboard server `/api/diagnostics/usage-drain` |
| `codex-usage-tracker-session-v1` | CLI `session --json`, MCP `session_usage(response_format="json")` |
| `codex-usage-tracker-context-v1` | CLI `context`, MCP `usage_call_context` when raw context is explicitly enabled |
| `codex-usage-tracker-context-disabled-v1` | MCP `usage_call_context` when raw context is disabled |
| `codex-usage-tracker-context-settings-v1` | Dashboard server `/api/context-settings` response |
| `codex-usage-tracker-open-investigator-v1` | Dashboard server `/api/open-investigator` response |
| `codex-usage-tracker-live-api-v1` | Dashboard server live API payload family marker |
| `codex-usage-tracker-status-v1` | Dashboard server `/api/status` response, MCP `usage_status()` |
| `codex-usage-tracker-calls-v1` | Dashboard server `/api/calls` response, MCP `usage_calls(...)` |
| `codex-usage-tracker-call-v1` | Dashboard server `/api/call` response, MCP `usage_call_detail(record_id=...)` |
| `codex-usage-tracker-threads-v1` | Dashboard server `/api/threads` response, MCP `usage_threads(...)` |
| `codex-usage-tracker-thread-calls-v1` | Dashboard server `/api/thread-calls` response |
| `codex-usage-tracker-dashboard-v1` | CLI `dashboard --json`, MCP `generate_usage_dashboard()` |
| `codex-usage-tracker-open-dashboard-v1` | CLI `open-dashboard --json` |
| `codex-usage-tracker-serve-dashboard-v1` | CLI `serve-dashboard --json` startup payload, including preferred React `dashboard_url` and legacy `legacy_dashboard_url` fallback |
| `codex-usage-tracker-pricing-coverage-v1` | CLI `pricing-coverage --json`, MCP `usage_pricing_coverage(response_format="json")` |
| `codex-usage-tracker-source-coverage-v1` | CLI `source-coverage --json`, MCP `usage_source_coverage(response_format="json")` |
| `codex-usage-tracker-content-search-v1` | MCP `usage_content_search(...)`; explicit local content-index search, may include indexed snippets |
| `codex-usage-tracker-thread-trace-v1` | MCP `usage_thread_trace(...)`; explicit local content-index thread/session timeline |
| `codex-usage-tracker-pattern-scan-v1` | MCP `usage_repetition_scan(...)`, `usage_command_loop_scan(...)`, `usage_file_churn_scan(...)`, `usage_context_bloat_scan(...)`; explicit local content/event-index pattern diagnostics |
| `codex-usage-tracker-repeated-file-rediscovery-v1` | MCP `usage_repeated_file_rediscovery(...)`; repeated safe file identity rediscovery candidates without full paths |
| `codex-usage-tracker-shell-churn-v1` | MCP `usage_shell_churn(...)`; repeated shell command family diagnostics without raw command output |
| `codex-usage-tracker-large-low-output-v1` | MCP `usage_large_low_output_calls(...)`; high-token low-output call candidates without raw fragments |
| `codex-usage-tracker-investigation-suggestions-v1` | MCP `usage_suggest_investigations(...)`; goal-led usage investigation suggestions for agents |
| `codex-usage-tracker-agentic-investigation-v1` | MCP `usage_investigate(...)`; goal-led aggregate investigation findings and next tools |
| `codex-usage-tracker-hypothesis-test-v1` | MCP `usage_test_hypotheses(...)`; explicit true/false/partial/insufficient hypothesis tests |
| `codex-usage-tracker-investigation-walk-v1` | MCP `usage_investigation_walk(question=...)`; bounded local hypothesis walk over normalized pattern evidence |
| `codex-usage-tracker-local-evidence-export-v1` | MCP `usage_local_evidence_export(question=...)`; strict shareable local evidence summary without raw/indexed content |
| `codex-usage-tracker-export-v1` | CLI `export --json`, MCP `export_usage_csv(...)` |
| `codex-usage-tracker-init-pricing-v1` | CLI `init-pricing --json`, MCP `init_usage_pricing_config()` |
| `codex-usage-tracker-update-pricing-v1` | CLI `update-pricing --json`, MCP `update_usage_pricing_config()` |
| `codex-usage-tracker-pin-pricing-v1` | CLI `pin-pricing --json` |
| `codex-usage-tracker-init-allowance-v1` | CLI `init-allowance --json`, MCP `init_usage_allowance_config()` |
| `codex-usage-tracker-parse-allowance-v1` | CLI `parse-allowance --json` |
| `codex-usage-tracker-update-rate-card-v1` | CLI `update-rate-card --json` |
| `codex-usage-tracker-init-thresholds-v1` | CLI `init-thresholds --json` |
| `codex-usage-tracker-init-projects-v1` | CLI `init-projects --json` |
| `codex-usage-tracker-support-bundle-v1` | CLI `support-bundle --json` |

## Shared Error Codes

CLI failures print a stable code in stderr:

```text
Error: [invalid_value] reset-db clears local aggregate usage rows. Re-run with --yes to confirm.
```

Known codes are `invalid_value`, `file_exists`, `file_not_found`, `permission_denied`, `runtime_error`, and `os_error`.

## Summary

Commands:

```bash
codex-usage-tracker summary --group-by model --json
codex-usage-tracker expensive --limit 10 --json
```

MCP:

- `usage_summary(response_format="json")`
- `most_expensive_usage_calls(response_format="json")`

Schema: `codex-usage-tracker-summary-v1`

```json
{
  "schema": "codex-usage-tracker-summary-v1",
  "group_by": "model",
  "is_expensive": false,
  "privacy_mode": "normal",
  "row_count": 1,
  "rows": []
}
```

`rows` contains aggregate summary rows for `summary` and aggregate per-call rows for `expensive`.

## Query

Command:

```bash
codex-usage-tracker query --since 2026-06-01 --project codex-usage-tracker --min-credits 1
```

MCP:

- `usage_query(...)`

Schema: `codex-usage-tracker-query-v1`

```json
{
  "schema": "codex-usage-tracker-query-v1",
  "filters": {
    "since": "2026-06-01",
    "until": null,
    "model": null,
    "effort": null,
    "thread": null,
    "project": "codex-usage-tracker",
    "pricing_status": null,
    "credit_confidence": null,
    "min_tokens": null,
    "min_credits": 1.0,
    "limit": 100,
    "privacy_mode": "normal"
  },
  "row_count": 1,
  "total_matched_rows": 1,
  "truncated": false,
  "rows": []
}
```

Supported filters:

- `since`, `until`
- `project`, `model`, `effort`, `thread`
- `pricing_status`: `priced`, `estimated`, `unpriced`
- `credit_confidence`: `exact`, `estimated`, `unpriced`, `user_override`
- `min_tokens`, `min_credits`
- `limit`; use `0` for all matched rows
- `privacy_mode`: `normal`, `redacted`, or `strict`

Privacy mode affects returned metadata after matching rows. `redacted` hides raw cwd/source paths, hides Git remote labels, and hashes unnamed project names. `strict` also hides project-relative cwd, Git branch, and tags. Configured project aliases are treated as explicit display opt-ins.

Per-call rows include derived timing fields when returned through dashboard/live call APIs: `call_started_at`, `call_duration_seconds`, `previous_call_event_timestamp`, and `previous_call_delta_seconds`. These values are derived from aggregate timestamps and thread adjacency; they do not read or store transcript content.

## Recommendations

Command:

```bash
codex-usage-tracker recommendations --since 2026-06-01 --limit 10 --json
```

MCP:

- `usage_recommendations(response_format="json")`

Schema: `codex-usage-tracker-recommendations-v1`

```json
{
  "schema": "codex-usage-tracker-recommendations-v1",
  "filters": {
    "since": "2026-06-01",
    "until": null,
    "model": null,
    "effort": null,
    "thread": null,
    "project": null,
    "include_archived": false,
    "min_score": null,
    "limit": 10,
    "privacy_mode": "normal"
  },
  "row_count": 1,
  "total_matched_rows": 1,
  "truncated": false,
  "threads": [],
  "rows": []
}
```

Rows include `recommendation_score`, `primary_recommendation`, `secondary_recommendations`, `primary_signal`, `secondary_signals`, `recommended_action`, and `flag_explanations`. Thread rollups summarize the highest-priority threads using the same aggregate-only signals.

## Action Brief Command

```bash
codex-usage-tracker action-brief --goal token_waste --evidence-limit 5 --json
```

MCP:

- `usage_action_brief(...)`

Schema: `codex-usage-tracker-action-brief-v1`

```json
{
  "schema": "codex-usage-tracker-action-brief-v1",
  "content_mode": "aggregate_action_brief",
  "includes_indexed_content": false,
  "includes_raw_fragments": false,
  "privacy_mode": "normal",
  "goal": "token_waste",
  "filters": { "since": null, "until": null, "thread": null, "include_archived": false, "evidence_limit": 5 },
  "summary": { "action_count": 1, "top_action_family": "large_low_output_context_pressure", "source_reports": [] },
  "actions": [],
  "recommended_next_tools": [],
  "caveats": []
}
```

Actions translate aggregate diagnostics into concrete workflow changes. Each action includes `finding`, `confidence`, compact `evidence`, `likely_waste_pattern`, `recommended_workflow_change`, `recommended_existing_tool`, `recommended_custom_solution`, `how_to_verify`, and `recommended_next_tools`. The default payload is shareable aggregate evidence and does not include prompts, assistant messages, raw command output, full paths, or indexed fragments.

## Allowance Intelligence

Commands:

```bash
codex-usage-tracker allowance-history --window-kind weekly --json
codex-usage-tracker allowance-diagnostics --window-kind weekly --json
codex-usage-tracker allowance-export --output /tmp/codex-allowance-evidence.json
```

MCP:

- `usage_allowance_history(...)`
- `usage_allowance_diagnostics(...)`
- `usage_allowance_export(...)`

Server API:

- `/api/allowance/history`
- `/api/allowance/diagnostics`
- `/api/allowance/export`

Schemas:

- `codex-usage-tracker-allowance-history-v1`
- `codex-usage-tracker-allowance-diagnostics-v1`
- `codex-usage-tracker-allowance-evidence-export-v1`

Allowance intelligence normalizes observed 5-hour and weekly usage snapshots from aggregate token-count rows. Diagnostics compare visible usage movement with locally estimated Codex credits and grade the evidence. Weekly windows are the primary signal; 5-hour windows are treated as noisy rolling counters. Weekly change candidates include `nonparametric-v1` statistical evidence and a stricter `summary.research_readiness.ready_for_public_claim` flag. Strict export omits prompts, assistant text, tool output, file paths, thread names, session IDs, and record IDs.

HTTP report endpoints accept `limit=all`, `limit=0`, `limit=none`, and `limit=null` as all rows up to the endpoint safety cap.

```json
{
  "schema": "codex-usage-tracker-allowance-diagnostics-v1",
  "generated_at": "2026-06-01T00:00:00+00:00",
  "privacy_mode": "strict",
  "include_archived": false,
  "window_kind": "weekly",
  "summary": {
    "observation_count": 4,
    "primary_evidence_grade": "possible_regime_change",
    "research_readiness": {
      "detector_version": "nonparametric-v1",
      "ready_for_public_claim": false,
      "weekly_positive_span_count": 3,
      "minimum_split_spans_for_public_claim": 6
    }
  },
  "windows": [],
  "spans": [],
  "change_candidates": [
    {
      "evidence_grade": "possible_regime_change",
      "capacity_ratio": 0.72,
      "outside_usage_possible": true,
      "statistical_evidence": {
        "detector_version": "nonparametric-v1",
        "method": "exact_permutation_mean_shift",
        "effect_size_cliffs_delta": -0.67,
        "p_value_one_sided": 0.18,
        "signal": "directional_effect_limited",
        "public_claim_ready": false
      }
    }
  ],
  "notes": []
}
```

## Session

Command:

```bash
codex-usage-tracker session <session-id> --json
```

MCP:

- `session_usage(response_format="json")`

Schema: `codex-usage-tracker-session-v1`

```json
{
  "schema": "codex-usage-tracker-session-v1",
  "requested_session_id": "019e374d-c19f-7da3-a44f-8de043a7a64e",
  "resolved_session_id": "019e374d-c19f-7da3-a44f-8de043a7a64e",
  "limit": 200,
  "privacy_mode": "normal",
  "row_count": 2,
  "rows": []
}
```

## Diagnostics

Commands:

```bash
codex-usage-tracker diagnostics summary --json
codex-usage-tracker diagnostics facts --sort uncached --json
codex-usage-tracker diagnostics fact-calls --fact-type compaction --fact-name post_compaction --json
```

Dashboard server API:

- `/api/diagnostics/summary`
- `/api/diagnostics/facts`
- `/api/diagnostics/fact-calls?fact_type=compaction&fact_name=post_compaction`
- `/api/diagnostics/compactions`
- `/api/diagnostics/tools`

Schema: `codex-usage-tracker-diagnostics-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostics-v1",
  "view": "facts",
  "filters": {
    "since": null,
    "until": null,
    "model": null,
    "effort": null,
    "thread": null,
    "min_tokens": null,
    "fact_type": null,
    "fact_name": null,
    "fact_category": null,
    "fact_group": null,
    "include_archived": false,
    "sort": "uncached",
    "direction": "desc",
    "limit": 50,
    "offset": 0,
    "privacy_mode": "normal"
  },
  "row_count": 1,
  "total_matched_rows": 1,
  "truncated": false,
  "raw_context_included": false,
  "rows": [],
  "notes": [
    "Associated token totals are not additive when one call has multiple diagnostic facts."
  ]
}
```

Diagnostics payloads report aggregate structured facts such as compaction, tool/function/MCP activity, command families, structured skill labels, search/read loops, and outcome events. They do not include prompts, assistant messages, tool arguments, tool output, patch text, raw commands, command arguments, file contents, or JSONL fragments. Token totals are associated with facts observed before a token-count row; they are not causal allocations.

Diagnostic snapshots use separate section endpoints instead of one large read payload. `GET` returns the latest stored section snapshot or `status: "missing"`; `POST /api/diagnostics/<section>/refresh` recomputes and replaces only that section. The dashboard button calls `POST /api/diagnostics/refresh`, which returns a small wrapper with `sections` and recomputes source-log-derived sections with one shared analyzer pass. This keeps ordinary dashboard refresh fast and prevents source-log rescans unless a diagnostics refresh is explicit.

## Diagnostic Overview Snapshot

Commands:

```bash
codex-usage-tracker diagnostics overview --json
codex-usage-tracker diagnostics overview --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/overview`
- `POST /api/diagnostics/overview/refresh`

Schema: `codex-usage-tracker-diagnostic-overview-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-overview-v1",
  "section": "overview",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {
    "computed_at": "2026-06-20T18:00:00+00:00",
    "history_scope": "active",
    "source_logs_scanned": 3,
    "usage_rows_scanned": 10,
    "raw_content_included": false
  },
  "overview": {
    "usage_rows": 10,
    "total_tokens": 12345,
    "cached_input_tokens": 9000,
    "uncached_input_tokens": 2000,
    "cache_ratio": 0.75
  },
  "notes": []
}
```

The overview snapshot is recomputed only when explicitly refreshed. Ordinary dashboard usage refreshes do not update diagnostic snapshots.

## Diagnostic Tool Output Snapshot

Commands:

```bash
codex-usage-tracker diagnostics tool-output --json
codex-usage-tracker diagnostics tool-output --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/tool-output`
- `POST /api/diagnostics/tool-output/refresh`

Schema: `codex-usage-tracker-diagnostic-tool-output-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-tool-output-v1",
  "section": "tool-output",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "function_calls": 1,
    "function_outputs": 1,
    "outputs_with_original_token_count": 1,
    "outputs_missing_original_token_count": 0,
    "original_token_sum": 42
  },
  "functions": [],
  "command_roots": [],
  "missing_reasons": [],
  "notes": []
}
```

The tool-output snapshot stores function names, conservative command roots, numeric counts, and terminal `Original token count` totals. It does not store raw tool output or command text.

## Diagnostic Commands Snapshot

Commands:

```bash
codex-usage-tracker diagnostics commands --json
codex-usage-tracker diagnostics commands --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/commands`
- `POST /api/diagnostics/commands/refresh`

Schema: `codex-usage-tracker-diagnostic-commands-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-commands-v1",
  "section": "commands",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "shell_function_calls": 1,
    "command_root_count": 1,
    "missing_command": 0
  },
  "commands": [
    {
      "root": "git",
      "total": 1,
      "children": [{"child": "status", "count": 1}]
    }
  ],
  "notes": []
}
```

The commands snapshot keeps only command roots and a bounded list of safe one-level child labels such as `status`, `diff`, or `-m:pytest`.

## Diagnostic Git Interactions Snapshot

Commands:

```bash
codex-usage-tracker diagnostics git-interactions --json
codex-usage-tracker diagnostics git-interactions --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/git-interactions`
- `POST /api/diagnostics/git-interactions/refresh`

Schema: `codex-usage-tracker-diagnostic-git-interactions-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-git-interactions-v1",
  "section": "git-interactions",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "git_shell_calls": 2,
    "git_command_calls": 1,
    "github_cli_calls": 1,
    "unique_interactions": 2,
    "interactions_with_original_token_count": 2,
    "interactions_missing_original_token_count": 0,
    "original_token_sum": 55
  },
  "interactions": [
    {
      "root": "git",
      "operation": "status",
      "category": "read_only",
      "mutability": "read_only",
      "calls": 1,
      "with_original_token_count": 1,
      "missing_original_token_count": 0,
      "original_token_sum": 42
    }
  ],
  "categories": [{"category": "read_only", "count": 1}],
  "mutability": [{"mutability": "read_only", "count": 1}],
  "notes": []
}
```

The Git interactions snapshot is a specialized view of shell commands. It persists only `git`/`gh` root labels, safe operation labels, coarse categories, counts, and token coverage. It does not persist raw command strings, branch names, remotes, file paths, tags, commit messages, PR titles, release notes, or raw command output.

## Diagnostic File Reads Snapshot

Commands:

```bash
codex-usage-tracker diagnostics file-reads --json
codex-usage-tracker diagnostics file-reads --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/file-reads`
- `POST /api/diagnostics/file-reads/refresh`

Schema: `codex-usage-tracker-diagnostic-file-reads-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-file-reads-v1",
  "section": "file-reads",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "read_commands": 1,
    "read_events": 1,
    "unique_paths_read": 1,
    "read_events_with_output_count": 1,
    "read_events_missing_output_count": 0,
    "allocated_output_token_sum": 42
  },
  "by_reader": [],
  "top_paths": [],
  "largest_read_commands": [],
  "path_privacy": {},
  "notes": []
}
```

The file-reads snapshot classifies common shell readers such as `cat`, `sed`, `nl`, `rg`, and `find`. Path labels are basename-only with a short irreversible hash; raw commands, command arguments, absolute paths, file contents, and tool output are not stored.

## Diagnostic File Modifications Snapshot

Commands:

```bash
codex-usage-tracker diagnostics file-modifications --json
codex-usage-tracker diagnostics file-modifications --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/file-modifications`
- `POST /api/diagnostics/file-modifications/refresh`

Schema: `codex-usage-tracker-diagnostic-file-modifications-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-file-modifications-v1",
  "section": "file-modifications",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "modification_events": 2,
    "modified_path_events": 3,
    "unique_paths_modified": 2,
    "largest_event_path_count": 2
  },
  "top_paths": [],
  "by_extension": [],
  "largest_events": [],
  "path_privacy": {},
  "notes": []
}
```

The file-modifications snapshot counts structured patch events and modified paths. Path labels are basename-only with short irreversible hashes; patch text, raw absolute paths, file contents, raw commands, tool output, and JSONL fragments are not stored.

## Diagnostic Read Productivity Snapshot

Commands:

```bash
codex-usage-tracker diagnostics read-productivity --json
codex-usage-tracker diagnostics read-productivity --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/read-productivity`
- `POST /api/diagnostics/read-productivity/refresh`

Schema: `codex-usage-tracker-diagnostic-read-productivity-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-read-productivity-v1",
  "section": "read-productivity",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "read_events": 1,
    "read_events_modified_later": 1,
    "read_events_modified_later_pct": 1.0,
    "unique_paths_read": 1,
    "unique_paths_modified_later": 1,
    "unique_path_modified_later_pct": 1.0,
    "correlation_note": "Read-to-modify counts are temporal correlations."
  },
  "by_reader": [],
  "top_modified_paths": [],
  "path_privacy": {},
  "notes": []
}
```

Read productivity is a temporal correlation, not causation. A read is counted as modified later only when the same privacy-preserving path key appears in a later structured patch event in the same source log.

## Diagnostic Concentration Snapshot

Commands:

```bash
codex-usage-tracker diagnostics concentration --json
codex-usage-tracker diagnostics concentration --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/concentration`
- `POST /api/diagnostics/concentration/refresh`

Schema: `codex-usage-tracker-diagnostic-concentration-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-concentration-v1",
  "section": "concentration",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "usage_rows": 4,
    "total_tokens": 100,
    "dimension_count": 3,
    "history_scope": "active"
  },
  "metrics": [
    {"metric": "top_1_source_log_share", "dimension": "source_log", "top_n": 1, "share": 0.5}
  ],
  "dimensions": [],
  "largest_impact_rows": [],
  "privacy": {},
  "notes": []
}
```

The concentration snapshot computes top-1/top-3/top-5 share and effective group count by source log/session, cwd/project label, and day. Metric ids such as `top_1_source_log_share` are stable JSON contract fields; dashboard views should render them as reader-facing labels. Source log labels use session-id prefixes or source hashes, cwd labels use basename-only labels, and raw source paths/cwd paths are not included.

## Diagnostic Usage Drain Snapshot

Commands:

```bash
codex-usage-tracker diagnostics usage-drain --json
codex-usage-tracker diagnostics usage-drain --refresh --json
```

Dashboard server API:

- `GET /api/diagnostics/usage-drain`
- `POST /api/diagnostics/usage-drain/refresh`

Schema: `codex-usage-tracker-diagnostic-usage-drain-v1`

```json
{
  "schema": "codex-usage-tracker-diagnostic-usage-drain-v1",
  "section": "usage-drain",
  "status": "ready",
  "refreshed": false,
  "raw_context_included": false,
  "snapshot": {},
  "summary": {
    "usage_rows": 4,
    "thread_count": 2,
    "positive_usage_spans": 3,
    "estimated_cost_usd": 0.42,
    "usage_credits": 120.0,
    "top_thread_cost_share": 0.6,
    "best_predictive_model": "previous_delta"
  },
  "thread_cost_curves": {
    "total_threads": 2,
    "shown_threads": 2,
    "max_points_per_thread": 120,
    "estimated_cost_usd": 0.42,
    "top_thread_share": 0.6,
    "threads": [
      {
        "thread_key": "thread:alpha",
        "thread": "Alpha",
        "call_count": 3,
        "estimated_cost_usd": 0.25,
        "avg_cost_usd": 0.083333,
        "shape": "near-linear",
        "points": [
          {"call_index": 1, "cumulative_cost_usd": 0.1},
          {"call_index": 3, "cumulative_cost_usd": 0.25}
        ]
      }
    ]
  },
  "time_series": {
    "visible_usage": {
      "unit": "visible_used_percent",
      "series": ["five_hour_used_percent", "weekly_used_percent"],
      "points": [
        {
          "timestamp": "2026-06-01T00:00:00Z",
          "five_hour_used_percent": 10.0,
          "weekly_used_percent": 20.0
        }
      ]
    },
    "weekly_credit_projection": {
      "unit": "projected_standard_usage_credits_per_full_week",
      "window_minutes": 10080,
      "points": [
        {
          "label": "Reset Jun 08",
          "observed_usage_delta_percent": 30.0,
          "observed_standard_usage_credits": 15000.0,
          "projected_weekly_credits": 50000.0,
          "ci_low": 47000.0,
          "ci_high": 53000.0,
          "confidence": "medium"
        }
      ]
    }
  },
  "model_highlights": {},
  "pricing": {},
  "notes": []
}
```

The usage-drain snapshot is an on-demand, aggregate-only research report. It uses indexed usage rows, estimated costs, Codex credit-rate annotations, visible usage counter spans, and compact model highlights. The dashboard renders thread names for the cumulative cost chart because this is local runtime metadata, not a shared support bundle. It still excludes prompts, assistant text, tool outputs, command text, raw JSONL paths, and patch text.

## Pricing Coverage

Command:

```bash
codex-usage-tracker pricing-coverage --json
```

MCP:

- `usage_pricing_coverage(response_format="json")`

Schema: `codex-usage-tracker-pricing-coverage-v1`

```json
{
  "schema": "codex-usage-tracker-pricing-coverage-v1",
  "model_count": 1,
  "priced_model_count": 1,
  "unpriced_model_count": 0,
  "total_tokens": 1000,
  "priced_tokens": 1000,
  "unpriced_tokens": 0,
  "estimated_cost_usd": 0.01,
  "priced_token_ratio": 1.0,
  "pricing_loaded": true,
  "pricing_path": "~/.codex-usage-tracker/pricing.json",
  "pricing_source": null,
  "rows": []
}
```

## Source Coverage

Command:

```bash
codex-usage-tracker source-coverage --json
```

MCP:

- `usage_source_coverage(response_format="json")`

Schema: `codex-usage-tracker-source-coverage-v1`

```json
{
  "schema": "codex-usage-tracker-source-coverage-v1",
  "content_mode": "aggregate_only",
  "includes_indexed_content": false,
  "includes_raw_fragments": false,
  "include_archived": false,
  "source_record_count": 2,
  "source_file_count": 2,
  "parser_version_count": 1,
  "warning_record_count": 0,
  "rows": [
    {
      "raw_shape_label": "token_count",
      "parser_adapter": "codex-jsonl",
      "parser_version": "codex-jsonl-v2",
      "record_count": 2,
      "source_file_count": 2,
      "warning_record_count": 0
    }
  ]
}
```

## Content Search

MCP:

- `usage_content_search(query="token waste")`

Schema: `codex-usage-tracker-content-search-v1`

This is an explicit local content-index investigation surface. It can include indexed snippets from local Codex logs, so do not treat it as a default shareable aggregate report.

```json
{
  "schema": "codex-usage-tracker-content-search-v1",
  "content_mode": "local_content_index",
  "includes_indexed_content": true,
  "includes_raw_fragments": true,
  "privacy_mode": "normal",
  "query": "token waste",
  "filters": {
    "since": null,
    "until": null,
    "model": null,
    "effort": null,
    "thread": null,
    "include_archived": false,
    "limit": 20,
    "offset": 0,
    "max_snippet_chars": 800
  },
  "search_mode": "fts5",
  "row_count": 0,
  "total_matched_rows": 0,
  "truncated": false,
  "has_more": false,
  "next_offset": null,
  "rows": []
}
```

## Thread Trace

MCP:

- `usage_thread_trace(thread="Add Codex token tracking")`
- `usage_thread_trace(session_id="...")`
- `usage_thread_trace(record_id="...")`

Schema: `codex-usage-tracker-thread-trace-v1`

This is an explicit local content-index investigation surface. It returns aggregate call metadata plus indexed fragments for a selected thread/session scope.

```json
{
  "schema": "codex-usage-tracker-thread-trace-v1",
  "content_mode": "local_content_index",
  "includes_indexed_content": true,
  "includes_raw_fragments": true,
  "privacy_mode": "normal",
  "filters": {
    "thread": "Add Codex token tracking",
    "thread_key": null,
    "session_id": null,
    "record_id": null,
    "since": null,
    "until": null,
    "include_archived": false,
    "limit": 100,
    "offset": 0,
    "max_snippet_chars": 800
  },
  "call_count": 0,
  "total_matched_calls": 0,
  "truncated": false,
  "has_more": false,
  "next_offset": null,
  "calls": []
}
```

## Pattern Scan

MCP:

- `usage_repetition_scan(min_occurrences=2)`
- `usage_command_loop_scan(min_occurrences=2)`
- `usage_file_churn_scan(min_occurrences=2)`
- `usage_context_bloat_scan(min_occurrences=2)`

Schema: `codex-usage-tracker-pattern-scan-v1`

This explicit local content/event-index diagnostic surface scans normalized fragment hashes, command roots, file hashes/basenames, and aggregate token rows. It does not include raw fragments.

```json
{"schema":"codex-usage-tracker-pattern-scan-v1","content_mode":"local_content_index","includes_indexed_content":true,"includes_raw_fragments":false,"privacy_mode":"normal","scan_type":"command_loop","scan_types":["command_loop"],"filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_occurrences":2,"limit":20},"pattern_count":0,"total_patterns":0,"patterns":[]}
```

## Repeated File Rediscovery

MCP:

- `usage_repeated_file_rediscovery(min_occurrences=2)`

Schema: `codex-usage-tracker-repeated-file-rediscovery-v1`

Ranks repeated safe file identities by path hash/identity, basename, extension, operation mix, adjacent retouches, aggregate token totals, and `usage_thread_trace` handles. It omits full paths and raw fragments.

```json
{"schema":"codex-usage-tracker-repeated-file-rediscovery-v1","content_mode":"local_content_index","includes_indexed_content":true,"includes_raw_fragments":false,"privacy_mode":"normal","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_occurrences":2,"limit":20,"sample_limit":3},"row_count":0,"total_candidates":0,"rows":[]}
```

## Shell Churn

MCP:

- `usage_shell_churn(min_occurrences=3)`

Schema: `codex-usage-tracker-shell-churn-v1`

Ranks repeated shell command roots and bounded command labels by failures, adjacent repeats, output bytes, aggregate token totals, and `usage_thread_trace` handles. It omits raw command output.

```json
{"schema":"codex-usage-tracker-shell-churn-v1","content_mode":"local_content_index","includes_indexed_content":true,"includes_raw_fragments":false,"privacy_mode":"normal","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_occurrences":3,"limit":20,"sample_limit":3},"row_count":0,"total_candidates":0,"rows":[]}
```

## Large Low-Output Calls

MCP:

- `usage_large_low_output_calls(min_total_tokens=20000,max_output_tokens=1000)`

Schema: `codex-usage-tracker-large-low-output-v1`

Ranks high-token calls that produced little output, including token totals, cache ratio, context-window percent, nearby activity counts, candidate explanations, and `usage_thread_trace` handles. It omits raw fragments, command output, and full file paths.

```json
{"schema":"codex-usage-tracker-large-low-output-v1","content_mode":"aggregate_with_local_activity","includes_indexed_content":false,"includes_raw_fragments":false,"privacy_mode":"normal","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_total_tokens":20000,"max_output_tokens":1000,"limit":20},"row_count":0,"total_candidates":0,"rows":[]}
```

## Investigation Suggestions

MCP:

- `usage_suggest_investigations(goal="token_waste", limit=2)`

Schema: `codex-usage-tracker-investigation-suggestions-v1`

Returns a short menu of goal-led investigations an agent can run, including the primary MCP tool, default arguments, follow-up tools, and privacy notes. Goal-specific requests include adjacent useful investigations so agents can keep exploring without guessing the next tool. It does not include raw/indexed content.

```json
{"schema":"codex-usage-tracker-investigation-suggestions-v1","content_mode":"aggregate_guidance","includes_indexed_content":false,"includes_raw_fragments":false,"privacy_mode":"normal","goal":"token_waste","available_goals":["overview","token_waste","allowance_change","cache_failure","workflow_churn"],"filters":{"since":null,"until":null,"thread":null,"include_archived":false,"limit":2},"summary":{"suggestion_count":2,"total_suggestions":4,"top_goal":"token_waste"},"suggestions":[{"goal":"token_waste","label":"Find obvious token-waste candidates","primary_tool":"usage_investigate","default_arguments":{"goal":"token_waste","evidence_limit":5},"follow_up_tools":["usage_large_low_output_calls","usage_shell_churn"],"privacy_notes":"Aggregate-first; no raw prompts, tool output, or full paths."},{"goal":"cache_failure","label":"Diagnose cache and context waste","primary_tool":"usage_investigate","default_arguments":{"goal":"cache_failure","evidence_limit":5},"follow_up_tools":["usage_large_low_output_calls","usage_calls","usage_report_pack"],"privacy_notes":"Aggregate-first; no raw prompt or transcript text."}]}
```

## Agentic Investigation

MCP:

- `usage_investigate(goal="token_waste")`

Schema: `codex-usage-tracker-agentic-investigation-v1`

Runs a goal-led aggregate investigation over existing tracker reports and returns normalized findings with compact evidence, evidence summaries, confidence, why it matters, missing-access notes, recommended action, verification tools, privacy notes, and caveats. `detail_mode="compact"` is the default. Use `detail_mode="full"` only when the full underlying diagnostic rows are needed.

```json
{"schema":"codex-usage-tracker-agentic-investigation-v1","content_mode":"aggregate_investigation","includes_indexed_content":false,"includes_raw_fragments":false,"privacy_mode":"normal","goal":"token_waste","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"evidence_limit":5,"detail_mode":"compact"},"summary":{"finding_count":1,"top_finding":"No strong local signal at default thresholds","confidence":"insufficient_local_evidence","source_reports":[]},"findings":[{"finding":"No strong local signal at default thresholds","evidence_count":0,"evidence_summary":{"row_count":0},"evidence":[],"confidence":"insufficient_local_evidence","recommended_action":"Lower thresholds, widen the time window, include archived sessions, or inspect top aggregate calls.","verify_with":["usage_calls","usage_report_pack"],"missing_access":"No supported aggregate signal was found at the selected thresholds.","privacy_notes":"No raw context needed for this follow-up."}],"recommended_next_tools":[],"caveats":["Local Codex logs only; this is not an official OpenAI usage ledger."]}
```

## Hypothesis Test

MCP:

- `usage_test_hypotheses(question="Look for actionable token waste", hypotheses=["Token waste is concentrated in large low-output calls."], evidence_limit=2)`

Schema: `codex-usage-tracker-hypothesis-test-v1`

Tests supplied hypotheses, or built-in defaults when none are supplied, against aggregate and local-index diagnostics. Each result includes `status` (`true`, `false`, `partially_true`, or `insufficient_evidence`), confidence, the "I would like / I will use / I'm missing" investigation framing, compact evidence, counter-evidence, and next tools. It does not include raw fragments.

```json
{"schema":"codex-usage-tracker-hypothesis-test-v1","content_mode":"aggregate_with_local_index_signals","includes_indexed_content":true,"includes_raw_fragments":false,"privacy_mode":"normal","question":"Look for actionable token waste","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"evidence_limit":2},"summary":{"hypothesis_count":1,"status_counts":{"true":1},"top_status":"true"},"hypotheses":[{"id":"hypothesis-1","hypothesis":"Token waste is concentrated in large low-output calls.","family":"token_waste","status":"true","confidence":"medium","i_would_like_to_be_able_to":"Find obvious token-waste candidates without reading raw conversations.","i_will_accomplish_this_using":"Rank large low-output calls and aggregate recommendation rows.","i_am_missing_access_to":"Whether each expensive call produced valuable work or was intentionally exploratory.","evidence_summary":{"row_count":2,"large_low_output_candidate_count":2},"evidence":[],"counter_evidence":[],"next_action":"Inspect the largest low-output rows, then verify whether a shorter handoff or smaller context would have avoided them.","recommended_next_tools":[{"tool":"usage_large_low_output_calls","reason":"Inspect the highest-token low-output calls.","default_arguments":{}}]}],"recommended_next_tools":[{"tool":"usage_large_low_output_calls","reason":"Inspect the highest-token low-output calls.","default_arguments":{}}],"caveats":["Local Codex logs only; this is not an official OpenAI usage ledger."]}
```

## Investigation Walk

MCP:

- `usage_investigation_walk(question="look for token waste")`

Schema: `codex-usage-tracker-investigation-walk-v1`

Runs a bounded local hypothesis walk over normalized pattern scans, ranks candidate branches, prunes branches without evidence, and returns recommended next MCP tools. Does not include raw fragments.

```json
{"schema":"codex-usage-tracker-investigation-walk-v1","content_mode":"local_content_index","includes_indexed_content":true,"includes_raw_fragments":false,"privacy_mode":"normal","question":"look for token waste","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_occurrences":2,"evidence_limit":5},"summary":{"branch_count":5,"supported_branch_count":0,"top_hypothesis":null,"confidence":"insufficient_local_evidence"},"branches":[],"recommended_next_tools":[]}
```

## Local Evidence Export

MCP:

- `usage_local_evidence_export(question="share token waste evidence")`

Schema: `codex-usage-tracker-local-evidence-export-v1`

Strict shareable summary derived from local investigation evidence. It omits raw fragments, snippets, record ids, thread names, command labels, file basenames, full paths, raw commands, and raw tool output.

```json
{"schema":"codex-usage-tracker-local-evidence-export-v1","content_mode":"shareable_local_evidence","includes_indexed_content":false,"includes_raw_fragments":false,"privacy_mode":"strict","question":"share token waste evidence","filters":{"since":null,"until":null,"thread":null,"include_archived":false,"min_occurrences":2,"evidence_limit":5},"summary":{"branch_count":5,"supported_branch_count":0,"top_hypothesis":null,"confidence":"insufficient_local_evidence","export_branch_count":0},"branches":[],"omitted_fields":["record_id","session_id","thread_name","raw_fragment","snippet","raw_command","raw_tool_output","full_path","path_basename","command_label"],"caveats":["Local evidence only; not an official OpenAI ledger."]}
```

## Lifecycle Commands

Most setup and file-writing commands accept `--json` and return a schema-specific payload with written paths and counts:

- `setup --json`: `codex-usage-tracker-setup-v1`
- `doctor --json`
- `inspect-log --json`
- `refresh --json`: `codex-usage-tracker-refresh-v1`
- `rebuild-index --json`: `codex-usage-tracker-rebuild-index-v1`
- `reset-db --yes --json`: `codex-usage-tracker-reset-db-v1`
- `dashboard --json`: `codex-usage-tracker-dashboard-v1`
- `export --json`: `codex-usage-tracker-export-v1`
- `pricing-coverage --json`
- `source-coverage --json`
- `recommendations --json`
- `init-pricing --json`, `update-pricing --json`, `pin-pricing --json`
- `init-allowance --json`, `parse-allowance --json`
- `update-rate-card --json`
- `init-thresholds --json`, `init-projects --json`
- `support-bundle --json`

`context` already returns JSON because it is an explicit on-demand context request. Treat `codex-usage-tracker-context-v1` output as sensitive local context even though it is redacted and size-limited by default. `max_entries=0` requests all matching entries and `max_chars=0` removes the character cap for that explicit request. Tool output and compacted replacement history are omitted unless explicitly requested. Compaction entries may include metadata such as `replacement_history_available`, `replacement_entry_count`, and `replacement_history_included`; replacement text appears only when `include_compaction_history` is true for that local request. Evidence responses include `action_timing`, derived from timestamps in the same selected-turn source scan, plus per-entry `action_timing` fields such as `since_turn_start_ms`, `since_previous_entry_ms`, and `reported_duration_ms` when available. MCP returns `codex-usage-tracker-context-disabled-v1` when raw context loading has not been explicitly enabled with `CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1`.
