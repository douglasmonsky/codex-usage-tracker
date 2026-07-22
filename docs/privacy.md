# Privacy Guide

Codex Usage Tracker is local-first. It reads Codex logs already written on your machine and, by default, stores aggregate usage metrics plus bounded local content snippets in SQLite so local MCP tools can support deeper investigation. The tracker does not upload usage data, logs, snippets, or reports.

The concise product-wide storage and output contract is documented in
[Data Posture](data-posture.md). This guide provides the detailed field,
selected-context, server, privacy-mode, and sharing rules behind that summary.

Use `codex-usage-tracker refresh --aggregate-only` or `codex-usage-tracker rebuild-index --aggregate-only` when you want the older aggregate-only SQLite posture.

## Stored In SQLite

The local SQLite database is stored at `~/.codex-usage-tracker/usage.sqlite3` by default. It can contain:

- session id, thread name, cwd, source file, turn id, and timestamps
- model, reasoning effort, context window, token counts, and derived efficiency ratios
- versioned usage fingerprints, canonical record pointers, exact-copy exclusion
  reasons, and copied-clone exclusion state; physical rows remain stored for
  local provenance while default totals use canonical rows
- subagent source, role, nickname, parent session id, and parent thread name when present
- call-origin category, reason, and confidence labels derived from event metadata during indexing
- archived-session flag, conservative thread key, adjacent aggregate record ids, and materialized thread-level summaries
- source-file provenance such as path, path hash, file size, mtime, indexed line and byte offsets, latest aggregate record id, parser diagnostics, and last indexed time
- observed Codex rate-limit snapshot metadata from local token-count logs, including plan type, limit id, 5-hour and weekly used percentages, window lengths, and reset times
- materialized allowance cohorts, reset-aware cycles and intervals, aggregate
  quality/coverage metrics, source revisions, and persisted statistical results
- diagnostic fact labels tied to aggregate call records, safe event categories, payload type labels, counts, timestamps, and line ranges
- pricing, credit, allowance, recommendation, and project metadata derived from aggregate fields
- aggregate OTel completion identifiers, token counters, normalized service
  tier/provenance, application version, semantic fingerprints, source cursors,
  and bounded reconciliation status from local
  `~/.codex-usage-tracker/otel/codex-completions*.jsonl` files
- normalized local content-index rows for local investigation, including conversation turns, bounded content fragments, tool calls, command runs, file events, source provenance, parser adapter metadata, parser warnings, and FTS5 search rows when SQLite supports FTS5
- bounded local investigation run summaries, including run kind, schema id, content-mode flags, strict summary JSON, branch counts, evidence counts, and timestamps

The content index is intended for local MCP/API exploration. It is not a hosted collection system and it does not change where the original Codex logs live. Normalized command and file-event rows store command roots/labels plus path hashes/basenames rather than full shell commands or full paths; bounded raw snippets remain confined to `content_fragments`.

The OTel completion reader accepts only `codex.sse_event` /
`response.completed` aggregate fields needed for conservative call matching and
tier classification. It never persists OTLP response bodies or arbitrary
attributes. Default exports do not expose staging fingerprints, source paths,
or matched record pointers. Support bundles report only whether the configured
completion directory exists and bounded aggregate refresh/reconciliation counts.
The exact response tier does not reveal whether ChatGPT credits or an API key
paid for the call; the tracker keeps that billing basis as separate local
configuration and defaults it to Unknown.

`rebuild-index` retains aggregate OTel staging so it can reconcile tiers after
canonical rows are recreated. Confirmed `reset-db --yes` deletes that staging
and its cursors. Neither operation changes or deletes the source exporter files.

Cloned Codex tasks can copy historical calls into another local JSONL file. The tracker keeps every physical row and its source metadata in SQLite, but default dashboard, CLI, MCP, report, recommendation, allowance, compression, and export totals use one canonical representative for strict fingerprint matches. Similar calls are never excluded on fuzzy evidence. Deduplication diagnostics expose aggregate totals plus bounded provenance metadata for excluded rows; they never include prompt, response, tool-output, or raw-log content.

## Shareable Outputs

Default shareable outputs omit indexed or raw content. That includes:

- CSV exports
- generated dashboard HTML
- support bundles
- dashboard screenshots generated for docs
- aggregate JSON reports
- recommendation reports
- allowance exports
- source coverage reports

Tier-aware shareable rows may include exact service-tier labels, API-equivalent
Standard/Priority cost scenarios, ChatGPT-equivalent credit scenarios, billing
basis, and source-stamped multiplier metadata. These are aggregate pricing
annotations and do not include authentication tokens or raw OTel payloads.

Those outputs should not include prompts, assistant messages, tool output, pasted secrets, raw snippets, reconstructed transcript evidence, indexed fragments, or full JSONL records unless a future command is explicitly documented as a local raw/content export.

Default totals and allowance intelligence use canonical usage rows. High-confidence
copied clone history is excluded and the excluded count is disclosed. The original
physical rows, source files, line numbers, and record ids stay in SQLite for local
provenance. Normal/strict allowance evidence returns aggregate provenance;
`privacy_mode=local` or the dashboard's **Show physical source links** control is
an explicit bounded opt-in to physical record identifiers. Fingerprinting does not
read or index transcript content, and fuzzy token-count similarity is diagnostic
only.

Privacy modes still affect metadata exposure. `normal` keeps local project metadata visible. `redacted` hides raw `cwd` and source paths, hides Git remote labels, and replaces unnamed projects with stable hashed labels such as `Project ab12cd34`. Configured project aliases are treated as explicit display opt-ins. `strict` also hides project-relative cwd, Git branch, and project tags.

## Diagnostic Facts

Diagnostic facts remain aggregate and label-oriented. They can store safe structured labels such as `patch_applied`, `function_call_output`, `post_compaction`, MCP tool/server labels, structured skill labels, command families such as `pytest`, `git`, or `unknown_command`, event counts, source line ranges, and token totals.

Diagnostic facts do not store raw tool arguments, command output, patch text, file contents, or raw JSONL fragments. If a future diagnostic needs indexed content, it should read the normalized content-index tables through an explicit local investigation API rather than hiding raw text in aggregate diagnostic fields.

On-demand diagnostic snapshots follow the same shareable-output boundary. Tool-output snapshots use terminal wrapper metadata such as `Original token count` when present and persist counts, coverage gaps, and safe function/command labels. Command snapshots keep command roots plus conservative one-level child labels. Git interaction snapshots keep only `git`/`gh` roots, safe operation labels, coarse categories, counts, and token coverage. File-read and file-modification snapshots persist counters, reader/event families, basename-only path labels, and short irreversible path hashes.

Diagnostic snapshots are not recomputed during ordinary dashboard or usage refresh. Stored snapshots can be displayed without rescanning source logs. Recalculation requires an explicit diagnostics `--refresh` command, batched localhost `/api/diagnostics/refresh` request, or targeted `/api/diagnostics/<section>/refresh` request. Localhost refresh requests run in a background worker and expose only aggregate progress metadata through the token-protected status endpoint.

## On-Demand Context

`usage_call_context`, `codex-usage-tracker context`, and the dashboard context endpoint read a selected source JSONL file only when explicitly requested. Returned context is redacted for common secret patterns and capped in size by default for CLI/MCP requests.

The Call Investigator uses the same endpoint at runtime to request quick redacted evidence for a selected call when the local context API is enabled. This endpoint still does not write raw context into CSV exports, support bundles, generated dashboard HTML, or shareable reports. Per-entry action timing in an evidence response is derived from already-read entry timestamps and contains numeric durations only.

Tool output is omitted by default for CLI/MCP/dashboard investigator context requests. The Call Investigator offers `Show tool output` when redacted, size-limited tool output is needed. Full serialized JSONL group analysis is also opt-in through `mode=full` / `Run full serialized analysis`; default quick mode returns only a fast serialized upper-bound estimate. Compacted replacement history remains omitted by default. Compaction metadata can show that replacement history exists, the entry count, and source line; replacement text is returned only for an explicitly requested selected call and is redacted before display.

Dashboard context loading can be disabled without restarting:

```bash
codex-usage-tracker serve-dashboard --no-context-api --open
```

The enable action is token-protected, localhost-only, and does not load selected-call context until a row-level context action is clicked.

For MCP users, `usage_call_context` is disabled unless the MCP server process has this environment variable:

```bash
CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1
```

Aggregate MCP tools do not require that opt-in.

## Localhost Server

The localhost server:

- binds only loopback hosts
- validates loopback `Host` and `Origin` headers
- protects refresh/context API calls with a random per-server token
- can disable the context API entirely
- serves aggregate dashboard/API routes without embedding raw transcript content into generated dashboard HTML
- serves `/api/status`, `/api/calls`, `/api/call`, `/api/threads`, `/api/thread-calls`, `/api/summary`, `/api/recommendations`, `/api/reports/pack`, `/api/investigations/agentic`, and compatibility `/api/usage` from SQLite-backed aggregate data
- exposes repeated-file, shell-churn, and large-low-output reports through
  `/api/investigations/*` with the same safe fields and raw-fragment flags as the
  corresponding MCP reports; the explicit investigation-walk route can use the
  local content/event index but still omits raw fragments
- exposes token-protected Compression Lab start, status, and profile routes
  using the same compact payload as MCP. The dashboard keeps only the
  aggregate profile in its in-memory query cache; candidate evidence, indexed
  excerpts, and raw fragments are not written to browser storage

The report pack contains aggregate report definitions, linked aggregate call
rows, a schema marker, and a server generation timestamp. It does not include
prompts, assistant text, tool output, command output, or indexed content.

Source JSONL reads happen during refresh/indexing, explicit on-demand context loading for one selected call, and explicit synthetic benchmark/diagnostic runs. Refresh also reads only local `codex-completions*.jsonl` OTLP exporter files for aggregate service-tier enrichment. Live refresh records source metadata and parser cursors so unchanged logs can be skipped and append-only growth can parse from the last indexed byte. Live aggregate APIs do not return indexed content unless an endpoint is explicitly documented as a local content investigation endpoint.

## Privacy Modes

Use `--privacy-mode` before the subcommand:

```bash
codex-usage-tracker --privacy-mode redacted dashboard --open
codex-usage-tracker --privacy-mode strict export --output usage-redacted.csv
codex-usage-tracker --privacy-mode strict query --since 2026-06-01
```

Dashboard payloads and support bundles include the active privacy mode so screenshots and support artifacts make the metadata posture visible.

## Support Bundles

Support bundles are designed for diagnostics without raw conversation content or indexed content fragments. They include package version, Python version, OS/platform, path existence checks, database schema state, refresh/parser diagnostics, pricing status, allowance status, threshold status, project config status, doctor results, and privacy metadata. They do not include raw logs, aggregate rows, prompts, assistant messages, tool output, on-demand context text, indexed content fragments, or pasted transcript content. Known secret-like patterns are redacted from string fields before a bundle is written.

Default support bundles keep local diagnostic paths for troubleshooting. Before sharing a bundle publicly, generate it in strict mode:

```bash
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

Strict mode redacts local diagnostic path strings in bundle doctor details while keeping booleans, counts, statuses, and parser diagnostics available.

## Costs, Credits, And Allowance

Cost estimates are calculated only from aggregate token fields and your local pricing config. They are omitted when no matching model price is configured. Pricing refreshes pull only OpenAI's public pricing markdown and do not send local usage data anywhere.

Codex credit estimates are calculated only from aggregate token fields and bundled or locally configured rate-card values. Confirmed Fast calls may apply the documented model-family credit multiplier; this does not change USD token-cost estimates. The optional allowance config stores only remaining percentages, reset times, and credit totals you manually enter. Observed rate-limit snapshots, when present in Codex token-count logs, store only structured percentages, window lengths, reset times, plan type, and limit id.

Allowance calibration and forecasts use canonical aggregate credits and observed
percentages. A displayed credits-per-percent value is a personal historical
estimate with cycle count and price coverage, not an official product conversion.

## Sharing Checklist

Before sharing a dashboard, CSV, JSON query result, support bundle, or screenshot:

1. Use `--privacy-mode redacted` or `--privacy-mode strict` when project names, directories, branches, or tags are sensitive.
2. Use `--privacy-mode strict support-bundle` for public issues unless a maintainer specifically asks for normal-mode local path diagnostics.
3. Do not share local raw JSONL logs.
4. Do not export on-demand context or indexed content unless you reviewed the content.
5. Prefer synthetic screenshots for public docs and issues.
6. Treat source paths and thread names as potentially sensitive even when raw messages are absent.
