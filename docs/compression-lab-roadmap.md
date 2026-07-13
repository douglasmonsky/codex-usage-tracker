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

Status: in progress

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

- Full uncached run: under 60 seconds on data near the maintainer's current scale.
- Warm profile and candidate list: under 500 ms.
- Candidate detail: under 1 second.
- Progress starts immediately and remains monotonic.
- Incremental refresh recalculates only changed records/threads plus global overlap totals.

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

## Current Restart Checkpoint

Worktree: `/Users/Monsky/Documents/Codex/2026-07-11/r11-compression-detectors`

Branch: `feature/compression-lab-detectors`

Last completed commit before the current run-builder slice: `0094dca` (`feat: add compression opportunity detectors`). The run-builder/performance work after that commit is intentionally left intact in the worktree and must not be discarded.

Validated behavior at this checkpoint:

- Cold success, zero findings, structured partial detector failure, exact cache reuse, forced replacement, and appended-record incremental recomputation.
- Deterministic per-thread cache manifests and candidate IDs.
- Staged progress through evidence, each detector, attribution, persistence, profile, and completion.
- Focused checkpoint: 66 compression/store tests passed; the full suite passed all 722 tests after keeping the unreleased schema at v15.
- Real local aggregate dogfood completed with 404,176 calls, 32,087 candidates, no detector warnings, and no raw content printed or committed.
- Exact cache hits use a compact public profile plus a transaction-level source generation, so they do not rebuild evidence or decode the private incremental manifest.
- All-history evidence reads bypass temporary scope materialization only when the scope is truly unfiltered.

Latest replacement benchmark (`include_archived=true`, all-history scope):

- Total: 47.939 seconds, including deletion and replacement of the prior 32,087-candidate run.
- Evidence loaded: 18.69 seconds.
- All detectors complete: 26.18 seconds.
- Attribution complete / persistence started: 30.40 seconds.
- Candidate persistence complete / profile started: 42.30 seconds.
- Profile complete: 47.59 seconds.
- Exact warm profile: 6.2 ms, below the 500 ms target.
- The prior comparable run took 77.575 seconds on 324,982 calls; the optimized run is 38 percent faster while processing 24 percent more calls.

Measured optimizations:

- Removed quadratic claim-to-record membership validation during candidate estimation.
- Reused a source-generation counter instead of hashing the complete normalized snapshot twice.
- Replaced per-event cryptographic manifest hashing with deterministic order-independent checksums and removed duplicate event identity encoding.
- Built attribution capacity directly from the estimator index rather than materializing generic row dictionaries.
- Removed an unused candidate-record secondary index and persisted compact public profiles separately from private incremental manifests.

Resume in this order:

1. Keep the PR at or below the 20-file ceiling and leave `.idea/` unstaged.
2. Commit the run-builder slice as `feat: build compression analysis profiles`.
3. Merge current `origin/main` without rewriting history, resolve only genuine conflicts, then push/open/merge PR 2 before starting PR 3.

## Resume Instructions

1. Read the canonical design and this execution ledger.
2. Start the next pending PR from current `main`.
3. Update the relevant PR status and append a dated progress-log entry.
4. Do not skip attribution invariants to add another detector quickly.
5. Do not route the skill to the new lab until shadow comparisons and MCP contracts pass.
