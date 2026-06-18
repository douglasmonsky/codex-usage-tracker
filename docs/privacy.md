# Privacy Guide

Codex Usage Tracker is designed around aggregate local analysis. It reads Codex logs already written on your machine and avoids storing raw transcript content.

## Stored In SQLite

The local SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default and contains aggregate metrics:

- session id, thread name, cwd, source file, turn id, timestamps
- model, reasoning effort, context window
- token counts and derived efficiency ratios
- subagent source, role, nickname, parent session id, and parent thread name when present
- call-origin category, reason, and confidence labels derived from event metadata during indexing
- archived-session flag, conservative thread key, and adjacent aggregate record ids for dashboard navigation
- materialized thread-level aggregate summaries for active and all-history scopes
- source-file refresh metadata such as path, path hash, size, mtime, indexed line/byte offsets, latest aggregate record id, parser diagnostics, and last indexed time
- observed Codex rate-limit snapshot metadata from local token-count logs, such as plan type, limit id, 5-hour/weekly used percentages, window lengths, and reset times
- pricing, credit, allowance, recommendation, and project metadata derived from aggregate fields

## Not Stored

The parser intentionally does not store:

- prompts
- assistant messages
- tool output
- pasted secrets
- raw transcript snippets
- raw logged context

Those fields are not written to SQLite, CSV exports, generated dashboard HTML, or synthetic screenshots.

Call-origin metadata is heuristic and confidence-labeled. It stores categories such as `user`, `codex`, or `unknown` plus a reason such as `user_message`, `tool_result`, `post_compaction`, or `agent_continuation`. It does not store the message text, tool output, compaction replacement text, or raw JSONL fragment that produced the category.

## On-Demand Context

`usage_call_context`, `codex-usage-tracker context`, and the `serve-dashboard` context endpoint read a single source JSONL file only when explicitly requested. Returned context is redacted for common secret patterns and capped in size by default for CLI/MCP requests. The call investigator uses the same endpoint at runtime and requests quick redacted evidence for the selected call when the local context API is enabled; that still does not persist raw context into SQLite, CSV, support bundles, or generated dashboard HTML.

Tool output is omitted by default for CLI/MCP and dashboard investigator context requests. The call investigator offers `Show tool output` when redacted, size-limited tool output is needed. Full serialized JSONL group analysis is also opt-in through `mode=full` / `Run full serialized analysis`; default quick mode returns only a fast serialized upper-bound estimate. Compacted replacement history remains omitted by default everywhere. Compaction metadata can show that replacement history exists, its entry count, and the source line, but the replacement text is returned only when explicitly requested for that selected call and is redacted before display.

Dashboard context loading can start off and then be enabled from the local details panel without restarting:

```bash
codex-usage-tracker serve-dashboard --no-context-api --open
```

The enable action is still token-protected, localhost-only, and does not load any context until you click a row-level context action.

For MCP users, `usage_call_context` is additionally disabled unless the MCP server process has this environment variable:

```bash
CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1
```

Aggregate MCP tools do not require that opt-in.

## Localhost Server

The localhost server:

- binds only to loopback hosts
- validates loopback `Host` and `Origin` headers
- protects refresh/context API calls with a random per-server token
- can disable the context API entirely
- refreshes aggregate rows without embedding raw transcript content into the dashboard
- serves `/api/status`, `/api/calls`, `/api/call`, `/api/threads`, `/api/thread-calls`, `/api/summary`, `/api/recommendations`, and the compatibility `/api/usage` endpoint from aggregate SQLite data without loading raw source JSONL context

Source JSONL reads happen during refresh/indexing, explicit on-demand context loading for one selected call, and explicit synthetic benchmark/diagnostic runs. Live refresh records metadata and aggregate-only parser cursors about source files so unchanged logs can be skipped and append-only growth can be parsed from the last indexed byte; that metadata does not store prompts, assistant messages, tool output, compaction replacement text, raw JSONL fragments, raw context, or reconstructed transcript evidence. The live aggregate APIs do not return that raw content either.

## Privacy Modes

Use `--privacy-mode` before the subcommand:

```bash
codex-usage-tracker --privacy-mode redacted dashboard --open
codex-usage-tracker --privacy-mode strict export --output usage-redacted.csv
codex-usage-tracker --privacy-mode strict query --since 2026-06-01
```

`normal` keeps local project metadata visible.

`redacted` hides raw `cwd` and source paths, hides Git remote labels, and replaces unnamed projects with stable hashed labels such as `Project ab12cd34`. Configured project aliases are treated as explicit display opt-ins.

`strict` also hides project-relative cwd, Git branch, and project tags.

Dashboard payloads and support bundles include the active mode so screenshots and support artifacts make their metadata posture visible.

## Support Bundles

Support bundles are designed for diagnostics without raw conversation content. They include package version, Python version, OS/platform, path existence checks, database schema state, refresh/parser diagnostics, pricing status, allowance status, threshold status, project config status, doctor results, and privacy metadata.

They do not include raw logs, aggregate rows, prompts, assistant messages, tool output, on-demand context text, or pasted transcript content. Known secret-like patterns are redacted from string fields before the bundle is written.

Default support bundles keep local diagnostic paths for troubleshooting. Before sharing a bundle publicly, generate it in strict mode:

```bash
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

Strict mode redacts local diagnostic path strings in the bundle and doctor details while keeping booleans, counts, statuses, and parser diagnostics available.

## Costs, Credits, And Allowance

Cost estimates are calculated only from aggregate token fields and your local pricing config. They are omitted when no matching model price is configured. Pricing refreshes pull only OpenAI's public pricing markdown and do not send local usage data anywhere.

Codex credit estimates are calculated only from aggregate token fields and bundled or locally configured rate-card values.

The optional allowance config is local and stores only the remaining percentages, reset times, or credit totals you manually enter. Observed rate-limit snapshots, when present in Codex token-count logs, store only structured percentages, window lengths, reset times, plan type, and limit id.

## Sharing Checklist

Before sharing a dashboard, CSV, JSON query result, or support bundle:

1. Use `--privacy-mode redacted` or `--privacy-mode strict` if project names, directories, branches, or tags are sensitive.
2. Use `--privacy-mode strict support-bundle` for public issues unless a maintainer specifically asks for normal-mode local path diagnostics.
3. Do not share local raw JSONL logs.
4. Do not enable or export on-demand context unless you have reviewed the content.
5. Prefer synthetic screenshots for public docs and issues.
6. Treat source paths and thread names as potentially sensitive even when raw messages are absent.
