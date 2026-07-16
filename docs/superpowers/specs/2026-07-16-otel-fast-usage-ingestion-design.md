# OTel Fast Usage Ingestion Design

## Goal

Enrich existing aggregate Codex usage calls with reliable Fast-versus-Standard service-tier
metadata from the local OpenTelemetry `response.completed` stream, then use confirmed Fast
status when estimating ChatGPT credit consumption.

The feature must remain local, aggregate-only, incremental, idempotent, and conservative. It
must never create a second usage call for an OTel completion, guess when more than one logical
call could match, or persist prompts, message bodies, arbitrary OTel attributes, account data,
or tool content.

## Non-goals

- Reconstruct Fast usage before completion-tier telemetry was emitted.
- Treat response timing, reasoning effort, or latency as proof of Fast mode.
- Change USD text-token cost estimates based only on a service-tier label.
- Replace session JSONL as the canonical source of usage calls and token totals.
- Persist or expose raw OTel payloads through the database, dashboard, exports, support
  bundles, or tests.
- Add remote telemetry export or change the user's collector configuration.

## Source contract

The optional local source is the file-exporter output under the tracker application directory:

```text
~/.codex-usage-tracker/otel/codex-completions.jsonl
~/.codex-usage-tracker/otel/codex-completions-*.jsonl
```

Each line is one OTLP JSON object that may contain multiple resource, scope, and log-record
groups. The parser considers only log records whose allowlisted attributes identify
`event.name = codex.sse_event` and `event.kind = response.completed`.

The parser may extract only these aggregate fields:

- `conversation.id`
- `input_token_count`
- `cached_token_count`
- `output_token_count`
- `reasoning_token_count`
- `model`
- `model_reasoning_effort`
- `service_tier`
- `app.version`
- log-record timestamp

All other attributes, resources, scopes, bodies, trace identifiers, and span identifiers are
ignored. Malformed lines or invalid field types increment bounded diagnostics without copying
the offending content into SQLite or report payloads.

## Tier normalization

The normalized call fields are:

- `service_tier`: `fast`, `standard`, another explicit non-Fast tier, or `NULL` when unknown.
- `fast`: `1` for confirmed Fast, `0` for confirmed non-Fast, or `NULL` when unknown.
- `service_tier_source`: `otel_response_completed` for this ingestion path.
- `service_tier_confidence`: `exact` for explicit tier values and `protocol` when Standard is
  established by versioned omission semantics.

Explicit `priority` and `fast` values normalize to `service_tier = fast` and `fast = 1`.
Explicit `default` and `standard` values normalize to `service_tier = standard` and `fast = 0`.
Other explicit values are preserved as normalized lower-case tier names with `fast = 0`.

Codex 0.143.0 and later emits `service_tier = priority` for Fast completions and omits the
field for Standard completions. Therefore, a missing service tier with a parseable
`app.version >= 0.143.0` normalizes to `service_tier = standard`, `fast = 0`, and
`service_tier_confidence = protocol`. A missing tier from an older or unparseable version
remains unknown.

## Persistent ingestion

Two aggregate-only sidecar tables make ingestion incremental and independent of file arrival
order.

### OTel source cursors

`otel_completion_sources` records the source path, device, inode, size, parsed byte offset,
parsed line number, and last refresh timestamp. Append-only files resume at the previous byte
offset. Truncation, inode replacement, or size regression resets the cursor safely. Rotated
files are discovered in deterministic path order.

### Completion staging

`otel_completion_events` stores one normalized aggregate completion per semantic fingerprint.
The fingerprint is a versioned SHA-256 digest over the normalized conversation ID, timestamp,
four token counters, model, effort, tier state, and app version. Re-reading a current or
rotated file is therefore idempotent.

The staging row stores only the extracted aggregate fields, source path, source line,
fingerprint, match status, and an optional matched record ID. It never stores the OTLP line,
body, arbitrary attribute map, prompt, account metadata, or tool content.

Supported match statuses are `pending`, `matched`, `ambiguous`, `conflict`, and `invalid`.
Pending and ambiguous rows remain available for a later refresh because session JSONL and OTel
files can advance in either order.

## Conservative correlation

Session JSONL remains authoritative for call identity and token totals. A normalized OTel
completion may enrich a usage call only when all of the following hold:

1. `conversation.id` equals `usage_events.session_id`.
2. Input, cached-input, output, and reasoning-output token counts match exactly.
3. Model values match when both sources provide a model.
4. Reasoning-effort values match when both sources provide an effort.
5. The candidates resolve to exactly one canonical usage-call group.

Timestamp proximity is not a matching key. Export batching and source-event timing can differ,
so timestamp heuristics would create false confidence. The timestamp is used only in the
completion fingerprint and diagnostics.

If candidates span multiple canonical groups, the completion remains `ambiguous`. If exactly
one canonical group matches, every physical clone in that canonical group receives the same
tier enrichment. This preserves clone consistency without changing usage fingerprints,
canonical IDs, or deduplication decisions.

Existing non-null tier enrichment is never silently replaced by a contradictory completion.
The completion becomes `conflict`, the existing call value is preserved, and an aggregate
conflict counter is emitted. Repeated agreement is idempotent.

The session-log upsert must use enrichment-owned merge semantics so a later source replacement
or incremental JSONL refresh cannot erase an existing non-null service tier.

## Refresh and rebuild behavior

Normal refresh performs these ordered phases:

1. Parse and upsert session JSONL usage calls as today.
2. Discover and incrementally parse OTel completion files when the optional directory exists.
3. Reconcile pending and ambiguous completion rows against current usage calls.
4. Recompute affected derived facts, thread summaries, and revision counters.
5. Record bounded OTel coverage diagnostics in refresh metadata.

An absent OTel directory is a supported no-op. OTel parse failures do not roll back valid
session-log ingestion; they produce aggregate diagnostics and preserve the last valid cursor.

Rebuild clears canonical usage-derived state but retains normalized OTel staging. It resets
stale match pointers, rebuilds session usage calls, then reconciles the retained completion
events. This makes tier enrichment reproducible without requiring rotated source files to
remain forever.

## Database and public rows

`usage_events` gains four repairable nullable columns:

```text
service_tier TEXT
fast INTEGER
service_tier_source TEXT
service_tier_confidence TEXT
```

These fields are additive to existing row and export contracts. Historical calls remain
`NULL`/unknown unless a conservative OTel match exists. They are not identity fields and must
not participate in usage fingerprints, canonical IDs, or duplicate classification.

Calls and call-detail payloads expose the four aggregate fields. Dashboard labels distinguish
Fast, Standard, and Unknown. Existing proxy analysis remains available for historical unknown
calls, but exact OTel enrichment takes precedence and proxy wording must not claim that direct
tier data is unavailable for enriched rows.

## Credit and USD pricing semantics

Confirmed Fast calls multiply the existing Standard ChatGPT credit estimate by the documented
model multiplier:

- GPT-5.6: `2.5`
- GPT-5.5: `2.5`
- GPT-5.4: `2.0`

Confirmed Standard and unknown calls use multiplier `1.0`; unknown calls must remain visibly
unknown rather than being labeled Standard. Credit annotations add the effective multiplier
and tier provenance so totals remain explainable.

USD token-cost estimates remain unchanged. `priority` can represent ChatGPT Fast mode or API
Priority processing, and the retained aggregate fields do not prove the authentication or
billing path. Applying an API Priority price automatically would therefore be unsafe.

## Diagnostics and privacy

Refresh diagnostics report aggregate counts only, including files scanned, completions
imported, matched, pending, ambiguous, conflicting, malformed, and unsupported-version rows.
Support bundles may include those counts and configuration presence, never source paths,
conversation IDs, fingerprints, record IDs, timestamps, token tuples, or raw payloads.

Default dashboards, CSV, JSON, MCP responses, screenshots, and fixtures remain aggregate-first.
All committed fixtures use synthetic conversation IDs, timestamps, models, and token counts.

## Test strategy

Implementation follows red-green-refactor cycles with synthetic files and databases.

Parser tests cover:

- OTLP batches containing multiple resource and scope groups.
- Allowlisted completion extraction and arbitrary-field rejection.
- Explicit Fast, explicit Standard, protocol-omitted Standard, and unknown older versions.
- Invalid JSON, invalid integers, missing identifiers, and non-completion log records.
- Current-file append, truncation, replacement, rotation, and semantic deduplication.

Store tests cover:

- OTel-before-JSONL and JSONL-before-OTel arrival.
- Unique exact match, no match, multiple canonical matches, and conflicting tiers.
- Repeated refresh idempotency.
- Canonical clone propagation.
- Session source replacement preserving tier enrichment.
- Rebuild from retained staging.
- Schema migration and repairable-column behavior.
- No raw OTel body or arbitrary attribute persisted in any table.

Pricing and report tests cover:

- Fast credit multipliers for GPT-5.6, GPT-5.5, and GPT-5.4.
- Standard and unknown credit multiplier behavior.
- USD cost estimates remaining unchanged.
- Exact tier taking precedence over historical proxy labels.
- Additive Calls, detail, export, and support-bundle contract behavior.

## Acceptance criteria

- A uniquely correlated synthetic Fast completion enriches exactly one canonical call group.
- A uniquely correlated synthetic Standard completion records confirmed Standard status.
- Ambiguous or unmatched completions never alter usage calls.
- Refresh, rotation, source replacement, and rebuild remain idempotent.
- Credit estimates use documented Fast multipliers only for confirmed Fast calls.
- USD estimates do not change from service-tier enrichment.
- Historical unknown calls remain unknown.
- No raw OTel content appears in SQLite, default reports, exports, support bundles, docs, or
  committed fixtures.
- Focused parser, store, migration, pricing, report, and privacy tests pass before the full
  repository verification gate.
