# CK-08R3A — Implement bounded EvidenceService physical queries

**Status:** Ready; CK-08R0 accepted/merged/exact-main verified at `306cef37eea2ae017aca824d898cc435f7e1bea0`

**Parent:** CK-08R3 implementation prerequisite

**Recommended owner:** `worker evidence-physical-query`; Sol

**Authority:** [TASK_PACKETS.md](../TASK_PACKETS.md),
[REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md),
[AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Apply scope/order/keyset and `LIMIT request.limit + 1` in SQLite
before decode, without semantic/budget changes.

**Blocker:** Retained commit `a28e9cdbff8e48d334712a449fdcee111c725673`
artifact `docs/decisions/evidence/ck08r3/evidence-scale-qualification.json`,
SHA-256 `ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471`,
stopped first/deep session `pre_scale_explain`: `SCAN stream`,
`MATERIALIZE model_calls_visible`, `AUTOMATIC COVERING INDEX`, and outer
`USE TEMP B-TREE FOR ORDER BY` preceded `LIMIT`. No scale/admission or
production edit ran.

**Dependencies:** Accepted CK-08R0. Consume `corrective-gates-v1` and current
request/page, selector/provenance, cursor/publication contracts from exact main;
never cherry-pick CK-08R3.

**Owned files/interfaces:** Evidence physical lock only:
`src/codex_usage_tracker/agent_kernel/evidence/service.py`, focused
`tests/agent_kernel/evidence/test_service.py` plus optional sibling; page SQL/
branches/parameters/decode. Forbid QueryService, registry/compiler/
contracts, cursor codec/version, selectors, DDL/index/publication, R3 evidence,
schema/projection and public/package APIs.

**Produces:** Physical fix plus structural/EXPLAIN tests; no scale/admission.

**Independent truth source:** Test-only relation evaluator uses no production
query/helper; it forms typed events, applies selector/view/cursor,
orders by `(time_missing, COALESCE(event_at_us,0), source_rank, source_order,
event_kind_order, logical_id, transition_rank)`, slices `limit + 1`, and
compares rows/order.

**Consumer seam:** `EvidenceService.read()` keeps one query-only snapshot;
`_page_rows()` applies scope/view/order/publication-bound keyset and final
`LIMIT ?` before decoding `limit + 1`. Byte shrink/CursorCodec stay.

**Parallelism:** R1/R2/07R1/QG1 stay independent; R3/R4/RG/09 stay blocked.

**Non-goals:** R3 scale, R2 paging, DDL/index/schema/backbone,
`evidence_timeline_current`, projections/counts/APIs/budgets, R4 and CK-09.

**Invariants:** Preserve 14 selectors, six provenance kinds, boundary pairs,
seven views/directions and that order. Cursor binds version, plan/version,
publication, request digest, last order and expiry; tamper/replacement/stale
fail closed. Tie/missing/late/replacement/base/tail cases stay gap-free.
No-refresh/query-only/one-snapshot/exact-count-off, 100 rows, 16,384 bytes,
catalog counts and 820,000-byte sdist remain fixed.

**EXPLAIN acceptance:** First/deep session pages both directions plus other
representative scopes omit all four blocker details. High-cardinality branches
use existing named PK/scope-order indexes; singleton lookups may use PKs.
Assert keyset, final `LIMIT ?`, bound/decode `limit + 1`, normalized failure
and no permissive version wildcard.

**Required tests/checks:** CK-07A builders plus synthetic tie/missing/base-tail/
lifecycle/late/replacement/selector/direction cases; no scale/real data.
Bootstrap/GitNexus; focused service/structural/EXPLAIN/semantic/cursor/byte/
authority; diff/release; `just v/vc`; staged `detect_changes`; one reviewer/PR;
hosted CI; squash merge; attached exact-main.

**Acceptance:** Truth/production rows/order match; reversible gap-free pages
are bounded; query-only/cursor/byte/release gates and lock hold.
Authorizes only R3, never scale/projections.

**Failure/rollback:** On forbidden plan/mismatch or lock/budget need, retain
SQL/parameters/plan/fixture digest, stop/create no R3; revert service/tests
without migration.

**Handoff:** After accepted merge/CI/exact-main, create exactly one user-owned
`test_engineer evidence-scale` task from new main with merge SHA, blocker
artifact/digest, lock, fixtures/budgets, truth/seam, EXPLAIN/order/cursor,
checks/risks/stops. It may create R4 only after R1/R2/R3/07R1 complete.

**Cleanup/docs:** Link merge/exact-main from R3; keep blocker historical.

**Suggested commit:** `fix: bound evidence physical queries`
