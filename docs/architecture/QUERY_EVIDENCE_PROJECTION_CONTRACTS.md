# Query, Evidence, and Projection Contracts

**Status:** Implementation authority
**Registry family:** `codex-usage-tracker.question-plan.v1`

The query surface is optimized for agent success, not schema exposure. Common
questions use named plans. Novel questions compose a small typed grammar.
Evidence is a separate bounded follow-up. No query starts refresh.

## Result grades

Every metric/column declares one grade:

| Grade | Meaning | Kernel storage |
| --- | --- | --- |
| `exact` | Direct observation or canonical sum/count. | Allowed |
| `deterministic` | Versioned reproducible calculation over exact facts. | Allowed |
| `configured_estimate` | Requires a validated external artifact such as a rate card. | Allowed with provenance |
| `model_inference` | Interpretation over disclosed facts/features. | Never a canonical fact |
| `unsupported` | Data cannot establish the requested conclusion. | Never a numeric substitute |

The kernel cannot relabel an estimate as exact because coverage is high. Missing
inputs remain `NULL`.

## Named-plan registry

Every Tier 1 question has a versioned registry record:

```yaml
question_id: Q-ACC-02
plan_id: top_sessions
plan_version: 1
parameters:
  window: required
  timezone: required
  limit: {default: 10, maximum: 25}
required_capabilities: [model_call_usage]
required_measurements: [uncached_input, cached_input, output]
answer_fields:
  uncached_input_tokens: exact
  cached_input_tokens: exact
  reasoning_tokens: exact_or_null
  output_tokens: exact
  top_share: deterministic
evidence: [E0, E1]
projection_consumers: [rollup_session_current, rollup_global_window]
order:
  - total_tokens desc
  - session_id asc
budgets:
  sql_p95_ms: 25
  mcp_p95_ms: 500
  response_bytes: 8192
```

The registry owns:

- intent phrases and question ID;
- request schema and defaults;
- capabilities and measurement requirements;
- logical plan and physical compiler name;
- answer grades and formulas;
- deterministic order and tie-breakers;
- coverage/freshness rules;
- evidence classes and selector kinds;
- admitted projections;
- SQL scan/sort, server, MCP, row, byte, and call budgets;
- synthetic oracle IDs;
- less-capable-model instruction snippet.

Registry changes require contract tests, qualification updates, and a version
change. A plan may not silently fall back to a broad generic scan that exceeds
its declared budget.

### Fact-backed plan admission

A named plan is admitted to implementation only after its exact typed request
has an executable fact-lineage triangle:

1. a scenario declaration emits canonical typed facts and selector
   occurrences;
2. an independent reference evaluator derives the expected row from those
   facts without calling the production compiler;
3. the permitted database-v1 fact plan produces the same row from one read
   snapshot.

The scenario, reference evaluator, and production plan may share versioned
formulas and contracts, but they cannot share computed answer rows. Candidate
or grading tables such as `question_cases`, `oracle_case` runtime reads, and
equivalent expected-answer caches are forbidden. A matching digest, formula
check, or database round trip alone does not admit a plan.

Every plan records its producer artifact identity, consumer seam check, and
requalification set. If any of those inputs change, the plan returns to
unimplemented until its seam qualification passes again.

Formula execution is governed by `formula-contract-v1.json`: 45 definitions,
61 catalog uses, and 185 answer-field bindings. Evidence execution is governed
by `selector-provenance-v1.json`. Each case declares ordered, role-tagged
required, conditional, and forbidden references. The materialized
`(role, selector_kind)` sequence must exactly equal the required sequence;
repeated kinds for different roles are valid. Each selector then resolves
through its authoritative owner with typed non-placeholder provenance.
`selector_anchors` is not a universal registry and no plan may substitute a
different kind when owner resolution fails.

Plan materialization is governed by `plan-operand-contract-v1.json`. It binds
every formula use and direct answer field to permitted logical relations,
typed request/publication/selector gates, grouping, complete order, closed
operand derivations, missing/empty behavior, and exact output extraction.
`compile_plan_operands` and `evaluate_plan` are pure L0 authorities; a
production plan still requires CK-07A's independent scenario and database-v1
fact selection and exact consumer replay before admission.

## Typed compositional boundary

The generic query grammar is allowlisted:

```text
dataset
operation
window
timezone
dimensions[]
measures[]
filters[]
group_by[]
order_by[]
limit
cursor?
include_exact_count?
```

Allowed operations are `rows`, `aggregate`, `share`, `comparison`,
`distribution`, and `timeline`. Dataset, dimension, measure, filter operator,
join path, and order key must be registered. Arbitrary SQL, expressions,
subqueries, user formulas, table names, and unbounded joins are rejected.

One request may contain up to eight independent plans so the agent can batch
related exact facts. The total result stays within one envelope byte budget.
The compiler rejects combinations with no admitted bounded plan and returns
compact guidance naming the closest presets/fields.

## Time, freshness, and coverage

- Windows are half-open integer UTC ranges derived from an explicit IANA
  timezone.
- `now` is captured once per batch.
- Calendar grains name timezone and week-start.
- All requests in a batch use one publication snapshot.
- Query reads committed facts even when a refresh is active.
- Insufficient coverage returns available facts plus a structured limitation
  when honest partial output is possible; otherwise it returns no rows and the
  exact expansion needed.
- Query never starts, joins, or polls refresh.

## Ordering, sorting, and pagination

Every plan defines a total order including logical-ID tie-breakers.

First pages use a registered index or a bounded admitted sort. Deep traversal
uses opaque signed keyset cursors containing:

- plan and plan version;
- publication ID;
- normalized request digest;
- last total-order tuple;
- expiry/version metadata.

A cursor from another publication or request fails with a restart hint. Offset
pagination is forbidden.

Sorting a displayed page in a client is not a product sort. User-requested
sorting must be compiled and applied to the complete eligible result domain
before pagination. An order is admitted only when:

- a suitable index/projection exists; or
- the plan's maximum domain is bounded and its complete server-side sort meets
  the plan budget.

Exact total counts are opt-in. Default page metadata returns
`returned_rows`, `has_more`, and `next_cursor`, not a full count scan.

## Human-readable fields

Ranked entity rows lead with:

- time/window where relevant;
- human label;
- entity kind;
- four token classes or the primary metric;
- status/completion basis;
- cost/credits and coverage where requested;
- concise operation/resource for tools;
- stable selector.

Opaque IDs, event IDs, generation internals, technical source paths, and
completion diagnostics belong at the end or in evidence metadata. Human labels
include provenance and fall back deterministically to a concise kind plus
short ID. A missing label cannot cause an empty result.

Tool rows present transport/tool name near the front, followed by semantic
operation and resource target. They never lead with an opaque invocation ID.

## Result envelope

One MCP result has one canonical structured representation:

```json
{
  "schema": "codex-usage-tracker.result.v1",
  "request_id": "opaque",
  "publication": {
    "id": "publication:...",
    "committed_at_us": 0,
    "observed_through_us": 0
  },
  "window": {
    "start_us": 0,
    "end_us": 0,
    "timezone": "America/New_York"
  },
  "coverage": {},
  "capabilities": {},
  "results": [
    {
      "question_id": "Q-ACC-02",
      "plan_id": "top_sessions",
      "plan_version": 1,
      "grades": {},
      "metrics": {},
      "rows": [],
      "caveats": [],
      "evidence_selectors": [],
      "page": {
        "returned_rows": 0,
        "has_more": false,
        "next_cursor": null
      }
    }
  ],
  "next_supported_questions": []
}
```

The transport may add a short scalar summary required by the host, but it
cannot duplicate the full rows as prose and JSON. Result serialization measures
final encoded bytes and fails closed before exceeding the hard maximum.

## Evidence service

Evidence accepts:

- one logical selector or compatible boundary pair;
- one view: `summary`, `timeline`, `calls`, `tools`, `resources`,
  `state_changes`, `allowance_interval`;
- direction and keyset cursor;
- row/byte limit;
- optional publication ID from the originating result.

It returns:

- resolved logical selector and alias basis;
- publication and coverage;
- entity summary;
- ordered rows with total-order keys, turn ordinal, lifecycle state/basis,
  four token measurements where applicable, transport/operation/resource,
  observed state changes, and occurrence coordinates;
- boundary selectors;
- page metadata.

An evidence page contains at most 100 rows and 16 KB. Evidence can page deeply
without omissions or duplicates and never requires a total count.

### Selector stability

Selectors survive:

- a clean rebuild from identical sources;
- source copy/archive;
- manifestation replacement with identical semantic events;
- physical schema/index/projection changes;
- publication rollback;
- late insertion.

If a supported identity-version correction changes string form without
changing the entity, a versioned alias resolves it and is disclosed. A semantic
split or merge cannot be hidden by aliasing.

### Occurrence evidence

Occurrence coordinates identify source manifestation/revision and record
byte range or ordinal. They prove provenance without storing or returning raw
body content. A caller may use the coordinate locally outside the MVP kernel,
but the evidence response does not dereference it.

```mermaid
sequenceDiagram
    participant A as Agent skill
    participant M as MCP query
    participant Q as Query planner
    participant D as SQLite snapshot
    participant E as Evidence service
    A->>M: named question or typed batch
    M->>Q: validated request
    Q->>D: begin read snapshot
    D-->>Q: publication + facts + projections + coverage
    Q-->>M: one bounded structured envelope
    M-->>A: facts, grades, selectors
    opt exact follow-up needed
      A->>E: selector + bounded view
      E->>D: same or declared publication snapshot
      D-->>E: ordered facts + occurrences
      E-->>A: keyset evidence page
    end
```

## Projections

### Admission rule

A projection is admitted only when:

1. at least one named Tier 1 plan is an explicit consumer;
2. the fact-backed plan misses its SQL/MCP budget or creates excessive model
   payload/calls;
3. the projection's exact semantics and missingness are defined;
4. dirty keys can be derived from accepted mutations;
5. ordinary-tail write/storage cost fits its budget;
6. a fact-backed oracle reconciles every affected key;
7. current-only storage is sufficient;
8. rate-card dependency is explicit;
9. removal criteria are defined.

No projection is added for a possible future dashboard or arbitrary query.

### Dependency metadata

Each projection registry record contains:

```text
projection_id
version
physical_owner
consumer_plan_ids
source_entity_kinds
source_measurements
lifecycle_dependencies
rate_card_dependency
dirty_key_kinds
key_expansion
update_statement_ids
delete_semantics
validation_plan
row_budget
database_byte_budget
wal_byte_budget
tail_time_budget
removal_trigger
```

### Current-only semantics

Projections represent the active publication. Historical evidence remains in
canonical facts/occurrences and publication deltas; there is no complete
projection copy per generation. An old publication selected through rollback
uses its own complete artifact.

A rate-card-dependent projection carries the selected digest. Rate changes
update valuation rows/keys only. Exact token rollups never inherit a rate-card
version.

### Initial candidate projections

These are hypotheses to measure, not automatic schema commitments:

| Projection | Candidate consumers | Dirty inputs |
| --- | --- | --- |
| Session/current usage rollup | `top_sessions`, `current_usage`, `top_expensive` | call tokens/status, hierarchy, project, label |
| Root-family usage rollup | `project_family_usage`, `parent_subagent_usage` | call tokens, parent/root relationship |
| Model/effort/time rollup | `model_effort_mix`, period drivers | call profile/tokens, UTC/calendar bucket |
| Daily usage rollup | current usage, comparisons, allowance overlay | call time/tokens, valuation key |
| Tool-family/resource rollup | tool behavior, resource hotspots | tool lifecycle, operation, resource, output/duration |
| Allowance interval summary | allowance movement/efficiency | exact adjacent observations, calls in interval |
| Latest publication delta | latest refresh changes | accepted publication mutation set |

The bake-off may eliminate, combine, or replace them.

```mermaid
flowchart LR
    F[Accepted fact and lifecycle changes] --> K[Dirty-key derivation]
    K --> S[session keys]
    K --> H[root-family keys]
    K --> T[time buckets]
    K --> M[model/tool/resource keys]
    K --> A[allowance-cycle keys]
    S --> P1[Session rollup]
    H --> P2[Family rollup]
    T --> P3[Time rollup]
    M --> P4[Profile/resource rollups]
    A --> P5[Allowance summary]
    P1 --> C1[top_sessions]
    P2 --> C2[parent_subagent_usage]
    P3 --> C3[period comparison]
    P4 --> C4[tool and model plans]
    P5 --> C5[allowance plans]
```

## Latest-publication deltas

Publication writes a compact mutation summary from accepted change records:

- facts inserted, terminalized, corrected, removed, or recanonicalized by kind;
- exact four-class token delta;
- sessions/turns/tools/resources/state changes/allowance observations affected;
- source and coverage changes;
- bounded sample selectors.

Recanonicalization is not labeled new usage. The latest-change plan reads this
summary rather than diffing all current facts.

## Exact counts and storage attribution

Exact counts are separate plans with explicit budgets. They may use compact
metadata maintained transactionally only when a named consumer justifies it.

Aggregate storage diagnostics report:

- page size/count/free list;
- bytes by table and index;
- WAL bytes;
- current publication/projection versions;
- rows by fact/projection kind;
- source selected/deferred bytes;
- dirty-key and projection-write counters.

Diagnostics do not return raw rows or technical paths by default.

## Query-plan gates

Every named plan test asserts:

- expected compiler/plan ID;
- required index/projection;
- no unapproved full scan, automatic index, or temporary sort;
- deterministic order;
- exact oracle result and grades;
- coverage and selector validity;
- first-page and exact-count behavior;
- final response bytes;
- SQL and MCP p95 at 100,000 and 1.3 million calls;
- one-call skill route;
- no refresh/job creation.

Deep-page tests assert keyset work stays proportional to page size plus
registered bounded joins, not the skipped prefix.

## Unsupported query behavior

Requests for productivity, proven waste, causal tool impact, counterfactual
subagent savings, semantic task success, exact raw context, or an unqualified
allowance forecast return a compact supported reframing from the question
catalog. They do not synthesize a numeric answer.
