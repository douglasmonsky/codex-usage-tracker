# CK-08R3A — Implement bounded EvidenceService physical queries

**Status:** Completed on merge; PR #417 hosted-green and exact-main verified at `38537f6cee42ad4ba2fb6e45354e410053c7a7cd`

**Recommended owner:** `worker evidence-physical-query`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Replace the retained unbounded EvidenceService physical plan with bounded, query-only, session-scoped keyset execution.

**Historical blocker:** R3 commit `a28e9cdbff8e48d334712a449fdcee111c725673` and artifact `ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471` exposed unbounded plans. PR #417 supersedes the rejected `718ff703…` and entity-leading `659c1957…` candidates while preserving them as read-only evidence.

**Dependencies:** Accepted CK-08R0 plus all linked CK-08R3A authorities merged and exact-main verified before implementation acceptance.

**Owned files/interfaces:** The exact atomic seven-production/nine-support cohort bound by repository authority, including EvidenceService, publication rank/order persistence, lifecycle storage, evidence-order DDL/schema, synthetic fixtures, and focused physical tests. No unrelated query, projection, public API, package, roadmap, CK-07, R1, R3, R4, RG, or CK-09 implementation.

**Produces:** Accepted bounded EvidenceService SQL, exact physical-plan tests, and linked synthetic evidence; no CK-08R3 scale artifact.

**Independent truth source:** A synthetic evaluator that imports no production query helper and independently applies selector, view, cursor, seven-part order, and `limit + 1`.

**Consumer seam:** `EvidenceService.read()` remains a query-only single snapshot; scope, keyset order, and `limit + 1` precede decoding.

**Parallelism:** The historical implementation lane is closed. CK-08R3 may start only after this accounting merge makes it Ready; CK-07R1, R1B, and QG1 remain independently held.

**Non-goals:** New production behavior, migration or compatibility paths, selector/API expansion, projection admission, budget or timing changes, CK-07/R1/QG1 changes, CK-08R3 scale execution, R4/RG accounting, or CK-09 dispatch.

**Invariants:** Preserve selector/version/view/direction/cursor/publication semantics; ties, missing, late, base, and tail behavior; gap-free query-only pagination; exact zero-based nonnegative source-rank equality, including valid rank 0 and preserved rank >0; at most 100 rows and 16,384 bytes; synthetic data only; wheel at most 1,000,000 bytes and sdist at most 2,000,000 bytes.

**Required tests/checks:** First/deep forward/backward EXPLAIN rejects `SCAN stream`, `MATERIALIZE model_calls_visible`, `AUTOMATIC COVERING INDEX`, and every `USE TEMP B-TREE FOR ORDER BY` except the exact portable one-row session-branch exception. The exception requires full plan ids/parents, unique leftmost session-event ancestry, and the contiguous session/occurrence/manifestation equality chain. Validate independent rows/order/decode bounds, valid active `rate_card` summary plus empty timeline/calls pages, authority identities, GitNexus, `just v`, `just vc`, one reviewer, hosted CI, merge, and exact-main.

**Acceptance:** Exact source/support, DDL/schema, fixture, rank/provenance, and authority identities match byte-for-byte. Session-scoped first pages and all other deep pages remain marker-free and bounded across 0/1,000/5,000 unrelated lifecycle rows. SQLite 3.45.1 may show at most one structurally proven deep timeline/allowance session-branch temp sort; all result truth, cursor, callback, and selector bounds remain invariant. Predecessor/foreign artifacts are rejected before application query, mutation, repair, or promotion without migration or compatibility views.

**Completion evidence:** PR #417 reused the existing worker and PR lineage, passed hosted run `30972312554` for Console and Python 3.10/3.14, and squash-merged at `38537f6cee42ad4ba2fb6e45354e410053c7a7cd`. The selected 16-path cohort had zero authority identity mismatches. Premerge focused validation passed 136 tests with one skip; dual SQLite 3.45.1/3.53.3 passed 12/12; `just vp`, `just v`, `just vc`, build, distribution, release-safety, and the single final reviewer passed. Fresh exact-main was clean with exact identities and 46 authority/scope/documentation tests passing. A duplicate postmerge full runtime rerun did not complete because host ENOSPC caused SQLite disk-I/O/temp-file failures; no product assertion failed, so this remains an environment-only limitation rather than a claimed passed rerun.

**Failure/rollback:** Preserve the first divergence or gate failure and stop; never blind-copy a candidate, weaken physical bounds, or treat an unchanged retry as evidence.

**Handoff:** Record SHA, PR/CI, identities, plans, measurements, review, exact-main, risks, and environment limitations. The coordinator may create an uncreated CK-08R3 task only after the merged machine DAG records it Ready.

**Cleanup/docs:** Preserve historical blockers and the R3A→R3→R4 dependency chain.

**Suggested commit:** `docs: record CK-08R3A acceptance`
