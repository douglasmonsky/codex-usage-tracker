# Product Recovery Task Packets

These packets implement the
[Product Recovery Roadmap](../product-recovery.md). The
[execution ledger](../product-recovery-execution.md) is the durable progress
record.

Every task packet is an instruction set, not a completion claim. The task owner
must:

1. Start from the dependency commit recorded in the ledger.
2. Re-read `AGENTS.md` and this packet.
3. Confirm a clean, task-specific worktree.
4. Add one observable failing contract or benchmark before implementation.
5. Run GitNexus impact before editing existing symbols.
6. Use synthetic fixtures only.
7. Update the execution ledger in the same changeset.
8. Complete focused and required broad validation.
9. Stabilize the diff before one final read-only reviewer.
10. Record accepted findings, reviewer metrics, deviations, and residual risk.

## Packets

- [R0 — Adopt the recovery roadmap](r0-adopt-recovery-roadmap.md)
- [R1 — Freeze agent outcome and performance baselines](r1-agent-outcome-baseline.md)
- [R2 — Define schema v3 and compact storage](r2-schema-v3-storage.md)
- [R3 — Accelerate cold build and incremental refresh](r3-build-refresh-performance.md)
- [R4 — Build persisted rollups and fast MCP/API paths](r4-fast-query-mcp.md)
- [R5 — Restore analytical primitives and human semantics](r5-analytical-primitives.md)
- [R6 — Rebuild Console usability](r6-console-usability.md)
- [R7 — Qualify the installed fresh-task agent outcome](r7-installed-agent-qualification.md)
- [R8 — Publish public product documentation](r8-public-docs.md)
- [R9 — Qualify and release 0.29.0](r9-release-0.29.0.md)

## Parallel Work Rule

Potential parallel lanes in these packets are planning information, not
authorization. They may run only when the user or maintainer explicitly
authorizes subagents for the current task. A coordinator cannot self-authorize
them, and no packet permits agents to edit one worktree concurrently.

The coordinator assigns:

- branch and base SHA;
- owned files;
- shared-contract version;
- integration checkpoint;
- expected handoff artifact.

When two tasks share a file, they are sequential regardless of conceptual
independence.
