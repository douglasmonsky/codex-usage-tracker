# Clean-Cutover Task Accounting

This file is the master completion ledger for the
[Agent-First Clean-Cutover Roadmap](AGENT_FIRST_CLEAN_CUTOVER.md). Detailed
scope, contracts, checks, acceptance criteria, and rollback instructions live
in the linked files under [`docs/roadmap/tasks/`](tasks/).

[REMAINING_EXECUTION_PLAN.md](REMAINING_EXECUTION_PLAN.md) controls readiness,
dependency waves, owner class, and allowed/forbidden parallelism. Parent CK-09
through CK-16 packets are accounting umbrellas and are never delegated
directly.

## Overall

- Completed packets: **13 / 22**
- In progress: **None**
- Not started: **9**
- Critical-path completion: **13 / 21**
- Optional packets: **CK-15**
- Completed corrective child tasks: **1 — CK-08R0**
- Remaining delegable child tasks: **41**
- Ready child tasks: **0**
- Conditional-ready child tasks: **5 — CK-08R1, CK-08R2, CK-08R3, CK-07R1, CK-QG1 after CK-08R0 exact-main verification**
- Blocked child tasks: **36**

A packet may be checked only after its acceptance criteria and required checks
pass, measurements and residual risks are recorded, and any required review is
resolved. Updating a checkbox also requires updating the packet's `Status`
line and the milestone accounting below.

Historical completion is preserved when a later consumer finds a semantic
mismatch. The corrective packet becomes a new dependency and must publish
linked requalification evidence for every affected prior packet. A digest,
formula-consistent oracle, or prior completion status cannot replace the
corrective packet's executable producer-to-consumer seam checks.

## Milestones

- [x] **M0 — Authority Ready** · 1 / 1 · CK-00 complete
- [x] **M1 — Architecture Selected** · 4 / 4 · CK-01–CK-04 complete
- [ ] **M2 — Kernel Alpha** · 9 / 10 · CK-05–CK-08, CK-07B–CK-07E, and
  CK-07A historically complete; CK-09 is blocked on corrective Waves 1–4
- [ ] **M3 — Codex MVP Qualified** · 0 / 3 · CK-10–CK-12 not started
- [ ] **M4 — Clean Cutover** · 0 / 2 · CK-13–CK-14 not started
- [ ] **M5 — Public Release** · 0 / 1 required · CK-16 not started
- [ ] **Optional enhancement** · 0 / 1 · CK-15 not started

## Packet checklist

### M0 — Authority Ready

- [x] **CK-00 — Clean authority and freeze the spike** · **Completed** ·
  depends on frozen `origin/main`
  · [packet](tasks/ck-00-clean-authority-and-freeze-spike.md)

### M1 — Architecture Selected

- [x] **CK-01 — Make the question catalog executable** · **Completed** ·
  depends on CK-00
  · [packet](tasks/ck-01-make-question-catalog-executable.md)
- [x] **CK-02 — Freeze logical contract vectors** · **Completed** ·
  depends on CK-01
  · [packet](tasks/ck-02-freeze-logical-contract-vectors.md)
- [x] **CK-03 — Build synthetic fixtures and oracles** · **Completed** ·
  depends on CK-02
  · [packet](tasks/ck-03-build-synthetic-fixtures-and-oracles.md)
- [x] **CK-04 — Run the physical-architecture bakeoff** · **Completed with an
  explicit growth-evidence exception** ·
  depends on CK-03
  · [packet](tasks/ck-04-run-physical-architecture-bakeoff.md)

### M2 — Kernel Alpha

- [x] **CK-05 — Implement the canonical storage kernel** · **Completed** ·
  depends on CK-04
  · [packet](tasks/ck-05-implement-canonical-storage-kernel.md)
- [x] **CK-06 — Implement the Codex adapter and ingestion** · **Completed** ·
  depends on CK-05
  · [packet](tasks/ck-06-implement-codex-adapter-and-ingestion.md)
- [x] **CK-07 — Implement publication, refresh, and recovery** · **Completed** ·
  depends on CK-06
  · [packet](tasks/ck-07-implement-publication-refresh-recovery.md)
- [x] **CK-07B — Freeze formula and provenance contract** · **Completed on
  merge via PR #383; exact-main verification is recorded in the completion
  handoff** ·
  corrective dependency discovered by CK-07A; depends on CK-07 and CK-07A
  blocker evidence
  · [packet](tasks/ck-07b-freeze-formula-and-provenance-contract.md)
- [x] **CK-07C — Freeze plan operands and missing canonical facts** ·
  **Completed on merge via PR #384; exact-main verification is recorded in
  the completion handoff** · corrective dependency discovered by CK-07A after CK-07B;
  depends on CK-07B and retained CK-07A blocker evidence
  · [packet](tasks/ck-07c-freeze-plan-operands-and-missing-facts.md)
- [x] **CK-07D — Implement effective-dated rate-card valuation** ·
  **Completed on merge via PR #385; exact-main verified at `e49531b`** · corrective dependency discovered
  after CK-07C; depends on merged CK-07C and retained CK-07A/CK-08 blocker
  evidence
  · [packet](tasks/ck-07d-implement-effective-dated-rate-card-valuation.md)
  · [gap evidence](../decisions/evidence/ck07d/effective-dated-valuation-gap.json)
  · [implementation evidence](../decisions/evidence/ck07d/effective-dated-valuation-implementation-evidence.json)
- [x] **CK-07E — Implement independent fact adapters** ·
  **Completed on merge; exact-main verification is recorded in the completion
  handoff** · prerequisite packet
  discovered after merged CK-07D; depends on CK-07B, CK-07C, CK-07D, and
  retained CK-07A/CK-08 blocker evidence
  · [packet](tasks/ck-07e-implement-independent-fact-adapters.md)
- [x] **CK-07A — Reconcile fact-backed oracles and qualify packet seams** ·
  **Completed; 80 / 80 fact-backed variants requalified** · depends on CK-07, the CK-08
  blocker evidence, CK-07B, CK-07C, CK-07D, and CK-07E
  · [packet](tasks/ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md)
- [x] **CK-08 — Implement query and evidence** · **Completed on merge; 21 plans
  and 42 variants passed, with 3 fact-table-sufficient and 18 measured
  projection-required classifications — CK-07A replaced the historical
  fact-backed oracle gap; the original
  [gap evidence](../decisions/evidence/ck08/fact-backed-oracle-prerequisite-gap.json)
  remains preserved** ·
  depends on CK-07A
  · [packet](tasks/ck-08-implement-query-and-evidence.md)
- [ ] **CK-09 — Admit projections and named plans** · Blocked; umbrella only ·
  depends on CK-08RG
  · [packet](tasks/ck-09-admit-projections-and-named-plans.md)

### M3 — Codex MVP Qualified

- [ ] **CK-10 — Deliver setup, MCP, CLI, and skill** · Not started ·
  depends on CK-09
  · [packet](tasks/ck-10-deliver-setup-mcp-cli-skill.md)
- [ ] **CK-11 — Build the installed-agent harness** · Not started ·
  depends on CK-10
  · [packet](tasks/ck-11-build-installed-agent-harness.md)
- [ ] **CK-12 — Qualify and harden the MVP** · Not started ·
  depends on CK-11
  · [packet](tasks/ck-12-qualify-and-harden-mvp.md)

### M4 — Clean Cutover

- [ ] **CK-13 — Execute the clean cutover** · Not started ·
  depends on CK-12
  · [packet](tasks/ck-13-execute-clean-cutover.md)
- [ ] **CK-14 — Delete the spike, Console, and obsolete surfaces** ·
  Not started · depends on CK-13
  · [packet](tasks/ck-14-delete-spike-console-obsolete-surfaces.md)

### M5 — Public Release

- [ ] **CK-16 — Publish documentation and release** · Not started ·
  depends on CK-14
  · [packet](tasks/ck-16-publish-docs-and-release.md)

### Optional enhancement

- [ ] **CK-15 — Add optional native presentation** · Not started ·
  depends on CK-14; does not block CK-16 unless explicitly selected
  · [packet](tasks/ck-15-add-optional-native-presentation.md)

## Remaining delegated child tasks

Readiness and parallelism are controlled by
[REMAINING_EXECUTION_PLAN.md](REMAINING_EXECUTION_PLAN.md). CK-08R0 is
complete on merge. Its five disjoint Wave-2 successors are Conditional Ready after
exact-main verification; every join and later child remains blocked on its
stated dependencies.

### Corrective gates

- [x] **CK-08R0 — Freeze corrective query and scale contracts** · Completed on merge; exact-main verification recorded in handoff · [packet](tasks/ck-08r0-freeze-corrective-contracts.md)
- [ ] **CK-08R1 — Build independent expected-answer truth** · Conditional Ready after CK-08R0 exact-main verification · [packet](tasks/ck-08r1-build-independent-answer-truth.md)
- [ ] **CK-08R2 — Implement bounded physical keyset execution** · Conditional Ready after CK-08R0 exact-main verification · [packet](tasks/ck-08r2-implement-physical-keyset-execution.md)
- [ ] **CK-08R3 — Qualify evidence service scale** · Conditional Ready after CK-08R0 exact-main verification · [packet](tasks/ck-08r3-qualify-evidence-scale.md)
- [ ] **CK-07R1 — Correct lifecycle preparation scale** · Conditional Ready after CK-08R0 exact-main verification · [packet](tasks/ck-07r1-correct-lifecycle-preparation-scale.md)
- [ ] **CK-QG1 — Enforce replacement-kernel maintainability** · Conditional Ready after CK-08R0 exact-main verification · [packet](tasks/ck-qg1-enforce-agent-kernel-maintainability.md)
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
