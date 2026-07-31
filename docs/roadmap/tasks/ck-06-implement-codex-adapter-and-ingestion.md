# CK-06 — Implement Codex adapter and bounded ingestion

**Status:** Completed
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

**Evidence:** [codex-adapter-ingestion-evidence.json](../../decisions/evidence/ck06/codex-adapter-ingestion-evidence.json)

**Implementation record:** The `codex-jsonl` adapter declares capability mask
`127` across allowance observations, model usage, session hierarchy, source
occurrences, state changes, tool lifecycle, and valuation. Structural source
records are normalized to integer UTC microseconds, and the synthetic fixture's
zero-based allowance ordinal is explicitly normalized to the positive storage
ordinal with basis `upstream_zero_based_plus_one`. The adapter emits no prompt,
response, reasoning, command, patch, or tool-output body. Publication,
promotion, refresh, recovery, projections, MCP, and release work remain CK-07
or later responsibilities.

**Validation record:** Focused adapter tests pass for complete/partial,
malformed, replacement, truncation, moving-tail, duplicate, parent, token,
resource, state-change, allowance, and 1/2/4/8-worker cases. The full
synthetic stream reproduces 100 canonical model calls and 102 occurrences;
the four token classes remain separate and cached totals remain NULL when five
calls lack cached input. Review accounting and final CI/main verification are
recorded in the evidence file after closeout.

**Failure/rollback:** Reject affected range/source and preserve prior cursor.
Delete unpublished new artifacts only.

**Cleanup/docs:** Record actual capability mask and any upstream field
limitation.

**Suggested commits:**

1. `feat: add Codex source adapter`
2. `perf: add bounded deterministic ingestion`

## Corrective requalification

CK-06 correctly exposed the canonical facts that revealed the CK-03 mismatch.
Its implementation remains complete, while
[CK-07A](ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md) must replay
the adapter against the corrected fixture, prove grading metadata cannot become
canonical facts, and refresh fixture digests, counts, measurements, and
evidence. A code change is admitted only if that unchanged replay exposes a
concrete adapter deficiency.

CK-07A requalified CK-06 ingestion against all 80 corrected variants without
an adapter implementation change. Historical CK-06 evidence remains
preserved; current seam authority is the
[CK-07A evidence](../../decisions/evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json).
