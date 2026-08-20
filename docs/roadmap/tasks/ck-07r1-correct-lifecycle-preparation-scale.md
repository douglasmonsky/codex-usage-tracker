# CK-07R1 — Correct lifecycle preparation scale

**Status:** `terminal_failed_no_rerun` after the sole v2 child launch consumed
the non-refundable token and durably recorded `failed_after_launch`; only
deterministic non-consuming corrective implementation prequalification remains,
while runtime acceptance and downstream readiness are unavailable

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `feature_worker lifecycle-scale`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Run authority:** The linked run-invocation authority remains immutable and
preserves the one-shot launch contract. The versioned
[consuming-boundary authority](../../decisions/evidence/ck07r1a0/lifecycle-consuming-boundary-authority-v1.json)
alone permits the bound existing worker to cross from exact
`worker_prequalification` to `launch_authorized_once` after authority merge and
exact-main verification. The first invocation then stopped before successful
child observation. The additive
[prelaunch-recovery authority](../../decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.json)
alone can authorize one corrected v2 invocation after preserving that terminal
ledger and proving the token remains unspent. That invocation has now occurred
and is terminal; the additive
[terminal-failure correction authority](../../decisions/evidence/ck07r1a0/lifecycle-terminal-failure-correction-authority-v1.json)
authorizes no run and only binds a deterministic benchmark/test correction.

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

**Preserved prelaunch failure:** The exact v1 ledger at
`output/ck07r1/lifecycle-requalification-v1.launch-token.json` has SHA-256
`5c2b42eca6a3e54cf4163226bc55f3c75aa35112c4ed0342c11f4e39cb9922be`,
state `prelaunch_failed`, stage `child_start_handshake`, and
`token_consumed=false`. No child was successfully observed or released and no
runtime output, stdout, stderr, or receipt exists. The v1 invocation and path
set are terminal and immutable. A corrected invocation is not a launched
process retry, restart, replacement, or refund; it is the one remaining
opportunity to observe the token-funded first successful child. It must use
the exact `lifecycle-requalification-v2` output, ledger, stdout, and stderr
paths and the exact corrected cohort bound by the recovery authority.

**Preserved terminal v2 failure:** The one permitted v2 invocation was made
exactly once. Child PID `20482` passed the exact handshake and consumed the
non-refundable token at `2026-08-19T19:44:55Z`, then exited 70. The immutable
v2 ledger SHA-256
`570e27824ee04a51aa4012adb461bd4aebb00b61541f2477fd9e1665854325a2`
records `failed_after_launch` and `token_consumed=true`; stderr SHA-256
`4cf4b10fd04f20a190e4ac41898d25b9295b3dc9d7addead8a81edd27b3aca2f`
records the exact child assertion; stdout is empty with SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
output and receipt are absent. No retry, restart, replacement, refund, or
second invocation exists or can be authorized.

The deterministic root cause is a benchmark defect, not a production planner
defect. The accepted `TailLimits.selected_records` ceiling is 32. The frozen
standard workload yields 1,369 selected records and 11,214,848 expected WAL
bytes, so the production planner must select `APPEND_SAFE_LARGE` with
`limit_exceeded:selected_records`. Production chunks additionally exceed the
WAL bound. The benchmark incorrectly asserted `APPEND_SAFE_SMALL` for every
chunk and therefore never exercised the selected large-artifact path.

The terminal-failure correction authority permits the same worker to correct
only the benchmark and its lifecycle test. The additive
[clean-committed transition authority](../../decisions/evidence/ck07r1a0/lifecycle-terminal-failure-clean-commit-authority-v1.json)
preserves the v1 authority bytes and binds exact PR #448 base `652f2166…`,
source head `927aa06f…`, and seven-path scope. It accepts only the exact dirty
all-or-none prepublication representation or the exact clean committed
PR/integrated representation; mixed, partial, extra, wrong-lineage, and
wrong-byte states remain forbidden. Every chunk must preserve the exact
`plan_refresh` result: small plans use the pointer-coordinated short writer;
large plans use the production-reachable isolated-artifact build, validation,
durable promotion, recovery, rollback, and prior-readability path. Tail limits,
production planner/preparation behavior, accepted authority bytes, both
terminal ledgers, and all run artifacts remain immutable.

The additive [clean-committed CI authority v2](../../decisions/evidence/ck07r1a0/lifecycle-terminal-failure-clean-commit-authority-v2.json)
preserves both v1 bridge files byte-for-byte and binds the exact hosted workflow
correction required by accepted lexical `.venv/bin/python` and matching
`sys.prefix` consumers. It creates `.venv` from the already-selected Python
3.10 or 3.14 matrix interpreter after the existing development install and
before verification, adds no network dependency step, and admits only the exact
follow-up authority scope or exact follow-up-plus-seven integrated state. It
does not reopen the consumed token or authorize a command, launch, retry,
replacement, refund, receipt, runtime acceptance, or downstream work.

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

**Acceptance:** Historical v2 launch — immediately before the one command, the worker must revalidate
the exact recovery authority bytes, the corrected three-path source cohort,
the preserved v1 ledger as the sole fourth dirty path, lexical worktree
`.venv/bin/python` plus matching `sys.prefix`, exact cwd/argv/environment,
capacity at or above 10 GiB, `matching_processes=[]`, all four new v2 artifact
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

**Post-terminal corrective acceptance:** The corrected two-file cohort may
enter only `corrective_implementation_prequalified` after exact unit-level
planner reproduction, 32/33 boundary tests, large-artifact promotion and
rollback/readability tests, independent lifecycle-fold equivalence, exact
small/large plan preservation, focused and full repository gates, one bounded
reviewer, hosted Console/Python 3.10/3.14, squash merge of the authority-only
packet, and fresh exact-main verification. This state is not runtime
qualification and cannot transition to `post_single_run` or `final_accepted`;
the existing complete-receipt requirement remains unsatisfied. No command
invocation or run artifact creation is part of this correction.

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

The hosted Console gate retains Chromium dependency and browser coverage. It
pins the canonical HTTPS Ubuntu archive before Playwright installs system
dependencies, bounds the Chromium install step at 10 minutes, and bounds the
complete Console job at 20 minutes. A mirror stall therefore fails closed
instead of hanging or bypassing Console evidence.

**Failure/rollback:** Retain the profile and create one narrow follow-up for a
new dominant blocker; never weaken the gate. The preserved v1 and v2 ledgers,
v2 stdout/stderr, absent output/receipt state, child identity, token
consumption, and terminal classifications are never deleted, moved, rewritten,
or reclassified. A separate explicit roadmap decision is required to resolve
the receipt-required acceptance dead end; no implementation or authority
correction may infer another run.

**Handoff:** Evidence digest, profiles, retained first hosted failure, PR #394
CI, exact-main result, and CK-08R4 input.

**Cleanup/docs:** Supersede only affected CK-07/08 scale claims.

**Suggested commit:** `perf: linearize lifecycle preparation`
