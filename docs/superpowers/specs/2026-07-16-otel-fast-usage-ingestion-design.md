# OTel Fast Usage Ingestion Design

## Goal

Enrich existing aggregate Codex usage calls with reliable response service-tier metadata from
the local OpenTelemetry `response.completed` stream, then use the exact observed tier together
with an explicit billing basis to estimate either ChatGPT credit consumption or API token cost
without conflating those two billing systems.

The feature must remain local, aggregate-only, incremental, idempotent, and conservative. It
must never create a second usage call for an OTel completion, guess when more than one logical
call could match, or persist prompts, message bodies, arbitrary OTel attributes, account data,
or tool content.

## Non-goals

- Reconstruct Fast usage before completion-tier telemetry was emitted.
- Treat response timing, reasoning effort, or latency as proof of Fast mode.
- Infer ChatGPT-versus-API billing from a service-tier label alone.
- Replace session JSONL as the canonical source of usage calls and token totals.
- Persist or expose raw OTel payloads through the database, dashboard, exports, support
  bundles, or tests.
- Add remote telemetry export or change the user's collector configuration.

## Alternatives considered

1. **Multiply every Fast USD estimate by the ChatGPT credit multiplier.** Rejected because API
   Priority premiums are model-specific and can differ from ChatGPT Fast credit multipliers.
2. **Keep one globally selected API tier.** Rejected because an exact response tier can vary by
   call, including Priority downgrades to Standard, so a global tier can misprice mixed history.
3. **Preserve the exact tier, cache all API tiers, and keep billing basis explicit.** Selected.
   This keeps ChatGPT credits and API-token USD as separately labeled estimates, uses the actual
   response tier for API-equivalent cost, and never infers authentication from OTel.

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

- `service_tier`: the exact normalized response tier (`priority`, `default`, `flex`, another
  explicit value), `standard` when established by versioned omission, or `NULL` when unknown.
- `fast`: `1` for the Codex accelerated path established by `priority`/`fast`, `0` for a
  confirmed non-Fast tier, or `NULL` when unknown. This is a derived product classification,
  not a billing-system discriminator.
- `service_tier_source`: `otel_response_completed` for this ingestion path.
- `service_tier_confidence`: `exact` for explicit tier values and `protocol` when Standard is
  established by versioned omission semantics.

Explicit tier names are preserved in normalized lower case. `priority` and `fast` set `fast = 1`;
`default`, `standard`, `flex`, and other explicit non-Fast values set `fast = 0`. The exact
response tier and the derived Fast classification must remain separately auditable.

Codex 0.143.0 and later emits `service_tier = priority` for accelerated completions and omits
the field for Standard completions. Therefore, a missing service tier with a parseable
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

Calls and call-detail payloads expose the four aggregate fields. Dashboard labels preserve the
exact observed tier and distinguish Priority/Fast, Default/Standard, Flex, Batch, another
explicit tier, and Unknown. Existing proxy analysis remains available for historical unknown
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

`priority` can represent ChatGPT Fast mode or API Priority processing, and the retained OTel
attributes do not prove the authentication or billing path. Reports therefore require an
explicit billing basis with three states:

- `chatgpt_credits`: apply the documented, source-stamped Fast credit multiplier to confirmed
  Fast calls; API USD remains an explicitly labeled equivalent estimate rather than actual spend.
- `api_tokens`: do not apply ChatGPT credit multipliers; select the exact API pricing table from
  the observed response tier (`priority`, `default`/`standard`, `flex`, or `batch`).
- `unknown`: do not present one falsely precise billing result; expose the Standard and Priority
  API-equivalent scenarios plus the unadjusted and Fast-adjusted ChatGPT credit scenarios when
  the required rates exist.

The local API pricing-v2 snapshot stores all published service-tier tables together under
`api_service_tiers`, while retaining `models` as the selected legacy projection. Existing
single-tier pricing-v1 files remain readable and keep their source tier as their only available
tier. `billing_basis` is an explicit local value (`chatgpt_credits`, `api_tokens`, or `unknown`)
preserved by pricing refreshes; it labels which estimate is applicable but never changes the
observed service tier. New costing APIs accept the row's observed service tier and never apply a
generic Fast multiplier to API USD because Priority premiums vary by model.

Cost annotations remain additive and backward compatible. `estimated_cost_usd` uses the exact
observed API tier when a pricing-v2 rate exists, while `standard_cost_usd` and
`priority_cost_usd` expose bounded comparison scenarios. `pricing_service_tier` records the
table actually selected. Existing pricing-v1 files keep their current single-tier behavior.
Credit annotations retain `usage_credits` as the ChatGPT-equivalent estimate and
`standard_usage_credits` as its baseline; `fast_usage_credits` exposes the documented Fast
scenario when the model has a source-stamped multiplier. The dashboard uses `billing_basis` to
label these as applicable or equivalent scenarios rather than claiming both are actual spend.

Fast credit multiplier metadata is part of the source-stamped Codex rate-card contract. Its
provenance is separate from `service_tier_source`: OTel proves which tier served the call, while
the rate card proves which numeric multiplier and effective source were used. Bundled and local
rate cards may define `fast_multipliers` by model family with `multiplier`, `source_url`,
`fetched_at`, and `confidence`. Row annotations expose that rate-card provenance through
`usage_credit_multiplier_source_url`, `usage_credit_multiplier_fetched_at`, and
`usage_credit_multiplier_confidence`; `usage_credit_multiplier_source` remains a bounded label.

## Presentation semantics

Dashboard and CSV rows preserve the exact service tier. Human labels distinguish Fast,
Priority, Default/Standard, Flex, Batch, another explicit tier, and Unknown. When billing basis
is unknown, the dashboard labels the tier as observed without claiming whether the call was
billed through ChatGPT credits or API tokens.

## Reset and rotation semantics

`rebuild-index` retains normalized OTel staging so tier enrichment can be reconstructed after
canonical usage rows are rebuilt. In contrast, confirmed `reset-db` clears both OTel staging
tables and their source cursors along with every other tracker-owned aggregate row.

Incremental ingestion derives resume identity and final size from the open file descriptor.
If a path changes inode between discovery and open, or the descriptor identity changes during
the guarded read, ingestion resets/retries without saving an offset from one inode against
another. A concurrent rotation must never permanently skip the beginning of the replacement
file.

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
- Source-stamped Fast multiplier provenance separate from OTel tier provenance.
- Pricing-v1 compatibility and pricing-v2 all-tier parsing.
- Per-call Standard, Priority, Flex, and Batch API rate selection without a generic multiplier.
- Explicit `billing_basis` preservation and unknown-basis scenario labels.
- Exact tier taking precedence over historical proxy labels.
- Additive Calls, detail, export, and support-bundle contract behavior.
- Confirmed reset clearing OTel staging/cursors while rebuild retains staging.
- Rotation during an active read without cross-inode cursor persistence.

## Acceptance criteria

- A uniquely correlated synthetic Fast completion enriches exactly one canonical call group.
- A uniquely correlated synthetic Standard completion records confirmed Standard status.
- Ambiguous or unmatched completions never alter usage calls.
- Refresh, rotation, source replacement, and rebuild remain idempotent.
- Credit estimates use documented Fast multipliers only for confirmed Fast calls.
- API USD estimates use the exact published tier table when that tier/model pair is available.
- ChatGPT credits and API USD remain separately labeled estimates, with explicit billing basis.
- Historical unknown calls remain unknown.
- `reset-db --yes` clears OTel completion rows and source cursors.
- No raw OTel content appears in SQLite, default reports, exports, support bundles, docs, or
  committed fixtures.
- Focused parser, store, migration, pricing, report, and privacy tests pass before the full
  repository verification gate.
