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
| What is my latest observed usage state? | Dashboard/status payload `observed_usage` from local `token_count.rate_limits` snapshots |
| How does this affect my allowance? | `usage_query(...)` rows with `usage_credits`, `usage_credit_confidence`, and allowance annotations |
| What happened in one session? | `session_usage(session_id=..., response_format="json")` |

The skill should separate exact facts from estimates. Observed usage snapshots are passive local-log data from indexed Codex token-count records, not native live account data. Copied remaining allowance in `~/.codex-usage-tracker/allowance.json` is a fallback when no observed snapshot is available.

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
| `codex-usage-tracker-plugin-install-v1` | CLI `install-plugin --json`, setup plugin payload |
| `codex-usage-tracker-plugin-upgrade-v1` | CLI `upgrade-plugin --json` |
| `codex-usage-tracker-plugin-uninstall-v1` | CLI `uninstall-plugin --json` |
| `codex-usage-tracker-refresh-v1` | CLI `refresh --json`, MCP `refresh_usage_index()` |
| `codex-usage-tracker-rebuild-index-v1` | CLI `rebuild-index --json` |
| `codex-usage-tracker-reset-db-v1` | CLI `reset-db --yes --json` |
| `codex-usage-tracker-summary-v1` | CLI `summary --json`, CLI `expensive --json`, MCP summary/expensive JSON |
| `codex-usage-tracker-query-v1` | CLI `query`, MCP `usage_query(...)` |
| `codex-usage-tracker-usage-impact-v1` | CLI `usage-impact --json`, dashboard server `/api/usage-impact?record_id=...`, `/api/call` usage-impact payload |
| `codex-usage-tracker-usage-impact-visible-v1` | Dashboard server `/api/usage-impact?record_ids=...` compact visible-row enrichment payload |
| `codex-usage-tracker-task-receipts-v1` | CLI `task-receipts --json`, dashboard server `/api/task-receipts`, `/api/call` task receipt payload |
| `codex-usage-tracker-usage-impact-estimate-v1` | Nested dashboard row `usage_impact.primary` and `usage_impact.secondary` estimate objects |
| `codex-usage-tracker-sessions-v1` | CLI `sessions --json`, dashboard server `/api/sessions` response |
| `codex-usage-tracker-work-session-v1` | Dashboard server `/api/session` response |
| `codex-usage-tracker-context-epochs-v1` | Dashboard server `/api/context-epochs` response and nested `/api/session` context epochs |
| `codex-usage-tracker-recommendations-v1` | CLI `recommendations --json`, MCP `usage_recommendations(response_format="json")` |
| `codex-usage-tracker-lifecycle-recommendations-v1` | CLI `lifecycle-recommendations --json`, dashboard server `/api/lifecycle-recommendations`, `/api/call` lifecycle guidance payload |
| `codex-usage-tracker-session-v1` | CLI `session --json`, MCP `session_usage(response_format="json")` |
| `codex-usage-tracker-context-v1` | CLI `context`, MCP `usage_call_context` when raw context is explicitly enabled |
| `codex-usage-tracker-context-disabled-v1` | MCP `usage_call_context` when raw context is disabled |
| `codex-usage-tracker-context-settings-v1` | Dashboard server `/api/context-settings` response |
| `codex-usage-tracker-open-investigator-v1` | Dashboard server `/api/open-investigator` response |
| `codex-usage-tracker-live-api-v1` | Dashboard server live API payload family marker |
| `codex-usage-tracker-status-v1` | Dashboard server `/api/status` response |
| `codex-usage-tracker-calls-v1` | Dashboard server `/api/calls` response |
| `codex-usage-tracker-call-v1` | Dashboard server `/api/call` response |
| `codex-usage-tracker-threads-v1` | Dashboard server `/api/threads` response |
| `codex-usage-tracker-thread-calls-v1` | Dashboard server `/api/thread-calls` response |
| `codex-usage-tracker-dashboard-v1` | CLI `dashboard --json`, MCP `generate_usage_dashboard()` |
| `codex-usage-tracker-open-dashboard-v1` | CLI `open-dashboard --json` |
| `codex-usage-tracker-serve-dashboard-v1` | CLI `serve-dashboard --json` startup payload |
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

## Refresh

Commands:

```bash
codex-usage-tracker refresh --json
codex-usage-tracker rebuild-index --refresh-workers 4 --json
```

Schemas:

- `codex-usage-tracker-refresh-v1`
- `codex-usage-tracker-rebuild-index-v1`

```json
{
  "schema": "codex-usage-tracker-refresh-v1",
  "scanned_files": 4,
  "parsed_events": 12,
  "skipped_events": 0,
  "inserted_or_updated_events": 12,
  "changed_source_files": 4,
  "append_source_files": 0,
  "full_reparse_source_files": 4,
  "inserted_records": 12,
  "deleted_records": 0,
  "affected_threads": 3,
  "skipped_downstream_work": false,
  "refresh_workers": 4,
  "parallel_parse_files": 4,
  "db_path": "/home/user/.codex-usage-tracker/usage.sqlite3",
  "parser_diagnostics": {}
}
```

`refresh_workers` reports the parser worker count used for that refresh. `parallel_parse_files`
is `0` when refresh used the sequential parser path. SQLite writes and read-model
maintenance remain serialized after parsing.

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

## Usage Impact

Command:

```bash
codex-usage-tracker usage-impact --record-id <record-id> --json
```

Dashboard API:

- `/api/usage-impact?record_id=<record-id>`
- `/api/usage-impact?record_ids=<record-id>,<record-id>` returns the compact
  visible-row enrichment shape for already rendered dashboard rows. This mode is
  bounded to visible record IDs and reads only persisted usage-impact estimates;
  it does not synchronously rebuild estimates.
- `/api/call?record_id=<record-id>` includes a nested `usage_impact` payload

Schema: `codex-usage-tracker-usage-impact-v1`

```json
{
  "schema": "codex-usage-tracker-usage-impact-v1",
  "record_id": "record-123",
  "limit": 100,
  "row_count": 2,
  "rows": [],
  "raw_context_included": false
}
```

Rows are derived from local observed Codex usage snapshots and the configured/local Codex credit estimate. They are useful for comparing likely per-call allowance movement, but they are not exact billing data and may exclude usage outside local Codex logs.

## Task Receipts

Command:

```bash
codex-usage-tracker task-receipts --record-id <record-id> --json
```

Dashboard API:

- `/api/task-receipts?record_id=<record-id>`
- `/api/call?record_id=<record-id>` includes a nested `task_receipts` payload

Schema: `codex-usage-tracker-task-receipts-v1`

```json
{
  "schema": "codex-usage-tracker-task-receipts-v1",
  "record_id": "record-123",
  "limit": 100,
  "offset": 0,
  "row_count": 0,
  "rows": [],
  "raw_context_included": false
}
```

Rows contain aggregate-only durable-output receipt signals such as `patch_applied`,
`tool_activity`, or `task_complete`. They do not include prompts, assistant messages,
tool output, patch text, command text, raw JSONL fragments, or reconstructed transcript
content.

## Lifecycle Recommendations

Command:

```bash
codex-usage-tracker lifecycle-recommendations --record-id <record-id> --json
```

Dashboard API:

- `/api/lifecycle-recommendations?record_id=<record-id>`
- `/api/call?record_id=<record-id>` includes a nested `lifecycle_recommendations` payload

Schema: `codex-usage-tracker-lifecycle-recommendations-v1`

```json
{
  "schema": "codex-usage-tracker-lifecycle-recommendations-v1",
  "filters": {
    "record_id": "record-123",
    "thread_key": null,
    "work_session_id": null,
    "context_epoch_id": null,
    "scope": null
  },
  "limit": 100,
  "offset": 0,
  "row_count": 0,
  "total_matched_rows": 0,
  "truncated": false,
  "rows": [],
  "raw_context_included": false
}
```

Rows are cautious derived guidance such as `continue_thread`, `start_fresh`,
`summarize_or_compact`, `lower_reasoning`, `inspect_low_evidence`, or
`inspect_delegated_work`. They combine aggregate counters, usage-impact estimates,
work-session/context-epoch metadata, and task-receipt signals. They do not include
raw prompts, assistant messages, tool output, JSONL fragments, or exact billing claims.

## Thread Work Sessions

Command:

```bash
codex-usage-tracker sessions --json
```

Dashboard API:

- `/api/sessions`
- `/api/session?work_session_id=<work-session-id>`
- `/api/context-epochs?work_session_id=<work-session-id>`

Schema: `codex-usage-tracker-sessions-v1`

```json
{
  "schema": "codex-usage-tracker-sessions-v1",
  "row_count": 1,
  "rows": [],
  "limit": 100,
  "offset": 0,
  "include_archived": false,
  "raw_context_included": false
}
```

Schema: `codex-usage-tracker-work-session-v1`

```json
{
  "schema": "codex-usage-tracker-work-session-v1",
  "record": {},
  "context_epochs": [],
  "raw_context_included": false
}
```

Rows are materialized from aggregate usage counters only. They group adjacent calls in the same resolved thread and split at cold-cache resume boundaries inferred from idle gaps, uncached input, and cache ratio. They do not contain prompts, assistant messages, tool output, or raw JSONL fragments.

Schema: `codex-usage-tracker-context-epochs-v1`

```json
{
  "schema": "codex-usage-tracker-context-epochs-v1",
  "row_count": 1,
  "rows": [],
  "work_session_id": "work-session-123",
  "limit": 100,
  "offset": 0,
  "raw_context_included": false
}
```

Context epoch rows are aggregate segments inside a work session. A new epoch starts at the first call in a session or at a call labeled `post_compaction`. The rows expose token/cache totals, first-call post-compaction uncached spike, context pressure, and a coarse compaction effectiveness label. They do not store replacement history or raw context.

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

`context` already returns JSON because it is an explicit on-demand context request. Treat `codex-usage-tracker-context-v1` output as sensitive local context even though it is redacted and size-limited by default. `max_entries=0` requests all matching entries and `max_chars=0` removes the character cap for that explicit request. Tool output and compacted replacement history are omitted unless explicitly requested. Compaction entries may include metadata such as `replacement_history_available`, `replacement_entry_count`, and `replacement_history_included`; replacement text appears only when `include_compaction_history` is true for that local request. MCP returns `codex-usage-tracker-context-disabled-v1` when raw context loading has not been explicitly enabled with `CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1`.
