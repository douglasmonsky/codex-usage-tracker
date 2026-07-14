# ADR 0010: Recommendation Engine Boundary

## Status

Accepted

## Context

Materialized recommendation facts must use the same scoring semantics as CLI,
dashboard, and MCP reports. The store domain cannot depend on the reports
domain because reports already depends on store queries. Copying the scorer
into persistence would create two authorities that could drift.

## Decision

The pure scorer remains in `reports`. The higher-level
`codex_usage_tracker.recommendation_engine` domain combines that scorer with
pricing configuration and store persistence.

The store refresh pipeline accepts a typed derived-fact callback and never
imports recommendation policy. CLI and server refresh entry points supply the
recommendation materializer, which runs inside the existing refresh
transaction after normalized rows and links are finalized.

## Consequences

- Refresh and report paths share one scoring implementation.
- Store persistence remains independent of pricing and report policy.
- Recommendation engine changes require parity tests for reports and facts.
- Raw store refresh remains available for store-level tests and migrations;
  product refresh paths use the recommendation-aware entry point.
