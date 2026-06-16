# Usage Impact Read Model Roadmap

Branch: `refactor/usage-impact-read-model`
Base: `perf/parallel-refresh-indexing` after source-byte-offset context seek.

## Goals

- Create or harden a derived usage-impact read model for observed allowance/rate-limit movement per call and window.
- Keep exact observed rate-limit facts separate from inferred per-call allocation.
- Use refresh deltas so no-op refreshes do not recalculate usage impact and append refreshes touch only affected/adjacent records.
- Expose usage-impact data through stable CLI/API/dashboard surfaces without claiming exact billing truth.

## Non-Goals

- No Sessions tab.
- No task receipts.
- No frontend rewrite.
- No exact billing claims.
- No raw prompt, assistant, tool output, raw JSONL, compaction replacement text, or reconstructed transcript persistence.
- No publishing, tagging, or main-branch merge.

## Privacy Constraints

- Persist only aggregate counters, ids, timestamps, limit metadata, confidence/status labels, and derived numeric estimates.
- Do not store raw commands or command output by default.
- Raw evidence remains explicit, redacted, on-demand, and not written back to SQLite or generated dashboard HTML.

## Schema / Read Model

Target `usage_impact` table fields:

- `record_id TEXT NOT NULL`
- `window_type TEXT NOT NULL` (`primary`, `secondary`)
- `plan_type TEXT`
- `limit_id TEXT`
- `observed_used_percent REAL`
- `observed_window_minutes INTEGER`
- `observed_resets_at INTEGER`
- `previous_observed_record_id TEXT`
- `previous_observed_used_percent REAL`
- `next_observed_record_id TEXT`
- `delta_used_percent REAL`
- `tokens_since_previous INTEGER`
- `estimated_tokens_per_percent REAL`
- `estimated_usage_credits REAL`
- `confidence TEXT NOT NULL` (`high`, `medium`, `low`, `unknown`)
- `status TEXT NOT NULL` (`fresh`, `pending`, `stale`, `unavailable`)
- `reason TEXT`
- `recalculated_at TEXT NOT NULL`
- primary key: `(record_id, window_type)`

## Implementation Checklist

- [ ] M0: Add this roadmap/checklist before implementation.
- [ ] M1: Audit existing usage-impact code and mark what already satisfies this roadmap.
- [ ] M2: Add or repair `usage_impact` schema, migration, indexes, and repair behavior.
- [ ] M3: Add calculator behavior for observed primary/secondary deltas and confidence/status labels.
- [ ] M4: Wire refresh-delta invalidation so no-op skips work and append/full-reparse rebuild affected intervals only.
- [ ] M5: Expose usage-impact CLI/API/call payload contracts with schema id `codex-usage-tracker-usage-impact-v1`.
- [ ] M6: Add compact dashboard call-detail chips without exact-billing language.
- [ ] M7: Add focused tests for windows, pools, no-op, append, ambiguity, JSON contracts, and privacy.
- [ ] M8: Run validation and benchmarks.
- [ ] M9: Commit, push, and open the branch PR without merging to `main`.

## Tests

- Primary and secondary windows remain separate.
- Compatible limit pools are compared; ambiguous pools are pending or low confidence.
- Adjacent observed intervals update when one record changes.
- No-op refresh does not invalidate/recalculate usage impact.
- Append refresh updates only inserted/affected adjacent observed intervals.
- JSON contracts expose no raw content.
- Privacy tests prove no raw content is persisted.

## Validation

- `python -m pytest tests/test_usage_impact.py`
- `python -m pytest tests/test_usage_impact_cache.py`
- `python -m pytest tests/test_store_dashboard_mcp.py`
- `python -m pytest tests/test_json_contracts.py`
- `python -m pytest tests/test_privacy.py`
- `python scripts/check_release.py`
- broader branch validation before PR.

## Known Caveats

- Usage impact is estimated from observed local Codex rate-limit snapshots and may exclude external usage or rounded snapshot changes.
- Confidence/status must communicate uncertainty; never call inferred per-call impact exact billing impact.
