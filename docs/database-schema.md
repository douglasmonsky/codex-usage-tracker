# Database Schema

The tracker uses one local SQLite database, normally
`~/.codex-usage-tracker/usage.sqlite3`. Migrations are additive and run during
normal store initialization. This page describes ownership and contracts rather
than duplicating every SQL column declaration; `store/schema.py` remains the
source of truth.

## Usage And Provenance

`usage_events` stores every parsed physical aggregate event. Provenance fields
include source file, source line/byte location, session and turn identifiers,
event timestamp, model/effort, token counters, cumulative counters, rate-limit
metadata, and parent-session metadata.

Logical identity adds:

- `usage_fingerprint`: strict stable identity, preferring an upstream event/call
  id and otherwise hashing timestamp, turn identity/timestamp, model, effort,
  token/cumulative fields, and rate-limit metadata while excluding session and
  source path;
- `canonical_record_id`: the physical row selected as the logical billable row;
- duplicate linkage/reason fields for high-confidence copied history; and
- an indexed fingerprint lookup so ingestion remains O(1) per parsed event.

The physical row is never deleted. Default queries select canonical rows; bounded
dedupe diagnostics can compare canonical and physical counts and inspect source
provenance. Similar token totals without the strict identity are not excluded.

`source_records` and source-state tables track incremental file cursors, file
identity, parser coverage, replacement, and refresh revision. Changing or removing
a source causes its owned physical rows/materializations to be replaced in a
transaction rather than accumulated blindly.

## Allowance Intelligence Materializations

`allowance_observations` stores normalized structured weekly and 5-hour snapshots,
their cohort/reset identity, canonical/physical linkage, conflicts, and source
revision.

`allowance_cycles` stores one reset-aware cycle summary: window/cohort identity,
normalized reset, observed range, latest/peak percentage, canonical token/credit
totals, price coverage, conflict/reversal/censor counts, quality/state, archive
scope, source revision, and model version.

`allowance_intervals` stores transitions inside a cycle: endpoint observation and
record provenance, visible percentage movement, canonical token/credit activity,
price coverage/confidence, censor/conflict reasons, explained/unexplained movement,
eligibility flags, source revision, and model version.

`allowance_source_state` stores the active semantic revision and materialization
status. Status, series, and evidence requests read one consistent revision.

Persisted allowance analysis tables store the revision/model/rate-card key,
detector parameters, result JSON, status, timestamps, and failure metadata.
Identical keys reuse a completed snapshot or the same in-flight job.

## Query And Index Rules

- Canonical totals use indexed canonical/duplicate fields.
- Fingerprint lookup is indexed and never scans transcript content or FTS.
- Evidence is ordered by descending observation time plus a stable tie-break and
  uses cursor pagination; the interactive limit is 1–500.
- Series ranges are finite and at most 366 days.
- Status reads bounded current/source-state rows and remains constant size.
- Physical provenance requires an explicit local/debug request and remains
  bounded.

## Privacy And Rebuilds

Allowance materializations and logical identity contain aggregate metadata only.
They do not contain prompts, assistant text, tool output, or raw JSONL content.
Rebuilds can recreate them from physical aggregate rows and source provenance.
The local content index is a separate opt-in investigation layer and is not used
for dedupe or allowance fitting.

See [Privacy Guide](privacy.md), [Architecture](architecture.md), and
[Allowance Intelligence](allowance-intelligence.md) for the external behavior.
