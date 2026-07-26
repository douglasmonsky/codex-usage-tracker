# Product Kernel Reset Execution Ledger

This is the durable execution record for the
[Product Kernel Reset](product-kernel-reset.md). The approved
[design](../superpowers/specs/2026-07-26-product-kernel-reset-design.md) and
[implementation plan](../superpowers/plans/2026-07-26-product-kernel-reset.md)
define scope and acceptance.

Update the applicable entry in the same changeset as each task. Do not mark a
task complete from intent, partial implementation, an unreviewed benchmark, or
an unpublished release.

## Ledger Rules

Every terminal task entry records:

- branch, base, and commits;
- exact files or modules owned;
- failing contract or benchmark added first;
- focused and broader verification with outcomes;
- before/after latency, lock, row, size, or surface measurements where
  applicable;
- privacy and synthetic-fixture confirmation;
- deviations and approved amendments;
- independent review findings, accepted findings, reviewer token count, and
  tokens per accepted finding;
- development-efficiency metrics from
  `config/kernel-development-efficiency-v1.json`, including focused and broad
  verifier runs, blocking and non-behavioral gate findings, gate-remediation
  lines, duplicate broad runs, verification wall time, and style-only commits;
  and
- residual risk and the exact next task unblocked.

Use `pending` for unavailable reviewer-token indexing. Never start extra
analysis or refresh work solely to populate review metrics.

### Churn monitoring

K1 is the first post-policy baseline. Do not claim a historical percentage
reduction from estimates. Beginning with K2, report each task against K1 and
the immediately preceding completed task. A reduction claim must name the
numerator, denominator, and task range.

Count an intentional failing contract test separately from a gate failure.
Count a gate finding as non-behavioral only when the implementation's behavior,
types, privacy, security, dependency direction, package contents, and public
contracts were already correct and the edit existed solely to satisfy a style
or overlapping metric. `gate_remediation_lines` is the added plus deleted lines
in those edits. A broad profile repeated on unchanged code counts as a
`duplicate_broad_run`; a retry after code, configuration, or environment repair
does not. A `style_only_commit` changes no behavior, contract, test expectation,
schema, documentation meaning, or generated source input.

The task entry and machine-readable record must agree before merge. Report zero
when a measured category did not occur and `pending` only while the task is in
progress.

## Program Status

| Task | Release | State | Depends on | Outcome |
| --- | --- | --- | --- | --- |
| K0 | documentation baseline | Complete | — | Archive former program and approve reset |
| K1 | 0.25.x bridge | Complete | K0 | Freeze accounting oracle |
| K1A | 0.26 integration | Complete | K1 | Quarantine legacy code and freeze agent scope |
| K2 | 0.26.0 | Not started | K1A | Kernel schema v1 and stable identity |
| K3 | 0.26.0 | Not started | K2 | Incremental/live ingestion |
| K4 | 0.26.0 | Not started | K3 | Bounded query engine |
| K5 | 0.26.0 | Not started | K3 | Evidence timeline and live stream |
| K6 | 0.26.0 | Not started | K4, K5 | Six-tool integration interfaces |
| K7 | 0.26.0 | Not started | K6 | Focused Evidence Console |
| K8 | 0.26.0 | Not started | K7 | Allowance efficiency |
| K9 | 0.26.0 | Not started | K8 | Release candidate and final absence audit |
| K10 | 0.26.0 | Not started | K9 | Audited release-branch cutover and qualification |
| K11 | 0.27.0 | Not started | K10 | Guided exploration |
| K12 | 0.27.0 | Not started | K11 | Optional context composition |
| K13 | 0.27.0 | Not started | K11 | Read-only overlay boundary |
| K14 | 0.27.0 | Not started | K12, K13 | Release qualification |
| K15 | 0.28.0 | Not started | K14 | Fault, recovery, and scale |
| K16 | 0.28.0 | Not started | K15 | Contract freeze and release |

## Baseline Evidence

### Published and repository baseline

- Published package: `codex-usage-tracking==0.25.1`.
- Documentation base: `origin/main` at
  `0a558dd328c1519c77fffe68b71a8bccdbd1a731`.
- Operational evidence branch: `fix/313-core-fast-path` at
  `96cc1546aa20b36d1a93945dc11cc88e6b19aa42`.
- Current experimental cache schema: version 39.
- Approximate authored surface: 90,500 Python source lines and 52,000
  TypeScript/TSX source lines.

### Synthetic 10,000-event refresh evidence

| Mode | Parallel cold refresh | Writer lock | Important result |
| --- | ---: | ---: | --- |
| Current normal default | 3.073 s | 3.040 s | Captures tools/turns but also builds fragments, FTS, compression, and diagnostics |
| Current aggregate-only | 1.742 s | 1.711 s | Omits structural tools/turns needed by the target product |

The target seam is to retain privacy-safe structural facts while removing
content indexing and interpretation-specific materialization from normal
ingestion. These measurements are comparison evidence, not claimed production
latency.

### Profile evidence

- Agent-perf run: `20260726T170258Z-5d2d8174`.
- Workload: bounded synthetic refresh.
- Finding: no single parser CPU hotspot dominated. Leading owned entries
  included compression-manifest accumulation, refresh orchestration, content
  persistence, and deferred index maintenance.
- Interpretation: the reset must remove coupled work and shorten writer
  ownership, not merely micro-optimize one parser function.

No live usage database or raw session content was inspected.

## K0 — Roadmap Reset

**State:** Complete
**Branch:** `docs/kernel-reset-roadmap`
**Base:** `origin/main` at
`0a558dd328c1519c77fffe68b71a8bccdbd1a731`
**Commit:** `e6d6b76 docs: reset product roadmap around lean data kernel`

### Scope

- Archive the 2026-07-21 MCP-first roadmap, design, plan, execution ledger, and
  Agent Maintainer change plan.
- Leave stable redirect documents at published paths.
- Adopt the Product Kernel Reset roadmap, design, implementation plan,
  execution ledger, deprecation ledger, and task-branch convention.
- Update public architecture, release, and repository guidance.
- Add focused public-document contract tests.

### Evidence before editing

- 0.24 foundation audit: `PROCEED`; healthy accounting core, overgrown product
  shell.
- Installed dogfood: exact queries useful; automatic narrative analysis,
  optional derived-state refresh work, duplicate/long-running job behavior, and
  compatibility weight undermined the central product.
- The user explicitly approved beta removal rather than runtime legacy support.

### Verification

- `python -m pytest tests/packaging/test_public_docs.py
  tests/cli/test_cli_release.py -q`: 44 passed.
- `python scripts/check_release.py`: passed.
- `npx markdownlint-cli2 README.md "docs/**/*.md"
  ".agent-maintainer/change-plans/*.md"`: 159 files, 0 errors.
- Changed-document local-link check: 23 Markdown files, all targets exist.
- `git diff --check`: passed.
- One final read-only review: 6 findings; all 6 accepted, addressed, and
  rechecked by the primary implementation pass.

### Review metrics

- Total findings: 6
- Accepted findings: 6
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Review resolution

- The original baseline kept K6 and K7 non-public while the 0.25 defaults
  remained releasable. The K0A amendment supersedes its wait-until-K9 deletion
  sequence with early K1A active-tree quarantine.
- The cutover has explicit `absent`, `building`, `ready`, `active`, and `failed`
  states, three authorized build triggers, atomic pointers, and distinct kernel
  versus installed-package rollback.
- Full paths live only in a non-exportable operational registry.
- K1 freezes an exact cross-surface retirement manifest consumed by K6/K9.
- K4 owns the pure versioned phase segmenter and golden tests.
- Public-document tests require the exact six-tool list and every archive
  redirect/artifact.

### Deviations

- The optional external Agent OS planning CLI was unavailable in the active
  environment, so the repository-native roadmap, design, implementation plan,
  change plan, and execution ledger are the durable handoff.
- Serena JetBrains activation encountered a stale workspace registration. Exact
  documentation paths and edits used repository-native tools; no semantic code
  edit depended on the stale IDE registration.

### Residual risk

This task changes authority and future intent only. Current 0.25 runtime
behavior remains unchanged until separately reviewed K1–K10 work lands. K1 is
now unblocked.

## K0A — Early Code Quarantine Amendment

**State:** Complete
**Branch:** `docs/kernel-reset-roadmap`
**Base:** `e6d6b76 docs: reset product roadmap around lean data kernel`
**Commit:** this changeset

### K0A contract added first

- The roadmap must put K1A before K2 and classify every K1 `git ls-files` path
  as exactly one of `keep`, `transplant`, `retire`, or `historical`.
- `verified` is the sole terminal status, with proof for all four
  dispositions.
- `main` remains the releasable 0.25.1 line; K1A–K9 use the non-publishable
  `kernel/0.26-integration` branch; K10 creates `release/0.26.0` from audited
  current `main`, incorporates qualified integration once, and opens the
  release-to-`main` cutover.
- Normal agent search after K1A sees only the integration worktree. Tagged
  v0.25.1 source is a bounded, policy-read-only oracle.

### K0A implementation

- Added the decision-complete code-quarantine design and linked it from the
  roadmap, architecture, detailed design, and implementation plan.
- Added K1 code-disposition inventory, K1A physical quarantine, progressive
  transplant, K9 final-absence, and K10 current-`main` reconciliation
  contracts.
- Defined full tracked-tree scope, disposition state transitions, persistent
  publication rejection, named mainline-port handling, and one exact K10
  release-branch topology.
- Updated repository, deprecation, release, README, changelog, and public-doc
  test guidance for the temporary integration topology.
- Added an Agent Maintainer change plan for this documentation-only amendment.

### K0A Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused docs | Pass | 44 public-doc and release-CLI tests |
| Release contract | Pass | `scripts/check_release.py` |
| Markdown and links | Pass | 161 Markdown files, 0 errors; 12 changed documents, all local links exist |
| Diff and disclosure | Pass | whitespace, secret-pattern, and absolute-user-path scans |
| Privacy | Pass | documentation and synthetic contract assertions only; no usage data inspected |

### K0A Review metrics

- Total findings: 6
- Accepted findings: 6
- Reviewer tokens: pending
- Tokens per accepted finding: pending

Token measurement timed out without inspecting private usage content. Per the
review policy, the review result remains recorded and completion does not retry
or block on usage indexing.

### K0A Review resolution

- Expanded the disposition manifest from selected product paths to the entire
  K1 tracked tree and made `verified` the sole terminal state for all four
  dispositions.
- Replaced the contradictory K10 branch descriptions with one audited
  current-`main` release-branch topology.
- Kept the branch/ref publication guard active through K9 and made its
  rejection checks part of the release-candidate evidence.
- Added a fail-closed workflow for changes that land on `main` after K1,
  including named port branches, manifest/oracle updates, and requalification.
- Strengthened public-document tests to enforce these safety contracts instead
  of checking vocabulary alone.

### Deviations and decisions

- Serena's guarded recovery reported the worktree and language services
  healthy, but this task's bridge continued resolving a stale unrelated
  project path. Documentation edits used exact repository-native tools; no
  semantic source edit depended on Serena.
- The temporary integration branch is an explicit, narrowly scoped exception
  to the repository's no-long-lived-development-branch rule.

### Residual risk and next task

- Physical deletion is intentionally deferred to K1A, after K1 freezes the
  exact manifests and rollback oracle.
- K1 remains the next task; K1A is blocked on its two machine-readable
  inventories.

## K1 — Accounting Oracle Baseline

**State:** Complete
**Branch:** `kernel/k1-oracle-baseline`
**Base:** `62726189c05d423f08abdec6ad1454434188d734`
**Commits:** `c62c3a6`, `09e6f44`, this changeset

### K1 contract added first

- Added 14 intentionally failing K1 contract tests before implementation.
  They required the accounting and source-lifecycle oracles, privacy boundary,
  exact retired-surface inventory, full-tree code disposition, fixed-seed
  benchmark evidence, and repository gate policy.

### K1 implementation

- Added a versioned synthetic-JSONL accounting oracle covering physical and
  canonical rows, copied-event deduplication and canonical promotion, four
  token classes, thread/model/effort/service-tier/time groupings, stable
  identity, delayed parent/subagent attachment, competing allowance
  observations and selection, local tool and MCP calls, skills, patches,
  tests, errors, compaction, completion, abort, rollback, and parsed malformed
  or unknown-event skipping.
- Exercised current source planning for new, appended, partially appended,
  replaced, truncated, archived, and restored sources without reading live
  Codex data.
- Generated 1,578 full-tree disposition entries and 1,194 retiring surface
  entries. Every staged `git ls-files` path resolves exactly once with one
  owner and a path-relevant proof. The retired inventory exactly derives 58 MCP
  tools, 69 HTTP routes, 91 CLI command paths, 87 schemas, all 38 tables, 17
  Console routes/aliases, 508 frontend assets, 28 package-data rules, and 298
  retired source modules from authoritative catalogs.
- Added fixed-seed old-runtime benchmarks and `agent-perf` attribution. The
  benchmark includes derived-state maintenance so K2–K9 comparisons cannot
  hide the legacy work.
- Retired wemake and the standalone duplicate-helper, private-import, and
  file-length ratchets. Aligned Agent Maintainer's remaining file bounds,
  widened roadmap change budgets, relaxed Xenon only to a B ceiling, and
  replaced generic verifier profiles with repository-owned `just` checks.
- Added constructive repository guidance for contract-first implementation,
  cohesive responsibility boundaries, direct code, deterministic generation,
  synthetic fixtures, focused iteration, and proportionate broad validation.
- Added a versioned development-efficiency ledger so K2 onward must report
  exact gate churn against K1 and the preceding task.
- Added a repository-owned replacement-kernel maintainability gate. It enforces
  600 physical/source lines and Xenon B absolute/module/average ceilings on the
  clean kernel while the existing product-complexity ratchet protects the
  legacy runtime until quarantine.

### K1 verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused oracle | Pass | final `pytest tests/kernel -q`: 26 tests |
| Determinism | Pass | both manifest generators matched `--check`; repeated oracle exports matched byte-for-byte semantic JSON |
| Repository CI-equivalent | Pass | final `just vc`: 2,085 Python tests; Ruff, MyPy, source Pyright 0 errors, Tach, dependency/dead-code/security/release/product/kernel-maintainability budget checks; 599 frontend tests, governance, bundle, and deterministic assets |
| Performance | Pass | cold 10k: 1.536 s wall / 1.063 s held lock; cold 100k: 20.633 s wall / 16.170 s held lock; 100,000 physical / 95,001 canonical rows |
| Profile | Pass | `agent-perf` run `20260726T194642Z-9b3625c3`; insertion, source records, links, and legacy compression facts were leading owned work; attribution only |
| Privacy | Pass | repository-only synthetic fixtures; no live database, real log, prompt, tool output, credential, or absolute user path inspected or stored |
| Release and guidance | Pass | `scripts/check_release.py`, generated guidance drift, manifest drift, and `git diff --check` passed |

### Development-efficiency baseline

- Contract red-test runs: 1
- Focused test runs: 33
- Broad verification runs: 5
- Duplicate unchanged-state broad runs: 0
- Blocking check groups: 8
- Non-behavioral blocking check groups: 6
- Gate-remediation lines: 74
- Recorded verification wall time: 966.0 seconds
- Style-only commits: 0

The first broad run used Agent Maintainer's generic CI profile and exposed four
non-product blockers: stale file-length baselines, stale/multiple change plans,
formatting of Python snippets embedded in archived Markdown plans, and a
test-wide Pyright scope that did not match GitHub CI. No application code was
rewritten. The repository acceptance wrappers were corrected, and the second
broad run passed. A redundant frontend-governance invocation was also removed
from `just vc`; `dashboard:verify` remains the single owner of that gate. K2 is
the first task eligible for a churn-reduction comparison.

The first two GitHub CI runs added two behavioral findings. The two new TOML
readers used Python 3.11's `tomllib` without the repository's Python 3.10
`tomli` fallback, and Xenon reached local environments only through a
Python-3.11-plus transitive dependency. The compatibility corrections passed a
clean Python 3.10 development install and its focused kernel checks. Both count
as blocking findings, not as non-behavioral gate churn.

### K1 review metrics

- Total findings: 6
- Accepted findings: 6
- Reviewer tokens: pending
- Tokens per accepted finding: pending

The single final reviewer identified six actionable gaps: semantic
misclassification, heuristic retirement inventories, parser-bypassing oracle
coverage, incomplete disposition ownership/proofs, unenforced maintainability
claims, and a warm/reused benchmark path. All six were accepted and corrected
by the primary agent. No second review pass was run.

### K1 deviations and decisions

- Serena's repository doctor passed, but JetBrains semantics remained
  unavailable because the worktree is outside the configured IDE helper roots.
  GitNexus selected cross-cutting paths; exact repository search and focused
  tests supplied authoritative symbol and contract evidence.
- The original K1 contract did not include gate-churn governance. The user
  explicitly approved retiring or adjusting low-value gates and requested
  ongoing reduction reporting on 2026-07-26.

### K1 residual risk and next task

- The disposition manifest begins in `classified`; K1A–K9 must advance each
  entry through its declared state machine, and only `verified` is terminal.
- Performance evidence describes the synthetic v0.25.1 path on one machine and
  is comparison evidence, not a production latency claim.
- K1A started from merged K1 commit
  `d8da9bccdb6674e7dca4c0872c36a1346949dc13`.

## K1A — Quarantine Legacy Code And Freeze Agent Scope

**State:** Complete
**Branch:** `kernel/k1a-legacy-quarantine`
**Base:** `d8da9bccdb6674e7dca4c0872c36a1346949dc13`
**Commits:** this changeset

### K1A contract added first

- Added a failing active-tree contract before deletion. It required every K1
  keep path, rejected every active retire/transplant/historical path, bounded
  new K1A files to one exact allowlist, imported the isolated kernel skeleton,
  and rejected publication from integration and every K1A-K9 task ref.
- The first run failed because the scope checker did not exist. The second
  failed with the 1,473 expected manifest-named legacy paths still active.

### K1A implementation

- Created detached policy-read-only reference worktree
  `codex-usage-tracker-v025-reference` at `v0.25.1` commit `0a558dd` and
  preserved it clean.
- Created and pushed `kernel/0.26-integration` at merged K1 commit `d8da9bc`,
  then created this K1A task branch from that exact head.
- Removed exactly 1,473 K1-classified non-keep paths: 1,063 retire, 231
  transplant, and 179 historical. All were clean tracked files before the
  manifest-driven deletion; no glob or user-modified target was used.
- Advanced every removed path to `removed`, preserved its source reference,
  owner, target, oracle, and absence test, and pinned the manifest quarantine
  base to the merged K1 SHA.
- Added the isolated `codex_usage_tracker.kernel` skeleton and kernel-local
  instructions. The active tree now contains 105 retained K1 paths plus six
  explicit K1A additions.
- Set integration identity to `0.26.0.dev0`, removed runtime dependencies,
  console scripts, MCP servers, plugin bundle claims, skills, package data, and
  legacy frontend tooling. Pricing and allowance scheduled workflows are
  paused until K8.
- Replaced legacy CI with the K1A phase gate and made the publish workflow call
  the persistent branch/ref guard before any release tooling.
- Replaced runtime-derived K1 manifest generation with frozen-inventory
  canonicalization and progressive transition validation.

### K1A verification

| Check | Result | Evidence |
| --- | --- | --- |
| Scope and inventories | Pass | 26 phase tests; exact 1,473-path removal; all non-keep states `removed`; no unclassified or physically present quarantined path |
| Static correctness | Pass | focused Ruff, MyPy, Pyright 0 errors/warnings, 600-line and Xenon-B kernel budget |
| Package isolation | Pass | `just vc` plus package-only rebuilds; wheel 13,512 bytes with 5 Python modules and metadata only; sdist remains below 200,000 bytes with an exact fail-closed member set; no CLI entry point, runtime dependency, MCP server, legacy runtime, frontend, skills, or plugin data |
| Development footprint | Pass | active paths 1,578 -> 111 (93.0% reduction); code-bearing files 1,248 -> 33 (97.4% reduction); tracked/active bytes 41,670,579 -> 3,830,579 (90.8% reduction); clean Python 3.10 dev resolution 117 -> 30 packages (74.4% reduction) |
| Privacy | Pass | synthetic K1 fixtures only; no live database, Codex log, prompt, tool output, secret, or full user path entered the repository |
| Reference safety | Pass | detached `v0.25.1` reference remains clean and was never built, tested, indexed, or activated |

### K1A development-efficiency comparison

| Metric | K1 | K1A final local | Change |
| --- | ---: | ---: | ---: |
| Non-behavioral blocking groups | 6 | 5 | 16.7% lower |
| Gate-remediation lines | 74 | 60 | 18.9% lower |
| Verification wall time | 966.0 s | 52.7 s | 94.5% lower |
| Style-only commits | 0 | 0 | unchanged |
| Duplicate unchanged-state broad runs | 0 | 1 | one regression |

The duplicate was explicit: after `just v` passed, `just vc` reran it before
building the package. K2 must call the package-only step after an already-green
phase check. K1A also narrowed Ruff from the retained K10 tree to phase-owned
files after one unrelated release-smoke style finding. Correctness, privacy,
release-ref, package-content, and maintainability gates remain blocking.

### K1A review metrics

- Total findings: 4
- Accepted findings: 4 (`K1A-R1` through `K1A-R4`)
- Reviewer tokens: pending
- Tokens per accepted finding: pending

The single final reviewer found four contract defects. K1A now proves every
retained release primitive is byte-identical to merged K1 and importable,
compares immutable disposition decisions and paths directly with the merged
K1 tree, checks physical keep/removal state independently of the Git index,
and enforces exact wheel/sdist member and dependency metadata. The retained
0.25 release tests remain byte-identical historical K10 inputs; they are
explicitly not collected on integration because they import quarantined
runtime and release-smoke helpers. Their applicable dependency-free primitive
contracts now run in the K1A kernel suite. No second review pass was run.

### K1A deviations and decisions

- Serena activation remains unavailable because its IDE broker points to a
  deleted local Agent Maintainer helper root. The K1A scope checker and exact
  Git path inventory are authoritative; the detached reference was not
  activated.
- GitNexus had indexed only older sibling worktrees. It was used to confirm the
  stale scope and was not refreshed from the reference. Integration indexing
  follows after K1A merge, as required by the quarantine design.
- Historical paths had no approved archive target, so all 179 were removed and
  remain accessible only through their manifest source refs and Git history.

### K1A residual risk and next task

- Retained K10 release primitives remain active but are not public-runtime
  entry points. Their 0.25 release suite remains intentionally excluded
  because it imports quarantined runtime and smoke helpers; K10 must port its
  applicable contracts and remove remaining dynamic 0.25 identity imports
  before release qualification.
- K2 must implement and verify only its owned transplant entries; all other
  removed paths remain forbidden.
- K2 is unblocked after K1A review, integration-targeting PR CI, and merge.

## Task Entry Template

Copy this section for each task and replace every placeholder.

```markdown
## KX — Title

**State:** In progress | Blocked | Complete
**Branch:** `kernel/kx-slug`
**Base:** `<sha>`
**Commits:** `<sha and subject>`

### Contract added first

- `<failing test, invariant, or benchmark>`

### Implementation

- `<owned modules and behavior>`

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass/Fail | `<command and summary>` |
| Broader | Pass/Fail | `<command and summary>` |
| Performance | Pass/Fail/N/A | `<before and after>` |
| Privacy | Pass/Fail | `synthetic fixtures; no private content` |

### Review metrics

- Total findings: `<n>`
- Accepted findings: `<n>`
- Reviewer tokens: `<n or pending>`
- Tokens per accepted finding: `<value, N/A, or pending>`

### Deviations and decisions

- `<none or approved change with owner/date>`

### Residual risk and next task

- `<remaining risk>`
- `<exact task unblocked>`
```
