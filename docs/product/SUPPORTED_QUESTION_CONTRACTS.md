# Supported Question Contracts

**Status:** Product and implementation authority
**Contract phase:** Question-to-primitive matrix
**Registry family:** `codex-usage-tracker.question-catalog.v1`

## Purpose

This catalog defines the questions the local kernel can support responsibly.
The contracts decide the logical schema, bake-off slices, projections, named
plans, result envelopes, evidence, and installed-agent trials. A schema feature
without a catalog consumer is not automatically product work.

The kernel returns facts, deterministic calculations, configured estimates,
coverage, and evidence. The model may interpret them, but must preserve grades
and prohibited claims.

## Support classes

| Code | Class | Contract |
| --- | --- | --- |
| `N` | Exact named preset | Normally one optimized `usage_query` request. |
| `C` | Exact compositional query | One bounded batch and at most one evidence follow-up. |
| `I` | Model inference | Kernel returns a versioned exact feature vector; conclusion is model-owned. |
| `O` | Optional capability | Supported only when the capability and measurement coverage are present. |
| `D` | Deferred | Deliberately outside the MVP/cutover catalog. |
| `U` | Unsupported | Available data cannot establish the requested conclusion. |

## Answer grades

| Grade | Definition |
| --- | --- |
| `exact` | Canonical observation or exact accounting over canonical observations. |
| `deterministic` | Reproducible versioned calculation over exact facts. |
| `configured_estimate` | Calculation requiring a validated external artifact such as a rate card. |
| `model_inference` | Interpretation produced by a model from disclosed features. |
| `unsupported` | No honest conclusion is available from the indexed measurements. |

Every returned field is graded. Mixed answers are expected: token totals may be
exact, cost a configured estimate, and a recommendation a model inference.

## Evidence classes

| Code | Required evidence |
| --- | --- |
| `E0` | Publication, freshness, requested window, selected and guaranteed-complete coverage, capabilities, measurements, and valuation coverage. |
| `E1` | Stable logical selector and human label for every returned entity row. |
| `E2` | Bounded total-ordered event/lifecycle sequence with keyset cursor, basis, status, and occurrence coordinates. |
| `E3` | Non-overlapping comparison windows, both totals, total delta, and signed driver contributions that reconcile. |
| `E4` | Exact allowance boundary selectors, interval compatibility, and included local facts. |
| `E5` | Exact feature vector, threshold/cohort/baseline, coverage, and representative selectors for model inference. |
| `E6` | Semantic ID, source manifestations, canonical-selection basis, and duplicate/excluded occurrence counts. |
| `E7` | Optional structural context categories, observed sizes/counts, estimator, inclusion basis, and coverage. |

## Performance classes

All targets are p95 on the qualification host and production-shaped synthetic
fixtures.

| Class | Workload | SQL/server | Local MCP | Calls | Default payload |
| --- | --- | ---: | ---: | ---: | ---: |
| `P0` | Status and coverage | `<=10 ms` | `<=250 ms` | 1 | `<=4 KB` |
| `P1` | Totals, rankings, small rollups | `<=25 ms` | `<=500 ms` | 1 | `<=8 KB` |
| `P2` | Bounded comparisons/features | `<=100 ms` | `<=500 ms` | 1 | `<=16 KB` |
| `P3` | Ordered evidence/sequence page | `<=100 ms/page` | `<=750 ms/page` | query plus at most one evidence call | `<=16 KB/page` |
| `P4` | Integrated review/candidate batch | `<=250 ms` | `<=750 ms` tracker call; `<=15 s` fresh answer | 1 plus optional evidence | `<=16 KB` |
| `P5` | Optional context composition | `<=100 ms` | `<=500 ms` | 1 | `<=16 KB` |

A plan fails if it meets latency by omitting required rows, coverage, grades, or
evidence metadata.

## Universal correctness

### Publication and canonical accounting

- One answer reads publication identity, facts, projections, coverage, and
  evidence from one SQLite snapshot.
- Source copies and archived/replaced manifestations may add occurrence
  evidence but never additional semantic usage.
- Query never starts refresh, setup, expansion, or projection work.

### Time and periods

- Stored and returned canonical instants are integer UTC microseconds.
- Windows are half-open `[start, end)`.
- Calendar windows require an explicit IANA timezone and week-start.
- Ongoing periods state `observed_through`.
- Comparisons use non-overlapping equal-duration windows, or disclose and
  normalize a partial current period.
- Exact boundary events at `start` are included; events at `end` are excluded.

### Missing and token semantics

- Missing is `NULL`, never zero.
- Ratios include only compatible observed numerators and denominators and
  disclose coverage.
- Uncached input, cached input, reasoning, and output are separate columns and
  measures.
- Default `total_tokens = uncached_input + cached_input + output`; reasoning is
  not added again without an explicitly different provider formula.

### Lifecycle, tools, and state

- End of source or absence of later events does not prove completion.
- Start, success, failure, cancellation, rollback, open, and unknown remain
  distinct.
- Transport, semantic operation, and resource are distinct.
- Write intent, successful completion, and observed mutation are distinct.
- State change belongs to its observation and containing turn/phase. It is not
  attributed only to the immediately preceding call or tool.
- Temporal adjacency is labeled non-causal.

### Hierarchy

- Parent-exclusive, descendant-exclusive, and family-inclusive usage are
  separate scopes.
- Descendants are counted exactly once.
- Late parent discovery updates relationships without changing usage identity.

### Pricing and allowance

- Cost and credits carry rate-card digest, match basis, priced/unpriced facts,
  coverage, and unpriced reason.
- Missing price is not zero cost.
- Every exact allowance observation is retained.
- Interval ratios require adjacent compatible observations and never establish
  provider billing causality.

### Ordering and disclosure

- Every result has a deterministic total order and logical-ID tie-breaker.
- Deep traversal uses keyset cursors.
- Exact counts are opt-in.
- One envelope discloses question/plan/version, publication, window, coverage,
  capabilities, grades, metrics/rows, caveats, selectors, page metadata, and
  next supported questions.
- The MCP response does not duplicate full rows in prose and structured data.

## Catalog map

`Foundation` proves the direction. `Cutover` completes the named MVP catalog.
`Advanced` uses bounded composition. `Inference`, `Optional`, and `Deferred`
do not block the first vertical proof unless a task packet says otherwise.

| ID | Plan | Class | Stage | Evidence | Perf | Default |
| --- | --- | --- | --- | --- | --- | --- |
| Q-ACC-01 | `current_usage` | N | Foundation | E0 | P1 | metrics + <=10 groups |
| Q-ACC-02 | `top_sessions` | N | Foundation | E0,E1 | P1 | 10 rows |
| Q-ACC-03 | `period_drivers` | N | Cutover | E3,E1 | P2 | 10 drivers |
| Q-ACC-04 | `model_effort_mix` | N | Foundation | E0 | P1 | 20 rows |
| Q-ACC-05 | `project_family_usage` | N | Cutover | E0,E1 | P1 | 10 rows/mode |
| Q-ACC-06 | `top_valued_entities` | N | Cutover | E0,E1 | P1 | 10 rows |
| Q-ACC-07 | `pricing_coverage` | N | Cutover | E0,E1 | P1 | 20 gaps |
| Q-CTX-01 | `cache_reuse_candidates` | N | Foundation | E1,E5 | P1 | 10 rows |
| Q-CTX-02 | `context_pressure_trajectory` | N | Cutover | E1,E2 | P2 | 10 sessions |
| Q-CTX-03 | `token_acceleration` | C | Advanced | E1,E5 | P2 | 10 sessions |
| Q-CTX-04 | `uncached_input_jumps` | N | Cutover | E2 | P2 | 10 pairs |
| Q-CTX-05 | `tool_output_adjacency` | C,I | Advanced | E2,E5 | P2 | 10 sequences |
| Q-CTX-06 | `cached_replay_small_output` | C,I | Advanced | E1,E5 | P2 | 10 rows |
| Q-CTX-07 | `context_composition` | O,D | Optional | E7 | P5 | 20 categories |
| Q-CTX-08 | `compaction_comparison` | C | Advanced | E2,E5 | P2 | 10 boundaries |
| Q-CTX-09 | `growth_without_mutation` | I | Inference | E2,E5 | P2 | 10 candidates |
| Q-CTX-10 | `long_vs_split_cohorts` | D,I | Deferred | E3,E5 | P4 | bounded cohorts |
| Q-WF-01 | `turn_completion_efficiency` | N | Foundation | E0,E1 | P1 | 10 sessions |
| Q-WF-02 | `first_action_mutation` | N | Foundation | E1,E2 | P2 | 10 turns |
| Q-WF-03 | `repeated_resource_operations` | C | Advanced | E2,E5 | P2 | 10 patterns |
| Q-WF-04 | `retry_cycles` | C | Advanced | E2,E5 | P2 | 10 cycles |
| Q-WF-05 | `tool_family_behavior` | N | Foundation | E0,E1 | P1 | 20 rows |
| Q-WF-06 | `tool_following_activity` | C,I | Advanced | E2,E5 | P2 | 10 sequences |
| Q-WF-07 | `resource_hotspots` | N | Cutover | E1,E2 | P2 | 20 resources |
| Q-WF-08 | `model_effort_transitions` | C | Advanced | E2 | P2 | 20 transitions |
| Q-WF-09 | `automation_candidates` | I | Inference | E5,E2 | P4 | 10 features |
| Q-WF-10 | `tool_duration_gaps` | C | Advanced | E2 | P2 | 20 rows |
| Q-DEL-01 | `parent_subagent_usage` | N | Cutover | E0,E1 | P1 | 10 families |
| Q-DEL-02 | `delegation_cohorts` | I | Inference | E3,E5 | P4 | bounded cohorts |
| Q-ALW-01 | `allowance_movement` | N | Foundation | E0,E4 | P1 | 20 observations |
| Q-ALW-02 | `allowance_interval_events` | N | Cutover | E4,E2 | P3 | 100 events/page |
| Q-ALW-03 | `allowance_local_efficiency` | C | Advanced | E4,E0 | P2 | 20 intervals |
| Q-ALW-04 | `allowance_cycle_comparison` | C | Advanced | E3,E4 | P2 | 12 cycles |
| Q-OPS-01 | `latest_publication_delta` | N | Foundation | E0,E1 | P1 | metrics + 10 samples |
| Q-OPS-02 | `data_health` | N | Foundation | E0 | P0 | compact status |
| Q-OPS-03 | `dedup_source_audit` | C | Advanced | E6 | P2 | 20 sources/entities |
| Q-OPS-04 | `evidence_timeline` | N | Foundation | E2,E4 | P3 | 100 rows/page |
| Q-REV-01 | `weekly_review` | N | Cutover | E0,E1,E3,E4 | P4 | compact sections |
| Q-REV-02 | `investigation_candidates` | I | Inference | E5 + route | P4 | <=10 candidates |
| Q-REV-03 | `compare_sessions` | C | Advanced | E1,E3,E2 | P2/P3 | two sessions |

## Question contracts

Shared defaults below apply unless a question states otherwise:

- caller supplies window/timezone; named current windows derive them once;
- default freshness is the committed publication with explicit age;
- default hard result cap is 16 KB;
- rows include human labels and stable selectors;
- synthetic cases include boundary time, duplicate occurrence, missing
  measurement, deterministic tie, and partial coverage;
- a less-capable model must use the named plan directly, repeat grades/caveats,
  and avoid every `Must not` claim.

### Accounting, concentration, and drivers

#### Q-ACC-01: Current usage

- **Intent:** “How much usage is in this session/today/this week/the selected
  window?” Variants include token breakdown and current project.
- **Facts and plan:** canonical calls, four token classes, session/project/time
  keys; `current_usage`; optional current session and project filters.
- **Calculation:** exact sums and counts; cost/credits only as current
  configured estimates. Any total formula is returned.
- **Coverage/evidence:** E0; E1 when grouped entity rows are present.
- **Must not:** infer completion, productivity, or remaining allowance.
- **Oracle emphasis:** start/end boundaries, partial day, missing reasoning,
  duplicate manifestation, empty observed window.

#### Q-ACC-02: Top sessions and concentration

- **Intent:** “List my top threads/sessions by usage” and “How concentrated is
  usage?”
- **Facts/projection:** session-exclusive call rollup, human label, global
  denominator; candidate session/current rollup.
- **Calculation:** ranked exact totals, top-N share, remainder share, optional
  top-1/top-5/HHI with versioned formulas.
- **Coverage/evidence:** E0 and E1 for every row; top-N plus remainder
  reconciles.
- **Must not:** call a large session wasteful or semantically group sessions by
  label.
- **Oracle emphasis:** ties, dominant outlier, archived copy, unknown label,
  all four token columns, stable order.

#### Q-ACC-03: Period change and drivers

- **Intent:** “Compare the last seven days to the previous seven and explain
  which sessions/projects/models/tools account for the arithmetic change.”
- **Facts/projection:** time-bucketed canonical usage and one requested driver
  dimension.
- **Calculation:** equal non-overlapping windows, totals, absolute/percentage
  delta, signed contributions reconciling to delta.
- **Coverage/evidence:** E3; E1 for entity drivers; partial periods use equal
  elapsed spans or disclose asymmetry.
- **Must not:** turn arithmetic contribution into causal explanation.
- **Oracle emphasis:** new/disappearing dimensions, zero prior, offsetting
  signs, DST boundary, partial history.

#### Q-ACC-04: Model, effort, and service-tier mix

- **Intent:** “Which model/effort combinations consume each token class?”
- **Facts/projection:** model profile, effort, service tier, four token fields,
  model/time rollup.
- **Calculation:** exact grouped totals/shares with explicit unknown
  categories and observed denominators.
- **Coverage/evidence:** E0; follow-up filter hints, no arbitrary model aliases.
- **Must not:** claim one profile is better without comparable outcomes.
- **Oracle emphasis:** missing effort, missing reasoning, profile transition
  within session, pricing alias not used for exact grouping.

#### Q-ACC-05: Project and session-family usage

- **Intent:** “Which projects or parent/subagent families dominate?”
- **Facts/projection:** project, session hierarchy, root, exclusive calls;
  project and root-family rollups.
- **Calculation:** project-exclusive and family-inclusive modes in separately
  labeled sections; descendants counted once.
- **Coverage/evidence:** E0/E1; hierarchy capability and unresolved parents
  disclosed.
- **Must not:** infer semantic task families from labels.
- **Oracle emphasis:** multi-level descendants, orphan, late parent, unknown
  project, copied child.

#### Q-ACC-06: Most expensive entities

- **Intent:** “Which calls, turns, or sessions have the highest current
  estimated dollar or credit value?”
- **Facts/projection:** canonical calls/four tokens, entity membership, selected
  rate-card revision; bounded top-entity valuation.
- **Calculation:** current configured valuation; unpriced entities remain
  visible; aggregate valuation is the sum of priced canonical calls.
- **Coverage/evidence:** E0/E1 with rate digest, rated/unrated tokens/calls.
- **Must not:** label estimate as billed cost or reconstruct historical prices.
- **Oracle emphasis:** mixed prices, before/exact/after effective boundaries,
  late-ingested historical calls, model-subset replacement, missing required
  token, ties, zero priced coverage.

Here, “reconstruct historical prices” means the price known at ingestion or
the amount charged. Applying the publication's current configured schedule by
explicit effective time remains an estimate and does not make either claim.

#### Q-ACC-07: Pricing and credit gaps

- **Intent:** “How much usage lacks cost or credit estimates, and which models
  explain the gap?”
- **Facts/projection:** current rate matches and model usage.
- **Calculation:** rated/unrated calls and tokens, coverage by explicit
  denominator, grouped unpriced reason.
- **Coverage/evidence:** E0; E1 for sample calls.
- **Must not:** report total spend as complete below 100% coverage.
- **Oracle emphasis:** absent/invalid/partial card, unmatched alias, observed
  call with no rate.

### Context and cache behavior

#### Q-CTX-01: Poor cache reuse under high input

- **Intent:** “Where is cache reuse low despite high input?”
- **Facts/projection:** calls/turns/sessions with observed uncached and cached
  input; session rollup or bounded call plan.
- **Calculation:** cached share and total input only on observed pairs; returned
  threshold/percentile revision.
- **Coverage/evidence:** E1; E5 when labeled an investigation candidate.
- **Must not:** equate poor cache reuse with workflow quality.
- **Oracle emphasis:** zero input, missing cached input, huge input with high
  reuse, percentile ties.

#### Q-CTX-02: Context-pressure trajectory

- **Intent:** “Which sessions approach context limits or deteriorate across
  turns?”
- **Facts/projection:** deterministic turn order, input, context window, cache
  reuse, compaction epochs.
- **Calculation:** pressure ratio, early/late comparison or versioned slope;
  never crosses epoch implicitly.
- **Coverage/evidence:** E1 for ranking, E2 for selected timeline; context-window
  coverage required.
- **Must not:** prescribe splitting or claim causality.
- **Oracle emphasis:** missing window, model window change, compaction, late
  event, open turn.

#### Q-CTX-03: Token acceleration

- **Intent:** “Which sessions accelerate across successive turns?”
- **Facts/plan:** ordered turn token totals; compositional feature plan.
- **Calculation:** returned versioned statistic with minimum N and outlier
  policy, such as later/earlier median ratio and second difference.
- **Coverage/evidence:** E1/E5; selected E2 follow-up.
- **Must not:** call acceleration waste or caused by context.
- **Oracle emphasis:** constant, linear, accelerating, one outlier, too-short,
  missing turn.

#### Q-CTX-04: Largest uncached-input jumps

- **Intent:** “Where did new input jump most between consecutive calls/turns?”
- **Facts/plan:** ordered calls/turns and context epoch.
- **Calculation:** absolute/percentage delta inside one session/epoch; boundary
  pair returned.
- **Coverage/evidence:** E2 with previous and current selectors.
- **Must not:** attribute jump to the preceding event.
- **Oracle emphasis:** first call, compaction, equal time, negative jump,
  missing prior.

#### Q-CTX-05: Tool-output adjacency

- **Intent:** “Which large tool outputs were followed by the largest new-input
  increase?”
- **Facts/plan:** tool output bytes, lifecycle, following model call, intervening
  count/time, input delta.
- **Calculation:** deterministic adjacency inside session/turn with maximum gap
  returned.
- **Coverage/evidence:** E2; E5 for model prioritization.
- **Must not:** say tool output was included or caused the increase.
- **Oracle emphasis:** multiple tools, intervening event, no following call,
  missing output/input.

#### Q-CTX-06: Cached replay with small output

- **Intent:** “Where is large cached replay producing little model output?”
- **Facts/plan:** cached input and output by call/turn/session.
- **Calculation:** ranking/ratio only on observed pairs; threshold revision
  returned.
- **Coverage/evidence:** E1/E5.
- **Must not:** infer little useful work because tools may carry the action.
- **Oracle emphasis:** zero output, missing output, tool-heavy turn, high
  uncached input.

#### Q-CTX-07: Context composition

- **Intent:** “How much observed context belongs to tools, MCP, files, messages,
  or other structural categories?”
- **Facts/plan:** optional structural component observations with inclusion
  basis and optional estimator.
- **Calculation:** exact observed bytes/counts; estimated tokens only with
  estimator; unattributed amount explicit.
- **Coverage/evidence:** E7 and capability present.
- **Must not:** expose raw bodies or claim observed source content was included
  in a call.
- **Disposition:** deferred until the metadata-only MVP qualifies and the
  capability proves enough value for its indexing cost.

#### Q-CTX-08: Compaction effect

- **Intent:** “How did token/context behavior differ immediately before and
  after compaction?”
- **Facts/plan:** compaction boundary, epochs, bounded calls/turns on both sides.
- **Calculation:** exact/deterministic differences over stated symmetric
  windows.
- **Coverage/evidence:** E2/E5.
- **Must not:** claim compaction caused improvement or degradation.
- **Oracle emphasis:** multiple compactions, missing side, model change, late
  event, unequal windows.

#### Q-CTX-09: Growth without observed state change

- **Intent:** “Which sessions combine context growth with few observed
  mutations?”
- **Facts/plan:** pressure/growth features, turn/phase state changes, capability
  coverage.
- **Calculation:** deterministic feature vector; model ranks candidates.
- **Coverage/evidence:** E2/E5; mutation capability mandatory.
- **Must not:** say no useful work occurred or a tool failed to change state.
- **Oracle emphasis:** unavailable mutation capability, delayed mutation after
  multiple tools, read-only task, one mutation.

#### Q-CTX-10: Long versus split sessions

- **Intent:** “Do long sessions differ from newly split related sessions?”
- **Disposition:** deferred model inference. The kernel lacks reliable semantic
  task relatedness and controlled outcomes.
- **Future facts:** explicit user-provided cohort/relationship, exact usage and
  context features.
- **Must not:** recommend splitting from label similarity or length alone.

### Workflow, tools, and resources

#### Q-WF-01: Turn count and completion efficiency

- **Intent:** “How many turns/calls/tokens did sessions use before observed
  completion?”
- **Facts/projection:** turn/session lifecycle, call usage, completion basis.
- **Calculation:** exact counts and tokens for completed/open/failed cohorts;
  ratios only with valid completion.
- **Coverage/evidence:** E0/E1.
- **Must not:** treat fewer turns as better or end-of-file as completion.
- **Oracle emphasis:** explicit success/failure/cancel, open tail, no calls,
  late terminal.

#### Q-WF-02: Before first action and mutation

- **Intent:** “How much time/tokens occurred before first tool action,
  successful tool, and observed mutation?”
- **Facts/plan:** turn start, ordered calls, tool lifecycle, state changes.
- **Calculation:** three separate first-boundary metrics; no mutation remains
  `NULL`.
- **Coverage/evidence:** E1/E2.
- **Must not:** attribute later mutation to only the boundary call/tool.
- **Oracle emphasis:** action fails then succeeds, success without mutation,
  mutation after multiple calls, read-only turn.

#### Q-WF-03: Repeated resource operations

- **Intent:** “Which files/resources were repeatedly read, searched, written,
  tested, or revisited?”
- **Facts/plan:** normalized resource links, operation, turn/session order.
- **Calculation:** exact counts, revisit distances, repeated runs; model may
  prioritize patterns.
- **Coverage/evidence:** E2/E5; resource coverage disclosed.
- **Must not:** call repetition unnecessary.
- **Oracle emphasis:** equivalent path spellings, ambiguous path, read/write
  mix, retries, copied sources.

#### Q-WF-04: Inspect-fail-reinspect-retry cycles

- **Intent:** “Show repeated inspect, attempt, failure, reinspect, retry
  sequences.”
- **Facts/plan:** tool lifecycle, semantic operation/resource, total order.
- **Calculation:** versioned finite sequence matcher; exact matched events.
- **Coverage/evidence:** E2/E5.
- **Must not:** label cycle waste or failure cause.
- **Oracle emphasis:** success first try, unrelated interleaving, cancellation,
  different resource, open retry.

#### Q-WF-05: Tool family behavior

- **Intent:** “Which tools/operations dominate calls, latency, output, failures,
  and adjacent token activity?”
- **Facts/projection:** transport, family, semantic operation, lifecycle,
  duration/output; tool rollup.
- **Calculation:** exact grouped counts/status; duration/output only observed;
  adjacency labeled deterministic non-causal.
- **Coverage/evidence:** E0/E1.
- **Must not:** convert unknown to zero or name tool ID before human tool name.
- **Oracle emphasis:** unknown operation, incomplete tool, missing duration,
  multiple transports, deterministic ordering.

#### Q-WF-06: Tool output versus following model activity

- **Intent:** “Compare tool output size with the next model-call token mix.”
- **Facts/plan:** exact tool-to-following-call adjacency, output bytes, four
  tokens, time/intervening events.
- **Calculation:** bounded feature vector and optional cohort statistics.
- **Coverage/evidence:** E2/E5.
- **Must not:** claim output caused or was included in context.
- **Oracle emphasis:** no following call, multiple tools, long gap, missing
  bytes/tokens.

#### Q-WF-07: Resource hotspots

- **Intent:** “Which resources receive the most reads, writes, tests, time,
  output, or observed changes?”
- **Facts/projection:** resource links, tool lifecycle, state changes; resource
  rollup candidate.
- **Calculation:** exact grouped metrics with operation breakdown and separate
  observed mutation count.
- **Coverage/evidence:** E1 and selected E2.
- **Must not:** call a hot resource a bottleneck without supporting timing.
- **Oracle emphasis:** normalized aliases, same basename/different project,
  write without change, change after cumulative work.

#### Q-WF-08: Model and effort transitions

- **Intent:** “Where did model, effort, or service tier change within a
  session?”
- **Facts/plan:** ordered model calls and profiles.
- **Calculation:** exact consecutive transition counts and token deltas.
- **Coverage/evidence:** E2.
- **Must not:** infer why the host/model changed or which choice was better.
- **Oracle emphasis:** unknown effort, compaction, repeated same profile, late
  call.

#### Q-WF-09: Automation or skill candidates

- **Intent:** “Which repeated structural workflows might deserve a script,
  skill, or optimized endpoint?”
- **Facts/plan:** versioned sequence/resource/tool feature vectors, frequency,
  spread, failure and mutation coverage.
- **Calculation:** deterministic candidate generation; final ranking and
  recommendation are model inference.
- **Coverage/evidence:** E5 and representative E2.
- **Must not:** persist `skill_candidate` or promise savings.
- **Oracle emphasis:** no candidate, one-off repetition, conflicting outcomes,
  high-frequency stable sequence.

#### Q-WF-10: Tool durations and gaps

- **Intent:** “Where did long completed-tool durations or observed inactive
  event gaps occur?”
- **Facts/plan:** tool lifecycle times and adjacent event times.
- **Calculation:** tool duration and event gap are separate rankings.
- **Coverage/evidence:** E2.
- **Must not:** call a gap thinking time, hang, user delay, or waste.
- **Oracle emphasis:** user gap, incomplete/cancelled tool, time tie, late
  event.

### Delegation

#### Q-DEL-01: Parent and subagent usage

- **Intent:** “Which parents delegated most, and how much usage is exclusive to
  parents, descendants, or the whole family?”
- **Facts/projection:** hierarchy/depth, canonical calls, family rollup.
- **Calculation:** exact exclusive/inclusive totals, child count, depth.
- **Coverage/evidence:** E0/E1; unresolved parents disclosed.
- **Must not:** claim delegation benefit or necessity.
- **Oracle emphasis:** multiple levels, orphan, copied child, parent with zero
  exclusive calls.

#### Q-DEL-02: Delegation behavior comparison

- **Intent:** “How do parent and subagent cohorts differ observationally?”
- **Facts/plan:** exact role cohorts, usage/context/tool/failure/mutation
  features, controls where observed.
- **Calculation:** observational comparison with cohort sizes and confounders.
- **Coverage/evidence:** E3/E5 and representative E1.
- **Must not:** claim counterfactual savings, quality improvement, or task
  equivalence.
- **Oracle emphasis:** unequal cohorts, missing role, model-mix confounder,
  extreme family.

### Allowance and limits

#### Q-ALW-01: Allowance movement and local usage

- **Intent:** “Show exact allowance observations/reset boundaries beside local
  calls, turns, four tokens, cost, and credits.”
- **Facts/projection:** every observation/cycle, compatible intervals, time
  usage rollup, current valuation.
- **Calculation:** exact boundary values and deterministic local usage between
  adjacent compatible observations.
- **Coverage/evidence:** E0/E4.
- **Must not:** claim local events fully explain drain or one call caused a
  percentage change.
- **Oracle emphasis:** identical repeats, reset, missing reset, incompatible
  plan, outside usage possible.

#### Q-ALW-02: Events between observations

- **Intent:** “Which exact calls, turns, tools, or mutations occurred between
  these adjacent observations?”
- **Facts/plan:** exact boundary selectors and canonical total-ordered events.
- **Calculation:** explicit half-open interval inclusion; keyset pages.
- **Coverage/evidence:** E4/E2.
- **Must not:** assign equal or causal contribution.
- **Oracle emphasis:** same-time boundaries, no events, reset, multiple
  sessions, late event.

#### Q-ALW-03: Local efficiency per percentage point

- **Intent:** “Estimate observed tokens/calls/turns/cost/credits per allowance
  percentage point.”
- **Facts/plan:** compatible positive-delta intervals and local numerators.
- **Calculation:** deterministic numerator/delta; cost/credits configured
  estimates; zero/negative/reset/incompatible yields `NULL`.
- **Coverage/evidence:** E4 and pricing E0.
- **Must not:** call the ratio the provider conversion formula.
- **Oracle emphasis:** zero/negative delta, reset, unpriced calls, multiple
  models.

#### Q-ALW-04: Completed cycle comparison

- **Intent:** “Compare local usage and observed allowance movement across
  completed reset windows.”
- **Facts/plan:** completed comparable cycles, exact observations, usage and
  current valuation.
- **Calculation:** cycle-level deterministic comparison; plan, limit, duration,
  and coverage compatibility disclosed.
- **Coverage/evidence:** E3/E4.
- **Must not:** infer provider-accounting changes.
- **Oracle emphasis:** incomplete current cycle, plan/duration change, missing
  observations, low pricing coverage.

### Operations, evidence, and reviews

#### Q-OPS-01: Latest publication changes

- **Intent:** “What changed in the latest incremental refresh/publication?”
- **Facts/projection:** accepted mutation summary and bounded sample selectors.
- **Calculation:** inserted/terminalized/corrected/removed/recanonicalized by
  type and exact token delta.
- **Coverage/evidence:** E0/E1.
- **Must not:** label recanonicalization or updated rows as new activity.
- **Oracle emphasis:** no change, one-call append, cross-publication tool
  completion, replacement, canonical-owner change.

#### Q-OPS-02: Data health and freshness

- **Intent:** “Is the index fresh/complete enough, and what capabilities or
  measurements are missing?”
- **Facts/plan:** publication, coverage, source inventory, capabilities,
  measurements, valuation, storage/operation state.
- **Parameters:** required captured `as_of_us`; optional scope/window. The
  kernel never reads a clock.
- **Calculation:** exact age/ranges/counts; `indexed_from` distinct from
  `guaranteed_complete_from`.
- **Coverage/evidence:** E0.
- **Must not:** claim deferred/uncertain sources do not exist.
- **Oracle emphasis:** deferred history, uncertain/malformed source, stale
  publication, missing card/capability.

#### Q-OPS-03: Deduplication/source audit

- **Intent:** “Are copied, archived, replaced, or truncated sources changing
  totals?”
- **Facts/plan:** semantic entities, occurrences, manifestations, canonical
  basis, recanonicalization records.
- **Calculation:** exact reconciliation of semantic and physical counts.
- **Coverage/evidence:** E6.
- **Must not:** call physical copies duplicate user work.
- **Oracle emphasis:** exact duplicate, near collision, replacement, archive,
  owner change.

#### Q-OPS-04: Evidence timeline

- **Intent:** “Show the exact timeline for this session/turn/call/tool/resource
  or allowance interval.”
- **Facts/plan:** ordered point events, lifecycle transitions/current state,
  human labels, four tokens, resources, state changes, occurrences.
- **Calculation:** deterministic total order and keyset pages; compact turn
  summary may precede event detail.
- **Coverage/evidence:** delivery surface for E2/E4.
- **Must not:** expose raw content, infer causality, or omit blanks by replacing
  them with zero.
- **Oracle emphasis:** late/equal-time event, replacement, lifecycle across
  publications, stable cursor/rebuild.

#### Q-REV-01: Weekly review

- **Intent:** “Give me a compact weekly usage review with concentration, change
  drivers, model/tool/context/allowance facts, coverage, and evidence routes.”
- **Facts/projection:** one batch of admitted named sections using one
  publication/window.
- **Calculation:** exact/deterministic sections; unavailable sections omitted
  with limitation; model writes synthesis.
- **Coverage/evidence:** E0/E1/E3/E4 as applicable.
- **Must not:** claim productivity, causal waste, or server-authored findings.
- **Oracle emphasis:** partial history, no allowance, unpriced model, outlier,
  optional context absent.

#### Q-REV-02: Actionable investigations

- **Intent:** “Choose up to three evidence-backed investigations.”
- **Facts/plan:** bounded versioned feature candidates for expensive usage,
  repetition, failure, context, completion, and observed mutation.
- **Calculation:** kernel generates features; model ranks no more than three,
  cites metrics/baseline/limitations.
- **Coverage/evidence:** E5 plus an appropriate E1/E2/E3/E4 route.
- **Must not:** claim proven waste, guaranteed savings, or causal diagnosis.
- **Oracle emphasis:** no candidate, conflicting signals, missing measurement,
  dominant outlier, low coverage.

#### Q-REV-03: Compare two sessions

- **Intent:** “Compare two sessions structurally by turns, calls, four tokens,
  tools, resources, changes, context, delegation, and completion.”
- **Facts/plan:** exact side-by-side entity metrics and optional aligned
  sequences.
- **Calculation:** deterministic deltas; inclusive family mode explicit.
- **Coverage/evidence:** E1/E3 and selected E2; E7 only if optional capability
  exists.
- **Must not:** assert semantic task equivalence or which session/model is
  better.
- **Oracle emphasis:** differing coverage/capabilities, open session, subagent
  family, optional capability on one side.

## Unsupported and reframed questions

| Unsupported wording | Supported response |
| --- | --- |
| “Which threads wasted the most tokens?” | Return high-usage sessions plus exact repetition, failure, context, completion, and mutation features; model may propose investigations. |
| “Which tool caused the context increase?” | Return exact adjacent tool/call sequence, intervening events, output bytes, and input delta with non-causal label. |
| “Did subagents save tokens?” | Return exclusive/inclusive totals and observational role cohorts. |
| “Which session accomplished the most work?” | Return observed completion, state changes, tool activity, and output; no semantic value judgment. |
| “Was this reasoning necessary?” | Return reasoning amount, sequence position, later actions, and cohort features; necessity is unsupported. |
| “Why did the model fail?” | Return lifecycle/error category and preceding/recovery sequence; causal explanation is model inference. |
| “Predict exactly when allowance runs out.” | Return exact observations and deterministic completed burn intervals; forecasting requires a qualified statistical workflow. |
| “What exact prompt or output was in context?” | Metadata-first MVP does not store raw bodies; optional future components disclose only structural categories and basis. |
| “Which model is best?” | Unsupported without controlled task/outcome data. |
| “Should I always split long sessions?” | Return context/cache trajectories and explicit cohorts; recommendation remains model-owned. |

## Admission and removal

A named preset is admitted only when:

1. the question is answerable without raw-content interpretation;
2. required stable evidence is bounded;
3. a deterministic synthetic oracle exists;
4. the optimized plan meets P0/P1/P2 at 100,000 and 1.3 million calls;
5. default response is at most 16 KB;
6. the skill needs one tracker call, or one query plus one evidence call;
7. less-capable-model qualification is accurate and useful;
8. ordinary tails can maintain any projection within their write budget.

A preset is demoted or removed when measurement coverage is routinely
insufficient, it cannot meet budgets without misleading truncation, agents
overstate its claims despite the contract, or it duplicates another preset.

## Executable registry requirements

The production registry has one machine record per catalog row containing:

```text
question_id and version
support class and stage
intent phrases
required and optional parameters
required capabilities and measurements
logical plan and physical compiler
answer fields, formulas, and grades
window/timezone semantics
coverage/freshness policy
evidence classes and selector kinds
prohibited claims
order, row, count, and byte limits
performance class and scan/sort budgets
projection consumers
synthetic oracle IDs
less-capable-model instruction
```

Static tests reconcile this Markdown catalog, registry, question-to-primitive
matrix, task packets, qualification prompts, and plan implementations.

`config/agent-kernel/formula-contract-v1.json` is the executable authority for
all formula IDs and answer-field bindings. A catalog question's
`selector_kinds` is a plan allowlist. Each scenario case declares the ordered,
role-tagged references that are required, conditional, or forbidden; repeated
kinds are allowed. Evidence is complete only when that required role/kind
sequence exactly equals the materialized sequence and every reference passes
the owner-specific rules in `FORMULA_AND_SELECTOR_CONTRACT.md`.

## Qualification

Every admitted question proves:

- exact rows/totals and formulas on synthetic truth;
- duplicate occurrences do not change totals;
- time boundaries/timezones and missing values are correct;
- hierarchy, pricing, allowance, and driver reconciliations pass;
- every selector resolves through its authoritative owner in the same
  publication or, for a request-owned window, the same request digest;
- keyset pages have no gaps/duplicates;
- no unsupported causal field exists;
- expected physical compiler/index/projection is used;
- no unapproved full scan/temporary sort;
- latency, payload, and tracker-call budgets pass;
- query starts no refresh or projection work;
- default and less-capable fresh Codex tasks answer accurately, use evidence,
  preserve grades, and do not poll.
