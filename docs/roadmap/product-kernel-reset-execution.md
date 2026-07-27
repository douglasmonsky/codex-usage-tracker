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
| K2 | 0.26.0 | Complete | K1A | Kernel schema v1 and stable identity |
| K3 | 0.26.0 | Complete | K2 | Incremental/live ingestion |
| K4 | 0.26.0 | Complete | K3 | Bounded query engine |
| K5 | 0.26.0 | CI fix pending | K3 | Evidence timeline and live stream |
| K6 | 0.26.0 | CI pending | K4, K5 | Six-tool integration interfaces |
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
| Verification wall time | 966.0 s | 57.3 s | 94.1% lower |
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

## K2 — Schema V1 And Stable Identity

**State:** Complete
**Branch:** `kernel/k2-schema-identity`
**Base:** `bb11bcbef30a37e5fefa483ec7f240cf4a79468a`
**Commits:** `629b612 feat: add kernel schema v1 and stable identities`;
integration merge `a32fbab8306f827c5d7e7161e1d6913f73e67452`

### K2 contract added first

- Five new contract files initially failed collection because the kernel
  schema, identity, database-lifecycle, cutover-control, and source-registry
  modules did not exist.
- A second contract-red run proved three primary-review findings before their
  fixes: reopened databases retained permissive modes, operational schema
  version drift was accepted, and failure codes were not actually bounded.

### K2 implementation

- Added the exact eight-table analytical schema:
  `sources`, `generations`, `threads`, `turns`, `model_calls`, `tool_calls`,
  `activity_events`, and `allowance_observations`, with 16 targeted indices
  under the 18-index budget.
- Added the exact three-table owner-only operational sidecar:
  `refresh_runs`, `source_registry`, and `cutover_control`. Full source paths,
  refresh leases/results, legacy-cache location, and activation state never
  enter analytical bytes.
- Chose the side-by-side filenames `codex-usage-kernel-v1.sqlite3` and
  `codex-usage-kernel-operational-v1.sqlite3`.
- Added stable namespaced IDs, canonical semantic fingerprints, bounded safe
  labels, atomic staging/install, read-only snapshots, short WAL writer
  transactions, integrity/version checks, 0600 permission repair, and explicit
  build/ready/active/failed cutover transitions.
- The K1 manifest had assigned 80 generic legacy paths to K2 despite the
  approved five-module design. Exact provenance review retained 16 relevant
  assignments as verified transplants, deferred two unproved
  cascade/deduplication lifecycle oracles to K3, and corrected 62 compression,
  diagnostics, dashboard, migration-chain, and other spike assignments to
  verified retirement. No legacy database is opened or migrated.

### K2 verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | 31 schema, identity, real-artifact cutover/rollback, permission, version, and privacy tests; Ruff, MyPy, Pyright, and Xenon/file-size budget pass |
| Broader | Pass | `just v`: 59 phase-owned tests, manifest/scope, static, release-safety, and privacy gates in 3.92 s |
| Package | Pass | package-only build plus `check_release.py --dist`; exact 10-module wheel, no CLI/MCP/plugin/runtime dependencies, and bounded fail-closed sdist |
| Privacy | Pass | synthetic fixtures only; full synthetic source path occurs only in the 0600 operational sidecar |
| Integration CI | Pass | Python 3.10 and 3.14 jobs in workflow run `30222635517`; PR #318 merged to integration |

The retained K1 oracle-adapter implementation tests are not collected in K2:
four deliberately import quarantined 0.25 runtime modules and are assigned to
the K3 ingestion replacement. A trial whole-directory run failed those exact
four adapters and passed the other 54 tests. K2 neither restored legacy code
nor converted those contracts to misleading skips.

### K2 development-efficiency comparison

| Metric | K1 | K1A | K2 final local | K2 vs K1 | K2 vs K1A |
| --- | ---: | ---: | ---: | ---: | ---: |
| Contract-red runs | 1 | 2 | 2 | 100.0% higher | unchanged |
| Focused verifier runs | 33 | 18 | 18 | 45.5% lower | unchanged |
| Broad verifier runs | 6 | 11 | 11 | 83.3% higher | unchanged |
| Blocking findings | 8 | 10 | 18 | 125.0% higher | 80.0% higher |
| Non-behavioral blocking groups | 6 | 5 | 10 | 66.7% higher | 100.0% higher |
| Gate-remediation lines | 74 | 60 | 230 | 210.8% higher | 283.3% higher |
| Verification wall time | 966.0 s | 57.3 s | 49.5 s | 94.9% lower | 13.6% lower |
| Style-only commits | 0 | 0 | 0 | unchanged | unchanged |
| Duplicate broad runs | 0 | 1 | 0 | unchanged | one lower |

K2 is substantially faster and eliminated duplicate broad verification, but it
did not reduce non-behavioral finding count or remediation volume. Two
Xenon-B findings caused most of the structural rewrite; the remaining churn
was invocation/configuration form, one Ruff form, one import form, one
over-broad test assertion, and the rejected whole-directory collection
experiment. This is a measured regression, not a claimed reduction. K3 must
use these figures to decide whether the absolute Xenon-B function ceiling
still has a favorable maintainability-to-churn ratio while preserving the
600-line bound, module budget, types, tests, privacy, and review.

### K2 review metrics

- Total findings: 6
- Accepted findings: 6 (`R1` through `R6`)
- Reviewer tokens: pending
- Tokens per accepted finding: pending

The sole reviewer found two high-, three medium-, and one low-severity defect.
All were accepted. K2 now binds readiness to the digest of one fully validated
artifact, activates only that artifact and a generation it contains, supports
validated atomic rollback, rejects schema drift on every normal connection
with bounded header/catalog checks, reserves full `quick_check` for lifecycle
boundaries, repairs operational permissions on every access, defers two
unproved lifecycle oracles to K3, and records every required churn metric. The
review-metrics helper was called once but reported no pending K2 attribution,
so token metrics remain pending without retry.

### K2 deviations and decisions

- The task design lists `refresh_runs` among cache tables while separately
  requiring jobs, leases, source paths, and cutover metadata to remain outside
  analytical facts. K2 resolves that tension by placing `refresh_runs` only in
  the operational sidecar.
- Serena activation remained unavailable after one guarded recovery because
  the IDE broker still resolved a deleted Agent Maintainer helper root.
  GitNexus and exact native searches were used without further broker retries.
- The 62 corrected manifest assignments remain available through immutable
  source refs. A later task may amend one explicitly only when its oracle
  demonstrates a current kernel need; generic spike ownership is not carried
  forward.

### K2 residual risk and next task

- K3 owns ingestion semantics, the two explicitly deferred cascade/deduplication
  oracles, and the four quarantined runtime adapters before collecting their
  implementation assertions.
- K2 is complete after integration-targeting CI and merge. K3 is unblocked
  from merge `a32fbab8306f827c5d7e7161e1d6913f73e67452`.

## K3 — Incremental And Live Ingestion

**State:** Complete

**Branch:** `kernel/k3-ingest-tail`

**Base:** `6145437bcc3c8943f5b8318bd5350617f111b441`

**Implementation commit:** `6d804be` (`feat: add incremental kernel ingestion`)

**Merged:** [PR #320](https://github.com/douglasmonsky/codex-usage-tracker/pull/320)
as `f5d988621f0cf3e130cf02ddc3a3681f9822be3d`

### Contract added first

- Contract-red run failed on the six absent K3 owners before implementation.
- Frozen source lifecycle, accounting, canonical-deduplication, parentage,
  allowance, parser-diagnostic, and privacy oracles now execute through the
  replacement kernel rather than quarantined runtime adapters.
- Added explicit no-change, append, partial-tail, moving-tail, replacement,
  truncation, archive move, process-crash, failed-promotion, stable-ID,
  two-process ownership, heartbeat, concurrent-generation, and 100,000-call
  writer-budget contracts.

### Implementation

- One discovery/parser/normalizer pipeline handles explicit hydration, refresh,
  watcher catch-up, and complete-line moving tails. Initial hydration streams
  at most 1,000 JSONL lines at a time into bounded writes and catches up new
  complete lines before promotion; it never retains the whole history.
- No-change performs no analytical write or generation bump. Ordinary appends
  and unique new sources reuse the active database. Replacement, truncation, or
  a proven active-versus-archive canonical conflict alone uses a validated
  side artifact, so normal refreshes do not copy or rebuild total history.
- Facts publish in 350-row bounded transactions behind a pending generation.
  The operational active generation keeps readers on the prior complete view
  until promotion. Partial-batch retries are idempotent.
- A distinct lease owner joins compatible work, rejects foreign live work,
  recovers stale ownership, renews long parsing from a host-side heartbeat,
  and fences every writer transaction and promotion.
- Source-local thread and allowance identities make replacement/truncation
  cascades exact even when active and archived files share a logical session.
  Pending generations never mutate already-visible thread or turn rows.
- Append promotion uses one bounded generation digest and one atomic sidecar
  cutover, avoiding repeated full-database hashing and integrity scans.
- The parser stores structural accounting only: four token classes, model and
  effort, thread/turn identity, tool/activity structure, and allowance
  observations. It never stores prompt text, reasoning, raw arguments, raw
  output, shell bodies, or full source paths.
- K3 resolved all 48 assigned legacy paths: 33 verified behavioral transplants
  and 15 verified retirements. Content-index refresh, worker-launch,
  observability, callbacks, server routes, and raw-log inspection were retired.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | Reviewer-remediation lifecycle, concurrency, reconciliation, privacy, oracle, and pipeline suites pass; final focused slice 23/23 |
| CI-equivalent | Pass | `just v`: 99 phase-owned tests in 20.08 s, Ruff, MyPy, Pyright 0 errors, complexity, manifests, scope, release safety, and diff checks pass |
| Performance | Pass | Final local 100,000-call run: 10.853 s, 503 bounded writer transactions, p95 33.407 ms against 50 ms budget; CI 3.10 drove removal of per-fingerprint work for collision-free initial hydration |
| Package | Pass | isolated 0.26.0.dev0 wheel and sdist pass exact release checks; isolated installed-wheel first-build plus no-change kernel smoke passed |
| Privacy | Pass | synthetic fixtures only; raw private sentinels and full source paths absent from analytical facts and oracle output |
| Integration CI | Pass | Python 3.10 in 51 s and Python 3.14 in 56 s on merge head `9fecb1e`; PR #320 squash-merged |

Agent-perf run `20260726T225506Z-ec362ecb` was incomplete because pinned
Scalene 2.3.0 on Python 3.14 exited without producing JSON. The identical
unprofiled workload is therefore the performance authority; no additional
profiler retries were started.

### Development-efficiency and churn

| Metric | K2 | K3 | Change |
| --- | ---: | ---: | ---: |
| Contract-red runs | 2 | 1 | 50.0% lower |
| Focused runs | 18 | 64 | 255.6% higher |
| Broad runs | 11 | 8 | 27.3% lower |
| Duplicate broad runs | 0 | 0 | unchanged |
| Blocking findings | 18 | 36 | 100.0% higher |
| Non-behavioral findings | 10 | 17 | 70.0% higher |
| Gate-remediation lines | 230 | 54 | 76.5% lower |
| Verification wall time | 49.5 s | 180.4 s | 264.4% higher |
| Style-only commits | 0 | 0 | unchanged |

K3 achieved the targeted reduction in meaningless edit volume and broad-gate
repetition, not a blanket reduction in every metric. Focused runs, findings,
and wall time rose because the single final review found ten substantive
correctness/performance issues and remediation added streaming, fencing,
catch-up, and recovery coverage. Despite that expansion, gate-only remediation
was 77.0% lower than K2, duplicate broad runs remained zero, and style-only
commits remained zero.

The closeout broad run initially found one further non-behavioral blocker:
preserved JetBrains `.idea/` state was untracked but not ignored, so the scope
gate treated it as product input. `.idea/` is now ignored without deleting or
mutating the user files; the subsequent full gate passed.

The Xenon absolute block ceiling remains C while module and average ceilings
remain B. The arbitrary 600-line file bound was retired after it demanded a
non-behavioral split of cohesive cutover and ingestion ownership. Repository
guidance now requires boundaries based on responsibility, dependency direction,
complexity, and testability instead of line count.

The change-plan file estimate was amended from 32 to 37. The final scope adds
the bounded digest owner and explicit repository guidance/policy coverage; the
4,899 changed lines remain below the 6,000-line budget.

### Review metrics

- Total findings: 10
- Accepted findings: 10
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Residual risk and next task

- Replacement/truncation intentionally pays for a side-artifact copy; ordinary
  no-change, append, and unique-source refreshes do not. K15 owns later
  fault/scale expansion beyond this K3 contract.
- The legacy installed-package smoke imports quarantined dashboard modules and
  is not applicable on integration. K3 instead qualified the built wheel in an
  isolated environment with synthetic first-build and no-change refreshes.
- K4 must resolve the active generation from the operational sidecar and bind
  every batch to that one generation; reads never infer readiness from
  `MAX(generation)`.
- K3 is merged into the non-publishable `kernel/0.26-integration` branch and
  unblocks K4.

## K4 — Bounded generation-consistent query engine

**State:** Complete
**Branch:** `kernel/k4-query-engine`
**Base:** `f7948ee824480e720e27111d2a8cf68dd1351cef`
**Commits:** `e4e0dba feat: add bounded kernel query engine`;
`b4e73e5 docs: close K4 local verification ledger`;
`ddfbd64 ci: isolate host-sensitive ingest benchmark`;
merged through PR #322 as
`a38bf4440ae04b34d9197628378f09c05fd2c060`

### Contract added first

- The first contract-red run failed collection because the kernel query package
  did not exist. A second red expansion required real non-overlapping period
  comparison, all seven datasets, exact scan counts, bounded phase scopes,
  stable selectors, opaque generation-bound cursors, and deterministic
  four-band phase token attribution.
- Requests accept only named datasets, operations, dimensions, measures,
  filters, ordering, limits, and comparison windows. Unsupported fields,
  aggregate shapes, cross-products, timelines, and unscoped phase scans fail
  before SQL execution.
- Every batch resolves the operational control once, opens one read-only
  analytical transaction, and binds every plan and cursor to that active
  generation. Query execution never starts refresh work or writes either
  database.

### Implementation

- `kernel.query.contracts` owns typed normalized requests, explicit half-open
  comparison windows, bounded batches and pages, opaque cursors, and
  adapter-independent results.
- `kernel.query.catalog` and `kernel.query.plans` own static SQL expressions and
  named version-1 plans for calls, turns, threads, tools, activities, phases,
  and allowance across rows, aggregate, share, comparison, distribution,
  time-series, and timeline operations. Filter values remain parameters.
- `kernel.query.service` returns normalized scope, generation, plan identity,
  exact matched/scanned/returned counts, truncation, cursor, elapsed time,
  grade/coverage metadata, and stable evidence selectors.
- The pure version-1 phase segmenter uses only privacy-safe turn, activity, and
  tool facts. It emits the approved phase vocabulary, basis, confidence,
  unknown fallback, and four token classes with explicitly deterministic
  attribution.
- K4 resolved all 18 frozen K4 disposition entries: 13 bounded behaviors were
  transplanted into the query owners and five legacy export/cache/derived
  summary paths were retired. No query cache was added because the measured
  plans meet budget.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | `pytest -q -s tests/kernel/query`: 25 passed; focused Ruff, Mypy, and maintainability checks clean |
| Broader | Pass | final `just v`: 126 passed; Ruff, Mypy, Pyright, Xenon, scope, manifests, and release checks clean in 26.29 s |
| Performance | Pass | final 100,000 synthetic calls: common p95 110.724 ms, comparison p95 135.543 ms, concentration p95 66.826 ms |
| Profiling | Pass | `agent-perf` run `20260727T005737Z-871485fd`, Scalene 2.3.0; `_execute_one` was the only ranked owned hotspot at 16.54 percent; attribution only |
| Package | Pass | exact wheel/sdist membership check and isolated no-dependency wheel import smoke |
| Privacy | Pass | synthetic fixtures only; query and phase facts contain no prompt, reasoning text, tool arguments/output, shell body, secret, or full source path |
| Integration CI | Pass | PR #322: Python 3.10 in 63 s; Python 3.14 with synthetic ingest performance and package isolation in 86 s |

The query timing assertion uses the identical unprofiled workload before the
profile capture. The contract budgets are 500 ms for common bounded queries
and 1 second for comparison/concentration.

### Review metrics

- Total findings: 6
- Accepted findings: 6 (`R1`–`R6`)
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Churn measurement

| Metric | K3 | K4 local | Change |
| --- | ---: | ---: | ---: |
| Contract-red runs | 1 | 2 | 100.0% higher |
| Focused runs | 64 | 25 | 60.9% lower |
| Broad runs | 8 | 8 | unchanged |
| Duplicate broad runs | 0 | 0 | unchanged |
| Blocking findings | 36 | 21 | 41.7% lower |
| Non-behavioral findings | 17 | 11 | 35.3% lower |
| Gate-remediation lines | 54 | 264 | 388.9% higher |
| Verification wall time | 180.4 s | 386.2 s | 114.1% higher |
| Style-only commits | 0 | 0 | unchanged |

K4 materially reduced focused-loop and finding counts while preserving all
maintained correctness gates; broad runs were unchanged. Total measured
verification wall time increased because final performance, package,
post-review, failed-CI, and corrected-CI qualification were all recorded.
Gate-remediation lines also increased because the new planner and validator
initially exceeded the Xenon complexity budget and were split into
responsibility-owned helpers; no arbitrary file-length or generic style gate
was restored.

Initial CI found one further non-behavioral blocker: the inherited K3 ingest
benchmark exceeded its 50 ms writer p95 threshold only on a shared Python 3.10
runner. The threshold remains unchanged and runs once in the Python 3.14
performance job; both interpreters still run all functional, typing, privacy,
scope, release, and K4 query contracts. Corrected CI passed in 63 and 86
seconds.

The one final reviewer found six substantive defects: truth grading for partial
measures, ambiguous shell phase classification, phase projection/order,
timezone-offset comparison, cursor/pagination determinism, and missing
oracle/plan/snapshot qualification. All six were accepted. The bounded fixes
also removed two redundant full scans from every non-empty SQL result.

### Deviations and decisions

- Estimated cost, credits, allowance burn rate, and observed usage per
  percentage point remain owned by K8 because schema-v1 does not yet contain
  the qualified inputs. K4 rejects those measures instead of inventing values.
- The warm status budget remains an adapter/status qualification owned by K6.
  K4 qualifies only the common, comparison, and concentration read plans.
- The repository has no profiling dependency. The exact pinned Scalene 2.3.0
  profiler ran from an isolated temporary environment, which was then moved to
  Trash; no project dependency or private data was added.

### Residual risk and next task

- K4 is merged into the non-publishable integration branch. K5 builds evidence
  timelines and the live event stream on its stable logical selectors and
  generation-consistent query service.

## K5 — Exact evidence timeline and live generation stream

**State:** Integration CI fix pending
**Branch:** `kernel/k5-evidence-live`
**Base:** `a38bf4440ae04b34d9197628378f09c05fd2c060`
**Commits:** `c45fa2c feat: add live kernel evidence timelines`; closeout
metadata in this changeset

### Contract added first

- The contract-red run failed collection because the kernel evidence and live
  packages did not exist. The completed contract covers thread, turn, call,
  tool, and allowance selectors; all six bounded evidence views; cursor and
  rebuild stability; read-only behavior; privacy; journal replay, retention,
  restart, concurrency, burst, disconnect, generation-gap, rollback, and
  snapshot fallback.
- Every evidence read resolves one active generation and opens one read
  snapshot. Logical IDs, rather than SQLite row IDs, drive selectors and stable
  relative destinations.
- The live contract publishes a fixed `generation_committed` event only after
  analytical promotion. Event IDs and publication identities are persistent;
  journal failure never invalidates a promoted analytical generation.

### Implementation

- `kernel.evidence` owns typed selectors, normalized bounded requests, opaque
  request- and generation-bound cursors, deterministic ordering, exact
  matched/scanned/returned counts, and privacy-safe summary, timeline, calls,
  tools, activities, and allowance pages.
- `kernel.live` owns the operational `live_events` journal, monotonic event
  allocation, bounded retention and replay, strict loopback-origin and
  `Last-Event-ID` validation, heartbeat and snapshot-required decisions, and
  deterministic server-sent-event frames.
- Ingestion accepts an optional journal seam and publishes numeric-only
  changed-source, inserted-call, inserted-tool, and deleted-row counters after
  promotion. Publication identity, not generation number alone, detects
  rollback or reused-generation divergence.
- K5 resolved its one frozen legacy disposition entry by transplanting the
  stable evidence responsibility into `kernel.evidence.service`; no legacy
  narrative analysis or content indexing returned.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | final evidence/live contracts: 42 tests; focused Ruff, Mypy, and maintainability checks clean |
| Broader | Pass | final pre-ledger `just v`: 141 passed; Ruff, Mypy, Pyright, Xenon, scope, manifests, and release checks clean in 37.63 s |
| Performance | Pass | 100,000 synthetic calls: 67.032 ms median and 68.387 ms p95 first-page latency, below the 500 ms budget |
| Profiling | Incomplete | `agent-perf` run `20260727T015044Z-fc265f11`, Scalene 2.3.0, exited zero but emitted no JSON profile; no hotspot claim |
| Package | Pass | wheel and sdist built; release-safety distribution check passed; isolated no-dependency wheel imports for `EvidenceService`, `GenerationJournal`, and `LiveStream` passed |
| Privacy | Pass | synthetic fixtures only; no live database, Codex log, prompt, reasoning, raw tool argument/output, shell body, secret, or full source path inspected or stored |
| Integration CI | Pass | PR #323 final corrected CI passed on Python 3.10 in 56 s and Python 3.14 in 79 s; squash merge `7d51a17acbd4a7648674ffa56c242a8a9b32eec3` |

The performance assertion uses the identical unprofiled synthetic workload.
Profiling is attribution-only and cannot replace that timing evidence.

### Review metrics

- Total findings: 5
- Accepted findings: 5 (`R1`–`R5`)
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Churn measurement

| Metric | K4 | K5 local | Change |
| --- | ---: | ---: | ---: |
| Contract-red runs | 2 | 2 | unchanged |
| Focused runs | 25 | 19 | 24.0% lower |
| Broad runs | 8 | 14 | 75.0% higher |
| Duplicate broad runs | 0 | 0 | unchanged |
| Blocking findings | 21 | 13 | 38.1% lower |
| Non-behavioral findings | 11 | 5 | 54.5% lower |
| Gate-remediation lines | 264 | 58 | 78.0% lower |
| Verification wall time | 386.2 s | 712.0 s | 84.4% higher |
| Style-only commits | 0 | 0 | unchanged |

K5 reduced focused runs, findings, and remediation lines against K4 while
preserving all behavioral, typing, privacy, scope, complexity, package,
release, and performance gates. Broad runs and total verification time
increased because initial CI, compatibility qualification, and corrected CI
are recorded separately. No duplicate broad run or style-only commit occurred.
The five non-behavioral findings were one future-schema test constant, two
focused Ruff forms, the Python 3.10 fixture selection, and inherited CI
performance-step wiring.

### Deviations and decisions

- Evidence destinations are stable relative `/evidence/...` paths. K6 owns the
  final adapter and HTTP prefix; K5 does not invent an integration surface.
- Call and tool selectors omit turn-wide activity unions because schema-v1
  cannot attribute every activity exactly to a call or tool. Broader
  attribution would be false precision.
- The journal deliberately exposes only `generation_committed` with
  numeric-only counters. Content events, prompts, reasoning, raw arguments,
  outputs, full paths, and server-authored narrative are outside K5.
- The change-plan file cap increased from 25 to 28 for the mandatory
  development-efficiency ledger and its policy test plus one CI regression
  test. The implementation inventory itself remained at 25 files and below the
  line budget.

### Residual risk and next task

- The Scalene capture did not emit a usable profile. The repeatable unprofiled
  100,000-call benchmark remains authoritative and passes with substantial
  headroom.
- K5 is complete. K6 may bind K4 queries and K5 evidence/live behavior to
  exactly the six approved integration interfaces without reintroducing
  narrative analysis.

## K6 — Six-tool kernel interface cutover

**State:** CI pending
**Branch:** `kernel/k6-interface-cutover`
**Base:** `7d51a17acbd4a7648674ffa56c242a8a9b32eec3`
**Commits:** pending

### Contract added first

- Exact six-tool MCP catalog, `/api/kernel/v1` route set, retained CLI command
  set, deterministic schemas/plugin bundle, and forbidden-name absence.
- Read paths stay generation-consistent and write-free. Refresh starts or
  joins one durable job, serializes the launch gap, and supports bounded
  host-side waiting.

### Implementation

- `kernel.application` composes status, refresh, batched query, evidence,
  allowance, live stream, and internally consistent job snapshots once for
  every adapter.
- `kernel.interfaces` provides direct stdio JSON-RPC, guarded loopback HTTP,
  and the operational CLI without compatibility profiles or narrative
  analysis.
- Generated schemas and plugin identity share one source of truth. K6 resolves
  all 40 frozen interface transplants and preserves every retired source path.

### Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Focused | Pass | interface/query/evidence/live contracts; Ruff, Mypy, and Pyright clean |
| Broader | Pass | final post-review `just v`: 172 passed in 35.31 s; scope, manifests, maintainability, privacy, and release checks clean |
| Performance | Pass | identical unprofiled synthetic adapter workload: status 0.514 ms p95, batched query 0.912 ms p95 |
| Profiling | Incomplete | `agent-perf` run `20260727T023958Z-652240e6` could not start because pinned Scalene 2.3.0 is absent; no hotspot claim |
| Package | Pass | exact wheel/sdist check; isolated no-dependency CLI and six-tool MCP handshake |
| Reference | Pass | public PyPI 0.25.1 retained installed-package smoke passed from the detached reference worktree |
| Privacy | Pass | synthetic fixtures only; no live database or local usage content inspected |

### Review metrics

- Total findings: 5
- Accepted findings: 5 (`R1`–`R5`)
- Reviewer tokens: pending
- Tokens per accepted finding: pending

### Churn measurement

K6 recorded one duplicate broad verifier because `just v` immediately reran an
already-green `just vp`. Four non-behavioral findings were limited to Ruff
import forms and namespace-package Mypy configuration; style-only commits
remain zero. The exact final counts live in
`config/kernel-development-efficiency-v1.json`.

### Deviations and decisions

- The HTTP prefix is frozen as `/api/kernel/v1`.
- The new skill is `skills/usage-kernel/SKILL.md`; the historical 0.25 skill
  paths remain absent under the K1 quarantine contract.
- The change-plan file budget increased from 38 to 55 after enumerating the
  complete generated schema, adapter, smoke, scope, and release inventory. K7
  console work is not included.

### Residual risk and next task

- Final read-only review is complete; integration CI is pending.
- K7 may consume only these frozen adapters and may not restore compatibility
  profiles, narrative analysis, or retired routes.

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
