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
| R2 | Pending | R1 | — | Schema v3 and compact storage contract |
| R3 | Pending | R2 | — | Cold build and incremental refresh acceleration |
| R4 | Pending | R2 | — | Persisted rollups and fast API/MCP |
| R5 | Pending | R3, R4 | — | Analytical primitives and human semantics |
| R6 | Pending | R4, R5 | — | Console usability |
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
| 2 | R3 ingestion | unassigned | R2 contract | ingest-owned files | Blocked |
| 2 | R4 query | unassigned | R2 contract | query-owned files | Blocked |
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
| Production-shaped size | Pending exact optimized run | The stopped build had loaded 77.7% of model facts. Its partial bytes project below 700 MiB, but projection is not acceptance evidence. |

The production run was stopped once the cold-build failure was decisive. Paying
for the remaining serial writer work would not improve the performance
decision, and the partial size projection is intentionally not reported as a
pass. R3 will remove repeated indexed selector lookups and thousands of
transactions before the next single full production-shaped run. That run will
provide the exact R2 size result and the R3 cold-build result together.

### Verification checkpoint

| Check | Result | Evidence |
| --- | --- | --- |
| Focused schema, allowance, and query | Pass | 14 tests before the final two schema contracts; final focused rerun pending checkpoint commit |
| Kernel | Pass with corrected catalog pending rerun | 290 passed; the only failure was the expected 15-to-17 analytical-table budget update |
| Ruff | Pass | all changed Python paths |
| Privacy | Pass | schema forbids raw prompts, responses, reasoning, tool arguments, tool output, shell bodies, and full paths |
| Full repository, distribution, installed | Pending | required before R2 merge |
| Review | Pending | one final read-only review after exact size evidence |

### Residual risk and next action

- The cold path remains dominated by repeated source/thread/turn selector
  lookups and thousands of bounded transactions whose cost grows with each
  B-tree. Progress remains at the coarse `writing` 45% stage while rows advance.
- The next checkpoint is a stacked R3 implementation from the exact R2 source
  commit. R2 remains open until the optimized full run proves the exact size
  ceiling and its final broad/review gates pass.
