# CK-04 — Run A/C/D physical bake-off and decide

**Status:** In progress
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
two-route local DBHub comparison, repeated unprofiled timings, agent-perf
attribution. Installed-model operability is deferred to CK-11.

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

## Execution record

**Status:** Remediation implemented; clean requalification pending
**Provisional direction:** Candidate A mechanisms
**Decision:** [PHYSICAL_ARCHITECTURE_DECISION.md](../../decisions/PHYSICAL_ARCHITECTURE_DECISION.md)
**Production schema contract:** [AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md](../../architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md)

The final read-only review identified seven accepted gaps in the first
qualification pass. Candidate A now has real crash/recovery execution,
database-derived query answers, per-case planner eligibility gates, real
1/2/4/8-worker parsing, an exact Agent Perf standard-build workload, a complete
production database-v1 contract, and a strict canonical decision-evidence
validator.

The earlier Candidate A speed and eligibility claims are historical only
because those remediations changed the measured code. CK-04 remains in
progress until a clean commit completes the required five-run timings,
69-query matrix, 25-case recovery matrix, growth sensitivity, DBHub comparison,
canonical v2 aggregate evidence, release-candidate checks, and CI.

The CK-04 DBHub benchmark is deterministic and local: five samples each
deliberately execute the `generic` and `named_preset` routes in alternating
global order. It does not ask a model to select a route, and the current runner
invokes no model. Exact model identity, host/runtime versions, reasoning effort,
synthetic-prompt artifact identity/hash, token source, and authorization for
billed calls were never frozen; CK-11 owns that installed-model operability
record.
