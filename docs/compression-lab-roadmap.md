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

Status: in progress

Issue: [#238](https://github.com/douglasmonsky/codex-usage-tracker/issues/238)

Branch: `feature/238-compression-mcp-progress-cache`

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

Status: complete

Issue: [#230](https://github.com/douglasmonsky/codex-usage-tracker/issues/230)

PR: [#231](https://github.com/douglasmonsky/codex-usage-tracker/pull/231)

Merge: `29f6cad`

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

Status: complete

Issue: [#232](https://github.com/douglasmonsky/codex-usage-tracker/issues/232)

PR: [#233](https://github.com/douglasmonsky/codex-usage-tracker/pull/233)

Merge: `0809875`

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

Status: complete

Issue: [#234](https://github.com/douglasmonsky/codex-usage-tracker/issues/234)

PR: [#235](https://github.com/douglasmonsky/codex-usage-tracker/pull/235)

Merge: `99c859a`

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

Status: complete

Issue: [#236](https://github.com/douglasmonsky/codex-usage-tracker/issues/236)

PR: [#237](https://github.com/douglasmonsky/codex-usage-tracker/pull/237)

Merge commit: `88b89b838b990f2b567b3e013c97dbe01afb893f`

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
- 2026-07-13: CP3 merged through PR #231 at `29f6cad`. CP4 added schema v17
  source checkpoints with byte/row cursors, per-source generations, device and
  inode identity, and a bounded 64 KiB parsed-prefix tail hash. Append planning
  now rejects truncation, rotation, parser drift, and larger in-place
  replacements before trusting the previous byte cursor.
- 2026-07-13: CP4 added detector-aware revision vectors for calls, threads,
  tools, commands, files, and fragments. Exact cache lookup reads one compact
  state row and hashes only dimensions consumed by the selected detectors;
  unknown detector families fail closed to the complete vector. The estimator
  policy revision remains part of every key, while derived cost/credit facts
  stay nullable until an explicit rate-card-backed estimator consumes them.
- 2026-07-13: The final 100,000-call CP4 benchmark preserved CP2/CP3's exact
  candidate and profile fingerprints. Revision lookup median was 0.982 ms,
  targeted aggregate append refresh was 0.376 seconds, and an actual one-event
  JSONL append refresh was 19.8 ms. Cold analysis remained 3.935 seconds with
  evidence plus detectors at 2.238 seconds and exact warm reuse at 3.302 ms.
  Agent Perf run `20260713T070642Z-044ace6a` attributed the next material work
  to fact folding and candidate/claim persistence, confirming CP5 as the next
  optimization boundary.
- 2026-07-13: CP4 merged through PR #233 at `0809875`. CP5 replaced the hot
  public-mapping round trip with a read-only structural write protocol. The
  store consumes validated allocated candidates directly without importing the
  compression domain, and bounded canonical-JSON caches reuse repeated detector
  metadata while preserving decoded payloads and fingerprints.
- 2026-07-13: Candidate rows, claim rows, prior-run supersession, and completed
  aggregate/public profiles now publish in one SQLite transaction. Synthetic
  claim failure proves rollback leaves the prior cacheable generation intact;
  retry coverage proves the same run can publish cleanly after the fault clears.
- 2026-07-13: The 100,000-call CP5 gate measured 44.884 percent faster
  candidate-heavy persistence, 3.555-second cold analysis, and 3.737 ms exact
  reuse. Candidate/profile fingerprints remained unchanged, one-event JSONL
  append refresh remained 20.0 ms, and peak RSS fell to 320.484 MiB.
- 2026-07-13: CP5 merged through PR #235 at `99c859a`. Agent Perf run
  `20260713T104332Z-7a85ad69` identified repeated persistence passes as the
  dominant true first-refresh cost, so CP6 moved aggregate, normalized content,
  provenance, diagnostic, and compression-fact production onto one parser pass
  with a bounded process queue and one deterministic SQLite writer.
- 2026-07-13: The initial clean post-refactor three-run CP6 gate generated
  100,000 synthetic token rows across 400 JSONL files (138.5 MB). Parallel
  refresh median was 17.729 seconds and worst-of-three was 17.740 seconds
  versus a 25.638-second serial median, a 30.850 percent speedup. Peak RSS was
  455.578 MiB coordinator RSS. Every benchmarked aggregate, summary, source,
  content, FTS, provenance, allowance, diagnostic, revision, and
  compression-fact table had identical row counts and fingerprints between
  serial and parallel builds. A subsequent hardened validation added sampled
  process-tree RSS rather than relying on coordinator memory alone, expanded
  parity to all 18 persisted table families, and exercised serial retry without
  re-entering the content-index process pool. It completed in 19.614 seconds
  parallel versus 26.416 seconds serial with 460.156 MiB process-tree RSS.
- 2026-07-13: CP6 rejected in-memory SQLite temporary storage after it raised
  peak RSS to 604.8 MiB, rejected multi-row fact inserts after they regressed
  persistence, and rejected larger worker payload batches that increased IPC
  and memory without improving wall time. The selected defaults cap workers at
  four, batch 16 source files per write cycle, use a bounded queue, and retain
  deterministic serial fallback.
- 2026-07-13: Agent Perf run `20260713T131211Z-5d4c9590` found no dominant
  Python hot loop in a direct 25,000-row refresh. The largest individual self
  CPU attributions were SQLite connection and bounded persistence helpers, each
  below 0.5 percent; the remaining elapsed time is primarily native SQLite I/O
  and child-process parsing. A six-worker trial improved a comparable loaded
  run by only about 0.16 seconds while increasing sampled process-tree RSS by
  roughly 119 MiB, so CP6 retains the four-worker cap.

## Current Restart Checkpoint

Worktree: `/Users/Monsky/Documents/Codex/2026-07-11/r11-compression-detectors`

Branch: `feature/238-compression-mcp-progress-cache`, tracking `origin/main` at
`aa7e4e322473b2be2c4e6f78f8cbb71b704c82f2`.

Pause checkpoint (2026-07-13):

- CP6 merged through PR #237 at `88b89b8`; its issue #236 is closed. The
  performance evidence below remains authoritative.
- Preserve the pre-existing untracked `.idea/` directory and local `uv.lock`.
  Do not stage, remove, or modify them for PR 3.
- No PR 3 implementation files have been edited yet. Only this roadmap and the
  completed CP6 change-plan status should be dirty at the checkpoint.
- Serena semantic recovery was exhausted for this task after two bounded doctor
  probes and broker/history inspection. Use native `rg`, type checks, tests, and
  inspections for the rest of this task rather than retrying Serena.
- Two read-only audits confirmed that none of the five planned
  `usage_compression_*` MCP tools exist yet. The synchronous run builder,
  persistent run/profile store, monotonic SQL progress update, candidate paging,
  and candidate detail primitives already exist and should be reused.
- The PR 3 implementation should add an in-process `CompressionJobRegistry`
  shared by the API and MCP surfaces. Under one lock it must reuse an exact
  completed SQLite profile, deduplicate an identical active request, or reserve
  a persistent pending run before launching one daemon worker.
- A reserved run ID must be returned immediately and remain queryable through
  process restart. Pending/running rows without an owned worker must report an
  explicit interrupted/orphaned state; do not silently claim that work is still
  progressing. Avoid cross-process lease/schema machinery unless a failing
  contract test demonstrates that it is required.
- Refactor the existing run builder minimally to accept a reserved run ID and
  update that row from pending to running/completed/failed. Preserve structured
  failure metadata and never expose raw exception messages or indexed content in
  default status payloads.
- Build pure compact payload helpers and one shared API layer before registering
  MCP tools. The common envelope must carry schema/detector/estimator versions,
  run/source/scope identity, coverage, pagination/truncation, duration/cache,
  privacy flags, and warnings/caveats.
- Proposed serialized payload budgets are 4 KiB for status, 8 KiB for profile,
  16 KiB for a candidate page, and 24 KiB for candidate detail. Confirm these in
  the roadmap contract tests before implementation; any change must be recorded
  here with a reason.
- Candidate list queries must remain stably sorted and pageable. Extend the SQL
  query rather than post-filtering when adding model, thread, or time filters.
  Internal/local API calls retain `limit=0` and `limit=None` unbounded semantics;
  MCP responses must still obey the serialized page budget and report
  truncation/next-page information.
- Candidate detail defaults to bounded evidence handles. `summaries` remains
  content-free; explicit `excerpts` may read indexed fragments but must apply
  evidence-count, per-excerpt, and total-character bounds and set honest privacy
  flags.
- Start with failing lifecycle, deduplication, monotonic-progress, restart,
  paging, privacy, and payload-budget tests. Then add `compression/jobs.py`,
  `compression/payloads.py`, `compression/api.py`, and
  `cli/mcp_compression.py`; register the five tools, add the compression domain
  dependency, update release tool-name contracts and MCP/schema docs, and run
  focused tests before the full verifier.
- PR 3 is only complete after immediate cold start, sub-500 ms representative
  warm profile/list queries, compact default payloads without raw fragments, and
  handles/summaries/bounded-excerpts detail modes are proven. Open and merge a
  focused PR closing #238, then continue PR 4 and PR 5 as separate roadmap PRs.

Validated behavior at this checkpoint:

- Schema v18 migrates existing source and compression-run tables additively and
  adds the source-file/line lookup index used by the one-pass ingestion writer.
- Append plans verify stored device/inode identity and a bounded hash at the
  prior parse boundary before reusing byte and parser-state cursors.
- Source rows persist byte offsets, row counts, parser revision, bounded source
  identity, and a generation that advances only when the parsed checkpoint
  changes.
- Compression writes advance only the affected call/thread or content fact
  dimensions; reset and the compatibility generation API advance all dimensions.
- Exact cache identity includes selected detector dependencies and estimator
  policy revision without traversing record manifests.
- Existing manifest comparison still scopes incremental detector work to changed
  records and threads after a relevant revision changes.
- Public compression schema version and candidate/profile payloads remain
  unchanged.
- Completed profiles and their candidate/claim generations publish atomically.
- The compatibility mapping writer remains available for existing callers;
  the run builder uses the structural typed path without `candidate.as_dict()`.
- Bounded multi-row statements stay within SQLite's conservative variable
  limit, while 4,096-entry canonical-JSON caches avoid repeated immutable-field
  encoding.
- Estimation still runs immediately after each detector while evidence is
  resident. Global overlap allocation remains intentionally portfolio-wide.
- Default first refresh parses each source once and streams aggregate rows,
  normalized content, provenance, diagnostics, and compression facts through a
  bounded queue to one SQLite writer.
- Refreshes replacing more than SQLite's variable limit of source files batch
  cleanup safely and rebuild content FTS once after the complete replacement.
- Worker output is merged in source-plan order; one-file, small-history, custom
  parser, and process-pool-failure paths remain serial.

Latest CP3 real-data benchmark (`include_archived=true`, all-history scope):

- Calls: 404,176; normalized sequence facts: 714,571; candidates: 32,087.
- Reviewed safe migration plus CP2 fallback rebuild: 36.613 seconds.
- Reviewed explicit fact preparation: 72.968 seconds, paid only when requested.
- Reviewed prepared fact-backed rebuild: 27.598 seconds; evidence 9.640
  seconds; evidence plus detectors 15.473 seconds.
- Reviewed exact warm profile: 4.219 ms.
- Fact-backed and fallback runs produced identical candidate and stable public
  profile fingerprints.

Latest CP4 synthetic gate (100,000 calls, 500,000 normalized evidence rows):

- Revision lookup median: 0.982 ms against the 10 ms exit gate.
- Targeted aggregate one-event append: 0.376 seconds against the 1 second gate.
- Actual JSONL one-event append refresh: 19.8 ms, one source scanned and one
  usage event inserted or updated.
- Cold build: 3.935 seconds; evidence plus detectors: 2.238 seconds; warm exact
  reuse: 3.302 ms; peak RSS: 330.359 MiB.
- Canonical candidate fingerprint:
  `566d9962a31e65cdf8b7a3cbba3be23992b4ceb5c457cd418226e33ff8e5cded`.
- Canonical profile fingerprint:
  `96afabe6c8cfdeea77c708570939c1157a43f333b0cfc49e6173f107861ceeeb`.

Latest CP5 synthetic gate (100,000 calls, 500,000 normalized evidence rows):

- Candidate-heavy 5,000-row mapping path: 192.169 ms; typed atomic path:
  105.916 ms.
- Persistence improvement: 44.884 percent against the 40 percent exit gate.
- Cold build: 3.555 seconds; exact warm reuse: 3.737 ms; peak RSS: 320.484 MiB.
- Revision lookup median: 0.989 ms; aggregate append: 0.295 seconds; actual
  one-event JSONL append refresh: 20.0 ms.
- Canonical candidate and profile fingerprints match CP2-CP4 exactly.

Latest CP6 true first-refresh gate (100,000 token rows, 400 JSONL files):

- Parallel median: 17.729 seconds; worst-of-three: 17.740 seconds.
- Serial median: 25.638 seconds; measured speedup: 30.850 percent.
- Hardened validation: 19.614 seconds parallel versus 26.416 seconds serial,
  with 460.156 MiB sampled process-tree RSS against the 544 MiB ceiling.
- All 18 persisted table families had exact serial/parallel row-count and
  fingerprint parity. Coordinator RSS remains a secondary diagnostic.

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

1. Re-read the applicable `AGENTS.md` files, run `git status --short --branch`,
   and confirm only this checkpoint and the CP6 plan status are intentionally
   modified. Preserve `.idea/` and `uv.lock`.
2. Create `.agent-maintainer/change-plans/compression-mcp-progress-cache.md`
   with the paths and test gates listed above, then commit the roadmap checkpoint
   as the first focused PR 3 commit.
3. Implement and verify PR 3 using the test-first sequence in this checkpoint;
   push, open, pass CI, and squash-merge it.
4. Start PR 4 (overlap-aware simulator) from the updated `main`, then PR 5
   (skill, plugin, docs, and local dogfood) from the updated `main`, each as its
   own issue, branch, reviewed PR, and roadmap update.

## Resume Instructions

1. Read the canonical design and this execution ledger.
2. Start the next pending Compression Lab or CP milestone from current `main`.
3. Update the relevant PR status and append a dated progress-log entry.
4. Do not skip attribution invariants to add another detector quickly.
5. Do not route the skill to the new lab until shadow comparisons and MCP contracts pass.
