# MCP Evidence Contracts

Core MCP tools return deterministic, versioned JSON contracts. The contract
models are frozen, mappings serialize in sorted order, and every nested numeric
value must be finite. Timestamps are generated in UTC and request identifiers
use `req-` followed by 32 lowercase hexadecimal characters.

## Schema Registry

| Schema | Contract |
| --- | --- |
| `codex-usage-tracker.scope.v1` | Time, history, privacy, and filter scope. |
| `codex-usage-tracker.freshness.v1` | Source revision, freshness state, threshold, and refresh guidance. |
| `codex-usage-tracker.accounting-context.v1` | Physical/canonical counts, exclusions, coverage, history, and privacy context. |
| `codex-usage-tracker.message.v1` | Warning or limitation with a stable code and optional remediation. |
| `codex-usage-tracker.recommendation.v1` | Action backed by one or more non-recommendation claims. |
| `codex-usage-tracker.finding.v1` | Typed claim with confidence, metrics, evidence, caveats, and optional recommendation. |
| `codex-usage-tracker.evidence.v1` | Deterministic evidence selector, metrics, source schema, and optional dashboard target. |
| `codex-usage-tracker.next-action.v1` | Bounded next action with stable code, tool, and arguments. |
| `codex-usage-tracker.mcp-envelope.v1` | Additive wrapper around one versioned core-tool result. |

The table above is checked for exact equality with the registered shared MCP
schema identifiers.

## Envelope

Every core response includes the tool name, request id, UTC generation time,
source revision, freshness, scope, data class, accounting context, warnings,
limitations, result schema and result, dashboard targets, and next actions.
Compatibility wrappers can retain historical payloads until removal; core tools
use the shared envelope.

## Claims And Recommendations

Findings distinguish observed, derived, estimated, inferred, and recommended
claims. A recommendation must identify at least one present non-recommended
finding that supports it. Unsupported recommendations are rejected before
serialization.

## Evidence And Data Boundaries

Evidence records contain deterministic identifiers, reviewed selectors, bounded
metrics, their source schema, and an optional dashboard target. The envelope's
data class is one of `aggregate`, `local_index`, `raw_context`, or
`administrative`; this canonical alias is defined in the core contract layer and
re-exported by MCP interface metadata.

## Payload Budgets

Payload size is the UTF-8 byte count of compact deterministic JSON. Budget
errors report both actual and maximum bytes so callers can trim results without
guessing. Non-finite values such as `NaN` and positive or negative infinity are
rejected recursively.
