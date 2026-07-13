# Compression Lab Roadmap

Canonical design: [Compression Lab Design](superpowers/specs/2026-07-11-compression-lab-design.md)

## Objective

Turn the MCP into a compact, measurement-first laboratory for finding and simulating reductions in context, token, and cost waste without double-counting evidence.

## Approved Decisions

- Research-grade measurement is the primary product goal.
- Every candidate receives a heuristic low/likely/high savings estimate.
- Estimates remain explicitly separate from measured exposure.
- The local content index is analyzed automatically.
- Default output summarizes evidence; raw excerpts require explicit detail mode.
- Use a unified opportunity ledger rather than adding unrelated endpoint-specific reports.
- Persist analysis runs and cache results, but defer persisted intervention experiments.
- First full-history analysis is asynchronous and reports progress.
- Existing MCP tools remain backward compatible and become evidence providers or compact routers.
- Initial detector families: stale context, file rediscovery, shell retries, repeated validation, tool-output bloat, and cache-break/resume overhead.

## Execution Ledger

### PR 1: Attribution Kernel And Run Cache

Status: complete

PR: [#221](https://github.com/douglasmonsky/codex-usage-tracker/pull/221)

Merge: `702d038edb55fe604e467a8f85706eeac77d7553`

Deliverables:

- Internal observation, candidate, estimate, claim, and profile contracts.
- Per-record/component capacity ledger.
- Deterministic candidate and scope identifiers.
- SQLite migrations for compression runs, candidates, and record claims.
- Cache validity and invalidation service.
- Synthetic overlap and migration tests.

Exit gates:

- No whole-call token multiplication across repeated events.
- Gross and portfolio capacity invariants pass.
- Existing databases migrate and refresh idempotently.
- Existing public MCP contracts remain unchanged.

### PR 2: Detectors And Estimators

Status: complete

PR: [#222](https://github.com/douglasmonsky/codex-usage-tracker/pull/222)

Merge: `98f2cd7be6d1a357279d827bb2190198e7bc1ff5`

Deliverables:

- Six detector implementations behind one detector protocol.
- Direct, matched-baseline, and fallback estimator tiers.
- Versioned `compression-estimator-v1` policy.
- Data-quality and confidence grading.
- Synthetic fixtures with manually calculated expected ranges.

Exit gates:

- Every candidate has low/likely/high estimates and disclosed assumptions.
- Each family declares eligible token components.
- Duplicate event/session fixtures cannot inflate exposure.
- Partial parser/content coverage produces warnings rather than false certainty.

### PR 3: Async MCP And Query Surface

Status: pending

Deliverables:

- `usage_compression_start`.
- `usage_compression_status`.
- `usage_compression_profile`.
- `usage_compression_candidates`.
- `usage_compression_candidate_detail`.
- Shared API payload builders and contract documentation.
- Job deduplication, monotonic progress, pagination, and payload budgets.

Exit gates:

- Cold calls return a job handle immediately.
- Warm profile/candidate queries meet the 500 ms target on representative data.
- Default payloads remain compact and omit raw fragments.
- Candidate detail supports handles, summaries, and bounded excerpts.

### PR 4: Overlap-Aware Simulator

Status: pending

Deliverables:

- Deterministic record/component overlap allocation.
- `usage_compression_simulate`.
- Combined intervention portfolio estimates.
- Calculation trace and verification-plan payloads.

Exit gates:

- Adjusted estimates never exceed gross estimates.
- Portfolio totals never exceed unique eligible capacity.
- Simulator results are deterministic for a run and candidate set.
- Unknown/stale candidates return actionable structured errors.

### PR 5: Skill, Plugin, Documentation, And Dogfood

Status: pending

Deliverables:

- Route broad waste questions through the Compression Lab lifecycle.
- Update source and packaged copies of both usage skills.
- Convert `usage_investigate` and `usage_action_brief` to compact profile routers.
- Add conversation examples and MCP/API documentation.
- Run old-versus-new shadow comparisons on local data.
- Document estimator limitations and future experiment tracking.

Exit gates:

- The skill retrieves only selected candidate details.
- Recommendations include evidence, estimate, assumptions, intervention, and verification.
- Existing tools remain callable and compatible.
- Full local and GitHub CI gates pass.

## Cross-Cutting Acceptance Criteria

- `observed_exposure_tokens` is never presented as proven waste.
- Low, likely, and high estimates are ordered and nonnegative.
- Token components remain separate through attribution and costing.
- Estimator and detector versions are present in reproducible payloads.
- Source revision, scope, coverage, cache state, and truncation are explicit.
- Default status/profile/list/detail responses meet their documented size budgets.
- No committed fixture or artifact contains real local prompts, commands, paths, or raw content.
- Source, tests, docs, stable JSON schemas, and bundled plugin assets change together.

## Performance Budget

- Full uncached run: under 20 seconds on data near the maintainer's current scale, with a 25-second P95 ceiling.
- Single-source append refresh: under 1 second when only bounded detector dependencies change.
- Warm profile and candidate list: under 500 ms.
- Exact unchanged warm profile: under 10 ms.
- Candidate detail: under 1 second.
- Progress starts immediately and remains monotonic.
- Incremental refresh recalculates only changed records/threads plus global overlap totals.

## Cold-Build Performance Program

The current typed-row loader reduced the same 404,176-call forced rebuild from
48.115 seconds to 38.708 seconds. Removing the separately measured prior-run
deletion cost gives an estimated first-ever cold build of about 35.5 seconds.
The remaining target requires changing the data flow, not further
micro-optimizing serialization.

All performance measurements use deterministic synthetic data for profilers and
report only aggregate timing/count evidence for real local data. Private indexed
content is never sent to a profiler or committed as a fixture.

### CP1: Performance Contract And Safe Loader Foundation

Status: complete

Issue: [#223](https://github.com/douglasmonsky/codex-usage-tracker/issues/223)

PR: [#224](https://github.com/douglasmonsky/codex-usage-tracker/pull/224)

Merge: `0c8bf5238ec23c642f2282d98f1a072700baea05`

Deliverables:

- Deterministic 100,000-call synthetic cold-build benchmark.
- Stage timings for evidence load, manifest, detection, attribution,
  persistence, and profile generation.
- Peak-memory and throughput reporting suitable for regression comparisons.
- Canonical candidate/profile fingerprints for old-versus-new equivalence.
- Typed SQLite row loading without intermediate row dictionaries.
- One manifest computation per run and compact revision identities.

Exit gates:

- Candidate count and canonical output fingerprints are unchanged.
- Real aggregate cold-build time improves by at least 15 percent.
- Exact warm behavior remains below 10 ms.
- Public evidence-query contracts remain backward compatible.
- No benchmark artifact contains private prompts, paths, commands, or content.

### CP2: Streaming Detector Consumption

Status: complete

Issue: [#225](https://github.com/douglasmonsky/codex-usage-tracker/issues/225)

Foundation PR: [#226](https://github.com/douglasmonsky/codex-usage-tracker/pull/226)

Foundation merge: `d0db081f77434e13e4874a56e89b69f577633fb6`

Engine PR: [#227](https://github.com/douglasmonsky/codex-usage-tracker/pull/227)

Engine merge: `b253a97a6615b609ba0d31bc7cc47d9b45f0a620`

Benchmark PR: [#228](https://github.com/douglasmonsky/codex-usage-tracker/pull/228)

Benchmark merge: `980b9546131427a3e2f4411b1975590bfd6dc787`

Deliverables:

- A bounded evidence-batch reader over the existing normalized SQLite tables.
- A detector lifecycle with initialize, observe-batch, and finalize phases.
- Compatibility adapters for detectors that still require a complete snapshot.
- Shared streaming estimator inputs that preserve component-level attribution.
- Deterministic ordering only for detector families that declare it necessary.

Exit gates:

- Streaming and snapshot engines produce identical canonical candidate/profile
  fingerprints across golden synthetic fixtures.
- Peak RSS falls by at least 20 percent on the current-scale aggregate workload
  and by at least 35 percent on the normalized synthetic workload.
- Evidence loading plus detector execution does not regress from the CP1
  baseline; CP3 owns the larger scan-elimination speed gate.
- Partial batches, empty tables, and detector failures retain current warnings
  and progress semantics.

### CP3: Detector-Ready Ingestion Aggregates

Status: implementation complete; PR open

Issue: [#230](https://github.com/douglasmonsky/codex-usage-tracker/issues/230)

PR: [#231](https://github.com/douglasmonsky/codex-usage-tracker/pull/231)

Deliverables:

- Persisted per-call token, cache, and output facts. Cost and credit columns are
  intentionally nullable until CP4 can bind derived pricing to a rate-card
  revision instead of persisting silently stale estimates.
- Persisted sequence/count facts for shell churn, repeated validation, file
  rediscovery, and tool-output concentration.
- Per-thread lifecycle and cache-resume summaries.
- Fast schema-only migration plus an explicit idempotent backfill from existing
  normalized content-index records. Automatic initialization never pays the
  full historical backfill cost.
- Detector queries over compact facts instead of repeated raw reconstruction.

Exit gates:

- Existing databases migrate immediately and can be explicitly backfilled
  without reparsing raw logs.
- Aggregate facts remain reproducible from normalized source records.
- Append ingestion updates only affected calls, threads, and sequence windows.
- Detector outputs remain equivalent to the CP2 streaming reference.
- Evidence loading plus detector execution is at least 35 percent faster than
  the CP1 baseline.

### CP4: Revision-State And Incremental Invalidation

Status: pending

Deliverables:

- Per-source byte offsets, source hashes, row counts, and generation counters.
- Per-aggregate and per-detector dependency revisions.
- A revision-vector cache key that avoids full Python manifest traversal.
- Dependency-aware invalidation of only affected detector families and threads.
- Recovery behavior for truncation, rotation, parser-version changes, and
  explicit replacement.

Exit gates:

- Exact unchanged checks use bounded metadata reads and remain below 10 ms.
- A representative one-event append refresh completes below 1 second.
- Truncation or parser drift cannot silently reuse stale detector results.
- Replacement remains available but is not required for ordinary append-only
  operation.

### CP5: Candidate Persistence Pipeline

Status: pending

Deliverables:

- One transaction with bounded bulk inserts for candidates and claims.
- Internal typed persistence that avoids mapping serialization on the hot path.
- Attribution performed alongside detection when required evidence is already
  present.
- Atomic profile publication after candidate and claim persistence succeeds.
- Rollback and retry coverage for interrupted builds.

Exit gates:

- Candidate-heavy persistence is at least 40 percent faster than CP1.
- Partial failures leave no visible mixed-generation profile.
- Public candidate/profile payloads remain unchanged.
- Candidate IDs and overlap allocation remain deterministic.

### CP6: Profile-Guided Parallel Ingestion

Status: pending

Deliverables:

- Parallel parsing across independent source files only after CP2-CP5 profiling.
- A single deterministic SQLite writer with bounded worker queues.
- Stable merge ordering and backpressure under skewed source sizes.
- Worker-count configuration with a conservative automatic default.
- Serial fallback for one-file histories and low-resource systems.

Exit gates:

- Current-scale true first build is consistently below 20 seconds and below
  25 seconds at P95.
- Parallel output fingerprints match the serial engine exactly.
- Parallel mode demonstrates a material speedup over the optimized serial path.
- Memory and writer contention stay within the documented benchmark budget.

### Performance Completion Audit

The program is complete only when all CP1-CP6 exit gates have authoritative
evidence. Each PR must update this ledger with its benchmark run, tests, PR,
merge commit, and any rejected optimization. A narrow test cannot establish a
whole-pipeline timing or equivalence claim.

## Deferred Queue

- Persisted intervention experiments and before/after comparisons.
- Dashboard Compression Lab workspace.
- Opt-in aggregate calibration datasets.
- Semantic task-value and effort-mismatch detection.
- Automatic workflow changes or tool execution.

## Progress Log

- 2026-07-11: Existing MCP and agentic reports inventoried.
- 2026-07-11: Local dogfood exposed blocking runtime and duplicated whole-call attribution in file/shell findings.
- 2026-07-11: Product direction selected as measurement-first with heuristic ranges for every candidate.
- 2026-07-11: Automatic internal content analysis with summarized defaults approved.
- 2026-07-11: Detector/simulator milestone approved; persisted experiments deferred.
- 2026-07-11: Unified opportunity ledger, async persistent cache, compact MCP contracts, detector set, and five-PR rollout approved.
- 2026-07-11: PR 1 attribution contracts, bounded overlap allocation, schema v15 run cache, and SQL-paged candidate repository implemented locally.
- 2026-07-11: Compression Lab preflight PR #220 merged at `7261d3f` with roadmap and hardening-tool compatibility.
- 2026-07-11: PR 1 merged as #221 at `702d038`; PR 2 detector and estimator work started from that exact base.
- 2026-07-12: PR 2 detector contracts, all six detector families, shared estimator indexing, cache-aware run building, staged progress, exact/incremental cache handling, and compact profiles implemented on `feature/compression-lab-detectors`.
- 2026-07-12: PR 2 merged as #222 at `98f2cd7`; CP1 cold-path profiling started from that exact base.
- 2026-07-12: The CP1 target was tightened to a 15-20 second first build, sub-second append refresh, and sub-10 ms unchanged reuse. CP2-CP6 define the structural path and equivalence gates.
- 2026-07-12: CP1 merged as #224 at `0c8bf52`. CP2 issue #225
  started a bounded row fold and compact detector snapshot from that exact base.
- 2026-07-12: CP2 preserved both canonical fingerprints and all 32,087
  real-data candidates. Clean CP1-versus-CP2 runs reduced peak RSS from
  539.828 to 332.781 MiB on normalized synthetic data and from 1,706.766 to
  1,340.469 MiB on the current-scale aggregate workload. Runtime improved
  modestly, so the 35 percent scan-elimination gate moved to CP3 rather than
  being weakened or claimed without evidence.
- 2026-07-12: CP2's durable normalized benchmark generated 500,000 evidence
  rows for 100,000 calls. Against the same database, CP1 used 562.156 MiB and
  7.325 seconds; CP2 used 337.938 MiB and 6.704 seconds with identical 15,030
  candidates and canonical fingerprints. The isolated exact warm hit was
  3.831 ms.
- 2026-07-13: CP3 added schema v16 detector-ready record, sequence, and thread
  facts with targeted ingestion/content-index maintenance and a safe CP2
  fallback whenever fact state is incomplete or stale. Automatic migration is
  schema-only after profiling showed an eager real-data backfill would add
  52.625 seconds to unrelated database initialization.
- 2026-07-13: Independent CP3 review reproduced stale-cache risk after content
  changes, orphan facts after reset/source replacement with SQLite foreign keys
  disabled, and partial sequence-store acceptance. The branch now advances
  generation during content synchronization, explicitly clears/replaces facts,
  stores integrity counts in fact state, and falls back whenever any persisted
  fact family is incomplete or version-mismatched. Benchmark fixtures compare
  fallback and fact-backed fingerprints on the same normalized database.
- 2026-07-13: On the current 404,176-call aggregate database, the final CP3
  comparison completed the fallback rebuild in 36.613 seconds and the prepared
  fact-backed rebuild in 27.598 seconds. Evidence loading plus detectors fell
  from 24.815 to 15.473 seconds, 37.7 percent, while both paths produced the
  same 32,087 candidates and canonical candidate/profile fingerprints. Exact
  reuse completed in 4.219 ms.
- 2026-07-13: Explicit fact preparation completed in 72.968 seconds after
  replacing planner-hostile target predicates and rebuilding secondary indexes
  once around the bulk load. This one-time, opt-in path spent 26.620 seconds on
  record facts, 15.652 on sequence facts, 10.960 on index creation, and 9.731
  on manifests; ordinary schema migration remains immediate and backfill-free.
  The final normalized 100,000-call gate completed in 3.861 seconds total with
  329.156 MiB peak RSS; evidence loading plus detectors took 2.237 seconds,
  58.8 percent below CP1's 5.428-second baseline while preserving CP2's exact
  candidate and profile fingerprints.

## Current Restart Checkpoint

Worktree: `/Users/Monsky/Documents/Codex/2026-07-11/r11-compression-detectors`

Branch: `feature/compression-detector-facts`

CP2 merged through PR #228 at `980b954`. CP3 is committed at `83af336` and open
for review in PR #231 after passing the precommit and full verifier profiles.

Validated behavior at this checkpoint:

- Schema v16 creates detector fact tables without blocking ordinary commands on
  a historical backfill.
- Record, relevant sequence, and thread facts reproduce CP2 snapshots,
  compaction coverage, manifests, candidates, and public profiles.
- Usage and content-index writes refresh only affected records and threads; a
  trigger-backed append test rejects accidental full record-fact rebuilds.
- Incomplete, stale, or version-mismatched fact stores fail closed to the CP2
  streaming loader.
- Reset and source replacement explicitly clear affected facts rather than
  relying on disabled SQLite foreign-key cascades.
- A hidden benchmark preparation mode measures explicit normalized backfill
  separately from cold analysis and warm reuse.
- Public compression schema version remains 1 because CP3 changes only internal
  evidence representation, not public profile or candidate contracts.

Latest CP3 real-data benchmark (`include_archived=true`, all-history scope):

- Calls: 404,176; normalized sequence facts: 714,571; candidates: 32,087.
- Reviewed safe migration plus CP2 fallback rebuild: 36.613 seconds.
- Reviewed explicit fact preparation: 72.968 seconds, paid only when requested.
- Reviewed prepared fact-backed rebuild: 27.598 seconds; evidence 9.640
  seconds; evidence plus detectors 15.473 seconds.
- Reviewed exact warm profile: 4.219 ms.
- Fact-backed and fallback runs produced identical candidate and stable public
  profile fingerprints.

Measured optimizations:

- Removed quadratic claim-to-record membership validation during candidate estimation.
- Reused a source-generation counter instead of hashing the complete normalized snapshot twice.
- Replaced per-event cryptographic manifest hashing with deterministic order-independent checksums and removed duplicate event identity encoding.
- Built attribution capacity directly from the estimator index rather than materializing generic row dictionaries.
- Removed an unused candidate-record secondary index and persisted compact public profiles separately from private incremental manifests.
- Materialized typed evidence directly from positional SQLite rows, avoiding roughly 1.5 million intermediate dictionaries.
- Removed unnecessary ordering from tool, command, file, and fragment evidence queries after verifying detectors and manifests are order-independent.
- Computed the incremental manifest once per run and added compact revision identities for every evidence family.
- Replaced planner-hostile bound target predicates with a fixed internal SQL
  fragment whitelist and rebuilt fact-table secondary indexes once around full
  backfills. Incremental refreshes retain their targeted indexed updates.
- Used `agent-perf`/Scalene on a 100,000-call synthetic workload. `_raw_rows` fell from 4.68 to 1.94 percent CPU attribution (`20260713T004417Z-167fcc53` to `20260713T005309Z-b5750e1d`), while unprofiled time fell from 8.75 to 8.01 seconds with the same 9,269 candidates.
- Rejected a direct candidate serializer after it improved the synthetic workload by only 0.13 seconds, and rejected BLAKE2b manifest hashing after it regressed the workload to 9.27 seconds.
- Added `scripts/benchmark_compression_lab.py` as the durable CP equivalence
  and regression harness. Its 100,000-call synthetic baseline completed cold
  analysis in 2.698 seconds with 10,000 candidates, 225.969 MiB peak RSS,
  stable candidate/profile fingerprints, and a 3.37 ms exact warm hit.

Resume in this order:

1. Merge CP3 PR #231 after its remote checks pass, leaving `.idea/` unstaged.
2. Start CP4 from updated `main` and add revision-aware invalidation, including
   a pricing/rate-card revision before derived costs or credits are persisted.
3. Land CP5 serially because candidate persistence consumes CP4 cache identity.
4. Add CP6 only after a fresh profile identifies the dominant remaining
   first-build stages; explicit fact preparation is currently a measured
   parallelization/ingestion-time target.

## Resume Instructions

1. Read the canonical design and this execution ledger.
2. Start the next pending Compression Lab or CP milestone from current `main`.
3. Update the relevant PR status and append a dated progress-log entry.
4. Do not skip attribution invariants to add another detector quickly.
5. Do not route the skill to the new lab until shadow comparisons and MCP contracts pass.
