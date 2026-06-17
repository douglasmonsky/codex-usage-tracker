# Context Epochs Roadmap

## Goal

Add context epochs inside each thread work session so the tracker can explain how compaction boundaries split a session into smaller context segments.

Hierarchy:

```text
Thread
  Work session, split by cold-cache resumes
    Context epoch, split by compactions
      Calls
```

User-facing label: **Context segment**.

Internal term: `thread_context_epochs`.

## Non-Goals

- Do not add task receipts.
- Do not add durable artifact scoring.
- Do not add lifecycle recommendations.
- Do not persist raw prompts, assistant messages, tool output, raw JSONL fragments, compaction replacement text, or reconstructed transcript content.
- Do not remove or rename existing Sessions, Calls, Threads, CLI, API, MCP, or JSON contracts.

## Privacy Constraints

- Persist aggregate counters, ids, timestamps, categorical compaction/start reasons, and derived metadata only.
- Raw evidence and compaction replacement history remain explicit, redacted, on-demand reads from local source logs.
- Epoch tables must not store raw commands, raw command output, prompt text, assistant text, tool output, or raw JSONL snippets.

## Boundary Rule

A new context epoch starts:

- at the first call in a work session, or
- at a call whose `call_initiator_reason` is `post_compaction`.

Compaction inside a work session splits epochs, but it does not create a new work session.

## Planned Schema

Add `thread_context_epochs`:

- `context_epoch_id TEXT PRIMARY KEY`
- `work_session_id TEXT NOT NULL`
- `thread_key TEXT NOT NULL`
- `epoch_index INTEGER NOT NULL`
- `start_record_id TEXT NOT NULL`
- `end_record_id TEXT NOT NULL`
- `start_reason TEXT NOT NULL`
- `compaction_before_record_id TEXT`
- `compaction_detected_at TEXT`
- `started_at TEXT NOT NULL`
- `ended_at TEXT NOT NULL`
- `duration_minutes REAL NOT NULL`
- `call_count INTEGER NOT NULL`
- token/cache/context aggregate columns
- first-call post-compaction diagnostics
- subagent/auto-review counters
- `compaction_effectiveness TEXT`
- `updated_at TEXT NOT NULL`

## Tests

- No compaction creates one epoch.
- A `post_compaction` call starts a new epoch.
- Compaction inside a session does not create a new work session.
- Epoch totals sum to session totals.
- Affected-thread rebuild updates epochs only for affected threads.
- API/dashboard payloads stay aggregate-only.
- Privacy tests confirm no raw context is persisted.

## Milestones

- [x] M0: Add context epochs checklist.
- [ ] M1: Add context epoch schema.
- [ ] M2: Build epochs from work sessions.
- [ ] M3: Add epoch query/API payload support.
- [ ] M4: Add Sessions dashboard epoch expansion.
- [ ] M5: Add compaction effectiveness heuristics.
- [ ] M6: Add tests/docs and run validation.
- [ ] M7: Commit, push, and open the branch PR without merging to `main`.
