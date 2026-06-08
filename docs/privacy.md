# Privacy Guide

Codex Usage Tracker is designed around aggregate local analysis for local AI coding-agent usage. It reads supported source logs already written on your machine and avoids storing raw transcript content.

## Stored In SQLite

The local SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default and contains aggregate metrics:

- session id, thread name, cwd, source file, source provider/app/format, turn id, timestamps
- model, reasoning effort, context window
- token counts and derived efficiency ratios
- subagent source, role, nickname, parent session id, and parent thread name when present
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

Claude Code support follows the same aggregate-only rule. The indexer reads local JSONL files under `~/.claude/projects`, extracts usage counters and metadata-like identifiers, and does not persist prompts, assistant text, or tool output.

## On-Demand Context

`usage_call_context`, `codex-usage-tracker context`, and the `serve-dashboard` context endpoint read a single source JSONL file only when explicitly requested. Returned context is redacted for common secret patterns and capped in size.

The context API can be disabled:

```bash
codex-usage-tracker serve-dashboard --no-context-api --open
```

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

## Costs, Credits, And Allowance

Cost estimates are calculated only from aggregate token fields and your local pricing config. They are omitted when no matching model price is configured. Pricing refreshes pull only OpenAI's public pricing markdown and do not send local usage data anywhere. Non-OpenAI model prices can be added through local manual pricing overrides.

Codex credit estimates are calculated only from aggregate token fields and bundled or locally configured rate-card values. They apply only to Codex/OpenAI rows; Claude Code and other non-Codex rows are marked `not_applicable` for credit confidence.

The optional allowance config is local and stores only the remaining percentages, reset times, or credit totals you manually enter.

## Sharing Checklist

Before sharing a dashboard, CSV, JSON query result, or support bundle:

1. Use `--privacy-mode redacted` or `--privacy-mode strict` if project names, directories, branches, or tags are sensitive.
2. Do not share local raw JSONL logs.
3. Do not enable or export on-demand context unless you have reviewed the content.
4. Prefer synthetic screenshots for public docs and issues.
5. Treat source paths and thread names as potentially sensitive even when raw messages are absent.
