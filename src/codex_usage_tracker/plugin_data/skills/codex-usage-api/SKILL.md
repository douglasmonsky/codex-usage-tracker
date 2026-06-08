---
name: codex-usage-api
description: Use when the user wants to discuss, investigate, compare, or explain Codex or AI coding-agent usage using the Codex Usage Tracker API or MCP tools.
---

# Codex Usage API Companion

Use this companion skill as the conversational analyst for Codex Usage Tracker data as it evolves toward AI Usage Tracker. It helps Codex choose the right aggregate-only API calls, interpret the results, and answer the user's usage questions with evidence. Codex is the default source; use source filters when the user asks about Claude Code or cross-source usage.

## Privacy Boundary

Normal usage answers must use aggregate-only API data. Do not expose prompts, assistant messages, tool output, pasted secrets, or raw transcript snippets.

When a user plans to share JSON, CSV, dashboards, screenshots, or support bundles, prefer `privacy_mode="strict"` for MCP calls or the CLI global option `--privacy-mode strict` before the subcommand. Explain that configured project aliases are treated as explicit display opt-ins.

The only exception is `usage_call_context`, which reads one selected record's local source JSONL on demand. Use it only when the user explicitly asks to inspect actual logged context, and state that the returned text is local, redacted, size-limited, and not persisted by the tracker.

## First Steps

1. For "Open dashboard" or similar dashboard-open requests, do not inspect repository files, plugin manifests, tool registries, git status, or local logs first. Run `codex-usage-tracker open-dashboard --refresh` immediately, then report the opened path or a brief failure. Add `--source all` when the user explicitly asks for all supported sources.
2. For "Heaviest thread?", "Thread leaderboard", or similar thread-ranking requests, do not inspect repository files, SQLite schemas, plugin manifests, process lists, dashboard servers, or local logs manually. Refresh the aggregate index, then call `usage_summary(group_by="thread", limit=10, response_format="json")`. Use `refresh_usage_index(source="all")` when the user asks across Codex and Claude Code. If MCP tools are unavailable, run `codex-usage-tracker refresh --json` and `codex-usage-tracker summary --group-by thread --limit 10 --json`; add `--source all` for cross-source questions.
3. For normal usage questions, do not inspect repository files, plugin manifests, or local logs first. Start with the aggregate MCP tools. If MCP tools are unavailable, use the CLI JSON fallback below.
4. Refresh before analysis with `refresh_usage_index` unless the user asks for a static historical snapshot. Keep archived sessions excluded unless the user explicitly asks for all history. State the source scope in the answer, especially when using `source="all"`.
5. Use `usage_doctor(response_format="json")` when setup, indexing, pricing, MCP discovery, or dashboard freshness is uncertain.
6. Prefer JSON responses for analysis:
   - `usage_summary(..., response_format="json")`
   - `session_usage(..., response_format="json")`
   - `most_expensive_usage_calls(..., response_format="json")`
   - `usage_recommendations(..., response_format="json")`
   - `usage_pricing_coverage(..., response_format="json")`
   - `usage_query(...)`
7. Check the top-level `schema` field before interpreting structured output. Known schema ids are documented in `docs/cli-json-schemas.md`.
8. If MCP tools are unavailable, fall back to the CLI equivalents:
   - `codex-usage-tracker refresh --json`
   - `codex-usage-tracker refresh --source all --json`
   - `codex-usage-tracker summary --group-by thread --json`
   - `codex-usage-tracker summary --group-by source_app --json`
   - `codex-usage-tracker query`
   - `codex-usage-tracker session --json`
   - `codex-usage-tracker expensive --json`
   - `codex-usage-tracker recommendations --json`
   - `codex-usage-tracker pricing-coverage --json`
9. If the `codex-usage-tracker` command is missing, run `codex-usage-tracker doctor --suggest-repair --json` only if the command is available through an absolute path or known environment. Otherwise report that the CLI is not on `PATH` and ask the user to run `codex-usage-tracker setup` or reinstall with `pipx`.
10. Use source-checkout fallbacks only when you are already inside the repo checkout. On PowerShell, run `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m codex_usage_tracker.cli <command>`. On POSIX shells, run `PYTHONPATH=src .venv/bin/python -m codex_usage_tracker.cli <command>`. Do not use `PYTHONPATH=src` outside that checkout, and do not keep exploring plugin files after a setup failure.

## Routing Questions To API Calls

- "What used the most?" Use `usage_summary(group_by="thread", response_format="json")` first for thread totals, then `most_expensive_usage_calls(response_format="json")` for supporting calls.
- "Which source/project/thread/model is driving usage?" Use `usage_summary` grouped by `source_app`, `source_provider`, `project`, `thread`, or `model`.
- "Can I share this?" Use redacted or strict privacy mode and avoid `usage_call_context`.
- "Why did usage spike?" Use `usage_recommendations(response_format="json")` first for ranked causes, then `usage_query` with `since`, `source_provider`, `source_app`, `project`, `thread`, `model`, `effort`, `min_tokens`, or `min_credits` for supporting rows.
- "What is unpriced, estimated, or not applicable?" Use `usage_pricing_coverage(response_format="json")` and `usage_query(pricing_status="unpriced")`, `usage_query(credit_confidence="estimated")`, or `usage_query(credit_confidence="not_applicable")`.
- "How does this affect my allowance?" Use Codex rows from `usage_query` and summarize `usage_credits`, `usage_credit_confidence`, and `allowanceImpact`. Explain that remaining allowance is only as accurate as the user's local allowance config, and that non-Codex rows do not consume Codex credit estimates in this tracker.
- "What happened in this session?" Use `session_usage(session_id=..., response_format="json")`.
- "What should I do next?" Use `usage_recommendations(response_format="json")` and explain the primary recommendation, secondary signals, recommendation score, and top thread rollups.

## Answer Style

- Lead with the direct answer and the key metric.
- For default prompt workflows, use at most one short progress update such as "Refreshing aggregate usage, then ranking threads." Avoid narrating tool discovery, process inspection, SQLite schema inspection, or plugin-file lookup.
- Name the data scope, such as source, time window, project, thread, model, row count, and whether rows were truncated.
- Separate exact facts from estimates. Call out `pricing_estimated`, missing `pricing_model`, `usage_credit_confidence`, and missing allowance windows.
- Include the next useful investigation when the answer depends on unclear pricing, stale allowance values, or a broad time window.
- Keep explanations tied to aggregate fields rather than guessing from conversation content.
