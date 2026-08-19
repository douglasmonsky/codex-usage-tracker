# CK-07R1 — Correct lifecycle preparation scale

**Status:** `blocked_hold` until the v1 consuming-boundary authority
squash-merges and exact-main verifies; then `ready_one_shot` for the bound
existing worker only, while implementation/runtime remain unaccepted

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `feature_worker lifecycle-scale`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Run authority:** The linked run-invocation authority remains immutable and
preserves the one-shot launch contract. The versioned
[consuming-boundary authority](../../decisions/evidence/ck07r1a0/lifecycle-consuming-boundary-authority-v1.json)
alone permits the bound existing worker to cross from exact
`worker_prequalification` to `launch_authorized_once` after authority merge and
exact-main verification.

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Replace repeated per-entity transition scans with equivalent
one-pass grouping and requalify publication-valid scale.

**Why:** The current lifecycle fold is quadratic and an existing
production-shaped preparation attempt exceeded 15 minutes.

**Controls:** Publication/recovery, lifecycle, canonical fact, and benchmark
contracts.

**Dependencies:** CK-07R1A accepted, merged, and exact-main verified at
`4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-07R1A0 path authority remains
historical; and the linked finite source/runtime authorities remain
`blocked_hold` with the one-run token unspent/unavailable. Accepted R3A
preparation `6689d61f…` remains a historical predecessor and accepted
R1B/current exact-main preparation `7d1831ff…` is the live predecessor. The
existing worker's fresh exact-main `6c08ecd9` reapplication derived the sole
candidate cohort: preparation `66c015de…`, benchmark `f108dbb4…`, and lifecycle
test `4c514889…`. Historical `d192c858…`, mixed or incomplete cohorts, and
every other digest fail closed. PR #394 head
`98a9b5b82951d136644a5fe5f8a70d320131ba08` is a stale failed
read-only witness and is not refreshed, rerun, or merged.

**Owned files/interfaces:** Lifecycle preparation implementation, focused
publication tests, profile/benchmark, and linked CK-07 evidence amendment;
the current authority binds predecessor preparation `7d1831ff…` to the atomic
`66c015de…` / `f108dbb4…` / `4c514889…` successor cohort, linked evidence
`36eb76ca…`, and the 720-second wrapper timeout without executing the worker.
The successor is permitted-not-accepted and launch remains unauthorized.
The versioned [shared successor overlay](../../decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json)
preserves all accepted CK-08R1B v1, CK-08R1 evidence, and CK-QG1 authority
bytes while allowing their consumers to recognize only this exact atomic
worker-prequalification state.

**Produces:** Publication-scale requalification with equivalent fold identity.

**Independent truth source:** Existing lifecycle-fold oracle and committed
database postconditions.

**Consumer seam:** Preparation to `PublicationWriter` to read-only publication.

**Parallelism:** Resume only existing worker
`019fbfe2-8fe4-7de2-9264-d58572366727` after the consuming-boundary authority
merges and exact-main verifies, using frozen cwd
`/Users/Monsky/Developer/Codex/2026-08-11/codex-usage-tracker-ck07r1-corrected-shared-overlay-exact-main-6c08ecd9`
and only the complete selected cohort. Historical
`d192c858…` cannot be reapplied directly.
Worker ownership is a normative coordinator/orchestration binding to that
exact existing Codex task plus recomputed repository evidence. It is not a
runtime-authenticated identity; the launcher must not accept or claim a
cryptographic or self-asserted per-task credential.
Never rebase, stash, reset, clean, delete, overwrite, or mutate the historical
V9/V10 witnesses. After the authority merge only, the separate frozen launch
lane must fetch and fast-forward only from prequalification base `67bb1a…` to
the exact merged main while preserving and recomputing the exact three dirty
candidate bytes. Any non-fast-forward transition or byte drift fails closed.
Do not create a replacement worker task. The planner-valid receipt is produced by that worker
and is required for acceptance, not for authority completion; other corrective
locks stay disjoint and no downstream packet becomes Ready here.

**Non-goals:** Writer/pointer/schema redesign, facts, projections, or budget
waivers.

**Invariants:** Same transition versions/folds; prior publication readable;
bounded RSS; synthetic data; no writer recovery regression.

**Required tests/checks:** Focused lifecycle/publication, equivalent results,
standard/production fixtures, five unprofiled samples, 30-day/all-time gates,
`just v/vc`; authority/schema/DAG/scope exact-record negative checks covering
the finite state transitions and real non-launching subprocess argv guard; no
E2E or benchmark run in the authority reconciliation.

**Acceptance:** Immediately before the one command, the worker must revalidate
the exact authority bytes and three-path Git delta, lexical worktree
`.venv/bin/python` plus matching `sys.prefix`, exact cwd/argv/environment,
capacity at or above 10 GiB, `matching_processes=[]`, all four frozen artifact
paths absent, the unconsumed token, and synthetic fixture identity. Any miss
fails closed without launch or artifact creation. If every gate passes, exactly
one successfully observed child PID/argv/cwd/owner/handshake consumes the
non-refundable token. No retry, restart, replacement, live/real data, or
fabricated receipt is permitted. The launcher-imported shared verifier enforces
the consuming authority before ledger/fork and requires candidate
`HEAD == refs/remotes/origin/main == live ls-remote origin/main`; the authority
feature branch and the stale `67bb1a…` HEAD cannot satisfy that activation.
The prequalification base must remain an ancestor of exact merged main. Work is linear in observations
plus prior transitions and all
publication-valid scale gates pass through the CK-07R1A0 reachable path and
the frozen CK-07R1A0 run-invocation contract. The existing worker must
revalidate the exact predecessor-to-successor digest
transition, bind every frozen path and prior identity, produce the
planner-valid receipt, and consume at most one new end-to-end run. The still-
unspent `maximum_new_end_to_end_runs=1` token can fund exactly one first
successful child launch only after the authority merge/exact-main gate and all
worker gates pass; this is not a retry, restart, or replacement of a launched
process. Receipt absence before dispatch is required; receipt absence or
invalidity at successor acceptance remains fail-closed.

The V11 candidate must construct and validate the fully overlay/cohort-bound
receipt and non-null stdout/stderr/output evidence before its first durable
`completed` finalization. Evidence read/hash/parse/validation/finalization
failure is terminal `failed_after_launch`, never false `completed`. Temporary
parent SIGINT/SIGTERM handlers route every wait interruption/error through
bounded TERM/KILL/reap before terminal persistence and remain installed
through evidence, receipt, and terminal ledger finalization; originals restore
only after the terminal-state attempt. Every terminal fallback persistence
call masks SIGINT/SIGTERM with the existing ignore guard and restores the prior
temporary handlers afterward; the outer final restoration of original
handlers remains last. The launch contract
requires the fork child to ignore SIGINT/SIGTERM while waiting for parent release and route
every pre-release failure to `os._exit(71)`; parent cleanup rejects nonpositive
PIDs. Unique same-directory `mkstemp` ledger updates close and unlink on every
failed or interrupted write/fsync/replace/post-replace path and retain durable
consumed/no-retry `failed_after_launch` evidence without temporary residue.
Interpreter identity requires the lexical repository-worktree
`.venv/bin/python` plus matching lexical venv
`sys.prefix`; base interpreters, symlink/resolved equivalence, wrong-worktree
venvs, and prefix mismatch are rejected before side effects.

**Failure/rollback:** Retain the profile and create one narrow follow-up for a
new dominant blocker; never weaken the gate.

**Handoff:** Evidence digest, profiles, retained first hosted failure, PR #394
CI, exact-main result, and CK-08R4 input.

**Cleanup/docs:** Supersede only affected CK-07/08 scale claims.

**Suggested commit:** `perf: linearize lifecycle preparation`
