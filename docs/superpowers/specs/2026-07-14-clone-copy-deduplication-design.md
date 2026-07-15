# Clone/Copy Usage Deduplication Design

## Goal

Prevent copied historical usage events in cloned Codex tasks from being billed or reported twice while continuing to count genuinely new calls made in the clone. Preserve every parsed source row for provenance and debugging without indexing transcript content.

## Principles

- Default totals are logical billable usage, not physical source-row counts.
- Only exact, high-confidence identities are automatically excluded.
- Similar token shapes are diagnostic evidence only and never trigger exclusion.
- Physical provenance remains queryable through a dedicated diagnostic surface.
- Identity lookup and classification use indexed operations with a constant number of database operations per parsed event. No FTS or content scan participates in deduplication.
- Existing databases are migrated and backfilled so historical clone overcounts are corrected after upgrade.

## Logical Identity

Each parsed `UsageEvent` gains these persisted fields:

- `upstream_usage_id`: optional stable upstream usage/event/call identifier, including its recognized source key.
- `usage_fingerprint`: versioned SHA-256 identity for the logical usage call.
- `canonical_record_id`: stable logical ID derived from `usage_fingerprint`; it is not a foreign key to a physical row.
- `is_duplicate`: `0` for the one billable physical representative and `1` for excluded copied rows.
- `duplicate_reason`: null for the representative and `copied_usage_fingerprint` for an automatically excluded row.

The existing `record_id` remains unchanged and continues to identify one physical parsed row. `source_file`, `line_number`, `session_id`, `source_records`, and other provenance fields remain physical.

### Fingerprint precedence

Fingerprint format is explicitly versioned as `usage-fingerprint-v2`.

1. When the token-count envelope contains a recognized non-empty `usage_id`, `event_id`, or `call_id` in the envelope, payload, or aggregate `info` object, the fingerprint hashes the version, identifier key/path, and identifier value. A generic `id` is not accepted because it may be a session identifier.
2. Otherwise, the fingerprint hashes a canonical JSON object containing:
   - the stable turn ID when present; cloned logs preserve this ID while rewriting imported event and turn timestamps;
   - event and turn timestamps, preserving nulls, only when no stable turn ID is available;
   - model and effort, preserving nulls;
   - model context window;
   - input, cached-input, output, reasoning-output, and total tokens for the call;
   - all corresponding cumulative token fields;
   - plan type, limit ID, and both primary and secondary rate-limit percentage/window/reset fields.

The fallback excludes `session_id`, thread labels, parent-session metadata, `source_file`, `line_number`, cwd, and derived pricing. This allows a copied event to retain its identity across a clone while preventing token-count-only matches. Canonical JSON uses fixed field names, fixed ordering, explicit null values, and unambiguous numeric serialization.

`canonical_record_id` is `sha256("canonical-usage-v1|" + usage_fingerprint)`. Because it is a logical ID, replacing or deleting a source file cannot leave duplicate rows pointing to a removed physical representative.

## Storage And Canonicalization

`usage_events` remains the physical table. Migration 24 adds the identity/status columns. Migration 25 reclassifies existing rows with the clone-stable v2 fingerprint. Both use the same production fingerprint function, select one deterministic representative per fingerprint, and create:

- an index on `usage_fingerprint`;
- an index on `canonical_record_id`;
- an index on `is_duplicate` and `duplicate_reason` for diagnostics;
- a partial unique index allowing only one row with `is_duplicate = 0` per non-null fingerprint;
- a read-only `canonical_usage_events` view selecting `is_duplicate = 0`.

The deterministic migration winner is the first row ordered by event timestamp, source file, line number, and record ID. Winner choice affects provenance display only; all rows share the same logical canonical ID.

During normal upsert, the store looks up the indexed fingerprint before assigning status. If no representative exists, the row is billable. If a representative exists under another physical `record_id`, the row is excluded with `copied_usage_fingerprint`. Reprocessing the same `record_id` preserves idempotency.

Source replacement collects the affected fingerprints before deleting physical rows. For any fingerprint whose representative was removed but whose physical siblings remain, it promotes one indexed deterministic sibling. Promotion changes only `is_duplicate` and `duplicate_reason`; the logical canonical ID remains stable. This work is bounded per affected physical event and never scans transcript content.

## Default Consumer Behavior

All billable/aggregate consumers switch from the physical table to `canonical_usage_events` or an equivalent mandatory canonical predicate:

- summary and expensive-call reports;
- static and live dashboard calls, counts, token summaries, and status;
- stable CLI and server JSON payloads;
- MCP summary, investigation, recommendation, and allowance tools;
- recommendation fact materialization and recommendation thread summaries;
- materialized thread summaries and latest billable record selection;
- allowance observation synchronization and allowance diagnostics;
- usage-drain, compression, and diagnostic aggregate calculations that represent call or token totals.

Per-record content, diagnostic facts, and source provenance may remain attached to physical `record_id` values. Any aggregation over those facts must join through canonical usage rows unless the surface is explicitly the physical diagnostic surface.

`source_records` continues to distinguish source file and line provenance. CSV/default exports become canonical-only; a physical export is not added in this change.

## Diagnostic Contract

Existing public APIs and MCP tools do not receive a `view=physical` switch. This prevents ordinary callers from accidentally mixing billable and provenance totals.

A dedicated dedupe diagnostic service is exposed consistently through CLI JSON, a localhost API route, an MCP tool, and the dashboard diagnostics/status UI. Its aggregate response includes:

- `dedupe_enabled` and fingerprint version;
- physical row count;
- canonical billable row count;
- excluded copied-clone row count;
- fingerprint groups containing excluded rows;
- physical, excluded, and canonical token totals;
- counts grouped by duplicate reason.

The dedicated physical-row diagnostic accepts a bounded limit and returns only aggregate/provenance fields: physical `record_id`, logical `canonical_record_id`, fingerprint version/hash, duplicate status/reason, source file, line number, session/turn IDs, timestamps, model/effort, and token fields. It returns no transcript, prompt, response, tool output, or content-index text.

Default dashboard/API/MCP payloads disclose the aggregate dedupe status and excluded-row count so users can understand why physical provenance counts differ from billable totals.

## Derived Data And Refresh

Migration and refresh must invalidate or rebuild persisted derivatives that can contain physical double counts:

- thread summaries are rebuilt from canonical rows;
- allowance observations for excluded rows are removed and only canonical observations are synchronized;
- recommendation facts and recommendation summaries are materialized from canonical rows;
- aggregate caches/revisions are touched so dashboard and MCP results cannot serve pre-dedupe totals.

Physical per-record facts remain available for investigation. If a representative is promoted after source replacement, derived billable materializations are refreshed for the affected logical identity and thread keys.

## Error Handling And Compatibility

- Rows missing a stable upstream identifier use the strict aggregate fingerprint; missing optional values are encoded as null rather than dropping fields.
- A malformed optional upstream identifier is ignored and the strict aggregate path is used.
- Existing `record_id` lookups remain physical and backward compatible.
- Default list/detail entry points that represent user consumption return canonical rows. Source-record and dedupe-diagnostic entry points are the explicit physical exceptions.
- Schema repair and migration checks require the new columns, indexes, view, migration metadata, and checksum.
- No existing schema ID or tool name is renamed. New contract fields are additive and documented.

## Testing

Synthetic tests cover:

1. An original session plus a clone containing the copied historical token event: two physical rows, one canonical billable row, and one excluded row.
2. A genuinely new call appended inside the clone: it receives a distinct fingerprint and remains billable.
3. Calls with equal token counts but different event timestamp or turn identity: both remain billable.
4. A recognized shared upstream usage/event/call ID: copied rows dedupe through the upstream-ID path.
5. Generic or malformed IDs: they do not trigger upstream-ID dedupe.
6. Repeated refresh and source replacement: physical provenance stays idempotent, a surviving sibling is promoted when needed, and canonical totals do not change.
7. Legacy database migration: fingerprints/statuses are backfilled, copied historical rows are excluded, and schema metadata reaches version 24.
8. Dashboard, reports, recommendations, allowance diagnostics, thread summaries, CLI JSON, server JSON, and MCP totals all agree on canonical counts and tokens.
9. The dedicated diagnostic reports excluded rows and bounded physical provenance without raw content.
10. Query-plan or index assertions confirm fingerprint lookup uses the fingerprint index and no content/FTS table participates.

## Documentation

Update architecture, database schema, dashboard, CLI/MCP, privacy, and JSON-contract documentation. Explain that usage totals are canonical by default, physical rows remain local provenance, automatic exclusion requires exact identity, and fuzzy matches are diagnostic-only.
