# CLI and MCP JSON Schemas

Codex Usage Tracker exposes aggregate-only JSON for automation through CLI `--json` flags and MCP tools. These payloads do not include prompts, assistant messages, tool output, or raw transcript snippets.

## Companion Skill Usage

The installed `codex-usage-api` skill is the recommended conversational entrypoint when a user wants to discuss usage instead of manually choosing commands. It should refresh aggregate data first, prefer JSON MCP tools, and fall back to these CLI JSON surfaces when MCP tools are unavailable.

| Question | Preferred JSON surface |
| --- | --- |
| What used the most? | `most_expensive_usage_calls(response_format="json")`, then `usage_summary(group_by="thread", response_format="json")` |
| Which project, thread, or model is driving usage? | `usage_summary(group_by="project" \| "thread" \| "model", response_format="json")` |
| Why did usage spike? | `usage_query(...)` with `since`, `project`, `thread`, `model`, `effort`, `min_tokens`, or `min_credits` filters |
| What is estimated or unpriced? | `usage_pricing_coverage(response_format="json")`, `usage_query(pricing_status="unpriced")`, or `usage_query(credit_confidence="estimated")` |
| How does this affect my allowance? | `usage_query(...)` rows with `usage_credits`, `usage_credit_confidence`, and allowance annotations |
| What happened in one session? | `session_usage(session_id=..., response_format="json")` |

The skill should separate exact facts from estimates. Remaining allowance is not native account data; it is only copied local state from `~/.codex-usage-tracker/allowance.json` when configured.

Use the global `--privacy-mode redacted` or `--privacy-mode strict` option, or the MCP `privacy_mode` argument, when project metadata should be hidden from JSON answers. The CLI option goes before the subcommand.

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
  "row_count": 2,
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
- `init-pricing --json`, `update-pricing --json`, `pin-pricing --json`
- `init-allowance --json`, `parse-allowance --json`
- `update-rate-card --json`
- `init-thresholds --json`, `init-projects --json`
- `support-bundle --json`

`context` already returns JSON because it is an explicit on-demand context request. Treat that output as sensitive local context even though it is redacted and size-limited.
