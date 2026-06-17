# Live Dashboard Read-Model API Roadmap

Branch: `refactor/live-dashboard-read-model-api`
Base: `feature/context-epochs`

## Goals

- Move the live dashboard frontend away from compatibility `/api/usage` row payloads.
- Hydrate visible dashboard tables from smaller SQL-backed read-model endpoints.
- Keep `/api/usage` for static dashboard export and compatibility.
- Make live refresh status-driven: no-op status refreshes should update status cards only, while changed data reloads only the active view.
- Preserve privacy behavior: raw evidence stays explicit, redacted, on-demand, and uncached.

## Non-Goals

- Do not remove `/api/usage`.
- Do not rewrite static dashboard export.
- Do not add task receipts, lifecycle recommendations, worker pools, or new raw evidence caching.
- Do not publish, tag, or merge to `main`.

## Privacy Constraints

- Read-model endpoints return aggregate rows only.
- Raw prompts, assistant messages, tool output, raw JSONL fragments, compaction replacement text, and reconstructed transcript content must not be embedded in generated dashboard HTML or persisted to SQLite.
- `/api/context` remains the only raw evidence path and must require explicit runtime access.

## Implementation Checklist

- [x] M0: Add this roadmap/checklist before implementation.
- [ ] M1: Audit current live frontend/API usage and preserve `/api/usage` compatibility.
- [ ] M2: Keep Calls hydration on `/api/calls` with status-driven refresh behavior.
- [ ] M3: Move Threads list and expanded thread calls to `/api/threads` and `/api/thread-calls`.
- [ ] M4: Keep Sessions list and context-segment expansion on `/api/sessions`, `/api/session`, and `/api/context-epochs`.
- [ ] M5: Make live refresh reload only the active view when status changes.
- [ ] M6: Add tests for active-view endpoint usage, no full-payload reloads, and static compatibility.
- [ ] M7: Run validation, commit, push, and open the branch PR without merging to `main`.

## Endpoint Targets

- `/api/status`: cheap freshness checks and optional refresh result.
- `/api/calls`: Calls table slices.
- `/api/threads`: Threads table slices.
- `/api/thread-calls`: expanded thread-call slices.
- `/api/sessions`: Sessions table slices.
- `/api/session`: single session detail payload.
- `/api/context-epochs`: expanded session context-segment slices.
- `/api/call`: direct investigator hydration.
- `/api/context`: explicit raw evidence only.

## Tests

- Status refresh does not include table rows.
- Calls hydration uses `/api/calls`, not `/api/usage`.
- Threads hydration uses `/api/threads`, not browser-side grouping of all calls.
- Expanded thread calls use `/api/thread-calls`.
- Sessions hydration remains SQL-backed.
- Static dashboard export and `/api/usage` compatibility remain intact.
- Privacy tests continue to prove raw context is absent from generated dashboard HTML and read-model APIs.

## Validation

- `python -m pytest tests/test_dashboard_data.py`
- `python -m pytest tests/test_dashboard_server.py`
- `python -m pytest tests/test_dashboard_payload.py`
- `python -m pytest tests/test_privacy.py`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_data.js`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_live.js`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard_tables.js`
- `node --check src/codex_usage_tracker/plugin_data/dashboard/dashboard.js`
- `python scripts/check_release.py`
