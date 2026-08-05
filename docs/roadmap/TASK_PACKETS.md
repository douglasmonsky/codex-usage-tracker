# Clean-Cutover Task Accounting

Master ledger for the [roadmap](AGENT_FIRST_CLEAN_CUTOVER.md); linked
[task files](tasks/) own scope and acceptance. The
[machine DAG](REMAINING_EXECUTION_PLAN.md) controls delegation; CK-09–16
parents are accounting umbrellas.

## Overall

- Completed packets: **14 / 22**
- In progress: **None**
- Not started: **8**
- Critical-path completion: **14 / 21**
- Optional packets: **CK-15**
- Completed corrective child tasks: **9 — CK-08R0, CK-08R1A, CK-08R1C, CK-08R2, CK-08R3A, CK-QG1A0, CK-QG1A, CK-07R1A, CK-07R1A0**
- Remaining delegable child tasks: **41**
- Ready child tasks: **2 — CK-QG1, CK-08R3**
- Conditional-ready child tasks: **1 — CK-07R1 after coordinator disposition of the preserved prelaunch incident and a clean exact-main reapplication path**
- Blocked child tasks: **38**
- Orchestration mode: **convergence — one coordinator, one existing task per active packet, at most one shared-authority task**
- Continuation policy: **reuse the active packet task for ordinary corrections; create a task only for a newly Ready distinct packet or a genuinely new authority decision**
- Handoff policy: **tasks proactively message the parent; no polling or wait-only tasks**
- Identity policy: **exact-main plus repository-relative paths; receivers recompute digests before acting**

## Parent packets

- [x] **CK-00 — Clean authority and freeze the spike** · Completed · [packet](tasks/ck-00-clean-authority-and-freeze-spike.md)
- [x] **CK-01 — Make the question catalog executable** · Completed · [packet](tasks/ck-01-make-question-catalog-executable.md)
- [x] **CK-02 — Freeze logical contract vectors** · Completed · [packet](tasks/ck-02-freeze-logical-contract-vectors.md)
- [x] **CK-03 — Build synthetic fixtures and oracles** · Completed · [packet](tasks/ck-03-build-synthetic-fixtures-and-oracles.md)
- [x] **CK-04 — Run the physical-architecture bakeoff** · Completed with growth-evidence exception · [packet](tasks/ck-04-run-physical-architecture-bakeoff.md)
- [x] **CK-05 — Implement the canonical storage kernel** · Completed · [packet](tasks/ck-05-implement-canonical-storage-kernel.md)
- [x] **CK-06 — Implement the Codex adapter and ingestion** · Completed · [packet](tasks/ck-06-implement-codex-adapter-and-ingestion.md)
- [x] **CK-07 — Implement publication, refresh, and recovery** · Completed · [packet](tasks/ck-07-implement-publication-refresh-recovery.md)
- [x] **CK-07B — Freeze formula and provenance contract** · PR #383 merged/exact-main verified · [packet](tasks/ck-07b-freeze-formula-and-provenance-contract.md)
- [x] **CK-07C — Freeze plan operands and missing canonical facts** · PR #384 merged/exact-main verified · [packet](tasks/ck-07c-freeze-plan-operands-and-missing-facts.md)
- [x] **CK-07D — Implement effective-dated rate-card valuation** · PR #385 merged/exact-main `e49531b` · [packet](tasks/ck-07d-implement-effective-dated-rate-card-valuation.md)
- [x] **CK-07E — Implement independent fact adapters** · Merged/exact-main verified · [packet](tasks/ck-07e-implement-independent-fact-adapters.md)
- [x] **CK-07A — Reconcile fact-backed oracles and qualify packet seams** · 80/80 requalified · [packet](tasks/ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md)
- [x] **CK-08 — Implement query and evidence** · 21 plans/42 variants historical · [packet](tasks/ck-08-implement-query-and-evidence.md)
- [ ] **CK-09 — Admit projections and named plans** · Blocked umbrella on CK-08RG · [packet](tasks/ck-09-admit-projections-and-named-plans.md)
- [ ] **CK-10 — Deliver setup, MCP, CLI, and skill** · Blocked on CK-09 · [packet](tasks/ck-10-deliver-setup-mcp-cli-skill.md)
- [ ] **CK-11 — Build the installed-agent harness** · Blocked on CK-10 · [packet](tasks/ck-11-build-installed-agent-harness.md)
- [ ] **CK-12 — Qualify and harden the MVP** · Blocked on CK-11 · [packet](tasks/ck-12-qualify-and-harden-mvp.md)
- [ ] **CK-13 — Execute the clean cutover** · Blocked on CK-12 · [packet](tasks/ck-13-execute-clean-cutover.md)
- [ ] **CK-14 — Delete the spike, Console, and obsolete surfaces** · Blocked on CK-13 · [packet](tasks/ck-14-delete-spike-console-obsolete-surfaces.md)
- [ ] **CK-15 — Add optional native presentation** · Optional after CK-14 · [packet](tasks/ck-15-add-optional-native-presentation.md)
- [ ] **CK-16 — Publish documentation and release** · Blocked on CK-14 · [packet](tasks/ck-16-publish-docs-and-release.md)

## Remaining delegated child tasks

Readiness is controlled by
[the machine DAG](REMAINING_EXECUTION_PLAN.md). R1C is accepted after R1A;
R1B is held on shared query/evidence/grading integration and must reuse its
existing worker after an explicit join path. QG1A follows CK-QG1A0 exact-main;
other corrective locks are unchanged.

### Corrective gates

- [x] **CK-08R0 — Freeze corrective query and scale contracts** · Completed on merge; exact-main verification recorded in handoff · [packet](tasks/ck-08r0-freeze-corrective-contracts.md)
- [x] **CK-08R1A — Freeze answer semantics and evidence closure** · Completed on merge; exact-main verification required in handoff · [packet](tasks/ck-08r1a-freeze-answer-semantics.md)
- [ ] **CK-08R1B — Implement production answer semantics** · Blocked on shared query/evidence/grading integration; resume existing worker only · [packet](tasks/ck-08r1b-implement-production-answer-semantics.md)
- [x] **CK-08R1C — Build independent semantic evaluator** · PR #411 merged/exact-main `fb0c578`; independent closure and all 80 variants accepted · [packet](tasks/ck-08r1c-build-independent-semantic-evaluator.md)
- [ ] **CK-08R1 — Requalify independent answer truth** · Blocked on CK-08R1B; CK-08R1C is accepted · [packet](tasks/ck-08r1-build-independent-answer-truth.md)
- [x] **CK-08R2 — Implement bounded physical keyset execution** · Completed on merge; exact-main verification recorded in handoff · [packet](tasks/ck-08r2-implement-physical-keyset-execution.md)
- [x] **CK-QG1A0 — Authorize PageExecutor source supersession** · Completed on merge; exact-main required before CK-QG1A · [packet](tasks/ck-qg1a0-authorize-page-executor-source-supersession.md)
- [x] **CK-08R3A — Implement bounded EvidenceService physical queries** · PR #417 hosted-green and squash-merged at `38537f6c`; exact-main identities verified · [packet](tasks/ck-08r3a-implement-evidence-physical-query.md)
- [ ] **CK-08R3 — Qualify evidence service scale** · Ready after CK-08R3A accepted merge and exact-main verification · [packet](tasks/ck-08r3-qualify-evidence-scale.md)
- [x] **CK-07R1A — Correct hosted lifecycle tail** · Accepted/merged at `4d807495`; exact-main verified · [packet](tasks/ck-07r1a-correct-hosted-lifecycle-tail.md)
- [x] **CK-07R1A0 — Freeze lifecycle planner/recovery path authority** · Path, finite source/runtime, run-invocation authority, and argv-correction authority merged through `479cbdb`; retained witnesses remain read-only · [packet](tasks/ck-07r1a0-freeze-lifecycle-path-authority.md)
- [ ] **CK-07R1 — Correct lifecycle preparation scale** · Conditional Ready after argv authority merge `479cbdb`, coordinator disposition of the preserved `prelaunch_failed` witness incident, and a clean exact-main reapplication path; only the existing worker may resume and no launch is yet authorized; PR #394 is stale read-only · [packet](tasks/ck-07r1-correct-lifecycle-preparation-scale.md)
- [x] **CK-QG1A — Correct page-executor complexity** · PR #408 merged/exact-main `30983d4`; authorized successor `9e80c867…` accepted without behavior or baseline change · [packet](tasks/ck-qg1a-correct-page-executor-complexity.md)
- [ ] **CK-QG1 — Enforce replacement-kernel maintainability** · Ready to refresh existing PR #392 from corrected exact main with the frozen baseline unchanged · [packet](tasks/ck-qg1-enforce-agent-kernel-maintainability.md)
- [ ] **CK-08R4 — Reclassify physical named plans** · Blocked on CK-08R1/R2/R3 and CK-07R1 · [packet](tasks/ck-08r4-reclassify-physical-plans.md)
- [ ] **CK-08RG — Authorize CK-09 resumption** · Blocked on CK-08R4 and CK-QG1 · [packet](tasks/ck-08rg-authorize-ck09-resumption.md)

### CK-09 children

- [ ] **CK-09-01 — Freeze residual projection registry** · Blocked on CK-08RG · [packet](tasks/ck-09-01-freeze-residual-projection-registry.md)
- [ ] **CK-09-02 — Implement usage, time, hierarchy projections** · Blocked on admission · [packet](tasks/ck-09-02-implement-usage-time-hierarchy-projections.md)
- [ ] **CK-09-03 — Implement workflow and tool projections** · Blocked on admission · [packet](tasks/ck-09-03-implement-workflow-tool-projections.md)
- [ ] **CK-09-04 — Implement allowance and evidence projections** · Blocked on admission · [packet](tasks/ck-09-04-implement-allowance-evidence-projections.md)
- [ ] **CK-09-05 — Bind projection-backed named plans** · Blocked on family lanes · [packet](tasks/ck-09-05-bind-projection-backed-named-plans.md)
- [ ] **CK-09-06 — Integrate and qualify projections** · Blocked on CK-09-05 · [packet](tasks/ck-09-06-integrate-and-qualify-projections.md)

### CK-10 children

- [ ] **CK-10-01 — Freeze application and interface contracts** · Blocked on CK-09-06 · [packet](tasks/ck-10-01-freeze-application-interface-contracts.md)
- [ ] **CK-10-02 — Implement setup, refresh, status services** · Blocked on CK-10-01 · [packet](tasks/ck-10-02-implement-setup-refresh-status-services.md)
- [ ] **CK-10-03 — Implement CLI and MCP adapters** · Blocked on CK-10-02 · [packet](tasks/ck-10-03-implement-cli-and-mcp-adapters.md)
- [ ] **CK-10-04 — Build plugin and usage skill** · Blocked on CK-10-01 · [packet](tasks/ck-10-04-build-plugin-and-usage-skill.md)
- [ ] **CK-10-05 — Integrate installed surface** · Blocked on CK-10-02/03/04 · [packet](tasks/ck-10-05-integrate-installed-surface.md)

### CK-11 children

- [ ] **CK-11-01 — Freeze installed harness contract** · Blocked on CK-10-05 · [packet](tasks/ck-11-01-freeze-installed-harness-contract.md)
- [ ] **CK-11-02 — Build artifact and CLI trial runner** · Blocked on CK-11-01 · [packet](tasks/ck-11-02-build-artifact-and-cli-trial-runner.md)
- [ ] **CK-11-03 — Build Desktop lower-model trial runner** · Blocked on CK-11-01 · [packet](tasks/ck-11-03-build-desktop-lower-model-trial-runner.md)
- [ ] **CK-11-04 — Integrate installed-agent scorecard** · Blocked on CK-11-02/03 · [packet](tasks/ck-11-04-integrate-installed-agent-scorecard.md)

### CK-12 children

- [ ] **CK-12-01 — Freeze qualification candidate** · Blocked on CK-11-04 · [packet](tasks/ck-12-01-freeze-qualification-candidate.md)
- [ ] **CK-12-02 — Run correctness, query, evidence qualification** · Blocked on CK-12-01 · [packet](tasks/ck-12-02-run-correctness-query-evidence-qualification.md)
- [ ] **CK-12-03 — Run performance, storage, payload qualification** · Blocked on CK-12-01 · [packet](tasks/ck-12-03-run-performance-storage-payload-qualification.md)
- [ ] **CK-12-04 — Run concurrency, crash, recovery qualification** · Blocked on CK-12-01 · [packet](tasks/ck-12-04-run-concurrency-crash-recovery-qualification.md)
- [ ] **CK-12-05 — Run artifact and fresh-agent qualification** · Blocked on CK-12-01 · [packet](tasks/ck-12-05-run-artifact-agent-qualification.md)
- [ ] **CK-12-06 — Integrate hardening decision** · Blocked on all lanes · [packet](tasks/ck-12-06-integrate-hardening-decision.md)

### CK-13 through CK-16 children

- [ ] **CK-13-01 — Freeze cutover and rollback drill** · Blocked on CK-12-06 · [packet](tasks/ck-13-01-freeze-cutover-rollback-drill.md)
- [ ] **CK-13-02 — Switch public entry points** · Blocked on CK-13-01 · [packet](tasks/ck-13-02-switch-public-entry-points.md)
- [ ] **CK-13-03 — Verify cutover and approve retirement** · Blocked on CK-13-02 · [packet](tasks/ck-13-03-verify-cutover-approve-retirement.md)
- [ ] **CK-14-01 — Freeze retention and deletion manifest** · Blocked on CK-13-03 · [packet](tasks/ck-14-01-freeze-retention-deletion-manifest.md)
- [ ] **CK-14-02 — Delete spike runtime** · Blocked on CK-14-01 · [packet](tasks/ck-14-02-delete-spike-runtime.md)
- [ ] **CK-14-03 — Delete Console, frontend, Node** · Blocked on CK-14-01 · [packet](tasks/ck-14-03-delete-console-frontend-node.md)
- [ ] **CK-14-04 — Integrate package and CI cleanup** · Blocked on CK-14-02/03 · [packet](tasks/ck-14-04-integrate-package-ci-cleanup.md)
- [ ] **CK-15-01 — Decide native presentation admission** · Blocked on CK-14-04 · [packet](tasks/ck-15-01-decide-native-presentation-admission.md)
- [ ] **CK-15-02 — Implement and qualify native presentation** · Blocked unless selected · [packet](tasks/ck-15-02-implement-qualify-native-presentation.md)
- [ ] **CK-16-01 — Freeze release scope and version** · Blocked on CK-14-04 · [packet](tasks/ck-16-01-freeze-release-scope-version.md)
- [ ] **CK-16-02 — Write public docs and synthetic assets** · Blocked on CK-16-01 · [packet](tasks/ck-16-02-write-public-docs-synthetic-assets.md)
- [ ] **CK-16-03 — Build once and qualify release candidate** · Blocked on docs/selected optional work · [packet](tasks/ck-16-03-build-once-qualify-release-candidate.md)
- [ ] **CK-16-04 — Publish and verify public artifacts** · Blocked on CK-16-03 and approval · [packet](tasks/ck-16-04-publish-verify-public-artifacts.md)

## Critical path

`CK-00 → CK-01 → CK-02 → CK-03 → CK-04 → CK-05 → CK-06 → CK-07 → CK-07B
→ CK-07C → CK-07D → CK-07E → CK-07A → CK-08 → corrective Waves 1–4
→ CK-09 → CK-10 → CK-11 → CK-12 → CK-13 → CK-14 → CK-16`

CK-15 remains outside the critical path unless the maintainer explicitly
promotes it into the release.
