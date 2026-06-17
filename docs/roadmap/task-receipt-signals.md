# Task Receipt Signals Roadmap

Branch: `feature/task-receipt-signals`
Base: stacked after `refactor/live-dashboard-read-model-api` until the read-model stack reaches `main`.

## Goals

- Add an aggregate-only task receipt signal layer that helps users distinguish costly work that produced durable project progress from costly work that only explored, retried, or produced transient output.
- Keep receipt signals safe: persist counts, categories, timestamps, ids, hashes, and derived labels only.
- Attach receipt summaries to calls, work sessions, and context epochs without reading or storing raw prompts, assistant messages, tool output, raw commands, command output, file contents, or raw JSONL fragments.
- Rebuild receipt read models incrementally from refresh deltas and affected thread keys.

## Non-Goals

- No raw evidence cache.
- No raw command text or command output persistence.
- No task-quality scoring from transcript content.
- No frontend rewrite.
- No publishing, tagging, or main-branch merge.
- No lifecycle recommendation overhaul; this branch only creates the signal foundation lifecycle recommendations can consume later.

## Privacy Constraints

- Do not persist prompts, assistant messages, tool output, raw JSONL fragments, compaction replacement text, or reconstructed transcript content.
- Do not persist raw shell commands, patch contents, file paths from tool output, or test output.
- Durable-output evidence is explicit and on-demand only through existing raw evidence controls.
- Persist only aggregate receipt metadata such as event category, count, timestamp, source line, hashed identifiers when needed, and derived confidence labels.
- Fixtures and docs must use synthetic data only.

## Receipt Categories

V1 categories should be conservative and derived from stable event envelopes:

- `patch_applied`: a patch/application event occurred.
- `tool_activity`: one or more tool/MCP/function-call completion events occurred.
- `user_confirmed`: a user message follows the work and may confirm next intent or completion.
- `task_complete`: an explicit task completion event occurred if Codex emits one.
- `no_receipt`: no durable-output-like signal is visible near the call.
- `unknown`: event shape is known too weakly to classify.

These categories are signals, not proof of correctness.

## Schema / Read Model

Add a `task_receipts` table:

- `receipt_id TEXT PRIMARY KEY`
- `record_id TEXT NOT NULL`
- `thread_key TEXT`
- `work_session_id TEXT`
- `context_epoch_id TEXT`
- `receipt_category TEXT NOT NULL`
- `receipt_confidence TEXT NOT NULL` (`high`, `medium`, `low`, `unknown`)
- `event_count INTEGER NOT NULL`
- `first_event_timestamp TEXT`
- `last_event_timestamp TEXT`
- `first_source_line INTEGER`
- `last_source_line INTEGER`
- `evidence_scope TEXT NOT NULL` (`same_turn`, `between_calls`, `session_window`)
- `reason TEXT`
- `updated_at TEXT NOT NULL`

Indexes:

- `task_receipts(record_id)`
- `task_receipts(thread_key)`
- `task_receipts(work_session_id)`
- `task_receipts(context_epoch_id)`
- `task_receipts(receipt_category, receipt_confidence)`

## Parser / Store Work

- Extend aggregate parser state with receipt counters for known non-token event envelopes between token-count events.
- Do not store event text, command strings, arguments, file content, or tool output.
- Attach per-call receipt counters to emitted usage events or materialize them from source event metadata.
- Rebuild `task_receipts` for affected record ids/thread keys only during append refresh.
- On no-op refresh, skip receipt rebuilds.
- On full reparse, delete stale receipts for deleted records and rebuild changed ranges.

## CLI / API / JSON Contracts

- Add `codex-usage-tracker task-receipts`.
- Add `codex-usage-tracker task-receipts --record-id ...`.
- Add `/api/task-receipts`.
- Add schema id `codex-usage-tracker-task-receipts-v1`.
- Include compact receipt summaries in `/api/call` and work-session/context-epoch detail payloads where practical.

## Dashboard

- In the call investigator, show a compact **Task receipt signals** section after exact token accounting.
- In Sessions and Context segments, show receipt category counts as compact chips.
- Use cautious wording such as "receipt signal" or "durable-output signal"; never claim a task was objectively completed.

## Implementation Checklist

- [x] M0: Add this roadmap/checklist before implementation.
- [ ] M1: Audit available safe event envelopes and classify V1 receipt categories.
- [ ] M2: Add task receipt schema, migration, indexes, and repair behavior.
- [ ] M3: Add aggregate-only parser/store receipt collection.
- [ ] M4: Materialize task receipts incrementally from affected refresh deltas.
- [ ] M5: Expose CLI/API/JSON contracts.
- [ ] M6: Add compact dashboard investigator/session/epoch receipt signals.
- [ ] M7: Add parser, migration, refresh, JSON contract, dashboard, and privacy tests.
- [ ] M8: Run validation and benchmarks.
- [ ] M9: Commit, push, and open the branch PR without merging to `main`.

## Tests

- Known synthetic patch/tool/task-complete envelopes produce receipt categories.
- Unclassified known non-token events do not produce false durable-output claims.
- No-op refresh skips receipt rebuilds.
- Append refresh rebuilds only affected receipt rows.
- Full reparse removes stale receipt rows for deleted records.
- CLI/API responses expose only aggregate receipt metadata.
- Generated dashboard HTML does not include raw transcript, command, tool output, or JSONL fragments.

## Known Caveats

- V1 receipt signals are evidence of workflow activity, not evidence that the user's task succeeded.
- Some durable outcomes may only be visible in raw tool output or filesystem state; this read model intentionally avoids persisting those details.
- Later lifecycle recommendations can consume this table to distinguish "expensive but productive" from "expensive and low-evidence" work.
