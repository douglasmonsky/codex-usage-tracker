# CLI Reference

This page lists the common command-line workflows. For tested JSON contract ids, payload shapes, and error codes, see [CLI And MCP JSON Schemas](cli-json-schemas.md).

## Index And Setup

Run first-time setup:

```bash
codex-usage-tracker setup
```

`setup` installs or refreshes the local plugin wrapper, initializes local config templates when needed, refreshes the aggregate index, runs `doctor`, and prints whether Codex needs a restart for plugin discovery.

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

Check setup without writing files:

```bash
codex-usage-tracker doctor
codex-usage-tracker doctor --suggest-repair
```

`doctor` validates local paths, database state, parser diagnostics, pricing and allowance config, dashboard output, plugin files, and MCP importability. `--suggest-repair` adds likely next commands without making changes.

Reset only the local aggregate database:

```bash
codex-usage-tracker reset-db --yes
```

`reset-db` deletes tracker-owned aggregate SQLite rows. It does not delete raw Codex logs and requires `--yes`.

## Plugin Lifecycle

```bash
codex-usage-tracker install-plugin
codex-usage-tracker install-plugin --python .venv/bin/python
codex-usage-tracker upgrade-plugin
codex-usage-tracker uninstall-plugin
```

`install-plugin` writes the package-owned local Codex plugin wrapper, companion skills, and MCP config. Use the `--python` form for source checkouts that should use a repo-local virtual environment.

`upgrade-plugin` refreshes an existing wrapper in place. `uninstall-plugin` removes only the tracker-owned plugin wrapper and marketplace entry.

## Dashboard

```bash
codex-usage-tracker dashboard --open
codex-usage-tracker dashboard --include-archived --open
codex-usage-tracker open-dashboard
codex-usage-tracker open-dashboard --no-refresh
codex-usage-tracker serve-dashboard --open
codex-usage-tracker serve-dashboard --no-refresh --open
codex-usage-tracker serve-dashboard --no-context-api --open
```

`serve-dashboard --context-api explicit` is the default and keeps context loading as an explicit per-row action. `serve-dashboard --no-context-api` or `--context-api disabled` starts with context loading off; a token-protected button in the local details panel can enable it without restarting the server.

`open-dashboard` and `serve-dashboard` refresh active-session logs before opening by default. Use `--no-refresh` only for an intentionally cached snapshot. The lower-level `dashboard` command writes from the current SQLite index and does not rescan logs.

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

## Support Bundle

```bash
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

Support bundles are diagnostic summaries for issues. They include package, platform, doctor, schema, parser, pricing, allowance, threshold, project-config, and privacy metadata. They exclude raw logs, aggregate rows, prompts, assistant messages, tool output, and context text.

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

Stable local config files:

- `pricing.json`: schema `_schema: codex-usage-tracker-pricing-v1`, optional `_source`, `models`, `aliases`, and `_estimated_models`. `models` maps model labels to USD-per-million-token rates such as `input`, `cached_input`, and `output`.
- `rate-card.json`: schema `codex-usage-tracker-codex-rate-card-v1`, optional `_source`, `credit_rates`, and `aliases`. `credit_rates` maps Codex model labels to credit rates for aggregate token counters.
- `allowance.json`: schema `codex-usage-tracker-allowance-v1`, `windows`, optional `credit_rates`, and `aliases`. `windows` stores copied 5-hour, weekly, or other allowance snapshots such as `remaining_percent`, `reset_at`, `remaining_credits`, and `total_credits`.
- `thresholds.json`: JSON object keyed by recommendation threshold names such as `low_cache_ratio`, `high_context_percent`, and `high_cost_usd`. Unknown keys are ignored.
- `projects.json`: JSON object with `aliases`, `ignored_paths`, and `tags` for local project attribution.

These config schemas are part of the 1.0 compatibility surface. New optional fields may be added, but existing meanings should not change without documentation and a compatibility plan.

## Privacy Mode

`--privacy-mode` is a global option, so place it before the subcommand:

```bash
codex-usage-tracker --privacy-mode redacted dashboard --open
codex-usage-tracker --privacy-mode strict export --output usage-redacted.csv
codex-usage-tracker --privacy-mode strict query --since 2026-06-01
```

`normal` keeps local project metadata visible. `redacted` hides raw `cwd` and source paths, hides Git remote labels, and replaces unnamed projects with stable hashed labels. `strict` also hides project-relative cwd, Git branch, and project tags.
