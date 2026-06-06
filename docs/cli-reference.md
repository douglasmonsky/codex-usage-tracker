# CLI Reference

This page lists the common command-line workflows. For tested JSON contract ids, payload shapes, and error codes, see [CLI And MCP JSON Schemas](cli-json-schemas.md).

## Index And Setup

Refresh the local aggregate index:

```bash
codex-usage-tracker refresh
```

Rebuild the local aggregate index after parser or schema changes:

```bash
codex-usage-tracker rebuild-index
```

`rebuild-index` clears only the local aggregate `usage_events` and refresh metadata tables, then rescans local Codex logs.

Inspect one Codex log without writing to SQLite:

```bash
codex-usage-tracker inspect-log ~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl
codex-usage-tracker inspect-log ~/.codex/sessions/YYYY/MM/DD/rollout-...jsonl --json
```

`inspect-log` reports parser adapter, aggregate token-count events, session ids, models, and parser diagnostics. It does not store raw prompts, assistant messages, tool output, or transcript snippets.

## Dashboard

```bash
codex-usage-tracker dashboard --open
codex-usage-tracker dashboard --include-archived --open
codex-usage-tracker open-dashboard
codex-usage-tracker serve-dashboard --open
codex-usage-tracker serve-dashboard --no-context-api --open
```

`serve-dashboard --context-api explicit` is the default and keeps context loading as an explicit per-row action. `serve-dashboard --no-context-api` or `--context-api disabled` serves live aggregate refresh while disabling `/api/context` entirely.

Dashboards default to active sessions only. Use `--include-archived` for an all-history static/opened dashboard, or switch the served dashboard's `History` control from `Active sessions only` to `All history` when you intentionally want archived logs scanned and included.

The localhost `/api/usage` endpoint accepts `limit` and `offset` query parameters, so automation can page aggregate rows without asking the server to load an entire large history at once.

## Summaries

```bash
codex-usage-tracker summary --group-by model
codex-usage-tracker summary --group-by project
codex-usage-tracker summary --group-by project_tag
codex-usage-tracker summary --group-by thread --limit 20
codex-usage-tracker summary --preset today
codex-usage-tracker summary --preset last-7-days
codex-usage-tracker summary --preset expensive
codex-usage-tracker summary --preset by-subagent-role
codex-usage-tracker expensive --limit 10
codex-usage-tracker recommendations --limit 10
codex-usage-tracker pricing-coverage
```

Useful investigations:

- Sort by `Highest Codex credits` to find calls or threads consuming the most usage allowance.
- Sort by `Cache` to find threads that are mostly new context versus mostly reused context.
- Sort by `Context` to find calls approaching the model context window.
- Filter by model or reasoning effort to compare usage patterns across model choices.
- Use `summary --preset by-subagent-role` to see whether delegated work is driving a large share of usage.
- Use `expensive --limit 10` for a quick list of the highest-cost calls.
- Use `recommendations --json` for ranked action rows and thread rollups with severity score, primary recommendation, and secondary signals.

## JSON Queries

```bash
codex-usage-tracker query --since 2026-06-01 --project codex-usage-tracker --min-credits 1
codex-usage-tracker query --pricing-status unpriced --limit 0
codex-usage-tracker recommendations --since 2026-06-01 --json
codex-usage-tracker summary --group-by model --json
codex-usage-tracker session <session-id> --json
```

Use `query` when you need stable JSON for automation across project, model, effort, thread, pricing, token, or credit filters.

## Session And Context

Show one session:

```bash
codex-usage-tracker session <session-id>
```

Load one call's logged context on demand:

```bash
codex-usage-tracker context <record-id>
```

Raw context is read from the original local JSONL source only when explicitly requested. It is not written to SQLite, CSV, or generated dashboard HTML.

## Export

```bash
codex-usage-tracker export --output usage.csv
codex-usage-tracker export --output usage.csv --limit 0
```

Use `--privacy-mode redacted` or `--privacy-mode strict` before sharing CSV output.

## Local Config

```bash
codex-usage-tracker update-pricing
codex-usage-tracker pin-pricing --output ~/.codex-usage-tracker/pricing-2026-06-05.json
codex-usage-tracker init-pricing
codex-usage-tracker update-rate-card
codex-usage-tracker init-allowance
codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"
codex-usage-tracker init-thresholds
codex-usage-tracker init-projects
```

Local config files live under `~/.codex-usage-tracker/` and are never committed by this project.

## Privacy Mode

`--privacy-mode` is a global option, so place it before the subcommand:

```bash
codex-usage-tracker --privacy-mode redacted dashboard --open
codex-usage-tracker --privacy-mode strict export --output usage-redacted.csv
codex-usage-tracker --privacy-mode strict query --since 2026-06-01
```

`normal` keeps local project metadata visible. `redacted` hides raw `cwd` and source paths, hides Git remote labels, and replaces unnamed projects with stable hashed labels. `strict` also hides project-relative cwd, Git branch, and project tags.
