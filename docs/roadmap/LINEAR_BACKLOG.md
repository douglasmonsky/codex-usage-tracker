# Linear-Ready Backlog

**Status:** Import/source document; no Linear objects have been created
**System of work:** Linear, not GitHub Issues

## Workspace model

### Initiative I1 — Agent-First Usage Kernel

Deliver the exact local facts, evidence, performance, and Codex experience that
prove the new direction.

Projects:

- P1 Contract and physical decision
- P2 Canonical kernel and publication
- P3 Answers and installed Codex experience

### Initiative I2 — Clean Cutover and Public Release

Retire the spike/Console and ship the clean product without compatibility
burden.

Projects:

- P4 Qualification and cutover
- P5 Runtime retirement
- P6 Public launch and optional presentation

## Milestones

| Milestone | Exit |
| --- | --- |
| M0 Authority Ready | CK-00 merged; one authority set and roadmap. |
| M1 Architecture Selected | CK-01–CK-04 complete; physical decision recorded. |
| M2 Kernel Alpha | CK-05–CK-09 plus corrective CK-07B and CK-07A complete; exact published facts independently reconcile to named-plan truth. |
| M3 Codex MVP Qualified | CK-10–CK-12 complete; installed fresh tasks pass. |
| M4 Clean Cutover | CK-13–CK-14 complete; spike/Console absent. |
| M5 Public Release | CK-16 complete; CK-15 included only if independently admitted. |

## Labels

| Label | Use |
| --- | --- |
| `workstream:contracts` | Product, question, logical, schema contracts |
| `workstream:fixtures` | Synthetic source and truth oracles |
| `workstream:storage` | SQLite, identity, facts, lifecycle |
| `workstream:adapter` | Codex JSONL and normalization |
| `workstream:publication` | Refresh, dirty keys, recovery |
| `workstream:query` | Plans, evidence, projections |
| `workstream:agent-experience` | Setup, MCP, CLI, skill |
| `workstream:qualification` | Benchmarks and fresh-agent trials |
| `workstream:cutover` | Entry points, retirement, package cleanup |
| `workstream:docs` | Public and authority documentation |
| `type:decision` | A decision artifact gates implementation |
| `type:performance` | Measured latency/storage/call/token work |
| `type:quality` | Correctness/recovery/packaging proof |
| `type:removal` | Deletes a retired surface |
| `cutover:blocker` | Must close before CK-13 approval |
| `parallel:eligible` | Safe only under the packet's explicit lane rules |

## Issue backlog

The acceptance summaries below are intentionally compact. Each issue
description should link the matching file under `docs/roadmap/tasks/` as the
complete contract and `TASK_PACKETS.md` as the completion ledger.

| Key | Linear issue title | Project | Milestone | Depends on | Labels | Acceptance summary |
| --- | --- | --- | --- | --- | --- | --- |
| CK-00 | Establish the agent-first documentation authority | P1 | M0 | — | workstream:contracts, workstream:docs, cutover:blocker | Required authority set exists; obsolete workflow docs/references removed; release/scope checks pass; spike ref/disposition frozen. |
| CK-01 | Make supported-question contracts executable | P1 | M1 | CK-00 | workstream:contracts, type:quality | Machine registry and Markdown reconcile; all fields/grades/evidence/budgets/oracles/lower-model hints validate. |
| CK-02 | Freeze logical kernel vectors | P1 | M1 | CK-01 | workstream:contracts, type:quality | Identity/time/token/lifecycle/source/allowance/valuation/publication/selector vectors pass without physical storage. |
| CK-03 | Build deterministic source fixtures and truth oracles | P1 | M1 | CK-02 | workstream:fixtures, type:quality, parallel:eligible | Tiny through production-shape fixtures deterministic; all vertical slices and named questions have independent truth. |
| CK-04 | Select the physical architecture through A/C/D bake-off | P1 | M1 | CK-03 | workstream:storage, type:performance, type:decision, parallel:eligible, cutover:blocker | All candidates measured identically; hard gates/early stops applied; decision names selected DDL/index/sequence/publication shape. |
| CK-05 | Implement isolated database-v1 canonical storage | P2 | M2 | CK-04 | workstream:storage, type:quality, cutover:blocker | New root/database identity; selected schema; logical vectors/tiny oracle pass; no spike import/open/migration. |
| CK-06 | Implement bounded Codex JSONL adapter and ingestion | P2 | M2 | CK-05 | workstream:adapter, type:performance, cutover:blocker | Source lifecycle/cursors/normalization/capabilities pass; selected history honest; deterministic parallel parse; no raw bodies. |
| CK-07 | Implement lock-bounded publication and crash recovery | P2 | M2 | CK-06 | workstream:publication, type:performance, type:quality, cutover:blocker | No-change/ordinary-tail/large-artifact paths pass; reads available; crash matrix and duplicate-operation reuse pass. |
| CK-07B | Freeze formula and selector-provenance authority | P2 | M2 | CK-07; CK-07A blocker evidence | workstream:contracts, type:quality, cutover:blocker | All 45 formulas and 185 fields are executable; all 14 selector kinds resolve through authoritative owners with exact provenance and lifecycle gates. |
| CK-07C | Freeze plan operands and missing canonical facts | P2 | M2 | CK-07B; retained CK-07A blocker evidence | workstream:contracts, workstream:storage, type:quality, cutover:blocker | All 61 formula uses and 185 answer fields have executable plan bindings; valuation, context, allowance, hierarchy, order, and publication inputs are materially representable without expected-answer data. |
| CK-07A | Reconcile fact-backed oracles and qualify packet seams | P2 | M2 | CK-07C; CK-08 blocker evidence | workstream:contracts, workstream:fixtures, workstream:qualification, type:quality, cutover:blocker | All question cases derive independent truth from canonical scenarios; Foundation/Cutover cases replay through CK-06/CK-07/database-v1; CK-03–CK-07 evidence is requalified. |
| CK-08 | Implement fact-backed query and stable evidence | P3 | M2 | CK-07A | workstream:query, type:quality | Exact registry plans/evidence/cursors/labels/grades work from one snapshot; projection admission report measured. |
| CK-09 | Add measured current projections and named plans | P3 | M2 | CK-08 | workstream:query, workstream:publication, type:performance, parallel:eligible, cutover:blocker | Foundation/Cutover plans pass oracles/SQL/MCP/bytes; every projection has consumer, dirty keys, storage/fanout budget. |
| CK-10 | Deliver agent-led setup, MCP, CLI, and skill | P3 | M3 | CK-09 | workstream:agent-experience, cutover:blocker | Recommended recent start, host wait/no polling, query-first warm path, closed bounded tools, version coherence. |
| CK-11 | Automate exact installed Codex qualification | P4 | M3 | CK-10 | workstream:qualification, type:quality | Exact wheel/plugin/skill installs in isolation; fresh CLI/Desktop/default/lower-model scorecards generated deterministically. |
| CK-12 | Pass the full correctness and performance qualification | P4 | M3 | CK-11 | workstream:qualification, type:performance, cutover:blocker | L0–L5, all scales/ranges, crash/lock, package, call/token/latency gates and <=25% byte-size ratchets pass. |
| CK-13 | Execute and approve side-by-side clean cutover | P4 | M4 | CK-12 | workstream:cutover, type:quality, cutover:blocker | Replacement owns candidate entry points/database; exact rollback/reinstall drill passes; deletion checkpoint approved. |
| CK-14 | Delete spike runtime, Console, and obsolete toolchain | P5 | M4 | CK-13 | workstream:cutover, type:removal, parallel:eligible, cutover:blocker | Old runtime/frontend/Node/tools/routes/schemas/config absent; useful oracles ported; package/CI budgets decrease; qualification stays green. |
| CK-15 | Evaluate bounded native presentation and Data Analytics handoff | P6 | M5 optional | CK-14 | workstream:agent-experience, workstream:query | Official-host support verified; usefulness improves without core latency/call/token burden, or task closes deferred with no code. |
| CK-16 | Publish product documentation and clean-cutover release | P6 | M5 | CK-14; CK-15 optional | workstream:docs, type:quality, cutover:blocker | Public narrative/install/examples match exact artifacts; build-once/public install/fresh-task evidence and hashes pass. |

## Linear issue template

Use this body when creating each issue:

```markdown
## Goal
<Copy the packet goal and why.>

## Controlling documents
- <Exact authority links>

## Dependencies
- <Linear issue links>

## Scope
<Exact packet scope and owned paths.>

## Non-goals
<Packet non-goals.>

## Acceptance
- [ ] <Exact acceptance checks>

## Measurements
- <Required workload, fixture digest, and budgets>

## Failure and rollback
<Packet behavior>

## Evidence
- Branch:
- Commits:
- Checks:
- Measurements:
- Review findings / accepted / token status:
- Residual risk:
```

## Recommended sequencing

1. Create I1/I2, P1–P6, M0–M5, and labels.
2. Create CK-00 only after this documentation branch is ready to merge; close
   it from that PR.
3. Create CK-01 through CK-04. Keep CK-05 blocked until the decision artifact
   is accepted.
4. Create CK-05 through CK-07 after M1. Close CK-07B, resume CK-07A before
   CK-08, and make CK-08 depend on merged seam evidence; then create CK-08 and CK-09. Use
   dependency links, not status text, to enforce the critical path.
5. Create CK-10 through CK-12 after named-plan contracts stabilize.
6. Do not put CK-13 in progress while any `cutover:blocker` is open.
7. Create CK-14 only after the maintainer approves CK-13's deletion checkpoint.
8. CK-15 is optional and must not block CK-16 by default.

## Parallel work lanes

| Parent issue | Child lanes | Merge checkpoint |
| --- | --- | --- |
| CK-03 | Fixture generator; accounting/lifecycle/evidence oracle case sets | Shared manifest/oracle schemas frozen |
| CK-04 | Candidate A; Candidate C; Candidate D | Shared harness complete, then decision integration |
| CK-06/CK-07 | Adapter parser cases; crash/failure harness | CK-05 ports fixed; publication integrates |
| CK-07A after CK-07B | Canonical scenario/reference evaluator; CK-04 proof replacement; CK-05–CK-07 replay | Shared formula, scenario, expected-row, selector, and evidence schemas frozen |
| CK-08/CK-11 | Query/evidence implementation; installed harness skeleton | Public schemas remain CK-10-owned |
| CK-09 | Session/family; time/model; tool/resource; allowance projection families | Dirty-key/projection registry frozen |
| CK-12 | Repeated performance; crash matrix; fresh CLI; fresh Desktop | Exact artifact and fixture digests frozen |
| CK-14 | Runtime deletion; frontend/Node deletion; package/CI cleanup | One owner integrates manifests/release check |

Each parallel child names owner, worktree, base SHA, file allowlist, and expected
artifact in its Linear description. Shared files are never co-owned.

## Cutover blockers

CK-13 cannot close while any of these is open:

- unresolved logical or physical decision;
- Foundation/Cutover question oracle failure;
- first-use or ordinary-tail hard-gate failure;
- analytical database lock during concurrent read/startup;
- selector instability;
- missing installed default/lower-model evidence;
- package/plugin/skill version mismatch;
- unresolved crash/rollback state;
- raw-body persistence;
- spike database migration/import;
- unresolved accepted final-review finding.

CK-16 cannot publish while CK-14 is incomplete or public artifact/install
evidence is missing.
