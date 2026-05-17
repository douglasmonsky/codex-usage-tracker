---
name: codex-usage-tracker
description: Use when the user asks about Codex token usage, model/reasoning efficiency, usage dashboards, CSV exports, or per-session/per-turn Codex usage stats from local logs.
---

# Codex Usage Tracker

Use this plugin to inspect aggregate token usage from local Codex session logs.

## Privacy Boundary

The tracker is aggregate-only. It should never return prompts, assistant message text, tool outputs, pasted secrets, or raw transcript snippets.

## Common Workflows

- Refresh the index before answering usage questions.
- Use `usage_doctor` when setup, plugin discovery, MCP launch, dashboard output, or pricing estimates look wrong.
- Use `usage_summary` for high-level totals by date, model, effort, cwd, thread, or session.
- Use `usage_summary` presets `today`, `last-7-days`, `by-model`, `by-cwd`, `by-thread`, and `expensive` for common requests.
- Use `usage_pricing_coverage` when the user asks whether costs are fully priced or which models use estimated or missing pricing.
- Use `session_usage` for per-call and per-turn detail for one session.
- Use `most_expensive_usage_calls` to identify high-token calls and aggregate efficiency signals.
- Use `generate_usage_dashboard` when the user wants a visual hoverable report.
- Use `export_usage_csv` when the user wants local spreadsheet-friendly data.
- Use `update_usage_pricing_config` when the user wants cost estimates based on OpenAI-published text-token pricing. This refreshes the local pricing cache and does not send local usage data anywhere. Internal Codex labels may include explicitly marked best-guess estimates when no public pricing row exists.
- Use `init_usage_pricing_config` only when the user wants a manual local pricing template or override file.
