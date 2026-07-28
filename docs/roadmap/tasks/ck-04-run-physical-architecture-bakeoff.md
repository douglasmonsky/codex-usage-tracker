# CK-04 — Run A/C/D physical bake-off and decide

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement bounded Candidates A, C, and D and select one physical
architecture through measured gates.

**Why:** The pivotal schema choice must be evidence-driven before production
code creates migration pressure.

**Controls:** `PHYSICAL_ARCHITECTURE_BAKEOFF.md`, CK-02/CK-03.
**Dependencies:** CK-03.

**Scope and expected files:**

- `experiments/physical-architecture/shared/**`;
- `candidate_a/**`, `candidate_c/**`, `candidate_d/**`;
- benchmark output schemas and ignored raw measurement directory;
- `docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md`;
- pinned DBHub v0.24.0 disposable research config;
- agent-perf workload definition.

**Schema/API changes:** Experimental DDL only; decision freezes selected
production table/index/projection shape.
**Non-goals:** Production imports, plugin/CLI, generic DBHub product access,
Semantic Kernel.

**Invariants:** Identical logical records/oracles/queries/evidence; no candidate
omits a slice or changes grades; failures stop early; prior valid publication
survives injected crashes.

**Tests/benchmarks:** Complete workload matrix, scales/history ranges,
parallel-worker experiments, query plans, storage/WAL/pages, crash matrix,
default/lower-model DBHub comparison, repeated unprofiled timings, agent-perf
attribution.

**Acceptance:** At least one candidate passes every hard gate; selection score
and sensitivity analysis are reproducible; decision names exact tables,
indexes, sequence authority, lifecycle storage, publication mechanism,
projections, rejected alternatives, risks, and follow-ups.

**Failure/rollback:** If none passes, publish a failed decision artifact naming
the smallest contract-preserving experiment to rerun. Do not start CK-05 or
choose Candidate C by preference.

**Cleanup/docs:** Experimental code remains isolated or is removed after
decision; no production copy/paste without a clean implementation packet.

**Parallelism:** A/C/D directories are disjoint and parallel-eligible after the
shared harness is frozen. One integrator owns shared files and scoring.

**Suggested commits:**

1. `test: freeze physical architecture bakeoff harness`
2. `perf: implement candidate a`
3. `perf: implement candidate c`
4. `perf: implement candidate d`
5. `docs: select agent-kernel physical architecture`
