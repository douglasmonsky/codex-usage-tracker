---
name: codex-usage-api
description: Use when the user wants to discuss, investigate, compare, or explain Codex usage using the Codex Usage Tracker API or MCP tools.
---

# Codex Usage API Companion

Use this companion skill as the conversational analyst for Codex Usage Tracker data. It helps Codex choose the right aggregate-only API calls, interpret the results, and answer the user's usage questions with evidence.

## Privacy Boundary

Normal usage answers must use aggregate-only API data. Do not expose prompts, assistant messages, tool output, pasted secrets, or raw transcript snippets.

When a user plans to share JSON, CSV, dashboards, screenshots, or support bundles, prefer `privacy_mode="strict"` for MCP calls or the CLI global option `--privacy-mode strict` before the subcommand. Explain that configured project aliases are treated as explicit display opt-ins.

The only exception is `usage_call_context`, which reads one selected record's local source JSONL on demand. Use it only when the user explicitly asks to inspect actual logged context, and state that the returned text is local, redacted, size-limited, and not persisted by the tracker.

## First Steps

1. Refresh before analysis with `refresh_usage_index` unless the user asks for a static historical snapshot.
2. Use `usage_doctor(response_format="json")` when setup, indexing, pricing, MCP discovery, or dashboard freshness is uncertain.
3. Prefer JSON responses for analysis:
   - `usage_summary(..., response_format="json")`
   - `session_usage(..., response_format="json")`
   - `most_expensive_usage_calls(..., response_format="json")`
   - `usage_pricing_coverage(..., response_format="json")`
   - `usage_query(...)`
4. If MCP tools are unavailable, fall back to the CLI equivalents:
   - `codex-usage-tracker refresh`
   - `codex-usage-tracker summary --json`
   - `codex-usage-tracker query`
   - `codex-usage-tracker session --json`
   - `codex-usage-tracker expensive --json`
   - `codex-usage-tracker pricing-coverage --json`

## Routing Questions To API Calls

- "What used the most?" Use `most_expensive_usage_calls(response_format="json")` and `usage_summary(group_by="thread", response_format="json")`.
- "Which project/thread/model is driving usage?" Use `usage_summary` grouped by `project`, `thread`, or `model`.
- "Can I share this?" Use redacted or strict privacy mode and avoid `usage_call_context`.
- "Why did usage spike?" Use `usage_query` with `since`, `project`, `thread`, `model`, `effort`, `min_tokens`, or `min_credits`, then compare timestamps, total tokens, cache ratio, context window percent, and recommendations.
- "What is unpriced or estimated?" Use `usage_pricing_coverage(response_format="json")` and `usage_query(pricing_status="unpriced")` or `usage_query(credit_confidence="estimated")`.
- "How does this affect my allowance?" Use rows from `usage_query` and summarize `usage_credits`, `usage_credit_confidence`, and `allowanceImpact`. Explain that remaining allowance is only as accurate as the user's local allowance config.
- "What happened in this session?" Use `session_usage(session_id=..., response_format="json")`.
- "What should I do next?" Rank actions from aggregate signals: high Codex credits, low cache reuse, context growth, estimated/unpriced rates, subagent or auto-review spikes, and high reasoning output.

## Answer Style

- Lead with the direct answer and the key metric.
- Name the data scope, such as time window, project, thread, model, row count, and whether rows were truncated.
- Separate exact facts from estimates. Call out `pricing_estimated`, missing `pricing_model`, `usage_credit_confidence`, and missing allowance windows.
- Include the next useful investigation when the answer depends on unclear pricing, stale allowance values, or a broad time window.
- Keep explanations tied to aggregate fields rather than guessing from conversation content.
