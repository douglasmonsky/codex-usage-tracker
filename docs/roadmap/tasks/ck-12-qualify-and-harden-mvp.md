# CK-12 — Qualify and harden the complete MVP

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Run every correctness, performance, concurrency, recovery, packaging,
and installed-agent gate and fix only demonstrated defects.

**Why:** This is the decision point where the replacement becomes credible.

**Controls:** `QUALIFICATION_PLAN.md`, all prior contracts.
**Dependencies:** CK-11.

**Scope and expected files:** Focused fixes within prior owners, measured
ratchet configs, qualification evidence artifact, release-check integration.

**Schema/API changes:** None unless a failed locked contract requires a recorded
amendment and rerun of affected gates.
**Non-goals:** New question surface, UI, branding, gate weakening.

**Invariants:** Identical workloads for speed claims; agent-perf attribution;
early stop; full matrix rerun after accepted semantic fixes; one final
reviewer.

**Tests/benchmarks:** Entire L0–L5 qualification plan, 100k/1.316M/growth,
all history ranges, concurrency/lock reproduction, crash matrix, exact wheel,
fresh CLI/Desktop default/lower model.

**Acceptance:** Every hard gate passes; residual host/model latency is
separated and within release criteria; no unresolved accepted review finding;
ratchets have <=3% headroom.

**Failure/rollback:** Keep replacement disabled and create a narrowly owned
follow-up packet. A hard-gate failure cannot be converted to a caveat.

**Cleanup/docs:** Record final measurements, artifact hashes, review metrics,
and remaining non-blocking risks.

**Suggested commits:** One focused fix per demonstrated owner, then
`test: qualify agent-first kernel candidate`.
