# CK-06 — Implement Codex adapter and bounded ingestion

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Translate Codex JSONL sources into canonical proposed changes with
bounded discovery, cursors, normalization, and source lifecycle.

**Why:** Correct fast tails begin at the adapter/source boundary.

**Controls:** `ADAPTER_CONTRACT.md`, CK-02/CK-03/CK-05.
**Dependencies:** CK-05.

**Scope and expected files:**

- `adapters/contracts.py`, `adapters/codex_jsonl/**`;
- source inventory/selection/cursor modules;
- parser worker pipeline and deterministic merge;
- canonicalization/change-set builder;
- adapter and ingest tests/benchmarks.

**Schema changes:** Writes through CK-05 repositories only; additive source
manifest/cursor tables must match selected decision.
**API changes:** Internal typed observation and proposed-change stream.

**Non-goals:** Publication promotion, projections, raw-body persistence,
redaction/sanitization, second adapter.

**Invariants:** Complete-record cursors; no parse of certain deferred history;
malformed isolation; deterministic output under parallel parsing; tool
transport/operation/resource separation; state-change non-attribution; every
allowance observation retained.

**Tests/benchmarks:** All source states, moving partial line, late event,
duplicate manifestations, parent discovery, lifecycle fragments, four tokens,
resource normalization, state change after cumulative activity, 1/2/4/8 parser
workers.

**Acceptance:** CK-03 adapter/accounting/source oracles pass; 30/90/year/all-time
selected bytes and coverage exact; parsing scales without nondeterminism; no
raw bodies enter proposed records.

**Failure/rollback:** Reject affected range/source and preserve prior cursor.
Delete unpublished new artifacts only.

**Cleanup/docs:** Record actual capability mask and any upstream field
limitation.

**Suggested commits:**

1. `feat: add Codex source adapter`
2. `perf: add bounded deterministic ingestion`
