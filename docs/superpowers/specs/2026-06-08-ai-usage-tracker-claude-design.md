# AI Usage Tracker With Claude Code Support

Date: 2026-06-08

## Summary

Codex Usage Tracker will evolve into a generic local AI usage tracker. Codex remains a fully supported source, but it becomes one ingestion adapter rather than the product identity. The first non-Codex source is Claude Code local JSONL history, read from `~/.claude/projects` by default.

The first implementation slice preserves the current package name, CLI command, plugin install path, and existing Codex behavior for compatibility. User-facing dashboard/docs language starts moving toward "AI Usage Tracker", while compatibility aliases remain in place until a later full rename is worth the churn.

## Goals

- Track aggregate token usage across Codex and Claude Code in one SQLite database.
- Preserve the existing aggregate-only privacy model: no prompts, assistant text, tool output, or transcript snippets are persisted to SQLite, CSV, generated dashboard HTML, fixtures, or commits.
- Keep existing Codex refresh, summary, dashboard, MCP, CSV, pricing, allowance, and context workflows working.
- Add explicit provider/app identity to usage rows so Gemini CLI and OpenCode/DeepSeek can be added behind the same adapter boundary later.
- Make OpenAI pricing updates remain backward compatible while preparing the pricing config for future provider-aware updaters.

## Non-Goals

- Do not rename the Python package, import path, local app directory, plugin name, or CLI binary in this slice.
- Do not fetch Anthropic, Google, or DeepSeek pricing automatically in this slice.
- Do not ingest Gemini CLI or OpenCode/DeepSeek logs in this slice.
- Do not infer account allowance state for Claude, Gemini, DeepSeek, or Codex from logged-in accounts.
- Do not persist raw Claude Code transcript text or derive fixtures from real Claude logs.

## Data Model

`usage_events` remains the aggregate fact table. It gains provider/source identity fields:

- `source_provider`: provider owner such as `openai`, `anthropic`, `google`, or `deepseek`.
- `source_app`: local app/client such as `codex`, `claude-code`, `gemini-cli`, or `opencode`.
- `source_format`: parser format/version such as `codex-jsonl-v1` or `claude-code-jsonl-v1`.
- `provider_request_id`: nullable provider request or message id when a source exposes one.
- `cache_creation_input_tokens`: integer token bucket for providers that separate cache writes from cache reads.

Existing Codex rows migrate with:

- `source_provider = "openai"`
- `source_app = "codex"`
- `source_format = "codex-jsonl-v1"`
- `provider_request_id = NULL`
- `cache_creation_input_tokens = 0`

Existing stable token columns stay intact. For Claude Code rows:

- `input_tokens` stores total Claude input tokens: normal input, cache creation, and cache read tokens.
- `cached_input_tokens` stores Claude cache-read tokens.
- `cache_creation_input_tokens` stores Claude cache-write tokens.
- `uncached_input_tokens` remains the derived field `max(input_tokens - cached_input_tokens, 0)`.
- `output_tokens` stores Claude output tokens.
- `reasoning_output_tokens` is `0` unless Claude exposes a stable per-message thinking token field in local JSONL.

This preserves current dashboard/report calculations while exposing Claude's extra cache-write bucket for detailed inspection and future cost logic.

## Adapter Architecture

Ingestion moves from a monolithic Codex parser to explicit source adapters.

Each adapter exposes:

```text
UsageSourceAdapter
- source_provider
- source_app
- source_format
- discover_logs(root, include_archived=False)
- load_session_index(root)
- parse_file(path, session_index, stats)
```

The current parser behavior becomes `CodexJsonlAdapter`. Its record id generation must remain stable for existing Codex fixtures and indexed rows.

The first new adapter is `ClaudeCodeJsonlAdapter`. It scans `~/.claude/projects/**/*.jsonl` by default, parses assistant response usage objects, and emits one `UsageEvent` per assistant response that has aggregate usage counters. It ignores prompt text, assistant text, and tool output during normal indexing.

`parser.py` can remain as a compatibility facade during the first slice, but provider-specific logic should live in adapter modules such as:

- `src/codex_usage_tracker/adapters/base.py`
- `src/codex_usage_tracker/adapters/codex_jsonl.py`
- `src/codex_usage_tracker/adapters/claude_code_jsonl.py`

## Refresh Flow

Existing commands keep working:

```bash
codex-usage-tracker refresh
codex-usage-tracker rebuild-index
codex-usage-tracker setup
codex-usage-tracker open-dashboard --refresh
codex-usage-tracker serve-dashboard --refresh
```

New refresh options:

```bash
codex-usage-tracker refresh --source codex
codex-usage-tracker refresh --source claude-code
codex-usage-tracker refresh --source all
codex-usage-tracker refresh --claude-home ~/.claude
```

`--source codex` is the compatibility default for the first slice. `--source all` scans Codex and Claude Code roots. Later, the default can become `all` after docs and setup flows are updated.

`RefreshResult` and refresh metadata should include per-source scanned file counts, parsed event counts, skipped events, and diagnostics while preserving existing top-level fields for JSON contract compatibility.

## Claude Code JSONL Parsing

The Claude adapter reads only local JSONL files. It should accept modest shape variation because local transcript formats can evolve.

For each JSONL entry:

- Parse JSON envelopes defensively.
- Identify assistant/model response records that include usage counters.
- Extract timestamp, model label, request/message id if present, cwd/project path if present or derivable from file path, session id, and parent/thread labels only from metadata-like fields.
- Extract aggregate token counters from usage fields such as input, cache read, cache creation, and output token counts.
- Skip records without usable usage counters.
- Increment diagnostics for invalid JSON, missing payload, unsupported event shape, missing usage, invalid integer, duplicate record, and skipped events.

The adapter must not store raw message content. On-demand context loading for Claude rows is not included in the first slice unless it can be implemented with the same explicit, redacted, size-limited behavior as Codex and clearly marked by `source_app`.

## Reports And Dashboard

Reports and dashboard payloads gain provider/app visibility:

- Add `source_provider`, `source_app`, and `source_format` to rows, CSV, JSON, and call details.
- Add summary grouping by provider and app.
- Add provider/app filters to query and dashboard payloads.
- Add visible provider/app pills or columns so mixed Codex and Claude rows are not confused.
- Rename user-facing "Codex usage dashboard" text toward "AI usage dashboard" where it describes the whole product.

Codex-specific terms remain only where they refer to Codex-specific semantics, especially credit/allowance displays.

## Pricing And Credits

There are two separate concepts:

- `update-pricing`: local USD token price cache for `estimated_cost_usd`.
- `update-rate-card`, `init-allowance`, and `parse-allowance`: Codex credit and copied allowance context.

In the first slice:

- `update-pricing` remains backward-compatible and OpenAI-oriented.
- `pricing.json` remains generic enough for manually entered Anthropic, Google, and DeepSeek model rates.
- Claude rows are unpriced unless matching manual pricing is present.
- Codex credit/allowance annotations apply only to Codex/OpenAI rows with matching Codex credit rates.
- Dashboard wording should avoid implying Claude rows consume Codex credits.

Future provider-aware pricing commands can extend the same concept:

```bash
codex-usage-tracker update-pricing --provider openai
codex-usage-tracker update-pricing --provider anthropic
codex-usage-tracker update-pricing --provider google
codex-usage-tracker update-pricing --provider deepseek
```

The first follow-up after Claude ingestion should be an Anthropic pricing updater.

## Privacy

The current privacy rules continue to apply to every provider.

Persisted/generated surfaces may include:

- session ids and provider request ids
- timestamps
- source app/provider/format
- local source file path, subject to existing privacy modes
- cwd/project metadata, subject to existing privacy modes
- model labels
- token counters
- cost estimates, credit annotations, recommendations, and derived ratios

Persisted/generated surfaces must not include:

- prompts
- assistant text
- tool output
- pasted secrets
- raw transcript snippets
- fixture data derived from real local logs

## Migration

Add a new schema migration that repairs or adds the new provider fields for existing databases. It should be idempotent, preserve current row ids, and backfill Codex defaults for rows where `source_app` is missing.

The release should document that existing SQLite indexes can either migrate in place or be rebuilt from local logs. `rebuild-index` must continue to work for users who prefer regeneration.

## Testing

Focused tests for the first slice:

- Existing Codex parser tests still pass without behavior changes.
- Existing JSON contracts remain valid.
- Schema migration adds provider fields and backfills Codex defaults.
- Claude synthetic JSONL fixtures parse usage counters without storing message text.
- Claude malformed/corrupt records produce diagnostics without crashing refresh.
- Mixed Codex and Claude refresh with `--source all` is idempotent.
- Query, CSV, dashboard payloads, and MCP wrappers expose provider/app fields.
- Provider/app filters work in SQL prefilters where practical.
- Codex credit annotations do not apply to Claude rows.
- Manual pricing can price a Claude model when `pricing.json` contains a matching model or alias.
- Static dashboard and exported CSV remain aggregate-only.

## Rollout Order

1. Add provider fields, schema migration, and row defaults.
2. Extract Codex parser into adapter form behind compatibility facades.
3. Add Claude Code JSONL adapter with synthetic fixtures.
4. Wire `refresh --source`, `--claude-home`, and mixed-source refresh metadata.
5. Add provider/app grouping and filters to reports, CLI JSON, MCP, CSV, and dashboard payloads.
6. Update dashboard copy and docs toward "AI Usage Tracker" while preserving compatibility names.
7. Add conditional Codex credit wording so mixed-provider dashboards stay clear.
8. Run focused tests, compile checks, node dashboard syntax checks, release checks, and build checks before publishing.

## Decisions For This Slice

- Keep `codex-usage-tracker` as the CLI and package name for this slice.
- Make `--source codex` the default initially, with `--source all` opt-in.
- Defer automatic Anthropic pricing fetching until after Claude ingestion lands.
- Defer Gemini CLI and OpenCode/DeepSeek adapters until the adapter boundary has been proven by Codex plus Claude.
