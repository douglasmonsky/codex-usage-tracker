# Documentation Authority

This is the single entry point for the agent-first clean cutover. Active
documents below are mutually controlling: each owns one implementation area,
and none of the archived documents may override them.

## Current packet boundary

CK-07 is complete with its
[publication, refresh, and recovery evidence](decisions/evidence/ck07/publication-refresh-recovery-evidence.json)
recorded. CK-05 canonical storage and CK-06 adapter/ingestion remain its
verified dependencies. CK-08 began from the verified CK-07 merge and found a
missing fact-backed oracle prerequisite: the frozen CK-03 question rows do not
equal the canonical database-v1 facts for their own requests, while the CK-04
query proof obtained those rows from a candidate-only `question_cases` table
that database-v1 explicitly forbids. CK-08 is therefore blocked at its packet
boundary with the exact
[prerequisite evidence](decisions/evidence/ck08/fact-backed-oracle-prerequisite-gap.json)
recorded. CK-09 is not admitted. The CK-04 growth exception remains explicit
and the strict v2 aggregate is not claimed. The authority set below wins over
historical operational checkpoints.

## Authority set

| Order | Document | Controls |
| ---: | --- | --- |
| 1 | `docs/decisions/PRODUCT_DIRECTION.md` | Product definition, responsibility boundary, non-goals, locked decisions, and success measures. |
| 2 | `docs/product/SUPPORTED_QUESTION_CONTRACTS.md` | Supported intents, answer grades, evidence, performance classes, named presets, and unsupported conclusions. |
| 3 | `docs/architecture/LOGICAL_KERNEL_CONTRACT.md` | Physical-design-independent entities, fields, identities, time, missingness, provenance, and publication semantics. |
| 4 | `docs/architecture/PHYSICAL_ARCHITECTURE_BAKEOFF.md` | Candidate A/C/D experiment, fixtures, workloads, measurements, and selection decision. |
| 5 | `docs/architecture/TARGET_ARCHITECTURE.md` | Package ownership and runtime boundaries after the bake-off. |
| 6 | `docs/architecture/ADAPTER_CONTRACT.md` | Codex source ingestion, normalization, capabilities, cursors, replacement, duplicates, and the future-agent seam. |
| 7 | `docs/architecture/PUBLICATION_REFRESH_RECOVERY.md` | Refresh state machine, dirty keys, small tails, large artifacts, crashes, promotion, and rollback. |
| 8 | `docs/architecture/QUERY_EVIDENCE_PROJECTION_CONTRACTS.md` | Named plans, bounded composition, evidence, pagination, projections, valuation, and result envelopes. |
| 9 | `docs/product/AGENT_SETUP_AND_MCP_EXPERIENCE.md` | First use, history selection, host waiting, reopen, refresh/expansion, call budgets, and skill behavior. |
| 10 | `docs/quality/QUALIFICATION_PLAN.md` | Synthetic truth, production-shape profiling, benchmarks, installed-agent trials, crash tests, and ratchets. |
| 11 | `docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md` | The only authoritative implementation roadmap, dependencies, gates, cutover, and release. |
| 12 | `docs/roadmap/TASK_PACKETS.md` and `docs/roadmap/tasks/` | Checkbox completion accounting and one agent-executable contract file per packet. |
| 13 | `docs/roadmap/LINEAR_BACKLOG.md` | Linear-ready initiative, project, milestone, issue, dependency, and label mapping. |

## Area ownership

| Question | Authority |
| --- | --- |
| What product are we building? | `PRODUCT_DIRECTION.md` |
| Can the product answer this question, and how? | `SUPPORTED_QUESTION_CONTRACTS.md` |
| What does a session, turn, call, tool, resource, observation, or publication mean? | `LOGICAL_KERNEL_CONTRACT.md` |
| Which physical schema is allowed? | The completed decision artifact required by `PHYSICAL_ARCHITECTURE_BAKEOFF.md` |
| Which package owns a behavior? | `TARGET_ARCHITECTURE.md` |
| How does Codex JSONL become canonical facts? | `ADAPTER_CONTRACT.md` |
| May this refresh rebuild or block readers? | `PUBLICATION_REFRESH_RECOVERY.md` |
| May this query, selector, or projection exist? | `QUERY_EVIDENCE_PROJECTION_CONTRACTS.md` |
| How should an installed agent set up and call the kernel? | `AGENT_SETUP_AND_MCP_EXPERIENCE.md` |
| What proves the implementation? | `QUALIFICATION_PLAN.md` |
| What happens next? | `AGENT_FIRST_CLEAN_CUTOVER.md` and its task packets |
| Where does work get tracked? | `LINEAR_BACKLOG.md`; Linear is intended after maintainer issue creation. |

## Required reading paths

### Implementing a task packet

1. Open the packet from the master checkbox ledger and read its controlling
   documents.
2. Read the relevant question IDs and logical entities.
3. Read the publication/query/adapter contract that owns the touched boundary.
4. Read the qualification cases and budgets before writing code.
5. Consult archived spike evidence only for the exact oracle or lesson named by
   the packet.

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

Archived documents, old branch names, current spike schemas, and historical
release notes never resolve an active-contract conflict.
