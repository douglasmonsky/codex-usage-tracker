# Remaining Clean-Cutover Execution Plan

**Status:** Central execution authority for all remaining delegated work

This file controls readiness, ownership, and parallelism. The phase roadmap is
[AGENT_FIRST_CLEAN_CUTOVER.md](AGENT_FIRST_CLEAN_CUTOVER.md); completion is in
[TASK_PACKETS.md](TASK_PACKETS.md). Reconcile any conflict before delegation.

## Current decision

CK-09 remains blocked until CK-08R independently proves semantics, physical
paging, measurements, and scale. CK-08R0 freezes the exact contracts and
requalification frontier in `docs/decisions/evidence/ck08r0/corrective-gates-v1.json`.
Preserve CK-03–CK-08 history and supersede only its four named claims.
Retained CK-08R3 pre-scale evidence at commit
`a28e9cdbff8e48d334712a449fdcee111c725673` proves the EvidenceService outer
query physically unbounded independent of scale profile. CK-08R3A owns that
production fix. CK-08R3 must not become Ready or be redelegated until CK-08R3A
is accepted, merged, and exact-main verified. Retained CK-08R1 work reached
80/80 parity by copying unsupported Q-REV-03/Q-WF-02 semantics; R1A freezes
their meaning, R1B/C implement disjoint consumers, and R1 is their
requalification join. CK-QG1 PR #392 also stays blocked: R2 introduced two
page-executor C/B/B violations, so QG1A must correct them without changing R2
behavior or the frozen maintainability baseline.
CK-07R1A is accepted, merged, and exact-main verified at
`4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-07R1A0 is accepted at the
current exact main `519b503aa3b23019033b6481687c08b23fc6c31e`; its linked
source-digest and run-invocation authorities reconcile the no-run candidate
from exact main `bdf545127b9cda20d22e00e9e9abb74c9550a470` and are authority
documentation only. PR #394 is a stale failed witness: head
`98a9b5b82951d136644a5fe5f8a70d320131ba08` failed the hosted Python 3.14
`ordinary.2000_call_tail` gate and is superseded read-only. It must not be
updated, rerun, or merged. The planner-valid lifecycle receipt is an
acceptance output of the existing CK-07R1 worker only after it revalidates the
retained candidate on the source-digest and run-invocation authorities' exact
merged main; the run-invocation authority is not a pre-dispatch dependency.
The first sample, 720-second wrapper timeout, all five underlying budgets,
one-run ceiling, and every fail-closed rule remain binding. CK-07R1 is blocked
until both authorities are accepted, merged, and exact-main verified; after
that exact-main handoff only the existing worker may be resumed for its
required revalidation. Earlier wording that says to resume, refresh, or rerun PR #394 is
historical provenance and does not authorize action. This source-digest
authority supersedes earlier CK-07R1 wording that says to resume, refresh, or
rerun PR #394; those retained references are historical provenance and do not
authorize action.

## Delegation law

- Delegate only **Ready** child packets; CK-09–CK-16 parents are umbrellas.
- Sol/default owns freezes, integration, and gates; bounded post-freeze or
  immutable qualification lanes may use Luna. `architect` is read-only.
- Start at exact dependency-complete `origin/main`, one worktree/branch/PR.
- After verified merge, `create_thread` each newly Ready successor; fan out,
  hold joins, deduplicate packet/frontier, and report blocked/gated work.
- One integrator owns shared authority/schema/registry/publication/package/
  release/final evidence; parallel writes are disjoint.
- Producers name artifact, consumer seam, independent truth, and executable
  comparison. Disproved premises stop dependents and retain reproduction,
  digest, and measurements; never weaken gates or hide failed prototypes.
- Synthetic fixtures only; no real Codex bodies, secrets, or private/local
  databases. Task names use `<role> <short-scope>`.

## Shared-file integration locks

Only one integrator may own a lock at a time:

| Lock | Files or interfaces |
| --- | --- |
| Authority | `AGENTS.md`, `docs/INDEX.md`, roadmap, this plan, ledger, qualification plan, parent packets |
| Query physical | request/result contracts, query registry/compiler bindings, cursor version |
| Evidence physical | `EvidenceService` fixed page SQL, scope-to-branch selection, bound parameters, focused physical tests |
| Publication physical | analytical DDL, projection registry, writer/preparation integration ports |
| Installed surface | application envelope, MCP catalog, plugin manifest, `.mcp.json`, entry points |
| Qualification | candidate hashes, fixture identity, scorecard/evidence schemas, final aggregates |
| Cutover/release | package membership, CI, version fields, release workflow and artifact manifest |

## Parallel wave summary

The machine DAG below controls readiness and dependencies; each child packet controls its owner and scope. Only these fan-outs are allowed:

- CK-08R0 -> CK-08R2/CK-08R3A; CK-08R1A -> CK-08R1B/R1C
  -> CK-08R1; CK-08R2 -> CK-QG1A0 -> CK-QG1A -> CK-QG1;
  CK-08R3A -> CK-08R3;
  CK-07R1A -> CK-07R1A0 -> CK-07R1;
  join at CK-08R4/CK-08RG.
- CK-09-01 -> CK-09-02/03/04; join at CK-09-05.
- CK-10-01 -> CK-10-02 and CK-10-04; CK-10-03 follows 10-02; join at 10-05.
- CK-11-01 -> CK-11-02/03; join at CK-11-04.
- CK-12-01 -> CK-12-02/03/04/05; join at CK-12-06.
- CK-14-01 -> CK-14-02/03; join at CK-14-04. CK-15 is optional and CK-16 remains gated.

All other edges are serialized. `Ready` authorizes creation; `Conditional Ready` requires its machine gate; `Blocked` forbids creation and implementation.

## Machine-readable delegation DAG

Tests bind this manifest to the ledger, child files, statuses, known
dependencies, and acyclic order. Conditional policy gates such as optional
CK-15 selection and maintainer publication approval remain stricter prose
conditions in the table and child files; they are not unconditional DAG edges.

<!-- delegated-task-dag:start -->
```json
{
 "schema": "codex-usage-tracker.remaining-delegation-dag.v1",
 "orchestration": {
  "mode": "self-propagating",
  "spawn": "all_newly_ready_successors",
  "join": "all_dependencies_complete",
  "duplicate_policy": "one_active_task_per_packet_and_dependency_frontier",
  "blocked_policy": "spawn_none_and_report_to_orchestrator"
 },
  "completed": ["CK-08R0", "CK-08R2", "CK-QG1A0", "CK-07R1A", "CK-07R1A0"],
  "ready": [],
  "conditional_ready": [{
    "condition": "Each lane's serialized corrective authority correction accepted, merged, and exact-main verified",
    "tasks": ["CK-08R1A", "CK-08R3A"]
  }, {
    "condition": "CK-QG1A0 merged and exact-main verified",
    "tasks": ["CK-QG1A"]
  }],
  "blocked": ["CK-07R1"],
  "tasks": [
    {"id": "CK-08R0", "file": "tasks/ck-08r0-freeze-corrective-contracts.md", "dependencies": []},
    {"id": "CK-08R1A", "file": "tasks/ck-08r1a-freeze-answer-semantics.md", "dependencies": ["CK-08R0"]},
    {"id": "CK-08R1B", "file": "tasks/ck-08r1b-implement-production-answer-semantics.md", "dependencies": ["CK-08R1A"]},
    {"id": "CK-08R1C", "file": "tasks/ck-08r1c-build-independent-semantic-evaluator.md", "dependencies": ["CK-08R1A"]},
    {"id": "CK-08R1", "file": "tasks/ck-08r1-build-independent-answer-truth.md", "dependencies": ["CK-08R1B", "CK-08R1C"]},
    {"id": "CK-08R2", "file": "tasks/ck-08r2-implement-physical-keyset-execution.md", "dependencies": ["CK-08R0"]},
    {"id": "CK-08R3A", "file": "tasks/ck-08r3a-implement-evidence-physical-query.md", "dependencies": ["CK-08R0"]},
    {"id": "CK-08R3", "file": "tasks/ck-08r3-qualify-evidence-scale.md", "dependencies": ["CK-08R3A"]},
    {"id": "CK-07R1A", "file": "tasks/ck-07r1a-correct-hosted-lifecycle-tail.md", "dependencies": ["CK-08R0"]},
    {"id": "CK-07R1A0", "file": "tasks/ck-07r1a0-freeze-lifecycle-path-authority.md", "dependencies": ["CK-QG1A0", "CK-07R1A"]},
    {"id": "CK-07R1", "file": "tasks/ck-07r1-correct-lifecycle-preparation-scale.md", "dependencies": ["CK-07R1A0"]},
    {"id": "CK-QG1A0", "file": "tasks/ck-qg1a0-authorize-page-executor-source-supersession.md", "dependencies": ["CK-08R2"]},
    {"id": "CK-QG1A", "file": "tasks/ck-qg1a-correct-page-executor-complexity.md", "dependencies": ["CK-QG1A0"]},
    {"id": "CK-QG1", "file": "tasks/ck-qg1-enforce-agent-kernel-maintainability.md", "dependencies": ["CK-QG1A"]},
    {"id": "CK-08R4", "file": "tasks/ck-08r4-reclassify-physical-plans.md", "dependencies": ["CK-08R1", "CK-08R2", "CK-08R3", "CK-07R1"]},
    {"id": "CK-08RG", "file": "tasks/ck-08rg-authorize-ck09-resumption.md", "dependencies": ["CK-08R4", "CK-QG1"]},
    {"id": "CK-09-01", "file": "tasks/ck-09-01-freeze-residual-projection-registry.md", "dependencies": ["CK-08RG"]},
    {"id": "CK-09-02", "file": "tasks/ck-09-02-implement-usage-time-hierarchy-projections.md", "dependencies": ["CK-09-01"]},
    {"id": "CK-09-03", "file": "tasks/ck-09-03-implement-workflow-tool-projections.md", "dependencies": ["CK-09-01"]},
    {"id": "CK-09-04", "file": "tasks/ck-09-04-implement-allowance-evidence-projections.md", "dependencies": ["CK-09-01"]},
    {"id": "CK-09-05", "file": "tasks/ck-09-05-bind-projection-backed-named-plans.md", "dependencies": ["CK-09-02", "CK-09-03", "CK-09-04"]},
    {"id": "CK-09-06", "file": "tasks/ck-09-06-integrate-and-qualify-projections.md", "dependencies": ["CK-09-05"]},
    {"id": "CK-10-01", "file": "tasks/ck-10-01-freeze-application-interface-contracts.md", "dependencies": ["CK-09-06"]},
    {"id": "CK-10-02", "file": "tasks/ck-10-02-implement-setup-refresh-status-services.md", "dependencies": ["CK-10-01"]},
    {"id": "CK-10-03", "file": "tasks/ck-10-03-implement-cli-and-mcp-adapters.md", "dependencies": ["CK-10-02"]},
    {"id": "CK-10-04", "file": "tasks/ck-10-04-build-plugin-and-usage-skill.md", "dependencies": ["CK-10-01"]},
    {"id": "CK-10-05", "file": "tasks/ck-10-05-integrate-installed-surface.md", "dependencies": ["CK-10-02", "CK-10-03", "CK-10-04"]},
    {"id": "CK-11-01", "file": "tasks/ck-11-01-freeze-installed-harness-contract.md", "dependencies": ["CK-10-05"]},
    {"id": "CK-11-02", "file": "tasks/ck-11-02-build-artifact-and-cli-trial-runner.md", "dependencies": ["CK-11-01"]},
    {"id": "CK-11-03", "file": "tasks/ck-11-03-build-desktop-lower-model-trial-runner.md", "dependencies": ["CK-11-01"]},
    {"id": "CK-11-04", "file": "tasks/ck-11-04-integrate-installed-agent-scorecard.md", "dependencies": ["CK-11-02", "CK-11-03"]},
    {"id": "CK-12-01", "file": "tasks/ck-12-01-freeze-qualification-candidate.md", "dependencies": ["CK-11-04"]},
    {"id": "CK-12-02", "file": "tasks/ck-12-02-run-correctness-query-evidence-qualification.md", "dependencies": ["CK-12-01"]},
    {"id": "CK-12-03", "file": "tasks/ck-12-03-run-performance-storage-payload-qualification.md", "dependencies": ["CK-12-01"]},
    {"id": "CK-12-04", "file": "tasks/ck-12-04-run-concurrency-crash-recovery-qualification.md", "dependencies": ["CK-12-01"]},
    {"id": "CK-12-05", "file": "tasks/ck-12-05-run-artifact-agent-qualification.md", "dependencies": ["CK-12-01"]},
    {"id": "CK-12-06", "file": "tasks/ck-12-06-integrate-hardening-decision.md", "dependencies": ["CK-12-02", "CK-12-03", "CK-12-04", "CK-12-05"]},
    {"id": "CK-13-01", "file": "tasks/ck-13-01-freeze-cutover-rollback-drill.md", "dependencies": ["CK-12-06"]},
    {"id": "CK-13-02", "file": "tasks/ck-13-02-switch-public-entry-points.md", "dependencies": ["CK-13-01"]},
    {"id": "CK-13-03", "file": "tasks/ck-13-03-verify-cutover-approve-retirement.md", "dependencies": ["CK-13-02"]},
    {"id": "CK-14-01", "file": "tasks/ck-14-01-freeze-retention-deletion-manifest.md", "dependencies": ["CK-13-03"]},
    {"id": "CK-14-02", "file": "tasks/ck-14-02-delete-spike-runtime.md", "dependencies": ["CK-14-01"]},
    {"id": "CK-14-03", "file": "tasks/ck-14-03-delete-console-frontend-node.md", "dependencies": ["CK-14-01"]},
    {"id": "CK-14-04", "file": "tasks/ck-14-04-integrate-package-ci-cleanup.md", "dependencies": ["CK-14-02", "CK-14-03"]},
    {"id": "CK-15-01", "file": "tasks/ck-15-01-decide-native-presentation-admission.md", "dependencies": ["CK-14-04"]},
    {"id": "CK-15-02", "file": "tasks/ck-15-02-implement-qualify-native-presentation.md", "dependencies": ["CK-15-01"]},
    {"id": "CK-16-01", "file": "tasks/ck-16-01-freeze-release-scope-version.md", "dependencies": ["CK-14-04"]},
    {"id": "CK-16-02", "file": "tasks/ck-16-02-write-public-docs-synthetic-assets.md", "dependencies": ["CK-16-01"]},
    {"id": "CK-16-03", "file": "tasks/ck-16-03-build-once-qualify-release-candidate.md", "dependencies": ["CK-16-02"]},
    {"id": "CK-16-04", "file": "tasks/ck-16-04-publish-verify-public-artifacts.md", "dependencies": ["CK-16-03"]}
  ]
}
```
<!-- delegated-task-dag:end -->

If CK-09-01 admits no projection in a family, that family task closes as
`Not needed` with evidence and no production diff. If CK-15-01 defers native
presentation, CK-15-02 closes the same way and does not block CK-16.

## Phase completion gates

- CK-09 becomes ready only through CK-08RG. No fixed projection count is
  authoritative before CK-08R4.
- CK-10 starts only after CK-09-06 is merged, hosted CI is green, and exact
  `main` is verified.
- CK-11 starts only from the coherent CK-10 wheel/plugin/skill candidate.
- CK-12 lanes consume one immutable candidate and fixture digest. A semantic
  fix invalidates the affected lanes and creates a bounded follow-up; no lane
  edits the candidate while other lanes measure it.
- CK-13 starts only after CK-12 accepts every hard gate.
- CK-14 deletion starts only after CK-13 proves reinstall/rollback and the
  maintainer approves runtime retirement.
- CK-15 is optional. It blocks release only when CK-15-01 explicitly selects
  it into the release candidate.
- CK-16-04 is an approval-gated public action. No task may publish from a local
  rebuild or mutate already published bytes.

## Handoff minimum

Record exact SHA, PR/CI, ownership, artifact/digest, consumer/truth, validation/
first noise, reviewer/risks, orchestrator ID, and Ready/created task/host IDs
with frontier. Receivers verify authority first.
