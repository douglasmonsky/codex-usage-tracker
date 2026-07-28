# Product Recovery Execution Ledger

This ledger records execution of the
[Product Recovery Roadmap](product-recovery.md) and its
[task packets](product-recovery-tasks/README.md).

Do not mark a task complete for intent, partial implementation, an unreviewed
benchmark, a source-only tag, or an unpublished package.

## Program Status

| Task | State | Depends on | Branch | Outcome |
| --- | --- | --- | --- | --- |
| R0 | Complete | — | `docs/product-recovery-roadmap` | Recovery authority merged as `117fff8` |
| R1 | Complete | R0 | `feature/r1-agent-outcome-baseline` | PR #342 merged as `aefb216`; frozen benchmark and measured failures |
| R2 | Complete | R1 | `feature/r2-schema-v3-compact-storage` | PR #344 merged as `f740939`; compact schema v3 published to `main` |
| R3 | Complete | R2 | `feature/r3-build-refresh-performance` | PR #344 merged as `f740939`; selective hydration and refresh gates pass |
| R4 | Complete | R2 | `feature/r4-fast-query-mcp` | PR #345 merged as `da42350`; persisted rollups and fast bounded paths |
| R5 | Complete | R3, R4 | `feature/r5-analytical-primitives` | PR #346 merged as `34528d1`; analytical facts and human semantics restored |
| R6 | In progress | R4, R5 | `feature/r6-console-usability` | Human-first Console implementation and browser qualification underway |
| R7 | Pending | R1; completes after R3–R6 | — | Installed fresh-task qualification |
| R8 | Pending | R0; completes after R6, R7 | — | Public documentation |
| R9 | Pending | R7, R8 | — | Public `0.29.0` release |

## Adoption Baseline

- Roadmap base: `origin/main` at
  `0f1483509a837857efaa42aa3b1be6487ea7ada4`.
- Repository version: `0.28.0`.
- Git tag: `v0.28.0` at
  `b23648e`.
- GitHub release: published, no package assets.
- Public PyPI latest: `0.27.0`.
- Active analytical schema: version 2.
- Product Kernel Reset K0–K15: complete.
- Product Kernel Reset K16: incomplete publication, superseded by R0.
- Paused public README and synthetic screenshot draft remains isolated on
  `docs/public-product-docs`.
- Paused thread-label investigation remains isolated on
  `fix/human-readable-thread-labels`.

## Measured Recovery Baseline

| Metric | Baseline | R1 authority |
| --- | ---: | --- |
| Cold production-shaped build | 1,096.357 s | pending reproducibility gate |
| Source history | 14.955 GiB | aggregate-only measurement |
| Stored fact rows | about 2.40 million | pending exact fixture manifest |
| Analytical database | about 1.17 GB | pending deterministic reproduction |
| Tables | 615.02 MiB | SQLite `dbstat` aggregate |
| Indexes | 501.21 MiB | SQLite `dbstat` aggregate |
| Allowance observations | 1,051,496 | schema-v2 aggregate |
| Same-timestamp allowance repeats | 518,900 | schema-v2 aggregate |
| Measured state-change rows | 133,587 | schema-v2 aggregate |
| Top-threads agent outcome | 5m45s | user-observed dogfood |

No raw prompt, response, reasoning, command, tool-output, or private path was
read to produce these measurements.

## Fresh-Task Agent Scorecard

R1 freezes the exact rubric and fixtures. Every subsequent task records:

| Dimension | Evidence |
| --- | --- |
| Readiness | package, plugin, MCP, skill, cached bundle, revision coherence |
| Exposure | fresh task exposes the expected six tools and no retired tools |
| Success | task returns a terminal useful answer |
| Accuracy | deterministic oracle comparison |
| Traceability | valid evidence selectors and destinations |
| Latency | end-to-end and tracker-tool wall time |
| Efficiency | MCP calls, batches, polls, retries, refresh jobs, response bytes |
| Usefulness | human labels, relevant metrics, explicit fact/estimate/inference |
| Freshness | correct committed generation and moving-tail behavior |

## Parallel Work Ledger

No parallel lane is active until its row names owners, worktrees, bases, and
disjoint file sets.

| Wave | Lane | Owner | Base | Files | State |
| --- | --- | --- | --- | --- | --- |
| 1 | R1 baseline | primary | `96c6335` | task packet allowlist | In progress |
| 2 | R3 ingestion | primary | `1f241f9` | ingest-owned files | Complete |
| 2 | R4 query | primary | `f740939` | R4 packet plus integrated rollup publication hook | In progress |
| 2 | R7 harness | unassigned | R1 harness | test/runner-owned files | Blocked |
| 2 | R8 copy audit | unassigned | R0 merge | docs-only files | Blocked |

## Task Entry Template

```markdown
## RX — Title

**State:** In progress | Blocked | Complete
**Branch:** `<branch>`
**Base:** `<sha>`
**Commits:** `<sha subject>`
**Owned files:** `<exact paths or directories>`
**Parallel lane:** `<none or named lane and integration checkpoint>`

### Contract added first

- `<failing test, benchmark, invariant, or task artifact>`

### Implementation

- `<behavior implemented>`

### Agent outcome

| Prompt | Success | End to end | Tool time | MCP calls | Accuracy | Usefulness |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `<prompt>` | Pass/Fail | `<time>` | `<time>` | `<count>` | `<grade>` | `<grade>` |

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass/Fail | `<command and summary>` |
| Broad | Pass/Fail | `<command and summary>` |
| Performance | Pass/Fail/N/A | `<identical before/after workload>` |
| Privacy | Pass/Fail | `synthetic fixtures; no private content` |
| Installed | Pass/Fail/N/A | `<wheel/plugin/skill/fresh-task evidence>` |

### Review metrics

- Total findings: `<n>`
- Accepted findings: `<n>`
- Accepted IDs: `<ids or none>`
- Reviewer tokens: `<n or pending>`
- Tokens per accepted finding: `<value, N/A, or pending>`

### Deviations and decisions

- `<none or approved decision>`

### Residual risk and next task

- `<remaining risk>`
- `<exact task unblocked>`
```

## R0 — Roadmap Adoption

**State:** Complete
**Branch:** `docs/product-recovery-roadmap`
**Base:** `0f1483509a837857efaa42aa3b1be6487ea7ada4`
**Commits:** `ba9e533 docs: add product recovery roadmap`;
`e1ec47e chore: ratchet roadmap sdist budget`;
`117fff8 docs: adopt Product Recovery roadmap (#340)` (squash merge)
**Owned files:** `AGENTS.md`; Product Recovery roadmap, ledger, and task
packets; historical notices in the Product Kernel Reset roadmap and ledger;
scope checker, focused scope test, and measured source-distribution budget
**Parallel lane:** none; R0 is coordinator-owned

### Contract added first

- The focused scope test failed at collection because
  `RECOVERY_ROADMAP_ADDITIONS` did not exist.
- The implemented contract now asserts the exact thirteen-file Product
  Recovery documentation inventory and its inclusion in the fail-closed active
  tree.

### Implementation

- Added the Product Recovery roadmap, execution ledger, and R0–R9 task
  packets.
- Made the installed fresh-task agent outcome the product north star.
- Recorded performance, storage, privacy, and incomplete-publication evidence.
- Defined the dependency graph, task ownership, acceptance gates, and safe
  parallel-subagent lanes.
- Made every parallel lane planning-only until explicitly authorized by the
  user or maintainer for the current task.
- Removed the R4/R5 dependency cycle, froze the R3/R4 rollup integration
  checkpoint, required supported local CLI/Desktop qualification, and made
  post-merge exact artifacts the only promotable release bytes.
- Pointed `AGENTS.md` to the new active authority.
- Preserved Product Kernel Reset documents as historical evidence and recorded
  K16 as superseded.
- CI and the matching local build measured source-complete sdists at
  402,327–402,593 bytes after adding the roadmap source. The sdist ceiling was
  ratcheted from 382,000 to 414,000 bytes, 2.83–2.90 percent headroom. Wheel,
  runtime source, Console, plugin, and catalog ceilings are unchanged.

### Agent outcome

Not applicable: R0 changes documentation and repository governance only. R1
creates the executable installed-agent scorecard.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | `pytest tests/kernel/test_kernel_scope.py -q`: 14 passed |
| Scope | Pass | `python scripts/check_kernel_scope.py`: integration scope passed |
| Release safety | Pass | `python scripts/check_release.py`: release-safety checks passed |
| Distribution | Pass | local wheel/sdist build plus `python scripts/check_release.py --dist`; 402,593-byte sdist under 414,000-byte ceiling |
| Broad | Pass | `just v`: 340 Python tests, 7 frontend tests, Ruff, MyPy, Pyright, maintainability, manifest, deterministic asset, scope, and release checks passed |
| Maintained CI | Pass | run `30287836844`: Focused Evidence Console, Python 3.10, and Python 3.14 passed |
| Diff | Pass | `git diff --check` |
| Performance | N/A | no runtime behavior changed |
| Privacy | Pass | documentation uses aggregate measurements and synthetic-only future fixtures; no private content or paths |
| Installed | N/A | no package, plugin, MCP, or skill bytes changed |

### Review metrics

- Total findings: 5
- Accepted findings: 5
- Accepted IDs: `PRR-1`, `PRR-2`, `PRR-3`, `PRR-4`, `PRR-5`
- Reviewer tokens: pending
- Tokens per accepted finding: pending

The metrics tool completed once with aggregate-only privacy, but reviewer-token
attribution was unavailable because the installed Usage Tracker CLI no longer
supports the metrics helper's `strict` command. It was not retried.

### Deviations and decisions

- The optional `agent_os` planning module was unavailable, so the approved
  plan was written directly into the repository's established roadmap format.
- Public `0.28.0` package publication is not resumed. The next qualified target
  is `0.29.0`.
- Initial PR CI correctly failed both distribution-building jobs because the
  new source documents exceeded the frozen 382,000-byte sdist ceiling. The
  measured ratchet is a source-package accounting correction, not a runtime or
  compatibility expansion.

### Residual risk and next task

- R0 has no remaining implementation, review, validation, or merge work.
- R1 is unblocked from exact R0 closure SHA
  `96c63359b3e79c8147d64dc6250a0de0968eb061`.

## R1 — Agent Outcome And Performance Baseline

**State:** Complete
**Branch:** `feature/r1-agent-outcome-baseline`
**Base:** `96c63359b3e79c8147d64dc6250a0de0968eb061`
**Commits:** source `959843c`; squash merge
`aefb2166eb006430bc5d66265a4256c53413e053`
**Owned files:** Product Recovery benchmark contracts and results under
`config/`; `scripts/benchmark_agent_outcome.py`; focused R1 and scope tests;
this ledger
**Parallel lane:** none

### Contract added first

- `tests/kernel/test_agent_outcome_baseline.py` initially failed at collection
  because the benchmark runner did not exist.
- The implemented contract freezes ten prompt IDs, eleven lifecycle scenarios,
  CLI and Desktop host identities, timing boundaries, fixed gates, two
  deterministic history profiles, a bounded answer schema, candidate
  coherence, privacy rejection, and scorecard validation.

### Implementation

- Added a streaming structural-only generator for an eight-thread CI workload
  and a 643-thread, 2.35-million-fact production-shaped workload.
- Added cold-build, byte-preserving no-change, and one-call append-safe
  measurements without editing kernel behavior.
- Added exact candidate binding across verified wheel `RECORD` bytes,
  wheel-executed package version and six-tool MCP catalog, source revision,
  plugin bundle digest, skill identity, and cached bundle digest.
- Added an ephemeral `codex exec` runner that discards raw task output and
  retains only bounded timings, counts, grades, versions, and error codes.
- Added executable deterministic oracles for all ten prompt intents and a
  lifecycle runner covering all eleven scenarios with measured or explicitly
  unsupported outcomes.
- Added a closed-world machine-readable scorecard schema with bounded typed
  strings and no prompts, responses, reasoning, tool arguments, raw results,
  paths, URIs, or extension fields.
- Fresh-host qualification now requires observed candidate registration,
  handshake, exact six-tool catalog, task exposure, supported launch method,
  candidate version, and bundle digest. It is never inferred from task success.
- Installed the exact candidate wheel locally, redirected the 0.28.0
  marketplace to this checkout, and removed the stale enabled 0.25.1 local
  plugin registration. The temporary synthetic Desktop MCP registration was
  removed immediately after the run.

### Agent outcome

| Host | Prompts | End-to-end range | Tool-time range | Calls | Exact accuracy | Usefulness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Codex CLI | 10/10 | 66.002–120.107 s | 12.331 ms–44.723 s | 1–3 | 0/10 | 0–3/4 |
| Codex Desktop | 10/10 | 50.428–137.955 s | 14.717–67.946 ms | 3–10 | 0/10 | 0–3/4 |

Every frozen prompt was executed in both advertised hosts against the same
synthetic committed generation. CLI had three 120-second terminal failures and
no exact oracle match. Desktop completed every task, but every answer violated
the requested closed answer schema; several returned object-valued facts,
list- or object-valued tool counts, or dictionary claim grades. Desktop spent
15.4–37.7 seconds before its first tracker call for eight tasks; the other two
started their first MCP call at 16.9 and 31.3 seconds. This separates
agent-orchestration latency from the mostly sub-68-millisecond Desktop tracker
work. The CLI allowance task independently exposed a 44.7-second tracker path.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Contract and scope | Pass | closed schemas, ten prompt oracles, eleven scenario outcomes, fail-closed scope checker |
| Reproducibility | Pass | two small-CI runs had stable SHA-256 `73508117…f1b4cd` after removing timing values |
| Small CI | Pass | 96 calls; 180.330 ms cold, 9.550 ms no-change, 23.495 ms tail; 286,720-byte database |
| Production-shaped | Measured failure | 1,316,864 initial calls and about 2.35 million facts; 792.320 s cold, 743.941 ms no-change, 1.886 s tail; 1,370,804,224-byte database |
| Candidate coherence | Pass | 129,519-byte wheel SHA-256 `551e171f…72a295`; source/cache plugin digest `84a60123…b62ec` |
| Fresh CLI task | Measured failure | all ten prompts observed; 0% exact accuracy; 66.002–120.107 s end to end |
| Fresh Desktop task | Measured failure | all ten prompts observed; 0% exact accuracy; every answer violated the bounded answer schema |
| Performance attribution | Pass | `agent-perf` Scalene run `20260727T172707Z-448eeb97`; attribution only |
| Privacy | Pass | synthetic fixtures only; persisted scorecard contains no prompt, response, reasoning, tool arguments, raw result, or local path |
| Installed | Pass | isolated candidate wheel smoke; two fresh raw MCP processes; warm Console p95 0.760 ms |
| Broad | Pass | `just vc`: 360 Python tests, 7 frontend tests, Ruff, MyPy, Pyright, maintainability, manifests, deterministic Console assets, scope, release checks, and rebuilt distributions |
| Distribution | Pass | 129,519-byte wheel; 409,824-byte source-complete sdist; both inside frozen budgets |
| Pull request | Pass | PR #342; required CI passed after one unchanged Python 3.14 performance-gate rerun |

### Review metrics

- Total findings: 7
- Accepted findings: 7
- Accepted IDs: R1, R2, R3, R4, R5, R6, R7
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Deviations and decisions

- The initial one-prompt probes were superseded by a full 20-task matrix after
  review found that nine prompt intents and most lifecycle paths were labels
  rather than executable baselines.
- Codex Desktop cannot inherit a shell-only cache override from an already
  running app. The qualifying task therefore used a temporary standalone MCP
  registration bound to the same exact installed wheel and synthetic cache,
  while the installed 0.28.0 plugin supplied the skill. That registration was
  removed after the task.
- Current failures remain recorded. Gates were not weakened.
- The first Python 3.14 CI attempt measured unchanged 100k-call writer p95 at
  64.732 ms against the 50 ms gate. The isolated rerun passed without code or
  threshold changes; Python 3.10 and Console lanes passed both attempts.
- Non-selector prompts record `not_applicable`; selector validity is awarded
  only when the exact synthetic selector resolves. Claim grading is aligned to
  fact, estimate, inference, and unsupported.

### Residual risk and next task

- The benchmark shows correct incremental planner choices but severe
  production-scale storage and cold-build amplification.
- The installed skill/query contract does not reliably lead agents to exact
  bounded answers; R4/R7 must make natural prompts succeed without teaching
  users the wire schema.
- R2 receives the frozen 2.35-million-fact storage/correctness oracle and the
  20-task agent-outcome matrix.
- R2 starts from exact authoritative base
  `aefb2166eb006430bc5d66265a4256c53413e053`.

## R2 — Define Schema V3 And Compact Storage

**State:** In progress
**Branch:** `feature/r2-schema-v3-compact-storage`
**Base:** `8afcb589e54ada05256f713a72c2f9ac9ba2cf7d`
**Commits:** pending
**Owned files:** analytical schema and writer storage boundary; focused schema,
allowance, query, scope, and budget contracts; this ledger
**Parallel lane:** none

### Contract added first

- The first focused run failed four schema-v3 contracts because the analytical
  store was still schema v2 and had no compact integer-key facts, allowance
  states, generation rollups, or metadata-only schema capability.
- The implemented contract now covers compact dimension and fact keys, exact
  selector round trips, four token classes, observation-trigger semantics,
  unchanged allowance-state compaction, interval deltas, generation-fenced
  rollups, and forbidden raw-content fields.

### Implementation checkpoint

- Analytical schema version 3 stores stable call, fingerprint, tool, activity,
  and allowance selectors as compact binary identities behind the existing
  logical selector views.
- Source, thread, turn, model, and tool dimensions provide integer foreign
  keys. Low-cardinality model/effort/tier/origin and tool-operation metadata
  are stored once per profile rather than once per fact.
- Repeated unchanged allowance snapshots update first/last observation bounds
  and count on one state. State changes create ordered intervals; the revealing
  call remains an observation trigger and is not treated as causal attribution.
- Seven generation-scoped rollup table contracts are frozen for the R4 updater.
  R2 does not populate them independently of fact publication.
- Side-by-side upgrade and rollback continue through the existing operational
  cutover state machine; schema-v2 bytes are never mutated in place.

### Measurement checkpoint

| Workload | Result | Evidence |
| --- | --- | --- |
| Small CI | Pass | 96 initial calls; 166.483 ms cold, 10.451 ms no-change, 26.491 ms tail; 237,568-byte database |
| Production-shaped cold | Stopped after decisive time failure | 17m20s; 1,023,666/1,316,864 model calls, 511,832 tools, 127,958 activities, 31,989 compact allowance states, and 513,318,912 database bytes |
| Production-shaped size | Pass | Exact optimized build produced a 634,011,648-byte database against the 734,003,200-byte ceiling with 1,316,864 model calls, 658,432 tools, 164,608 activities, 41,152 allowance states, 643 threads, and 164,608 turns. |

The first production run was stopped once cold-build failure was decisive; its
partial size projection was intentionally not reported as a pass. The stacked
R3 implementation then completed the identical immutable corpus in 111.402
seconds and proved the exact R2 storage result above.

### Verification checkpoint

| Check | Result | Evidence |
| --- | --- | --- |
| Focused schema, allowance, and query | Pass | final schema-v3, allowance, query, privacy, and exact-selector contracts pass on the stacked R3 implementation |
| Kernel | Pass | 294 tests passed; the only broad rerun finding was the measured source-byte ceiling, ratcheted to 1% headroom and rechecked |
| Ruff | Pass | all changed Python paths |
| Privacy | Pass | schema forbids raw prompts, responses, reasoning, tool arguments, tool output, shell bodies, and full paths |
| Full repository, distribution, installed | Pending | required before R2 merge |
| Review | Pending | one final read-only review after exact size evidence |

### Residual risk and next action

- Exact storage acceptance is complete. R2 remains open only for its final
  stable-diff review, broad repository/distribution checks, and merge.
- R3 owns the remaining refresh qualification and ledger closeout from the
  exact R2 checkpoint.

## R3 — Accelerate Cold Build And Incremental Refresh

**State:** In progress
**Branch:** `feature/r3-build-refresh-performance`
**Base:** `1f241f963019b3f45d3eb64e521471f7c6efa6f7`
**Commits:** pending
**Owned files:** discovery, parser/normalizer, ingestion, analytical writer,
refresh progress/recovery, focused performance contracts, and this ledger
**Parallel lane:** none

### Contract added first

- The initial 100,000-call contract failed with 503 writer transactions,
  11.293 seconds elapsed, and 27.736 ms writer p95.
- Focused contracts now separate unpublished staging transactions from the
  live incremental writer-lock budget, require no more than ten cold-build
  transactions for 100,000 calls, preserve 50 ms live-writer p95, prove exact
  turn counts across parser batches, defer and restore secondary indexes, and
  expose advancing writing/indexing/validating progress.
- A coverage-aware first-build amendment freezes three whole-source presets:
  `recent_30d`, `recent_90d`, and `complete`. The cutoff is captured once in
  UTC; uncertain timestamps are hydrated; every source is cataloged; expansion
  is explicit and monotonic; and partial history can never be labeled complete.
  This amendment intentionally coordinates R2 operational coverage state, R3
  discovery/ingestion, R4 interface/query truth, and R7 installed qualification
  before those tasks are separately closed.

### Implementation checkpoint

- Initial parsing remains bounded at 1,000 complete lines. Twenty-five already
  normalized batches share one staging transaction, eliminating cumulative
  count rescans and reducing the 100,000-call workload from 503 transactions
  to eight including index/finalization transactions.
- Source, thread, turn, fact, model-profile, and tool-profile selector keys are
  resolved in bounded maps rather than one SQLite lookup per fact.
- Stable thread and turn identities are cached within each normalized batch;
  row constructors no longer execute eagerly for identities already observed.
- Every secondary query index is absent only while the never-published cold
  artifact bulk-loads, then restored before validation and WAL publication.
- The disposable staging artifact uses journal-off/synchronous-off bulk
  durability. Published and incremental databases retain WAL, normal
  durability, foreign-key checks, and the existing side-by-side cutover.
- Prepared batch execution replaces one Python-to-SQLite call per compact
  fact. Failed never-active bulk artifacts are discarded and rebuilt; active
  generations and rollback artifacts are never replaced.
- Cold-build progress advances from 45% to 80% using committed byte coverage,
  then reports canonicalizing, indexing, validating, and promoting stages.

### Unprofiled performance evidence

| Workload | Before | Current | Result |
| --- | ---: | ---: | --- |
| 100,000 model calls | 11.293 s; 503 transactions | 2.857 s; 8 transactions | 74.7% faster |
| 160-source production slice | 49.825 s | 18.643 s | 62.6% faster with identical counts/bytes |
| Full 643-source production corpus | 792.320 s | 111.402 s | 7.11x faster; passes 240 s gate |
| Full database | 1,370,804,224 bytes schema v2 | 634,011,648 bytes schema v3 | 53.7% smaller; passes 700 MiB gate |
| Three-year `recent_30d` first use | no selective baseline | 2.562 s; 17/643 sources; 34,816 calls | 98.3% below 20 s gate; coverage remains explicitly partial |
| Explicit 30-day → 90-day expansion | 37.043 s on live incremental writer | 3.929 s on unpublished bulk clone | 89.4% faster; adds exactly 35 sources and 71,680 calls |
| Explicit 90-day → complete expansion | exceeded 240 s on live incremental writer; aborted | 110.193 s on unpublished bulk clone | passes 240 s; adds exactly 591 sources and 1,210,368 calls |
| One-call append-safe tail | 1.886 s R1 | 420.444 ms on owned 160-source production slice | passes 500 ms gate |
| 32-call bounded tail | not frozen in R1 storage row | 501.004 ms on owned 160-source production slice | passes 2 s gate |

The full result contains exactly 1,316,864 model calls, 658,432 tool calls,
164,608 activity events, 41,152 allowance states, 643 threads, and 164,608
turns. A five-run no-change distribution performed zero writer transactions:
one filesystem-cold sample was 2.463 seconds and four warm samples were
1.178–1.199 seconds. That remaining source-discovery cost is not hidden as a
query or status latency result.

The selective run used a deterministic 1,095-day version of the same
643-source, 526,480,341-byte production fixture. It cataloged all sources,
hydrated 13,855,383 recent bytes, deferred 512,624,958 bytes without parsing
them, and published a partial-coverage revision with zero uncertain sources.
Generating the fixture took 10.487 seconds and is excluded from refresh time.
Large monotonic expansions now clone the committed generation, bulk-stream only
newly selected sources without secondary indexes on the unpublished clone, and
atomically promote after validation. Small tails remain on the WAL incremental
path. The complete expansion produced the exact 1,316,864-call corpus without
reparsing the first 52 sources.

### Profiling evidence

- Unprofiled timings above are the only speedup evidence.
- `agent-perf` runs `20260727T203428Z-800177dc` and
  `20260727T203508Z-8d02e30b` both failed before workload execution because
  Scalene 2.3.0 exited 251 without a JSON profile.
- `agent-perf` run `20260727T220332Z-66e4ce6d` also failed before workload
  execution because its runtime could not locate pinned Scalene 2.3.0.
- A bounded cProfile fallback attributed the pre-index-deferral 100,000-call
  path primarily to normalization/stable identity work and per-row SQLite
  execution. It was used only to choose the next experiment.
- A second attribution-only cProfile run of the exact three-year
  `recent_30d` path completed in 4.166 seconds under instrumentation. Bounded
  cataloging accounted for 0.949 seconds and the selected-source initial
  stream for 3.106 seconds; the deferred 512 MB was not parsed.

### Verification checkpoint

| Check | Result | Evidence |
| --- | --- | --- |
| Ingest/lifecycle/accounting | Pass | 38 focused pipeline, reconciliation, concurrency, lifecycle, oracle, job, and database tests |
| Fault recovery/privacy/schema | Pass | 29 focused scale-recovery, privacy, and schema tests before final progress contract |
| Kernel profile | Pass with measured budget remediation | 294 tests passed; only source-byte ceiling exceeded, then ratcheted to 1% headroom and rechecked |
| Ruff | Pass | all changed Python paths |
| MyPy | Pass | 59 source files |
| Performance contracts | Pass | current 100,000-call, live-tail lock, index restoration, and progress tests |
| Selective hydration focus | Pass | 34 hydration, ingest, reconciliation, source-registry, Ruff, and MyPy checks |
| Final review | Pass after remediation | one read-only reviewer reported six findings; R1–R5 accepted and fixed, R6 retained as release-hardening risk |

### Residual risk and next action

- The final 111.402-second full run preceded the progress-only instrumentation;
  the current code requires one final bounded production confirmation after the
  selective-hydration contract is frozen.
- Full no-change refresh still catalogs 643 sources in about 1.18 seconds warm
  and up to about 3 seconds with cold filesystem metadata. Coverage-aware
  selective initial hydration and a bounded source catalog are now the active
  R3 implementation checkpoint.
- R2 and R3 remain stacked and unmerged. Broad repository/distribution
  validation and separate intentional commit/merge evidence remain before
  either task is marked complete.
- The final read-only review accepted fixes for incomplete bulk-artifact
  recovery, upgrade availability, mixed expansion/tail isolation,
  cross-preset recovery coverage, and terminal hydration-state cleanup. Review
  token attribution is `pending` because the local metrics helper invoked a
  retired `strict` CLI command; five of six findings were accepted.
- The rejected R6 observation concerns the pre-existing bounded generation
  digest, which binds validated generation metadata rather than every fact
  byte. R8/R9 must either freeze a broader deterministic artifact-integrity
  contract or explicitly document why SQLite integrity, foreign-key checks,
  accounting oracles, and exact release hashes remain the chosen layers.

## R4 — Build Persisted Rollups And Fast MCP/API Paths

**State:** In progress
**Branch:** `feature/r4-fast-query-mcp`
**Base:** `f740939a58f1a1bbba60d3fd19016e14b154ba89`
**Commits:** pending
**Owned files:** rollup updater, query catalog/plans/contracts/service,
application cache, refresh preset adapters and schemas, focused interface,
query, recovery, and performance contracts, scope allowlist, and this ledger
**Parallel lane:** none

### Contract added first

- Four initial R4 contracts failed because status/query omitted history
  coverage, partial all-history reads did not fail closed, query execution did
  not prove refresh absence, and refresh had no hydration-preset transport.
- A production-shaped append contract then exposed a critical integration
  defect: rebuilding every rollup from 100,000 prior calls held the active
  writer lock for 229.652 ms against the 50 ms ceiling.
- The current contracts cover generation/request cache reuse and invalidation,
  exact partial-history opt-in, new-install `recent_30d` default, monotonic
  explicit expansion, atomic rollup recovery, no-change upgrade backfill,
  HTTP/MCP preset transport, bounded time-band/tool-operation plans, and
  exact incremental-rollup parity.
- Final review added deterministic coverage for publication/coverage
  interleaving, cross-preset interrupted append recovery, regrouping stored
  model/tool dimensions, nullable tool-measure fallback, and immutable
  historical release evidence.

### Implementation checkpoint

- `usage_refresh` retains the six-tool surface and accepts `recent_30d`,
  `recent_90d`, or `complete` through MCP, HTTP, CLI, and the background
  worker. New installs default to 30 days; an existing or explicitly expanded
  complete generation never silently narrows.
- Status and query envelopes expose the committed preset, cutoff,
  completeness, source/byte coverage, and coverage revision. Partial
  all-history queries fail closed unless `allow_partial=true`; bounded queries
  never launch refresh or deferred hydration.
- Query cache lookup, partial-history validation, execution, and response
  coverage bind to one operational SQLite publication snapshot. Interrupted
  valid generations publish before a different-preset retry continues, while
  retaining prior conservative coverage until the retry publishes its own.
- Common global, thread, model/effort/tier, daily/hourly, and tool-operation
  aggregates read generation-scoped persisted rollups. Subset dimensions are
  regrouped exactly; nullable tool duration/output measures retain the generic
  exact path instead of converting missing values to zero. Query responses are
  cached by publication, generation, normalized request, coverage revision,
  and optional-content status, with observable hit/miss metadata and bounded
  deep-copy isolation.
- Append-safe refreshes seed compact prior-generation rollups and apply only
  the new generation delta. Replacement, expansion, and one-time upgrade
  backfill rebuild on unpublished clones. The atomic global rollup row is the
  publication marker; interrupted post-fact updates recover the rollups before
  promotion, while readers remain on the prior generation.
- R4 integrated the updater call site after R3 merged. This is an intentional
  deviation from the packet's earlier parallel ownership wording; there was no
  concurrent R3 writer and no ingestion file was edited by another lane.

### Unprofiled performance evidence

| Workload | Before | Current | Result |
| --- | ---: | ---: | --- |
| 100,000-call model/effort query | generic fact scan | 4.744 ms p95; 4 rollup rows | passes 500 ms stretch |
| 100,000-call thread concentration | generic fact scan | 2.157 ms p95; 250 rollup rows | passes 1 s gate |
| 100,000-call daily bands | generic fact scan | 2.258 ms p95; 28 rollup rows | passes 500 ms stretch |
| 100,000-call week comparison | unchanged generic path | 145.575 ms p95 | passes 1 s gate |
| 2,000-call append over 100,000 active calls | 229.652 ms writer p95 | 35.565 ms writer p95 | 84.5% lower; passes 50 ms gate |
| Synthetic 100,000-call kernel benchmark | — | 5.00 s unprofiled | attribution baseline |

### Profiling evidence

- Unprofiled timings above are the only speedup evidence.
- `agent-perf` run `20260727T235119Z-a3ca6bb7` was incomplete because Scalene
  did not emit JSON for the direct pytest workload.
- `agent-perf` run `20260727T235209Z-3f902139` completed the identical
  100,000-call synthetic kernel workload in 6.113 seconds under Scalene 2.3.0.
  Its ranked application hotspots were existing writer insertion/deletion and
  selector mapping; the rollup updater did not appear among the ranked
  hotspots. This is attribution evidence only.

### Verification checkpoint

| Check | Result | Evidence |
| --- | --- | --- |
| R4 query/coverage/recovery focus | Pass | 21 final rollup/query/coverage tests plus focused interruption, upgrade-backfill, and preset contracts |
| Broad touched surface | Pass | 144 query, interface, Console, content, live, allowance, ingestion, fault, and concurrency tests |
| Performance | Pass | 100,000-call query distributions and active-writer 50 ms gate |
| Ruff, MyPy, Pyright | Pass | active kernel, kernel tests, and scope script |
| Agent Perf | Pass with one compatibility caveat | one complete Scalene run; direct pytest capture incomplete |
| Full repository | Pass | 387 Python tests; frontend build/lint/typecheck/tests; Ruff, MyPy, Pyright, maintainability, scope, manifests, and release safety |
| Distribution and installed | Pass | exact 148,034-byte wheel and 449,942-byte sdist; clean and supported 0.26/0.27 upgrade smokes, two fresh MCP tasks each, and installed Console/allowance smoke; observed warm Console p95 no worse than 0.853 ms |
| Final review | Pass after remediation | one read-only reviewer reported five findings; R1–R5 accepted and fixed; reviewer token attribution pending because the installed tracker CLI lacks the metrics helper's legacy `strict` command |

### Residual risk and next action

- PR #345 passed CI and squash-merged as `da42350`. The source branch and
  worktree remain preserved.
- The first PR CI attempt exposed one stale installed-Console assumption: its
  synthetic allowance fixture relied on the former complete-history default.
  The smoke now explicitly requests `complete`; the local installed
  Console/allowance smoke passes without changing product behavior.
- The next Python 3.14 attempt exposed a pre-refresh upgrade boundary:
  read-only status queried schema-v3 coverage before a 0.26/0.27 sidecar had
  migrated. Publication snapshots now report conservative empty coverage for
  pre-v3 sidecars without writing. The v2-to-v3 migration creates the exact
  active/staged coverage schemas, and both published upgrade paths pass locally.

## R5 — Restore Analytical Primitives And Human Semantics

State: in progress on `feature/r5-analytical-primitives`, based on merged R4
commit `da42350`.

### Contract added first

- Added synthetic contracts for the four token classes and total, configured
  cost, estimated credits, coverage, allowance intervals, human thread labels,
  turn ordinal/completion basis, bounded tool semantics, adjacent-call impact,
  and copied-row exclusion.
- Added explicit upgrade, append, and parser-boundary contracts:
  parser v1 is replaced once by parser v2 and then returns to `no_changes`; a
  later completion event closes the existing turn without double-counting its
  call or tool; and tool start/output records merge across the 1,000-line
  parser batch boundary.
- Added privacy contracts proving that raw arguments, tool output, full source
  paths, and absolute targets are not persisted. Partial rate coverage keeps
  unrated usage visible rather than presenting it as zero.

### Implementation checkpoint

- Thread results pair a prompt-derived, bounded, control-stripped display label
  with the stable exact selector. Session-index renames are resolved without
  reparsing transcript JSONL.
- Tool facts retain only operation class, safe project-relative target,
  timestamps, status, duration, output byte count, argument-key shape, turn,
  and deterministic adjacent model-call token classes. The response caveat
  states that adjacency is not causal attribution.
- Turns remain open until an observed completion, abort, or rollback event and
  accumulate append-safe call/tool counts across generations.
- Configured cost and estimated credits use the local dated rate card with
  provenance, confidence, rated/unrated call coverage, and distinct semantics
  from observed allowance drain.
- Allowance rows are time-first and expose interval-local calls, turns, four
  token classes, total tokens, and observed drain without assigning the drain
  to the revealing call.
- Parser version 2 deliberately reparses a legacy source once. The source
  upsert now persists the new parser version; this fixed a defect that would
  otherwise have forced the same replacement reparse on every subsequent
  refresh.
- Tool upserts now report only genuinely new tool rows and preserve the active
  source/canonical adjacent call when an archived copy is encountered.
- The final review exposed and the implementation now covers nine additional
  edge contracts: label-less thread dimensions, pre-promotion tool isolation,
  moving-tail relinking, non-project target rejection, structural-only copy
  ownership, missing-ID tool occurrence identity, normalized structured-output
  byte semantics, invalid-rate-card degradation, and effective turn completion
  across every evidence view.
- Refreshes stage whenever an existing tool will be enriched or a new call can
  relink a prior tool in the same turn. Failed pre-promotion refreshes therefore
  leave the active generation unchanged, while successful moving-tail refreshes
  publish the following canonical call as the deterministic adjacent call.

### Unprofiled performance evidence

All measurements use fixed synthetic data; no local usage content was read.

| Workload | Current p95 | Budget/result |
| --- | ---: | --- |
| 100,000-call top threads with four token classes, cost, credits, and labels | 508.637 ms | passes 1 s concentration gate |
| 25,000-tool detailed adjacent-impact first page | 380.419 ms | passes 500 ms common-query gate |
| 100,000-call allowance read | 402.455 ms | passes 500 ms gate |
| 100,000-call evidence first page | 117.200 ms | passes 500 ms gate |
| Warm batched adapter query | 0.370 ms | passes 500 ms gate |
| Warm status | 0.567 ms | passes 50 ms local gate |

The linked-tool canonicality path was measured at 456.274 ms p95 before the
bounded fast-path change and 370.013 ms immediately afterward, a 19% reduction
on the identical 25,000-tool workload. The combined final run measured
380.419 ms p95. Common responses were 18,442 bytes for top threads and 10,071
bytes for tool impact, both below the 64,000-byte focused ceiling.

### Profiling evidence

- `agent-perf` run `20260728T021431Z-de01d540` completed the R5 synthetic
  workload under Scalene 2.3.0 in 22.235 seconds.
- Ranked application attribution identified query execution and the two
  deterministic per-call pricing functions on the cost/credit path. The
  profile is attribution evidence only; the unprofiled timings above are the
  performance evidence.
- A pricing lookup micro-optimization did not improve the identical
  end-to-end workload and was removed rather than retained as speculative
  complexity.

### Verification checkpoint

| Check | Result | Evidence |
| --- | --- | --- |
| R5 correctness/privacy focus | Pass | 24 dedicated R5 contracts plus focused query, allowance, evidence, application, rollup, ingestion, and concurrency suites |
| Performance suite | Pass | 10 synthetic query, allowance, evidence, adapter, ingest, and kernel benchmark tests |
| Ruff | Pass | changed R5 implementation and tests |
| MyPy, Pyright | Pass | 62-source MyPy surface; Pyright 0 errors and 0 warnings |
| Full repository | Pass | 412 Python tests, 7 frontend tests, scope, manifests, maintainability, release safety, lint, typecheck, and deterministic Console assets |
| Built distributions | Pass | wheel 158,032 bytes and sdist 469,613 bytes before the final ledger-only rebuild; both remain below their release-candidate ceilings; artifact digests stay in the external build manifest because this ledger is packaged in the sdist and ordinary wheel builds carry archive timestamps |
| Installed package | Pass | clean candidate, public 0.27 upgrade, exact R4-base 0.28 upgrade with one-time parser-v2 replacement, two fresh MCP tasks each, and installed Console/allowance smoke; warm Console p95 no worse than 0.953 ms |
| Final review | Pass after remediation | one read-only reviewer reported nine findings; R1–R9 were accepted and fixed; reviewer token attribution is pending because the installed tracker CLI lacks the metrics helper's legacy `strict` command |

### Deviations and decisions

- No explicitly authorized subagents were used. Shared parser, writer, query,
  evidence, and allowance ownership made sequential integration safer.
- SQLite timestamp subtraction can vary by a few microseconds; duration
  contracts retain exact observed endpoints and use a 0.02 ms assertion
  tolerance.
- Configured-cost concentration currently remains a bounded fact query because
  token pricing depends on the external rate-card revision. It passes the
  required 1-second gate without adding a query-time database writer.

### Residual risk and next action

- R5 merged through PR #346 as `34528d1`. Its task branch and worktree remain
  preserved. R6 consumes the frozen presentation fields; R7 consumes the
  installed-package and fresh-task qualification fixtures.

## R6 — Rebuild Console Usability

State: in progress on `feature/r6-console-usability`, based on merged R5
commit `34528d1`.

### Contract added first

- Tightened warm committed-generation rendering to 500 ms and asserted one
  status read plus one batched query per open, with no refresh request.
- Added browser contracts for immediately useful Top Threads and Recent Calls
  Explore results, Calls/Threads dataset switching, keyboard sorting, local
  filtering, local pagination, exact evidence links, human-first evidence
  columns, cost/credit visibility, and the allowance graph.
- Added pure model contracts for deterministic column order, human labels,
  null-safe sorting, pagination, allowance reset/drain presentation, and
  estimated-credit ratios that never coerce missing estimates to zero.

### Implementation checkpoint

- Live now shows calls, total tokens with all four token classes, cache reuse,
  configured cost, estimated credits, a compact token timeline, and human
  thread leaders. Snapshot and implementation-first cards were removed.
- Explore performs one batched request that returns guidance, Top Threads, and
  Recent Calls. The useful results precede the custom composer; exact call and
  thread identities remain available through evidence links and collapsed
  technical details.
- Shared tables provide keyboard-operable sorting, local filtering, and
  pagination without additional API calls. Time, human labels, totals, compact
  token mix, cost, credits, and actions precede technical identity.
- Evidence timelines show turn ordinal, event/tool semantics, compact call or
  adjacent-tool token impact, cost, credits, duration, and action. Selectors,
  generation, raw identifiers, and provenance are collapsed and copyable.
- Limits restores a real SVG usage-over-time graph. Its primary table begins
  with observation time, drain, local tokens, estimated credits,
  credits-per-point, tokens-per-point, reset boundary, and window; secondary
  ratios and coverage remain in technical details.

### Unprofiled performance evidence

All measurements use the committed synthetic browser fixture. No local usage
content was read.

| Route/workload | Runs | Median | p95 | Requests per open | Refreshes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Live desktop warm open | 25 | 39.3 ms | 57.2 ms | 1 status + 1 query | 0 |
| Live mobile warm open | 25 | 35.4 ms | 53.5 ms | 1 status + 1 query | 0 |
| Explore useful defaults | 25 | 39.6 ms | 52.0 ms | 1 status + 1 query | 0 |
| Limits graph and intervals | 25 | 38.7 ms | 54.2 ms | 1 status + 1 allowance | 0 |

Sorting, filtering, and pagination remain browser-local and add zero API
requests. The generated Console source totals 70,310 bytes at this checkpoint,
below the retained 90,000-byte ceiling.

### Profiling evidence

- `agent-perf` Node runs `20260728T034955Z-a60e89fe` and
  `20260728T035047Z-890b5e78` completed their synthetic workloads, but the
  pinned wrapper mishandled the space in its Application Support profile path
  and reported both as incomplete despite creating V8 profile files.
- No hotspot or speedup claim is inferred from those incomplete profiles. The
  repeated unprofiled browser measurements above are the performance evidence.

### Visual and verification checkpoint

- Desktop Live, Explore, and Limits were inspected from synthetic screenshots.
  The visual pass caught and fixed raw thread/share columns, incorrect aggregate
  call metadata, invisible SVG geometry, raw epoch reset timestamps, and
  missing-credit coercion.
- Frontend unit tests, JavaScript syntax checks, TypeScript checks, the bundle
  budget, and the deterministic asset build pass.
- The final desktop/mobile Chromium matrix passed 35 tests with three
  intentional skips. It covers cached reopen request counts, default Explore
  results, Calls/Threads switching, keyboard sorting, local filtering and
  pagination, exact evidence links, cross-generation enrichment rejection,
  small monetary facts, time-scaled graphs, responsive rendering, and the
  Limits graph.
- The complete repository gate passed 412 Python tests, Ruff, MyPy, Pyright,
  frontend lint/type/unit checks, deterministic assets, scope, maintainability,
  release-safety, and diff checks.
- The clean installed-wheel Console and allowance smoke passed. The package
  smoke passed two fresh MCP tasks and measured warm Console p95 at 0.873 ms.

### Release-candidate evidence

| Artifact or gate | Result |
| --- | --- |
| Wheel | 165,088-byte installed candidate passed Console, allowance, and two-fresh-task MCP smoke; exact build digest is reported by PR qualification |
| Sdist | Source-complete candidate passed composition and measured-plus-3% budget; the exact post-ledger artifact is reported by PR qualification rather than self-embedded |
| Release composition | Pass; built distributions contain current deterministic source and remain within measured-plus-3% ceilings |
| Installed Console | Pass; Console and allowance render from the exact wheel |
| Installed package | Pass; two fresh MCP tasks and warm Console p95 0.873 ms |
| Full repository | Pass; 412 tests and all static, type, scope, budget, and release gates |

### Visual, accessibility, and review handoff

- Final synthetic fixture screenshots are reproducible under `test-results/`:
  `r6-live-final.png`
  (`6cc4b2ac38ad9dd7b75beb020b88fccd1572575735a9552454b97f1b62f8791e`),
  `r6-explore-final.png`
  (`f9dbc54ca45b1e268f82300f5dbca86c53fd442e11d8602017c56799684987ad`),
  and `r6-limits-final.png`
  (`2fbe2e46a7dd1d71f188c31fea04521bd58fedabfc00fd33aa738180a19058b6`).
  These ignored local artifacts were visually inspected after the final asset
  build; R8 owns publishing qualified copies.
- Keyboard navigation, skip-link focus, sortable column-header state, local
  pagination, desktop/mobile responsive flows, chart accessible names, and
  evidence actions pass the Chromium matrix. Sort state now belongs only to
  the semantic column header.
- Final source asset identities are `app.js`
  `d7937620127c92b3ad263bffcc88e41540137bc1748d7f7f3ac6279a20c29576`,
  `model.js`
  `fe055e912c10af545d117465550561e67cd280a35d59d467f758ae84f3b37652`,
  `styles.css`
  `29c43210f90fd14899f1419c4045035db33f4d3d53658da4e26aad052fc6cc5b`,
  and `index.html`
  `17151aa63c5c47da7202aec87054693481797e11696beca840a165c07f8931da`.
- The single stable-diff reviewer reported seven findings and all seven were
  accepted: significant small-value formatting, numeric reset timestamps,
  generation-fenced evidence enrichment, real time-scaled graphs, pricing
  coverage, durable R8 handoff evidence, and valid ARIA sort ownership.
  Reviewer token attribution is pending because no bounded reviewer-token
  result was available; no retry blocks R6.
- Initial PR CI exposed inherited performance-test contention: Python 3.10
  measured top-thread p95 at 1.146 seconds inside the broad suite, while Python
  3.14 independently measured writer p95 at 70.5 ms. An unchanged rerun moved
  the miss to tool-impact p95 at 518.6 ms while Python 3.10 passed, confirming
  runner contention rather than an R6 behavior change. All five hard
  performance contracts now run together in the dedicated Python 3.14 step
  and are excluded from the broad matrix; their ceilings are unchanged. The
  exact dedicated command passed 12 policy and performance tests locally.

PR/CI merge remains before R6 completion.
