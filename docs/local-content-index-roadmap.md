# Local Content Index Roadmap

This roadmap describes the experimental direction for evolving Codex Usage Tracker from
aggregate-only usage diagnostics into local content-indexed MCP exploration.

The goal is to give local MCP tools enough structured context to investigate why usage
was expensive, repetitive, noisy, or confusing, while keeping the product local-first and
clear about what is safe to share.

## Product Stance

Codex logs already exist on the user's machine. The tracker should make those local logs
more useful by building a structured local content index by default, with an aggregate-only
mode available for users who want the older storage posture.

New stance:

- Local content indexing is enabled by default for richer diagnostics.
- Nothing is uploaded by the tracker.
- Aggregate-only mode remains available through config and refresh/setup options.
- Shareable reports omit indexed content and raw fragments by default.
- Raw/content exports are explicit, local, and unredacted.

This is a pre-1.0 direction change. Implementation PRs must update product docs,
privacy docs, setup text, and support-bundle language before changing behavior.

## No-Redaction Policy

The tracker should not promise redaction for indexed content. Redaction heuristics are
fragile, create false confidence, and are difficult to validate across prompts, tool
output, secrets, source paths, pasted data, and project-specific identifiers.

Use an omit-or-include model instead:

- Default exports, support bundles, public screenshots, and shareable reports omit content
  fields entirely.
- Raw/content exports require explicit user action.
- Raw/content exports are unredacted and must tell the user to review before sharing.
- APIs must declare whether a payload is aggregate-only, indexed-content, or raw-fragment.

Suggested payload metadata:

```json
{
  "content_mode": "aggregate_only",
  "includes_indexed_content": false,
  "includes_raw_fragments": false
}
```

For explicit local content tools:

```json
{
  "content_mode": "indexed_content",
  "includes_indexed_content": true,
  "includes_raw_fragments": false
}
```

## Storage Architecture

SQLite remains the canonical store. The next architecture should add normalized content
tables plus SQLite FTS5, rather than introducing Postgres, a graph database, or a vector
database as the primary store.

Recommended table families:

- `usage_events`: existing aggregate usage and pricing facts.
- `source_records`: source JSONL provenance, file path, line number, record hash, parser
  adapter, parser version, raw event shape label, parse warnings, and refresh metadata.
- `conversation_turns`: normalized user, assistant, system, and tool-result turns.
- `tool_calls`: tool name, call id, arguments summary shape, timing, status, output size,
  source linkage, and token linkage.
- `command_runs`: command root, bounded command label, exit status, duration, output size,
  failure category, retry group, source linkage, and token linkage.
- `file_events`: file read/write/edit events, operation type, path identity, extension,
  basename, path hash, and source linkage.
- `content_fragments`: bounded local text snippets selected for search, with role,
  fragment kind, content hash, size, source pointer, and token linkage.
- `content_fts`: FTS5 virtual table over searchable fragments and safe labels.
- `diagnostic_facts`: derived reusable facts, separate from base parsed records.
- `investigation_runs`: MCP hypothesis scans, scoring results, pruned branches, and
  evidence links.

Do not make the database a blind mirror of every JSONL payload. Store normalized facts,
bounded snippets, hashes, sizes, and source pointers. Full raw retrieval can remain
on-demand from the original source logs when an explicit tool asks for it.

## Parser And Format Drift

The parser should not let downstream diagnostics depend directly on OpenAI's current
raw JSONL shape.

Target flow:

```text
raw Codex JSONL
  -> format detector
  -> parser adapter
  -> normalized internal records
  -> derived diagnostics
  -> MCP/API exploration tools
```

Requirements:

- Keep parser adapters versioned and additive.
- Store adapter name, parser version, source record hash, and observed raw shape label.
- Preserve unknown event shapes as parser diagnostics instead of failing refresh.
- Prefer partial parse over failed refresh.
- Track parser coverage: parsed records, unknown shapes, recognized turns, recognized
  tool calls, recognized commands, recognized file events, and skipped content fragments.
- Maintain synthetic golden fixtures for every known Codex log shape.
- Make reindexing possible when parser adapters improve.

Important rule: store facts separately from interpretations.

Example fact:

- A command root ran seven times in one thread.
- Five runs failed.
- The related calls consumed 120k tokens.

Example interpretation:

- This is likely command-loop waste.

Keeping these separate makes diagnostics auditable and lets future detectors improve
without corrupting the base data.

## MCP And API Direction

The MCP should become an exploratory diagnostics interface over the normalized local
index, not just a collection of summary endpoints.

Initial content-index tools:

- `usage_content_search`: search indexed local fragments and safe labels with filters for
  thread, role, tool, command, file event, date, model, effort, and token impact.
- `usage_thread_trace`: return a structured thread timeline linking turns, tool calls,
  command runs, file events, token movement, cache behavior, and source pointers.

Second-stage pattern tools:

- `usage_repetition_scan`: find repeated asks, repeated file reads, repeated commands, and
  repeated tool-output patterns.
- `usage_context_bloat_scan`: find long-thread drift, cold resumes, low cache reuse, and
  tool-output context pressure.
- `usage_command_loop_scan`: find repeated command failures and retry loops.
- `usage_file_churn_scan`: find high-token file read/edit patterns and repeated
  rediscovery of the same repo facts.

Third-stage investigation tool:

- `usage_investigation_walk`: run a bounded hypothesis search over the APIs, score
  evidence, prune weak branches, and return a compact grounded report.

Investigation walk inputs:

```json
{
  "goal": "token_waste",
  "time_window": "recent",
  "max_branches": 8,
  "max_depth": 4,
  "content_mode": "indexed_content"
}
```

Investigation walk output should include:

- top findings
- evidence links
- confidence
- caveats
- pruned hypotheses
- recommended action
- next best drill-down

The MCP skill should route prompts such as "look through my usage for token waste" to
these tools instead of producing generic advice.

## Export And Sharing Behavior

Default shareable artifacts:

- aggregate-only
- no indexed snippets
- no raw fragments
- no prompts
- no assistant text
- no tool output
- no file contents

Explicit local content exports:

- require a raw/content flag or separate command
- are unredacted
- write local files only
- include a warning to review before sharing
- declare content classes included

Support bundles should remain aggregate/content-omitting by default. If a future support
workflow needs content, it must be a separate explicit local artifact.

## Aggregate-Only Mode

Aggregate-only mode should remain available for users who prefer the old storage model or
want smaller databases.

Possible controls:

```bash
codex-usage-tracker setup --aggregate-only
codex-usage-tracker refresh --aggregate-only
codex-usage-tracker config set content_index.enabled false
```

The final interface can differ, but implementation must provide a clear documented way to
disable content indexing before the default changes.

## Phased Milestones

### Milestone 1: Roadmap And Compatibility Prep

- Land this roadmap.
- Open an experimental implementation branch.
- Keep current runtime behavior unchanged.
- Update future implementation plans to call out the product stance change explicitly.

### Milestone 2: Source Provenance Foundation

- Add `source_records` and parser adapter metadata.
- Store source record hashes, source pointers, parser versions, raw shape labels, and parse
  warnings.
- Add parser coverage reporting.
- Add synthetic fixtures for known event shapes.
- Keep existing aggregate refresh behavior compatible.

### Milestone 3: Normalized Content Index

- Add normalized turns, tool calls, command runs, file events, and bounded content
  fragments.
- Add FTS5 search when available.
- Add aggregate-only mode before enabling content index by default.
- Keep full raw retrieval on-demand from original source logs.

### Milestone 4: Search And Trace MCP Tools

- Add `usage_content_search`.
- Add `usage_thread_trace`.
- Update source and packaged skills to route content-search and thread-trace questions to
  the new tools.
- Ensure tool outputs declare content mode and do not feed raw fragments into shareable
  reports by accident.

### Milestone 5: Pattern Diagnostics

- Add repeated file-read, command-loop, tool-output bloat, repeated-restatement, and
  context-bloat detectors.
- Store derived facts separately from interpretations.
- Add focused tests with synthetic logs that prove detectors are evidence-backed and do not
  require real logs.

### Milestone 6: Investigation Walk

- Add hypothesis library and scoring.
- Add branch pruning.
- Add compact investigation reports.
- Add skill guidance so MCP can answer "what is wasting tokens?" using structured evidence.

## Next Actionable MCP Insight Diagnostics

These follow-on diagnostics should turn the local content/event index into sharper
recommendations instead of broad summaries.

### Top Repeated File Rediscovery

Add an endpoint/MCP tool that ranks exact safe file identities by repeated local
rediscovery. It should group by path hash, basename, extension, operation, and
thread/session linkage while omitting full paths by default.

Useful output:

- repeated path hash count
- unique threads and calls touching the file
- linked aggregate token totals
- first/last observed timestamps
- operation mix such as read, edit, or write
- safe drill-down handles for `usage_thread_trace`

Acceptance criteria:

- Does not expose full paths unless an explicit raw/local export mode is added.
- Ranks repeated file reads separately from actual edit/write churn.
- Flags files reread many times across adjacent calls as rediscovery candidates.
- Includes synthetic tests with repeated reads of the same file and unrelated
  same-extension reads.

### Shell Churn Diagnostic

Add an endpoint/MCP tool for repeated shell command families and shell-loop
sequences, especially `sed`, `rg`, `git`, `nl`, test commands, package commands,
and repeated unknown command labels.

Useful output:

- command root, bounded command label, status, exit code, retry group
- adjacent-run loop evidence within the same thread/session
- linked aggregate token totals and output byte totals
- failure/retry categories
- recommended action such as "use a script", "cache this query result", or
  "summarize findings once before continuing"

Acceptance criteria:

- Separates productive one-off shell work from repetitive churn.
- Detects high-frequency successful loops as well as failing retries.
- Groups safely by command root/label without raw command output.
- Includes tests for repeated `sed`/`rg`/`git`/`nl` sequences and mixed benign
  commands.

### Large Low-Output Calls

Add an aggregate-first report/MCP tool for calls that consume large input/context
but produce little output. These are strong token-waste candidates because they
often mean the model paid to carry context without making much progress.

Useful output:

- total/input/cached/uncached/output/reasoning token counts
- cache ratio and context-window percent
- thread/session/call timestamp
- nearby command/file/tool activity counts
- candidate explanation such as cold resume, tool-output pressure, stale thread,
  or low-value continuation

Acceptance criteria:

- Defaults to aggregate-only output.
- Supports thresholds for minimum total tokens and maximum output tokens.
- Can be used by `usage_investigation_walk` as a first-class evidence branch.
- Includes tests for high-input low-output calls, high-output false positives,
  and low-cache cold-resume cases.

## Testing Requirements

Each implementation milestone must include:

- migration tests from existing databases
- synthetic parser fixtures for raw-shape coverage
- refresh idempotency tests
- aggregate-only mode tests
- FTS availability/fallback tests
- MCP contract tests
- export/support-bundle content-mode tests
- installed package smoke coverage before release

Content-index tests must use synthetic logs only. Do not commit real Codex logs, real
prompts, real assistant messages, real tool output, or private project data as fixtures.

## Open Decisions For Implementation

These are intentionally deferred until the experimental branch starts implementation:

- exact schema column names
- exact config command names
- FTS tokenizer choice
- whether bounded snippets are stored by default in the first implementation slice
- whether semantic embeddings are added later as an optional local index
- whether DuckDB is useful for heavy analytical exports

The first experimental implementation should start with source provenance and parser
adapter metadata before adding searchable text.
