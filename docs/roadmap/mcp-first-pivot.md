# MCP-First Product Pivot

This document is the normative release sequence for the MCP-first product
pivot. The approved [design](../superpowers/specs/2026-07-21-mcp-first-product-pivot-design.md)
and [implementation roadmap](../superpowers/plans/2026-07-21-mcp-first-product-pivot.md)
remain the detailed contracts for the program.

The merged `2026-07-19` MCP-first dashboard transition is completed foundation
input. It is not the active roadmap and does not authorize work outside this
program.

## Product Direction

MCP is the primary analysis interface. Deterministic application services
perform calculations and classifications, and the live React dashboard becomes
a supporting Evidence Console for inspecting exact local evidence. The CLI
continues to support setup, automation, recovery, export, and compatibility.

## Release Sequence

| Release | Outcome | Compatibility state |
| --- | --- | --- |
| `0.22.0` | Stable MCP core profile, shared contracts, truthful positioning, and generic job facade | Existing dashboard and old tools still work; old tools move to the `full` profile. |
| `0.23.0` | Evidence Console becomes the default; CLI and HTTP v2 ship | Old pages remain direct-link routes and old CLI names remain aliases. |
| `0.24.0` | Architecture, database integrity, context offsets, and infrastructure hardening | Old pages are notice-only; old APIs and aliases remain supported. |
| `0.25.0` | Expired dashboard, static, MCP, CLI, and HTTP compatibility is removed | Only documented stable and advanced surfaces remain. |
| `0.26.0` | Feature-free stabilization and pre-1.0 contract hardening | No new public surface; migration and package gates prove the final state. |

If another minor release ships before program execution begins, every planned
minor shifts by the same amount. Task order and compatibility duration do not
change.

## Surface-Growth Freeze

During the pivot, do not add a dashboard workspace, top-level MCP concept,
top-level CLI command, runtime dependency, or SQLite table unless the approved
roadmap names it. A design amendment is required before unplanned public-product
surface growth. The stabilization release is feature-free.

Existing raw-context controls, loopback request guards, deterministic
accounting, and aggregate-first shareable outputs remain unchanged unless a
roadmap task explicitly changes them. Examples, fixtures, and screenshots must
remain synthetic.

## Compatibility Policy

Compatibility is bounded by [the deprecation ledger](../deprecations.md). An
item cannot be removed before its recorded removal release or while its
compatibility test fails. Semantic changes require an explicit contract revision
or breaking-change notice; aliases must not silently change meaning.

## Execution

Each task uses a focused `pivot/<task-number>-<slug>` branch, starts with the
named failing tests, implements only its declared interfaces, and records
verification and risks in the
[execution ledger](mcp-first-pivot-execution.md). Release, compatibility, schema,
and public-contract changes require an independent reviewer before merge.
