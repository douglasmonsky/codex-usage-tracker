# Qualification and Benchmark Plan

**Status:** Release and cutover authority
**Core metric:** A fresh installed Codex task gives a fast, exact, useful answer
with few calls and few model tokens.

Unit tests and microbenchmarks are necessary but not sufficient. The product is
qualified only through the exact wheel, plugin, MCP catalog, and skill that a
user installs.

## Evidence levels

| Level | Scope | What it can prove |
| --- | --- | --- |
| L0 | Pure contract/vector tests | Identity, formulas, ordering, missingness. |
| L1 | Synthetic adapter/storage integration | Canonical facts, lifecycle, source handling, publication. |
| L2 | Query/evidence/projection tests | Exact answers, plans, selectors, pagination, grades. |
| L3 | Repeatable performance harness | Build/tail/query/storage/CPU budgets. |
| L4 | Exact built distribution | Packaging, dependency, bundle, version, clean install. |
| L5 | Fresh Codex CLI/Desktop tasks | Real tool selection, latency, token efficiency, accuracy, usefulness. |
| L6 | Cutover/recovery drill | Side-by-side safety, rollback, artifact promotion, retirement readiness. |

No lower level substitutes for a required higher level.

### Evidence claim classes

Evidence must state the exact class proved; these claims are not
interchangeable:

| Claim | Required proof |
| --- | --- |
| Structural validity | Schema, identity, ordering, and digest checks pass. |
| Formula consistency | Values inside one oracle record satisfy its declared formulas. |
| Canonical-fact lineage | The exact typed request selects canonical typed facts emitted by its scenario, and an independent evaluator derives the expected result from those facts. |
| Consumer replay | The actual downstream adapter, storage, publication, or query path produces the same result from only its permitted inputs. |

A packet may claim only the classes it executed. A prior packet's completion,
matching hashes, or internal oracle reconciliation cannot substitute for
canonical-fact lineage or consumer replay.

Every dependency edge used as truth records a seam contract with:

```text
producer artifact path, schema, revision, and digest
consumer packet and executable path
independent truth source or reference evaluator
executable seam check
exact request/result comparison
affected evidence and packets to requalify after change
```

If consumer replay disproves an upstream claim, the dependent packet stops.
The roadmap admits a corrective packet, preserves the historical record, and
requires current requalification evidence before the dependency may be
consumed again.

CK-07C adds an L0 prerequisite for CK-07A: the versioned plan-operand artifact
must schema-validate and reconcile exactly 40 plans, 61 formula uses, 112
direct bindings, 73 formula-output bindings, and all 185 answer fields. Its
pure compiler/evaluator vectors cover request and fact typing, gates, grouping,
total order, `NULL` and empty behavior, exact decimal serialization, missing
operands, output extraction, and internal-only formula consumption. These
contract vectors prove executability only; they do not substitute for
CK-07A's 80-case canonical-fact lineage and database consumer replay.

CK-07D adds the remaining L0 valuation prerequisite. Synthetic calls before,
at, and after an explicit pricing boundary must select the greatest matching
publication-captured revision effective at each call's `event_at_us`.
Late-ingested historical calls, model-subset changes, future revisions, missing
times, invalid lineages, and ambiguous equal-effective matches must replay
identically through the pure reference boundary and database-v1 publication
path. Typed unpriced valuation rows must remain unpriced in coverage. CK-05,
CK-07, and CK-07C valuation seams require linked requalification before CK-07A
may resume.

CK-07D's local implementation results, artifact identities, twelve acceptance
proofs, validation measurements, review state, and residual merge gates are
recorded in
`docs/decisions/evidence/ck07d/effective-dated-valuation-implementation-evidence.json`.
That local evidence does not unblock CK-07A or CK-08 before merge and
exact-main verification.

CK-07E is the final L0 adapter prerequisite before CK-07A. A structural
reference adapter and a separately implemented query-only database-v1 adapter
must independently emit equivalent normalized `CanonicalFact` rows,
`PlanRequest`, and exact ordered owner-specific evidence. Qualification covers
every plan relation/fact family, all 14 selector owners, typed non-placeholder
provenance, NULL/empty/ties/order/no-window behavior, effective-dated
valuation and unpriced coverage, import/source independence, privacy, and
clean rebuild/replacement/late-event stability. These comparisons stop at the
fact/request/evidence boundary: CK-07E must record 0 / 80 CK-07A answer
comparisons and cannot update CK-04 scoring or CK-03 through CK-07 seam
evidence.

CK-07A completes that L0 chain with 80 / 80 exact answer comparisons through
structural-v2 source JSONL, CK-06 ingestion, CK-07 publication/recovery,
query-only database-v1, Candidate A's permitted fact-table/planner lane, and
both independent adapters. Its durable evidence records all 185 answer-field
bindings, 14 selector kinds, six provenance kinds, ordered references, SQL
sources/plans, response bytes, timings, lifecycle replay, privacy, and CK-03
through CK-07 requalification. CK-04's current-commit growth repetitions 3 and
4 remain waived; the strict five-repetition aggregate remains unclaimed.

## Synthetic fixture strategy

Fixtures contain no real local usage records or raw content. A deterministic
generator emits:

- Codex-shaped JSONL structural records;
- source layouts, copies, archives, truncations, replacements, malformed lines,
  uncertain dates, and moving tails;
- sessions, turns, calls, tools, resources, activities, compactions, observed
  mutations, hierarchy, allowance observations, and rate cards;
- exact four token classes and deliberate missing fields;
- expected canonical identities, counts, totals, lifecycle states, coverage,
  selectors, occurrence coordinates, and question answers.

Every fixture has a manifest:

```text
schema and generator version
seed and manifest digest
history range and timezone
source/file/byte counts
event-kind and missingness distributions
duplicate/replacement/late-event cases
capabilities and rate-card revision
expected canonical/projection counts
question oracle IDs
```

Tiny fixtures are hand-auditable. Scale fixtures are generated from the same
semantic case library, not a separate simplified benchmark model.

CK-03 freezes the source revision as `agent-kernel-structural-v1`. Source
records are compact canonical JSON Lines; manifests and oracle bundles use
canonical JSON. Every artifact digest is SHA-256: exact source bytes, the
complete oracle bundle, and the manifest with its own digest field omitted.
Only the tiny fixture is checked in. Small, standard, production-shaped, and
growth fixtures are generated on demand from versioned profiles. The exact
format, atomic CLI, digest ratchets, and measured generation evidence are
recorded in
[`tests/agent_kernel/fixtures/README.md`](../../tests/agent_kernel/fixtures/README.md).
Manifest-only generation still serializes and hashes every source byte; it
does not substitute an estimate.

## Production-shape profiler

A local opt-in profiler may inspect aggregate structure of a user-owned source
tree to improve synthetic distributions. It records only:

- files and bytes by age/source kind;
- JSONL record-size histograms;
- event-kind and lifecycle-transition counts;
- missing-field/capability counts;
- session/turn/call/tool/resource cardinalities and bounded histograms;
- timestamp density/ties;
- source copy/replacement/truncation counts;
- four token-class presence and numeric histograms;
- allowance-observation cadence/repetition counts;
- aggregate database/table/index/WAL bytes and phase timings.

It does not record raw values, paths, labels, IDs, prompt/response/reasoning,
command/patch/tool-output bodies, or database rows. Output is reviewed locally
before any fixture-distribution update and is never a release artifact.

## Correctness oracles

### Accounting oracle

Proves:

- one canonical count across duplicate occurrences;
- sessions, turns, calls, projects, and hierarchy;
- four token classes and explicit total formulas;
- time windows/timezones;
- parent-exclusive, descendant-exclusive, and family-inclusive sums;
- current rate-card cost/credit coverage;
- every allowance observation and compatible interval;
- publication delta reconciliation.

### Lifecycle oracle

Proves:

- point event versus lifecycle entity;
- start/progress/success/failure/cancel/rollback/open/unknown;
- transitions across publications;
- late terminal events;
- turn completion basis;
- tool intent/success/state-change separation;
- state change after cumulative preceding activity;
- crash/restart fold equivalence.

### Evidence oracle

Proves:

- stable logical selectors and aliases;
- source occurrence coordinates;
- total order and tie-breakers;
- keyset pages with no gaps or duplicates;
- source copy/replacement/recanonicalization stability;
- boundary pairs for deltas and allowance intervals;
- no raw body in database or envelope.

### Question oracle

Every catalog ID has:

- canonical and intent-variant prompts;
- exact request record;
- expected plan/compiler/projection;
- expected fields/rows/grades/order;
- required caveats and selectors;
- prohibited claims;
- default and hard byte limits;
- less-capable-model expected behavior.

Every question variant also has a fact-lineage triangle:

1. one scenario declaration emits its canonical typed facts and real selector
   occurrences;
2. an independent reference evaluator calculates the expected row for the
   exact typed request without production SQL or copied grading output;
3. the downstream consumer calculates the same row from its permitted
   canonical facts.

The reference evaluator and production consumer may share locked formulas and
typed contracts, but they must not share computed answer rows. `oracle_case`
records, the oracle bundle, `question_cases`, or an equivalent expected-answer
table are grading metadata only and cannot appear in a runtime answer path.
Mutation qualification proves both directions: changing grading output cannot
change the consumer result, while changing canonical facts changes the
consumer result and causes oracle comparison to fail.

CK-07B adds two L0 gates. The formula registry must reconcile exactly to 45
definitions, 61 question uses, and all 185 answer fields, with one synthetic
success vector per formula plus boundary/null/empty failures. The selector
registry must reconcile exactly to all 14 logical/catalog kinds. For every
structural-v2 case, qualification compares the full ordered
`(role, selector_kind, selector, provenance)` sequence, proves referenced
entity existence, rejects placeholders, and replays clean rebuild, source
replacement, and late events. Q-ALW-02 and Q-OPS-01 use their plan-specific
no-window rules.

## Performance workloads

Use the scales, history ranges, workloads, hard gates, and early-stop rules in
`PHYSICAL_ARCHITECTURE_BAKEOFF.md`. The final implementation adds:

- installed process startup and warm reuse;
- CLI encode/decode;
- MCP transport and final encoded response;
- plugin/skill prompt tokens;
- concurrent read during small and large refresh;
- repeated reopen without refresh;
- one active moving JSONL tail;
- 24-hour, 7-day, 30-day, 90-day, one-year, and all-time named plans;
- deep evidence pages and exact-count opt-in.

Record median, p95, maximum, and coefficient of variation over at least five
unprofiled runs. Cold filesystem tests state how cache was controlled. Warm
tests reuse the same process and committed database.

Required pull-request CI runs the same scale workloads in invariants mode:
deterministic correctness, plans, bounds, transaction shape, and response sizes
remain blocking, while shared-host wall clock is not a merge gate. The separate
repeated qualification protocol in
[`CI_PERFORMANCE_QUALIFICATION.md`](CI_PERFORMANCE_QUALIFICATION.md) owns
absolute timing evidence. A GitHub-hosted runner may enforce absolute latency
only when same-run calibration qualifies it. Explicit strict mode on a known
qualification host remains the authoritative absolute-budget command. The
repository-owned runner bounds the scale suite to five minutes in CI and
`just v`, and its versioned 17-metric contract fails closed on missing,
renamed, extra, or changed budgets.

### Mandatory attribution

Use the `agent-perf` skill and pinned dev dependency on the identical 100,000
and production-shaped workloads for Python CPU attribution. Profile only
synthetic or explicitly approved aggregate workloads. Change one suspected
cause per experiment. The speed claim comes from unprofiled repeated runs;
profile comparisons explain attribution.

### Early termination

A run stops when it irrecoverably exceeds:

- history-specific wall-time ceiling;
- database/index/WAL byte ceiling;
- peak memory ceiling;
- full-scan or temporary-sort allowance;
- writer transaction/lock ceiling;
- projection fanout ceiling;
- final response byte ceiling.

The partial result is recorded as a failure. The suite never waits 20–30
minutes once the acceptance target has already been missed.

## Concurrency and locking qualification

Tests use separate processes and assert:

- status/query/evidence remain available on the prior publication during parse,
  artifact build, and validation;
- small analytical `BEGIN IMMEDIATE` time is measured and bounded;
- operational job recovery never writes the analytical database;
- a second compatible refresh joins without a second worker;
- an incompatible refresh returns one conflict, not a blocked SQLite call;
- a query cannot trigger refresh;
- a moving-tail catch-up is bounded;
- worker-start failure is terminal;
- outer job state and nested progress agree;
- process termination at every crash boundary preserves a readable
  publication.

Regression reproductions include the old failure pattern: long derived work
plus a concurrent service start. The replacement passes only if service reads
start promptly and no long analytical lock is held.

## Query and projection qualification

For each named plan:

- exact oracle;
- current producer/consumer seam evidence;
- plan/compiler ID;
- required index/projection;
- `EXPLAIN QUERY PLAN`;
- no unapproved full scan, automatic index, or temporary sort;
- 100,000 and 1.3-million-call p95;
- result byte budget;
- deterministic ordering/ties;
- missing/coverage grades;
- selector resolution;
- one-call skill route;
- no implicit refresh.

Every projection additionally proves:

- declared named consumers;
- fact-backed equivalence;
- dirty-key derivation;
- one-call, one-tool, lifecycle-completion, late-event, hierarchy, rate-card,
  and deletion updates;
- storage/WAL/write fanout;
- no full rebuild on ordinary tail;
- version-upgrade artifact path;
- removal when no consumer remains.

## Database and package size attribution

Report:

- total database and free bytes;
- bytes/rows by table and index;
- WAL/checkpoint bytes;
- operational sidecar bytes;
- selected/deferred source bytes;
- source package, wheel, plugin, and skill bytes;
- runtime dependency count;
- frontend/Node/static-asset absence after retirement.

Byte-size ratchets use the measured accepted output plus no more than 25%
headroom. Exact catalog counts remain unbuffered. A
ratchet change requires the exact semantic reason and before/after attribution.

## Exact installed artifact qualification

One build job produces the wheel and source distribution once. Record hashes
and sizes, then:

1. create an isolated environment with no source checkout on `PYTHONPATH`;
2. install the exact wheel;
3. install/replace the exact same-version plugin bundle and skill;
4. verify distribution, CLI, plugin, MCP schema, skill, and cached-bundle
   versions/digests;
5. start two independent MCP processes against one synthetic cache;
6. run setup, warm query, explicit tail refresh, evidence, allowance, repair
   readout, and no-change behavior;
7. verify the exact intended tools and no retired tools;
8. scan installed files and distributions for Console/frontend assets after
   retirement;
9. repeat from the public package index before release completion.

Source-checkout fallback, symlinked plugin code, ambient local databases, and
real Codex logs invalidate the run.

## Fresh Codex qualification loop

This is the primary product acceptance loop.

### Preflight

- install the candidate wheel/plugin/skill locally;
- start a brand-new Codex CLI task and a brand-new Desktop thread so tool
  catalogs cannot be stale;
- bind only the synthetic source/cache;
- record tool catalog and coherent versions;
- do not use raw logs, direct SQLite, tracker CLI analysis, or old Console as
  evidence inside an MCP-only trial.

### Prompt suites

Run:

1. every Foundation named preset;
2. every Cutover named preset;
3. representative Advanced compositions;
4. model-inference candidates with prohibited-claim checks;
5. unsupported wordings and expected reframings;
6. setup at every history preset;
7. warm reopen and moving-tail follow-up;
8. exact evidence follow-up for selected rows.

For each prompt, record:

```text
host and model
start/end and time to first tracker call
tracker calls/batches/polls/retries/refreshes
per-call server and wall latency
response bytes
model input, cached input, reasoning, and output tokens where available
question/plan/version
oracle accuracy
grade and caveat accuracy
selector validity
human-label usefulness
final answer usefulness score
unsupported claims
```

The agent outcome is judged, not merely the tool response.

### Acceptance

Foundation and Cutover named prompts require:

- 100% deterministic oracle accuracy;
- one tracker query, with only contract-required evidence as a second call;
- zero model polls and duplicate refreshes;
- zero missing-as-zero, causality, productivity, or waste overclaims;
- valid human-readable labels and selectors;
- tracker response within its class;
- fresh-thread answer `<=15 s` p95 on the pinned supported host, with host/model
  startup reported separately;
- final answer usefulness at least 4/5 on the closed rubric;
- model-token and response-byte budget at or below the measured ratchet.

If the host itself prevents the end-to-end gate while tracker time passes, the
release records and escalates that residual; it does not hide it by weakening
the target or adding preflight calls.

## Less-capable-model qualification

The supported lower-capability lane receives the same skill and closed schemas.
It must:

- choose the named plan without generic exploration;
- preserve four token columns and grades;
- disclose coverage;
- not infer missing as zero or adjacency as cause;
- use returned human labels/selectors;
- answer or reframe within the same call budget;
- avoid paging/polling loops.

The plan/skill contract is rejected if only a frontier model can operate it
correctly. A compact `decision_hint` may be added to the registry when it
reduces errors without embedding narrative conclusions.

## Crash and recovery matrix

Run abrupt-process tests at every state in
`PUBLICATION_REFRESH_RECOVERY.md`, plus:

- disk full before and during analytical transaction;
- malformed and disappearing source;
- stale lease/PID reuse;
- sidecar corruption with valid analytical artifact;
- analytical candidate corruption with valid active/rollback;
- pointer mismatch;
- schema/projection incompatibility;
- invalid rate-card replacement;
- read process open during promotion;
- two simultaneous startup recovery processes.

Every test asserts active publication, rollback availability, sidecar terminal
state, abandoned-artifact disposition, and subsequent successful operation.

## Cutover qualification

Run the spike and replacement side by side on the same synthetic source root
but separate database identities. Compare:

- intentionally equivalent accounting and evidence cases;
- documented corrected semantics;
- supported question answers;
- setup/tail/query/storage performance;
- installed-agent outcomes;
- public tool catalogs and error migrations.

Cutover does not migrate the spike database. The release candidate selects the
replacement only after all gates pass. Rollback selects the untouched spike
runtime/database. After the rollback window, the retirement packet proves
frontend, old runtime, obsolete schemas/routes/tools, Node dependencies, and
package assets are absent.

## Release artifact verification

Before publication:

- full functional/type/lint/security/release profiles pass;
- exact dependency and file membership checks pass;
- wheel/sdist/plugin/skill hashes and sizes are recorded;
- clean installed smoke passes;
- fresh Codex qualification passes;
- synthetic database/WAL/package ratchets pass;
- no raw/private fixture data or secret material is present;
- one final read-only review has no unresolved accepted finding.

After publication:

- download public artifacts;
- verify byte identity with promoted artifacts;
- install in a clean environment;
- install the public plugin bundle;
- run the small synthetic setup/query/evidence/no-change smoke;
- record public URLs, hashes, sizes, and result.

## Regression reporting

Every performance change records:

- identical before/after workload and fixture digest;
- unprofiled distribution;
- CPU attribution run and caveat;
- database/index/WAL/page differences;
- plan/scan/sort differences;
- tracker calls/bytes/model tokens;
- effect on every named consumer;
- ratchet update, if any.

“Faster” is never inferred from code shape, profiler percentages, or a smaller
microfixture.
