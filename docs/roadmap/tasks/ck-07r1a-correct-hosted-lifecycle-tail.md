# CK-07R1A — Correct hosted lifecycle tail

**Release-candidate package ceilings:** sdist remains at most 2,000,000 bytes;
wheel remains at most 1,000,000 bytes.

**Status:** Completed on merge; exact-main verified at `4d8074952f679877f2b4fbb3e89c51015e96a197`

**Parent:** Corrective prerequisite for CK-07R1

**Recommended owner:** `worker lifecycle-tail`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Diagnose and materially correct the hosted Python 3.14 Candidate A
`ordinary.2000_call_tail` failure from run `30685780055`.

**Dependencies:** CK-08R0 and this authority correction accepted, merged, exact-main verified.

**Owned files/interfaces:** Only the attributable Candidate A ordinary-tail
implementation or exact CI/profile wiring and focused tests; no budget,
publication semantics, R1/R3/QG1, shared authority, or PR #394 evidence edits.

**Produces:** Controlled attribution and a material code/wiring correction
before one exact hosted profile rerun.

**Independent truth source:** Frozen lifecycle oracle/postconditions, exact
synthetic profile, first hosted failure, and controlled identical-workload
measurements separating code bottleneck from runner/CI wiring.

**Consumer seam:** Existing CK-07R1 worker refreshes PR #394 from corrected
exact main and reruns all required CI; CK-07R1 remains the acceptance owner.

**Parallelism:** Disjoint from R1A/B/C, R3A, and QG1A.

**Non-goals:** Unchanged-state retry, waiver, threshold increase, hidden first
sample, fixture/profile change, unrelated optimization/refactor, R4/RG/09.

**Invariants:** Preserve budgets (ms) standard/all-time/no-change/call-tail/
tool-tail = `5000/120000/100/500/500`, lifecycle folds, publication/recovery,
synthetic-only data, first failure, PR #394, and evidence digest
`67d0d91c70be7aa997d4d2257bc095ce75cd0de7373573bfdf1c081ea1dd7fe9`.

**Required tests/checks:** Reproduce/attribute the exact Python 3.14 path with
controlled evidence; prove a material correction before rerun; focused
lifecycle/publication and all five unchanged budgets; `just v`; `just vc`;
hosted CI.

**Acceptance:** Attributable cause and correction are recorded; the exact
profile passes without waiver/profile/budget change; semantics and first sample
remain visible.

**Failure/rollback:** Retain cause/first sample and keep CK-07R1/R4/RG/09 blocked.

**Handoff:** SHA, before/after controlled evidence, correction, budgets,
checks/CI/review/exact-main; notify worker
`019fbb41-804b-7fe2-8987-3d2b9e94a4d5` to refresh retained head
`98a9b5b82951d136644a5fe5f8a70d320131ba08` on PR #394.

**Cleanup/docs:** CK-07R1 owns requalification evidence and acceptance.

**Suggested commit:** `perf: correct hosted lifecycle tail`
