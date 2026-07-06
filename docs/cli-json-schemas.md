# CLI, MCP, and Dashboard JSON Schemas

Codex Usage Tracker exposes aggregate-only JSON for automation through CLI `--json` flags, MCP tools, and the local dashboard server API. These payloads do not include prompts, assistant messages, tool output, or raw transcript snippets.

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
- `recommendations --json`
- `init-pricing --json`, `update-pricing --json`, `pin-pricing --json`
- `init-allowance --json`, `parse-allowance --json`
- `update-rate-card --json`
- `init-thresholds --json`, `init-projects --json`
- `support-bundle --json`

`context` already returns JSON because it is an explicit on-demand context request. Treat `codex-usage-tracker-context-v1` output as sensitive local context even though it is redacted and size-limited by default. `max_entries=0` requests all matching entries and `max_chars=0` removes the character cap for that explicit request. Tool output and compacted replacement history are omitted unless explicitly requested. Compaction entries may include metadata such as `replacement_history_available`, `replacement_entry_count`, and `replacement_history_included`; replacement text appears only when `include_compaction_history` is true for that local request. Evidence responses include `action_timing`, derived from timestamps in the same selected-turn source scan, plus per-entry `action_timing` fields such as `since_turn_start_ms`, `since_previous_entry_ms`, and `reported_duration_ms` when available. MCP returns `codex-usage-tracker-context-disabled-v1` when raw context loading has not been explicitly enabled with `CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1`.
