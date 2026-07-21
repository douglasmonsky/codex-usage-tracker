# Subagent Usage Analytics MCP/API Design

**Status:** Approved
**Date:** 2026-07-21

## Context

Codex Usage Tracker already parses and persists subagent metadata on usage events:
`thread_source`, `subagent_type`, `agent_role`, `agent_nickname`,
`parent_session_id`, `parent_thread_name`, and `parent_session_updated_at`.
The generic usage summary can group usage rows by role or type, but it does not
provide a spawn-level contract, distinguish sessions from calls, or compare
subagent usage with direct-agent usage.

This design adds a dedicated aggregate report exposed through MCP and CLI JSON.
It uses only the existing local usage-event data and does not add lifecycle
instrumentation.

## Goals

- Count distinct observed subagent sessions as observed spawns.
- Attribute calls, turns, tokens, and estimated cost to subagents.
- Show role, type, and parent-thread breakdowns.
- Compare subagent usage with direct-agent usage in the same base scope.
- Expose one stable payload through a purpose-built MCP tool and CLI command.
- Preserve aggregate-first privacy and existing pricing-coverage semantics.

## Non-goals

- Counting spawned agents that produced no persisted usage event.
- Tracking live, failed, cancelled, or zero-usage spawn lifecycle events.
- Claiming that subagents caused token or cost changes.
- Adding a localhost HTTP endpoint or dashboard UI.
- Returning prompts, responses, raw context, or session identifiers.
- Reporting agent nicknames by default.

## Definitions

### Subagent row

A canonical usage row is subagent-linked when any existing subagent signal is
present:

- `thread_source == "subagent"`; or
- `subagent_type` is non-empty; or
- `parent_session_id` is non-empty.

This matches the repository's existing attachment and diagnostic behavior.

### Observed spawn

An observed spawn is one distinct, non-empty `session_id` among subagent rows in
the selected scope. Multiple calls or turns in one subagent session count as one
observed spawn.

Rows without a usable `session_id` contribute to aggregate subagent usage but do
not contribute to `observed_spawns`. Per-spawn metrics use only usage rows with a
usable subagent session ID. Coverage fields disclose excluded rows and tokens.

### Direct-agent row

A canonical usage row that does not satisfy the subagent predicate is a direct
agent row. Direct-agent metrics are an observed baseline, not a counterfactual.

## Architecture

The feature has one domain path and two thin adapters:

```text
canonical_usage_events
  -> subagent aggregate queries
  -> SubagentUsageReport
  -> MCP subagent_usage
  -> CLI codex-usage-tracker subagents [--json]
```

### Store query layer

Add focused query functions under `src/codex_usage_tracker/store/`. They own SQL
cohort selection and aggregation, use `canonical_usage_events`, and return plain
mappings. They do not render output or load pricing.

The queries produce:

- base-scope direct and subagent totals;
- spawn-attributable totals for per-spawn calculations;
- role and type breakdowns;
- parent-thread breakdowns; and
- metadata and pricing coverage inputs.

Existing canonicalization and idempotent refresh behavior remain unchanged.

### Report layer

Add a focused report module under `src/codex_usage_tracker/reports/`. It owns:

- input validation;
- pricing annotation and coverage;
- shares, ratios, and per-spawn calculations;
- the versioned JSON payload; and
- concise Markdown rendering.

The report is the sole application contract. MCP and CLI adapters must not
recalculate metrics.

### Adapters

- Register one MCP tool named `subagent_usage`.
- Add one CLI command named `subagents` with a `--json` output mode.
- Both adapters call the same report builder and return equivalent payloads.
- No HTTP route is added in v1.

## Request contract

The shared report accepts:

| Parameter | Default | Semantics |
| --- | --- | --- |
| `since` | `None` | Existing ISO-8601 date/datetime lower-bound semantics. |
| `parent_thread` | `None` | Select the named parent thread and its attached subagents. |
| `agent_role` | `None` | Restrict the subagent cohort to one exact role. |
| `subagent_type` | `None` | Restrict the subagent cohort to one exact type. |
| `include_archived` | `False` | Include archived sessions when true. |
| `limit` | `10` | Maximum rows in each breakdown; integer from 1 through 100. |
| `response_format` | `"markdown"` | MCP output: `markdown` or `json`. |
| `privacy_mode` | `"normal"` | Existing supported privacy modes. |

The CLI mirrors these as flags and adds `--json`. CLI `--json` and MCP
`response_format="json"` return the same payload.

`since` and `include_archived` define the base comparison scope. When
`parent_thread` is provided, direct rows for that thread are compared with
subagent rows attached to it. `agent_role` and `subagent_type` narrow only the
subagent cohort; the response metadata makes clear that the direct baseline is
the unfiltered direct cohort in the same base time/archive/parent scope.

## Response contract

The new schema ID is `codex-usage-tracker.subagent-usage.v1`. The payload has a
stable top-level shape even when no rows match:

```text
schema_id
generated_at
filters
definitions
summary
comparison
by_role
by_type
top_parent_threads
coverage
warnings
```

### `definitions`

Machine-readable notes define:

- observed spawn as a distinct persisted subagent session;
- direct and subagent cohort predicates;
- the per-spawn attribution denominator; and
- `observed_comparison_not_causal: true`.

### `summary`

The summary includes:

- `observed_spawns`;
- `subagent_calls` and distinct `subagent_turns`;
- input, cached input, uncached input, output, reasoning output, and total tokens;
- estimated cost in USD;
- subagent shares of calls, turns, tokens, and covered estimated cost; and
- attributable calls, turns, tokens, and estimated cost per observed spawn.

Token and call shares use the complete matching base scope. Cost shares use
covered estimated cost and must be read with the adjacent pricing coverage.

### `comparison`

The comparison contains parallel `subagent` and `direct` aggregates plus
explicit deltas or ratios for:

- tokens per call;
- tokens per turn;
- cache ratio;
- output-token ratio; and
- reasoning-output ratio.

Undefined ratios are JSON `null`, not zero. Markdown rendering labels the
comparison as descriptive and non-causal.

### Breakdowns

`by_role` and `by_type` contain, per group:

- group key;
- observed spawns;
- calls and turns;
- token components and total tokens;
- estimated cost and pricing coverage; and
- share of subagent tokens and observed spawns.

Missing values use one stable `unknown` bucket.

`top_parent_threads` contains privacy-processed parent labels, observed child
spawns, role mix, calls, turns, tokens, and estimated cost. Unmatched or missing
parents use `unknown parent`.

### `coverage`

Coverage reports:

- subagent rows and tokens lacking a usable session ID;
- observed spawns lacking role metadata;
- observed spawns lacking type metadata; and
- priced, estimated, and unpriced cost counts and token totals.

Warnings are concise, deterministic, and included when missing identifiers or
incomplete pricing materially limit interpretation.

## Privacy

- The report is aggregate-first and never includes prompt or response content.
- Raw `session_id` and `parent_session_id` values are never returned.
- Parent-thread labels pass through existing project privacy handling.
- Strict privacy mode redacts or pseudonymizes identifying labels consistently
  with other report surfaces.
- Agent nicknames are excluded from the default contract because they are
  high-cardinality and potentially identifying.
- Synthetic fixtures are required for tests, docs, and examples.

## Validation and error handling

- Invalid `since`, `limit`, `response_format`, or `privacy_mode` values produce
  concise existing-style validation errors.
- Empty datasets return zeros, empty arrays, complete definitions, and coverage;
  absence of data is not an error.
- Missing pricing never blocks token analytics.
- Missing session IDs never inflate observed-spawn counts.
- Division by zero produces `null` ratios and per-spawn values.
- Parentless and unmatched subagents remain visible under `unknown parent`.

## Testing

Use new focused test modules rather than enlarging the existing MCP/store
hotspot. All fixtures must be synthetic.

Required coverage:

1. One subagent session with multiple calls counts as one observed spawn.
2. Several roles and types produce correct independent breakdowns.
3. Missing session, role, type, and parent metadata produce correct coverage and
   `unknown` buckets.
4. Direct and subagent cohorts use identical base time/archive/parent scope.
5. Role/type filters narrow subagents without silently narrowing the direct
   baseline.
6. Token shares, per-spawn metrics, ratios, and zero-denominator behavior are
   correct.
7. Priced, estimated, and unpriced models preserve existing cost semantics.
8. Archived-session and `since` filters work together.
9. Normal and strict privacy modes protect parent labels.
10. CLI JSON and MCP JSON payloads are equivalent.
11. Markdown output is concise and contains the non-causal caveat.
12. Empty data returns the stable v1 payload shape.
13. Existing summary, MCP, parser, and dashboard contracts remain unchanged.
14. Payloads contain no raw prompts, context, or sensitive session identifiers.

## Documentation and packaging

Update MCP documentation, CLI documentation, JSON schema documentation, and both
source and packaged copies of the operational skills. Include example questions
such as:

- How many observed subagents spawned this week?
- Which roles and subagent types used the most tokens?
- What share of usage came from subagents?
- Which parent threads spawned the most subagents?
- How did observed subagent usage compare with direct-agent usage?

Examples must state that zero-usage spawns are invisible and comparisons are not
causal. Existing package and plugin release checks must verify bundled docs and
skill parity where applicable.

## Acceptance criteria

- One MCP call answers the approved spawn, attribution, comparison, role/type,
  and parent-thread questions.
- Observed spawns are distinct subagent sessions, never usage-row counts.
- CLI JSON and MCP JSON share one stable v1 payload.
- Existing public contracts remain backward compatible.
- Aggregate privacy and pricing-coverage guarantees are preserved.
- Focused tests and the repository's required public-contract gates pass.
