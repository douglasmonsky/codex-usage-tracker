# CK-03 — Build shared synthetic fixtures and truth oracles

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Produce one deterministic source generator and correctness oracle for
all candidates and final qualification.

**Why:** Candidate-specific fixtures would make performance and correctness
comparisons meaningless.

**Controls:** CK-01/CK-02, `QUALIFICATION_PLAN.md`,
`PHYSICAL_ARCHITECTURE_BAKEOFF.md`.
**Dependencies:** CK-02.

**Scope and expected files:**

- `tests/agent_kernel/fixtures/generator/**`;
- tiny hand-auditable fixtures;
- small/standard/production/growth manifests generated on demand;
- accounting, lifecycle, evidence, source-lifecycle, question-answer, and
  crash-state oracle modules;
- aggregate production-shape profile schema;
- deterministic fixture CLI.

**Schema/API changes:** Fixture/oracle formats only.
**Non-goals:** Reading real logs, storing raw content, candidate schema.

**Invariants:** Same seed/config produces identical source bytes/manifests;
scale uses same semantic cases; expected results derive independently from
candidate SQL; no private values/paths.

**Tests/benchmarks:** Digest reproducibility on two processes/Python versions,
tiny hand audit, generator time/bytes, manifest completeness, all question
oracle references.

**Acceptance:** All five bake-off slices and every Foundation/Cutover question
have truth cases; 100k and 1.316M fixtures reproduce exact declared
distributions; fixture generation is excluded from product timing.

**Failure/rollback:** Delete generated artifacts, keep generator source. Do not
patch candidates around an oracle error; fix and rerun all candidates.

**Cleanup/docs:** Record fixture revision/digest policy in qualification docs.

**Suggested commits:**

1. `test: add agent-kernel source fixture generator`
2. `test: add accounting lifecycle and evidence oracles`
