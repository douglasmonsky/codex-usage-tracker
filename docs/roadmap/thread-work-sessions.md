# Thread Work Sessions Roadmap

Branch: `feature/thread-work-sessions`
Base: `refactor/usage-impact-read-model` after the incremental refresh and usage-impact read-model work.

## Goals

- Add a Sessions read model that groups calls within a thread into contiguous work sessions.
- Split sessions at cold-cache resume boundaries so users can see where a thread effectively restarted.
- Surface high-uncached, low-cache, long-running, or handoff-worthy sessions without reading raw transcript content.
- Rebuild sessions incrementally for only affected thread keys during append refreshes.

## Non-Goals

- No task receipts.
- No artifact scoring.
- No context epochs, except lightweight compaction counts if already available from aggregate metadata.
- No parallel parser worker pool.
- No raw prompt, assistant, tool output, raw JSONL, compaction replacement text, or reconstructed transcript persistence.
- No publishing, tagging, or main-branch merge.

## Privacy Constraints

- Persist only aggregate counters, ids, categorical metadata, timestamps, line numbers, and derived recommendations.
- Do not persist prompts, assistant messages, tool output, raw commands, raw JSONL fragments, or message snippets.
- Raw evidence remains explicit, redacted, on-demand, and never written to SQLite, generated dashboard HTML, CSV exports, or fixtures.
- Tests and screenshots must use synthetic aggregate data only.

## Cold-Cache Boundary V1

A call starts a new work session when it is the first call in a thread or when it is classified as a cold-cache resume.

A call is a cold-cache resume boundary when it has a previous call in the same thread and either:

- Idle resume: idle gap is at least `cold_resume_idle_minutes`, input tokens are at least `cold_resume_min_input_tokens`, uncached input tokens are at least `cold_resume_min_uncached_tokens`, and cache ratio is at most `cold_resume_max_cache_ratio`.
- Huge miss: uncached input tokens are at least `cold_resume_huge_uncached_tokens` and cache ratio is at most `cold_resume_huge_max_cache_ratio`.

Repeated boundaries are suppressed when the previous cold-cache boundary in that thread occurred within `cold_resume_cluster_suppression_minutes`.

## Threshold Config

Add local threshold keys with conservative defaults:

- `cold_resume_idle_minutes`
- `cold_resume_max_cache_ratio`
- `cold_resume_min_input_tokens`
- `cold_resume_min_uncached_tokens`
- `cold_resume_huge_uncached_tokens`
- `cold_resume_huge_max_cache_ratio`
- `cold_resume_cluster_suppression_minutes`

Unknown threshold keys remain ignored, and missing new keys fall back to defaults for older local configs.

## Schema / Read Model

Add table `thread_work_sessions`:

- `work_session_id TEXT PRIMARY KEY`
- `thread_key TEXT NOT NULL`
- `thread_label TEXT`
- `session_index INTEGER NOT NULL`
- `start_record_id TEXT NOT NULL`
- `end_record_id TEXT NOT NULL`
- `cold_start_record_id TEXT`
- `start_reason TEXT NOT NULL`
- `started_at TEXT NOT NULL`
- `ended_at TEXT NOT NULL`
- `duration_minutes REAL NOT NULL`
- `idle_minutes_before REAL`
- `call_count INTEGER NOT NULL`
- `model_summary TEXT`
- `effort_summary TEXT`
- `input_tokens INTEGER NOT NULL`
- `cached_input_tokens INTEGER NOT NULL`
- `uncached_input_tokens INTEGER NOT NULL`
- `output_tokens INTEGER NOT NULL`
- `reasoning_output_tokens INTEGER NOT NULL`
- `total_tokens INTEGER NOT NULL`
- `avg_cache_ratio REAL NOT NULL`
- `min_cache_ratio REAL NOT NULL`
- `max_context_window_percent REAL NOT NULL`
- `largest_uncached_record_id TEXT`
- `largest_uncached_input_tokens INTEGER NOT NULL`
- `cold_resume_uncached_tokens INTEGER NOT NULL`
- `compaction_count INTEGER NOT NULL DEFAULT 0`
- `subagent_call_count INTEGER NOT NULL DEFAULT 0`
- `auto_review_call_count INTEGER NOT NULL DEFAULT 0`
- `suggested_next_action TEXT`
- `recommendation_score REAL`
- `recommendation_reasons_json TEXT NOT NULL DEFAULT '[]'`
- `updated_at TEXT NOT NULL`

Indexes:

- `(thread_key, session_index)`
- `started_at`
- `total_tokens`
- `uncached_input_tokens`
- `suggested_next_action`

## Store Work

- Add `store_work_sessions.py`.
- Add `rebuild_thread_work_sessions(conn, thread_keys=None)`.
- Add `query_thread_work_sessions(...)`.
- Add `query_thread_work_session(...)`.
- During normal refresh, rebuild work sessions after affected-thread adjacency and thread summaries, using only affected thread keys.
- Keep full rebuild behavior available for repair and maintenance flows.

## CLI / API / JSON Contracts

- Add `codex-usage-tracker sessions`.
- Add `codex-usage-tracker sessions --thread-key ...`.
- Add `codex-usage-tracker sessions --json`.
- Add `/api/sessions`.
- Add `/api/session`.
- Add JSON schema ids:
  - `codex-usage-tracker-sessions-v1`
  - `codex-usage-tracker-work-session-v1`

## Dashboard

Add a Sessions tab after Threads:

- Insights
- Calls
- Threads
- Sessions

Sessions default sort:

- `uncached_input_tokens desc`

Columns:

- Thread
- Started
- Ended
- Idle before
- Duration
- Calls
- Total tokens
- Uncached input
- Cache ratio
- Largest miss
- Context peak
- Suggested action

Filters:

- Cold resumes only
- High uncached
- Needs handoff
- Recent
- Active sessions only / All history

## Implementation Checklist

- [x] M0: Create this roadmap/checklist before implementation.
- [x] M1: Add threshold defaults, config template coverage, and docs wording.
- [x] M2: Add `thread_work_sessions` schema, migration, indexes, and repair behavior.
- [x] M3: Add materializer and query helpers with synthetic unit tests.
- [x] M4: Wire affected-thread refresh rebuilds without global session rebuilds on append/no-op.
- [x] M5: Add CLI, API, and JSON contract coverage.
- [x] M6: Add Sessions dashboard tab with SQL-backed row loading.
- [x] M7: Update docs and run full branch validation.
- [x] M8: Commit, push, and open the branch PR without merging to `main`.

## Tests

- Thread with no cold resume creates one work session.
- Cold-cache resume creates two work sessions, and the cold boundary call starts the second session.
- Huge uncached miss creates a boundary even without the idle threshold.
- Boundary cluster suppression prevents repeated session splits within the suppression window.
- Partial affected-thread rebuild matches full rebuild for changed thread keys.
- Full reparse removes stale sessions for old thread keys.
- CLI and API responses expose aggregate-only session data.
- Dashboard renders the Sessions tab from synthetic aggregate data.

## Validation

- `python -m pytest tests/test_store_work_sessions.py`
- `python -m pytest tests/test_store_dashboard_mcp.py`
- `python -m pytest tests/test_json_contracts.py`
- `python -m pytest tests/test_privacy.py`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- `python scripts/check_release.py`

## Known Deferred Work

- Context epochs split by explicit compaction events.
- Task receipts and artifact signals.
- Worker-pool parsing.
- Broader frontend read-model migration.
