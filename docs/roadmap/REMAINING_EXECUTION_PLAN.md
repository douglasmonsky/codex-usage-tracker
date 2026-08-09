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
`a28e9cdbff8e48d334712a449fdcee111c725673` proved the EvidenceService outer
query physically unbounded independent of scale profile. CK-08R3A corrected
that production path in PR #417, passed hosted Python 3.10/3.14 and Console,
and was squash-merged and exact-main identity verified at
`38537f6cee42ad4ba2fb6e45354e410053c7a7cd`. The same premerge tree passed
focused, dual-SQLite, full, package, safety, and review gates. A duplicate
postmerge full runtime rerun did not complete because the host exhausted disk
space and SQLite could not create temporary files; no product assertion
failed, and this environment-only limitation does not override the exact-tree
and hosted acceptance evidence. CK-08R3 then qualified the separate
synthetic 100,000-call and 1,316,864-call profiles with `first_failure=null`,
all 196 selector/view/direction outcomes per profile, typed seven-part truth,
late-event, truncation, cursor, and query-only contracts. PR #425 passed hosted
Python 3.10/3.14 and Console, squash-merged at
`0fad272b3205614fb254398c9c9dc0a56d5ba7cd`, and was exact-main verified.
CK-08R3 is complete; CK-08R4 remains blocked on CK-08R1 and CK-07R1.
Retained CK-08R1 work reached
80/80 parity by copying unsupported Q-REV-03/Q-WF-02 semantics; R1A now freezes
their meaning and closure. R1C is accepted at exact main
`fb0c57886097a6b985d2f321b2de858cbdfc0a97`; the exact
[R1B join authority](../decisions/evidence/ck08r1b/answer-semantics-join-authority.json)
binds the shared query/evidence/grading seams accepted through PR #430;
CK-08R1B then passed the exact 23-path cohort,
80/80 production-versus-independent replay, full local/package gates, one
bounded review, and hosted Python 3.10/3.14 plus Console checks in PR #430;
it squash-merged and was exact-main verified at
`9e9332b3ae2be78cedb581ff8f76149ad76f4440`. CK-08R1 requalified all 80
synthetic variants through separate production and independent closures with
exact rows, grades, order, evidence, provenance, null semantics, grading
isolation, and sentinel mutations. Its schema-valid
[`answer-truth-requalification.v2`](../decisions/evidence/ck08r1/answer-truth-requalification-v2.json)
is complete on merge; hosted CI, squash merge, and exact-main verification
remain acceptance handoff requirements. The R1B exact reviewer correction
binds production
publication hierarchy ownership, independent start/terminal window membership,
duplicate stable-ID rejection, production-compiler replay, and the Q-REV-03
direct-fact/internal-formula decision. Its exact selected-cohort acceptance
correction additionally requires all authoritative late relationships before
one hierarchy computation and explicit non-null required tool timestamps.
The final writer-closure correction extends that atomic cohort to 23 paths:
writer-owned prior-state loading supplies every connected existing ancestor and
descendant, preparation emits every changed descendant after reparenting, and
unaffected session rows remain exact. The final multi-publication correction
retains those 23 paths and binds the remaining closure seam:
`SessionObserved` native parents seed their exact semantic parent component,
and persisted/incoming late-parent relations compare event/source coordinates
so stale replay cannot reverse a newer reparent. Exact replay is idempotent;
conflicting equal-order parent or basis declarations fail closed. The selected
cohort now also seeds an existing directly reparented session so its complete
persisted descendants are recomputed, requires parent/basis/occurrence
provenance equality for equal-coordinate idempotency, and resolves
current-batch relations by the six-part authority order before logical
identity with one emitted winner. PR #430 passed hosted CI, squash-merged, and
was exact-main verified at `9e9332b3ae2be78cedb581ff8f76149ad76f4440`.
R1B is complete. R1 is complete on merge with its independent two-lane
requalification artifact; no successor becomes Ready while CK-07R1 remains
conditional.
CK-QG1A removed R2's two page-executor C/B/B violations
without changing behavior or the frozen maintainability baseline and is
accepted at exact main `30983d4b5005e7e2a507757c76a3c05ab56281e6`.
The linked [CK-QG1 exact maintainability baseline transition authority](../decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json)
permitted only the exact accepted-main writer provenance finding transition.
PR #392 then passed exact normalized baseline enforcement, full validation,
review, and hosted Console/Python 3.10/3.14 before squash merge and fresh
exact-main verification at `68050b9313ccc5be8e1fcd0ccd5b95cb4173f3ff`.
CK-QG1 is complete; its v2 [writer transition authority](../decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json)
binds current main `dd771073` writer `13da341f…` to reviewed PR #430 writer
`d163e6c5…` with the unchanged `fda777e2…` baseline and identical normalized
findings. CK-08R1B is accepted at `9e9332b3`; CK-08R1's serialized
production-versus-independent answer-truth requalification is complete on
merge. CK-08R4 remains blocked on CK-07R1, and CK-08RG remains blocked on
CK-08R4.
CK-07R1A is accepted, merged, and exact-main verified at
`4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-07R1A0 was accepted at
`519b503aa3b23019033b6481687c08b23fc6c31e`; its linked
path authority remains preserved read-only. The finite source/runtime,
run-invocation authority, and argv-correction authority are merged through
`479cbdbfdd39604fc90eb94777ea0270474adde2`. PR #394 is a stale failed witness: head
`98a9b5b82951d136644a5fe5f8a70d320131ba08` failed the hosted Python 3.14
`ordinary.2000_call_tail` gate and is superseded read-only. It must not be
updated, rerun, or merged. The planner-valid lifecycle receipt is an
acceptance output of the existing CK-07R1 worker only after the coordinator
records the preserved prelaunch-incident disposition and the worker
revalidates the candidate from a clean exact-main worktree. The accepted
authorities do not authorize a launch by themselves.
The old frozen-command attempt is preserved exactly as a terminal
`pre_child_argv_guard_failure` (exit 2 after `0.075241709` seconds, no child or
runtime evidence), and its old benchmark/test identities cannot be reused.
Only `(sys.argv[0], *sys.argv[1:]) == LAUNCH_COMMAND[1:]` is authoritative.
The argv-correction authority is accepted and merged at
`479cbdbfdd39604fc90eb94777ea0270474adde2`. During its local proof, an
instrumentation mistake invoked the corrected candidate from the retained V5
witness and stopped at the child-handshake boundary. It produced only the
preserved `prelaunch_failed` launch-token ledger, with
`token_consumed=false`, no successful child/PID/receipt/runtime evidence, and
no retry. The witness remains read-only. CK-07R1 stays Conditional Ready until
the coordinator records an incident disposition and a clean exact-main
reapplication path; the incident does not authorize a launch or a replacement
worker.
The first sample, 720-second wrapper timeout, all five underlying budgets,
one-run ceiling, and every fail-closed rule remain binding. CK-07R1 is
Conditional Ready pending the incident disposition and clean exact-main
reapplication path; until then its current authority state is `authority_main`
and no worker may resume. After that handoff only the existing stopped worker
may be resumed for required revalidation of the corrected exact candidate. The
worker may enter
`worker_prequalification` only with the exact selected successor,
`post_single_run` only with a complete planner-valid receipt and bound dynamic
evidence identity, and `final_accepted` only after worker merge and exact-main
verification. The still-unspent one-run token may fund exactly one first
successful child launch after all gates pass; this is not a retry, restart, or
replacement of a launched process. Earlier wording that says to resume, refresh, or rerun PR #394 is
historical provenance and does not authorize action. This source-digest
authority supersedes earlier CK-07R1 wording that says to resume, refresh, or
rerun PR #394; those retained references are historical provenance and do not
authorize action.

## Delegation law

- Delegate only **Ready** child packets; CK-09–CK-16 parents are umbrellas.
- Use one durable coordinator, one existing task per active packet, and at most
  one shared-authority task. Sol at medium reasoning owns readiness,
  integration, collision handling, and gates; bounded deterministic workers
  normally use the less costly Luna profile at max reasoning. `architect` is
  read-only.
- Start at exact dependency-complete `origin/main`, one worktree/branch/PR.
- After verified merge, create only uncreated newly Ready distinct packets.
  Reuse the existing packet task for implementation defects, tests,
  environment setup, validation corrections, review findings, and exact-main
  reapplication. A new authority task requires a genuinely new policy or
  contract decision.
- Every task proactively messages its parent on completion, blocking, or a
  fail-closed stop. The handoff triggers continuation; do not create polling or
  wait-only tasks.
- Exact-main plus repository-relative artifact paths are authoritative.
  Receivers recompute digests and exact commands from committed manifests
  instead of trusting multi-hop prompt transcription.
- Before a one-shot or irreversible operation, prove the exact entry point and
  process boundary with a real non-consuming integration preflight. Stubbed or
  in-process tests alone are insufficient.
- Use bounded subagents inside the active task for focused read-only research,
  tests, or one independent review. Durable tasks represent independent
  ownership, not every intermediate correction.
- Classify blockers as implementation, authority, environment, or external.
  Once crash integrity is restored, leave recovery mode and return to this
  convergence topology.
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
  "mode": "self-propagating-convergence",
  "spawn": "newly_ready_distinct_packets_only",
  "join": "all_dependencies_complete",
  "duplicate_policy": "one_active_task_per_packet_and_dependency_frontier",
  "continuation_policy": "reuse_existing_task_for_same_packet",
  "authority_policy": "new_task_only_for_new_policy_or_contract_decision",
  "handoff_policy": "proactive_parent_handoff_from_repository_verified_state",
  "identity_policy": "exact_main_and_repository_paths_receiver_recomputes_digests",
  "one_shot_policy": "real_non_consuming_preflight_before_authorized_attempt",
  "recovery_exit_policy": "return_to_convergence_after_integrity_restored",
  "blocked_policy": "spawn_none_and_report_to_orchestrator"
 },
  "completed": ["CK-08R0", "CK-08R1A", "CK-08R1B", "CK-08R1C", "CK-08R1", "CK-08R2", "CK-08R3A", "CK-08R3", "CK-QG1A0", "CK-QG1A", "CK-QG1", "CK-07R1A", "CK-07R1A0"],
  "ready": [],
  "conditional_ready": [{
    "condition": "ARGV authority accepted at 479cbdb; coordinator records the preserved prelaunch incident disposition and a clean exact-main reapplication path; resume only existing worker 019fbfe2-8fe4-7de2-9264-d58572366727; no replacement, launch, or downstream task",
    "tasks": ["CK-07R1"]
  }],
  "blocked": [],
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
