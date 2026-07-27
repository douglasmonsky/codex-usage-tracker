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
| R1 | Pending | R0 | — | Agent outcome and performance baseline |
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
| 1 | R1 baseline | primary | R0 merge | task packet allowlist | Pending |
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
- R1 is unblocked from exact merged-main SHA
  `117fff8d38390cb64c6ebef21545908c333a767f`.
