# Qualification and Benchmark Plan

**Status:** Release and cutover authority
**Core metric:** A fresh installed Codex task gives a fast, exact, useful answer
with few calls and model tokens.

The product qualifies only through the exact wheel, plugin, MCP catalog, and
skill a user installs; unit tests and microbenchmarks are insufficient.

## Evidence levels

| Level | Required scope |
| --- | --- |
| L0 | Pure identity/formula/order/missingness vectors |
| L1 | Synthetic adapter/storage/lifecycle/publication integration |
| L2 | Exact query/evidence/projection/selector/page/grade behavior |
| L3 | Repeatable build/tail/query/storage/CPU performance |
| L4 | Exact distribution, dependency, bundle, version, clean install |
| L5 | Fresh CLI/Desktop selection, latency, tokens, accuracy, usefulness |
| L6 | Side-by-side cutover, recovery, rollback, retirement |

No lower level substitutes for a required higher level.

### Evidence claim classes

| Claim | Required proof |
| --- | --- |
| Structural validity | Schema, identity, order, digests |
| Formula consistency | Oracle record satisfies formula |
| Canonical-fact lineage | Typed request selects facts; independent truth derives result |
| Consumer replay | Real downstream path matches from permitted inputs only |

Each consumed dependency records producer path/schema/revision/digest,
consumer executable, independent truth, exact seam check, and affected
requalification. Completion or hashes never substitute for lineage/replay;
failure retains history, adds a correction, and stops dependents.

CK-07C's 40 plans/61 uses/185 fields are L0, not lineage. CK-07D independently
selects effective-dated rate cards; CK-07E matches structural/query-only facts,
requests, order, 14 selectors, provenance, valuation, privacy, and lifecycle
while recording 0/80 answers. Historical CK-07A's 80/80 consumers share
`evaluate_plan`; CK-04 runs 3/4 remain waived. CK-08's 21 plans/42 variants,
keysets and provisional two-scale results use mixed timing/post-materialization
paging, so they admit neither projections nor CK-09.

### Corrective interpretation and immutable parallel qualification

R1A freezes Q-REV-03/Q-WF-02 and executable transitive closure before parallel
R1C is accepted at exact main `fb0c57886097a6b985d2f321b2de858cbdfc0a97`;
the exact R1B join authority makes only the existing worker Ready to reconcile
its bound shared query/evidence/grading seams before final two-lane R1 replay.
R3 scale awaits merged/exact-main R3A.
CK-QG1A removed only R2's two rank-D findings against its unchanged baseline and is accepted at exact main `30983d4b5005e7e2a507757c76a3c05ab56281e6`; CK-QG1 PR #392 then passed the exact authorized normalized baseline ratchet, hosted CI, squash merge, and fresh exact-main verification at `68050b93`. CK-07R1A preserves the first hosted Python
3.14 `ordinary.2000_call_tail` failure and
`5000/120000/100/500/500` budgets; only a controlled material correction can
resume PR #394. Stale, grading-dependent, retried-only, or waived evidence
blocks CK-09.

CK-12 freezes one candidate and byte-identical inputs/budgets for four
read-only lanes. Lanes never repair it; failure creates a new candidate
identity and affected-lane replay.

## Synthetic fixtures and aggregate profiling

Deterministic synthetic structural JSONL covers source lifecycle/malformation,
sessions/hierarchy/rates, four tokens/missingness, allowance, identities,
lifecycle, selectors, occurrences, and answers. Manifests bind generator/seed/
digests, history/timezone, source counts/distributions, capabilities/rate
revision, and expected counts/oracles. Tiny is committed; larger profiles reuse
the cases. SHA-256 covers exact bytes, oracle bundle, and self-omitted manifest;
manifest-only mode still serializes/hashes every record.

An opt-in local profiler may emit aggregate files/bytes/ages, record-size and
numeric histograms, event/lifecycle/missing/capability counts, entity
cardinalities, timestamp density/ties, source lifecycle counts, allowance
cadence, and database/table/index/WAL/timing totals. It never emits paths,
labels, IDs, values, rows, or raw prompt/response/reasoning/command/patch/tool
output, and never becomes a release artifact.

## Correctness oracles

| Oracle | Mandatory coverage |
| --- | --- |
| Accounting | Canonical dedup counts; hierarchy; four tokens/formulas; timezones/windows; family modes; current valuation/coverage; allowance; publication delta |
| Lifecycle | Point versus entity; all terminal/open/unknown states; cross-publication/late transitions; completion; tool intent/success/mutation; cumulative activity; crash-fold equivalence |
| Evidence | Stable selectors/aliases; source coordinates; total order/ties; gap-free keysets; copy/replacement/recanonicalization; delta/allowance boundaries; no raw bodies |
| Question | Every catalog ID's prompts, typed request, plan/projection, exact rows/fields/grades/order, caveats/selectors, prohibited claims, byte limits, lower-model behavior |

Every question variant has a fact-lineage triangle: one declaration emits
canonical typed facts and selector occurrences; an evaluator independent of
production SQL/grading computes the exact request result; the real consumer
computes the same result from permitted facts. Lanes may share locked formulas
and typed contracts, never computed rows. Grading tables are unavailable to
runtime. Mutating grading cannot change either result; mutating canonical facts
changes both and breaks comparison.

Formula authority reconciles 45 definitions, 61 uses, and 185 fields with
success/boundary/null/empty vectors. Selector authority reconciles all 14 kinds
and exact ordered `(role, kind, selector, provenance)` sequences, entity
existence, non-placeholders, rebuild/replacement/late events, and plan-specific
Q-ALW-02/Q-OPS-01 no-window rules.

## Performance, attribution, and early stop

Use bakeoff scales/history/hard gates plus installed startup/warm reuse,
CLI/MCP/final bytes, skill tokens, concurrent reads, reopen, moving tail,
named history plans, deep evidence, and exact-count opt-in. Record median, p95,
max, and coefficient of variation over at least five unprofiled runs; disclose
cold-cache control. PR CI keeps deterministic plans/bounds/transactions/bytes
blocking in invariants mode. Absolute timing uses the separate calibrated
qualification protocol or explicit strict known host; the 17-metric runner
fails closed and bounds CI/`just v` scale to five minutes.

Use pinned `agent-perf` on identical synthetic 100,000/production workloads,
changing one suspected cause. Repeated unprofiled runs support speed claims;
profiles only attribute CPU. Stop and retain partial failure when wall time,
database/index/WAL bytes, RSS, scan/sort allowance, lock, projection fanout, or
response bytes irrecoverably exceed the frozen gate.

## Concurrency, query, and projection qualification

Separate processes prove prior-publication reads during build/validation,
bounded small `BEGIN IMMEDIATE`, sidecar-only recovery, compatible refresh join,
incompatible conflict without blocking, no query refresh, bounded moving tail,
terminal worker-start failure, coherent job/progress, and readable publication
at every crash boundary. Reproduce long derived work plus concurrent service
start; prompt reads and no long analytical lock are mandatory.

Each named plan proves exact oracle and current producer/consumer seam;
compiler/plan/index/projection identity; EXPLAIN with no unapproved scan,
automatic index, or temp sort; 100,000/1.3-million p95; bytes; order/ties;
missing/coverage grades; selectors; one-call skill route; and no refresh.
Each projection additionally proves declared consumers, fact equivalence,
dirty keys, one-call/tool/lifecycle/late/hierarchy/rate/deletion updates,
storage/WAL/write fanout, no ordinary-tail rebuild, upgrade path, and removal
when unused.

## Size, artifact, and installed-agent qualification

Report database/free/table/index/WAL/sidecar/source/package/plugin/skill bytes,
dependency count, and post-retirement frontend/Node absence. Ratchets use
accepted measured output plus at most 25% headroom; catalog counts have none.
Any change records semantic reason and before/after attribution.

Build wheel/sdist once and record hashes/sizes. Source-isolated install of that
wheel and same-version plugin/skill verifies versions/digests/catalogs, two MCP
processes, setup/query/tail/evidence/allowance/repair/no-change, tool inventory,
retired-surface absence, then public-index repeat. Checkout/symlink fallback,
ambient databases, or real logs invalidate.

Fresh CLI and Desktop tasks bind only synthetic source/cache and record catalog
versions. They may not use raw logs, direct SQLite, old Console, or side
channels. Run all Foundation/Cutover presets, representative Advanced/
inference/unsupported wordings, every history setup, warm/moving-tail follow-up,
and row evidence. Record host/model/time-to-first-call, calls/batches/polls/
retries/refreshes, latency/bytes/four token classes, question/plan/version,
oracle/grade/caveat/selector accuracy, labels, usefulness, and unsupported
claims.

Foundation/Cutover acceptance is 100% oracle accuracy; one query plus only
contract-required evidence; zero polls/duplicate refreshes/overclaims;
valid labels/selectors; class response budget; fresh-thread answer <=15 s p95
on pinned host with startup separated; usefulness >=4/5; and token/byte
ratchets. Host failure is reported, never hidden by weaker targets/preflight.

The supported lower-capability lane uses the same skill/schemas and must select
the named plan without exploration, preserve four tokens/grades/coverage,
avoid missing-as-zero and adjacency-as-cause, use labels/selectors, stay within
call budget, and avoid paging/polling. Reject a contract operable only by a
frontier model.

## Recovery, cutover, release, and regression

Abrupt-process tests cover every publication state, disk/source/lease,
sidecar/candidate/pointer/schema/projection/rate failures, open-reader
promotion, and simultaneous recovery; assert active/rollback readability,
terminal sidecar, abandoned-artifact disposition, and later success.

Run spike and replacement on the same synthetic source with separate database
identities. Compare intended accounting/evidence, corrected semantics,
supported answers, setup/tail/query/storage, installed-agent outcomes, catalogs
and migrated errors. Never migrate the spike database. Select replacement only
after all gates; rollback selects untouched spike. Retirement then proves old
runtime/frontend/schemas/routes/tools/Node/assets absent.

Before publication require full functional/type/lint/security/release checks,
exact membership/dependencies/hashes/sizes, clean installed and fresh-Codex
qualification, synthetic byte ratchets/privacy, and one resolved final review.
After publication download, byte-compare, clean-install wheel/plugin, run small
setup/query/evidence/no-change smoke, and record URLs/hashes/sizes/results.

Every performance change records identical workload/fixture digest, unprofiled
distribution, CPU attribution/caveat, database/index/WAL/page and plan/scan/
sort deltas, calls/bytes/tokens, all consumer effects, and ratchet change.
Never infer “faster” from code shape, profiler percentages, or microfixtures.
