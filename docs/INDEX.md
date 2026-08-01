# Documentation Authority

This is the single entry point for the agent-first clean cutover. Active
documents below are mutually controlling: each owns one implementation area,
and none of the archived documents may override them.

## Current packet boundary

CK-07A is complete after consuming the merged CK-07B formula/provenance,
CK-07C plan/direct-fact, CK-07D effective-dated valuation, and CK-07E
independent-adapter prerequisites. Its
[canonical evidence](decisions/evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json)
records 80 / 80 fact-backed comparisons through structural-v2 source JSONL,
CK-06 ingestion, CK-07 publication/recovery, query-only database-v1, Candidate
A's permitted fact-table/planner path, and two fact-adapter consumers of the
same production answer evaluator. All 185
answer-field bindings, 14 selector kinds, six provenance kinds, exact ordered
references, response bytes, timings, SQL sources/plans, lifecycle modes, and
CK-03 through CK-07 requalifications are recorded.

The historical
[CK-08 prerequisite gap](decisions/evidence/ck08/fact-backed-oracle-prerequisite-gap.json)
remains preserved as the reproduction that caused the stop, but it is no
longer the current boundary blocker. CK-04's invalid `question_cases`
correctness proof is replaced; its current-commit growth repetitions 3 and 4
remain explicitly waived and no strict five-repetition aggregate is claimed.
CK-08 is historically complete on merge: all 21 plans and 42 fact-backed
variants reconcile through the shared evaluator, every plan received a
provisional physical classification, and no projection or public surface was
added. Its single final reviewer findings were all accepted and corrected.

A downstream architecture audit reproduced four current gaps: the
expected-answer path is not semantically independent; runtime keyset
pagination occurs after full Python materialization; CK-08's reported SQL
timing includes compiler/Python work and cannot admit 18 projections; and
publication/evidence scale plus replacement maintainability need corrective
proof. [`corrective-gates-v1`](decisions/evidence/ck08r0/corrective-gates-v1.json)
preserves history and keeps CK-09 blocked.
[REMAINING_EXECUTION_PLAN.md](roadmap/REMAINING_EXECUTION_PLAN.md) is the
central execution authority.

## Authority set

| Order | Document | Controls |
| ---: | --- | --- |
| 1 | `docs/decisions/PRODUCT_DIRECTION.md` | Product definition, responsibility boundary, non-goals, locked decisions, and success measures. |
| 2 | `docs/product/SUPPORTED_QUESTION_CONTRACTS.md` | Supported intents, answer grades, evidence, performance classes, named presets, and unsupported conclusions. |
| 3 | `docs/architecture/LOGICAL_KERNEL_CONTRACT.md` | Physical-design-independent entities, fields, identities, time, missingness, provenance, and publication semantics. |
| 4 | `docs/architecture/FORMULA_AND_SELECTOR_CONTRACT.md` | Executable formula semantics, answer-field bindings, selector ownership, provenance, and exact comparison. |
| 5 | `docs/architecture/PLAN_OPERAND_AND_FACT_CONTRACT.md` | Executable plan-to-operand/direct-fact bindings, pure compiler boundary, valuation relation, and missing canonical facts. |
| 6 | `docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md` | Candidate A/C/D experiment, fixtures, workloads, measurements, and selection decision. |
| 7 | `docs/architecture/TARGET_ARCHITECTURE.md` | Package ownership and runtime boundaries after the bake-off. |
| 8 | `docs/architecture/ADAPTER_CONTRACT.md` | Codex source ingestion, normalization, capabilities, cursors, replacement, duplicates, and the future-agent seam. |
| 9 | `docs/architecture/PUBLICATION_REFRESH_RECOVERY.md` | Refresh state machine, dirty keys, small tails, large artifacts, crashes, promotion, and rollback. |
| 10 | `docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md` | Named plans, bounded composition, evidence, pagination, projections, valuation, and result envelopes. |
| 11 | `docs/product/AGENT_SETUP_AND_MCP_EXPERIENCE.md` | First use, history selection, host waiting, reopen, refresh/expansion, call budgets, and skill behavior. |
| 12 | `docs/quality/QUALIFICATION_PLAN.md` | Synthetic truth, production-shape profiling, benchmarks, installed-agent trials, crash tests, and ratchets. |
| 13 | `docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md` | The only authoritative implementation roadmap, dependencies, gates, cutover, and release. |
| 14 | `docs/roadmap/REMAINING_EXECUTION_PLAN.md` | Remaining task graph, readiness, role routing, ownership locks, and allowed/forbidden parallelism. |
| 15 | `docs/roadmap/TASK_PACKETS.md` and `docs/roadmap/tasks/` | Completion accounting and one agent-executable contract file per delegated task. |
| 16 | `docs/roadmap/LINEAR_BACKLOG.md` | Historical Linear-ready mapping; no Linear change is authorized by the decomposition. |

## Area ownership

| Question | Authority |
| --- | --- |
| What product are we building? | `PRODUCT_DIRECTION.md` |
| Can the product answer this question, and how? | `SUPPORTED_QUESTION_CONTRACTS.md` |
| What does a session, turn, call, tool, resource, observation, or publication mean? | `LOGICAL_KERNEL_CONTRACT.md` |
| What exactly does a formula compute, and how must selector evidence resolve? | `FORMULA_AND_SELECTOR_CONTRACT.md` |
| How do named plans derive formula operands and direct facts, and which missing fact representations are authoritative? | `PLAN_OPERAND_AND_FACT_CONTRACT.md` |
| Which physical schema is allowed? | The completed decision artifact required by `PHYSICAL_ARCHITECTURE_BAKEOFF.md` |
| Which package owns a behavior? | `TARGET_ARCHITECTURE.md` |
| How does Codex JSONL become canonical facts? | `ADAPTER_CONTRACT.md` |
| May this refresh rebuild or block readers? | `PUBLICATION_REFRESH_RECOVERY.md` |
| May this query, selector, or projection exist? | `QUERY_EVIDENCE_PROJECTION_CONTRACTS.md` |
| How should an installed agent set up and call the kernel? | `AGENT_SETUP_AND_MCP_EXPERIENCE.md` |
| What proves the implementation? | `QUALIFICATION_PLAN.md` |
| What happens next, and what may run in parallel? | `REMAINING_EXECUTION_PLAN.md`, constrained by `AGENT_FIRST_CLEAN_CUTOVER.md` |
| Where does work get tracked? | `LINEAR_BACKLOG.md`; Linear is intended after maintainer issue creation. |

## Required reading paths

### Implementing a task packet

1. Open the Ready child task from `REMAINING_EXECUTION_PLAN.md`, confirm its
   exact dependencies and ownership lock, then read its controlling documents.
2. Read the relevant question IDs and logical entities.
3. Read the publication/query/adapter contract that owns the touched boundary.
4. Read the qualification cases and budgets before writing code.
5. Consult archived spike evidence only for the exact oracle or lesson named by
   the packet.
6. For every upstream artifact consumed as truth, run the packet's executable
   seam check against the actual consumer path and independent reference
   evaluator; a digest or prior completion status is not sufficient.

### Changing a product contract

1. Amend `PRODUCT_DIRECTION.md` if responsibility or non-goals change.
2. Amend affected question contracts and logical semantics.
3. Update architecture, qualification, roadmap, packet, and backlog mappings in
   the same change.
4. Add or change an executable contract before production implementation.

### Preparing cutover or release

Read the roadmap, publication/recovery protocol, qualification plan, cutover
packets, and release packet. The roadmap's active runtime-retirement gate
controls deletion. Consult the spike disposition only for the historical
inventory and named oracles; it cannot add or waive a cutover condition.

## Historical material

Everything under `docs/archive/` is non-authoritative. The useful archive is:

- `docs/archive/SPIKE_DISPOSITION.md`
- `docs/archive/SPIKE_PERFORMANCE_EVIDENCE.md`
- `docs/archive/spike/KERNEL_STABLE_CONTRACT_0_28.md`
- `docs/archive/spike/ALLOWANCE_EFFICIENCY_FINDINGS.md`
- `docs/archive/spike/OVERLAY_ADAPTER_CONTRACT_0_28.md`

Git history contains prior roadmaps, review reports, UI plans, and superseded
proposals. They are intentionally absent from the active tree.

The 0.28 implementation, tests, fixtures, and release tooling remain executable
oracles until the retirement gate. Their current behavior is not product
authority unless an active document explicitly adopts it.

## Conflict rule

If two active documents appear inconsistent:

1. product responsibility and non-goals win over implementation convenience;
2. question and logical contracts win over a physical candidate;
3. safety and publication invariants win over latency;
4. the qualification plan decides whether a claim is proven;
5. stop the affected packet and record a decision amendment rather than
   silently choosing the spike behavior.

If an already completed packet's artifact fails in a downstream consumer,
preserve the historical completion record, add a corrective packet to the
dependency graph, and require linked requalification evidence for every
affected downstream seam before dependent work resumes.

Archived documents, old branch names, current spike schemas, and historical
release notes never resolve an active-contract conflict.
