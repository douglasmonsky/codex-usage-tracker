# CK-08R1A — Freeze answer semantics and evidence closure
**Status:** Completed on merge — exact-main verification required in handoff
**Recommended owner:** `default answer-contracts`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Freeze `answer-semantics.v1` and `answer-truth-requalification.v2` before implementation.
**Dependencies:** This correction accepted/merged/exact-main.
**Owned files/interfaces:** New semantic/evidence contracts/schemas, Q-REV-03/Q-WF-02 operand sources, vectors/tests/links; no consumer/evaluator.
**Produces:** [`answer-semantics.v1`](../../../config/agent-kernel/answer-semantics-v1.json), its schema/vectors, and [`answer-truth-requalification.v2`](../../decisions/evidence/ck08r1a/answer-truth-requalification-v2.schema.json).
**Independent truth source:** Existing contracts plus retained reproductions; dirty code/grading is non-authoritative.
**Consumer seam:** R1B/C independently consume the exact semantic/vector digests; R1 recomputes both closures.
**Parallelism:** Serialized freeze complete; R1B/C fan out after merge/exact-main.
**Non-goals:** Implementations, stored answers, SQLite/query, projections/public/R3/R4/RG/09.

## Q-REV-03
Each side is its requested stable session; events obey optional half-open window. Missing required capability fails; available-empty is zero/empty.

- `completion_state`: `{left,right}` exact `{lifecycle_state,completion_basis}`. Open sessions remain explicitly open; absent/duplicate/malformed session fails.
- `turn_call_counts`: each side `{turn_count,call_count}` from distinct selected-session `turn_id`/`call_id`.
- `tool_metrics`: each side `{invocation_count,succeeded_count,failed_count,open_count}` from stable IDs/exact lifecycle; unknown fails.
- `state_change_metrics`: each side `{count,by_mutation_kind}` from state-change IDs; keys sorted.
- `resource_metrics`: each side `{count,by_kind}` over distinct resources linked by side tools or state changes; dangling/conflicting joins fail.
- `context_features`: side `null` when context-window measurement unavailable; else `{observed_call_count,distinct_context_window_tokens}` sorted. Capability-available empty calls yield `0/[]`; mixed missing fails.
- `delegation_metrics`: each side `{exclusive_tokens,descendant_tokens,inclusive_tokens}`. Exclusive is session four-class total; descendant is strict descendants by hierarchy; inclusive uses `exclusive_inclusive_scope_v1`. Missing hierarchy/token makes affected value `null`.
- `token_deltas`: `{uncached_input_tokens,cached_input_tokens,reasoning_tokens,output_tokens,total_tokens}` right-left via `side_by_side_delta_v1`; total sums four classes. Missing class makes it and total `null`.

Vectors move every named fact between sides and isolate its field.

## Q-WF-02
Boundary order is `(event_at_us_is_null,event_at_us,source_rank,source_order,event_kind_order,logical_id,transition_rank)`.

- Action: earliest tool **start** coordinate, any outcome.
- Success: earliest **terminal succeeded transition**, neither start nor canonical call.
- Mutation: earliest state-change coordinate.
- Tokens: four-class canonical-call total strictly before boundary in selected cohort.
- Present boundary/no prior call is `0`; absent is `null`; missing prior token is `null`; malformed start/terminal/lifecycle/order fails.

Contracts expose separate complete tool start/terminal coordinates. A canonical call between one tool's start and succeeded terminal transition is excluded from action and included in success. Require failed-then-success, absent, zero, missing-token, tie, delayed-mutation vectors.

## Closure/grading
Each lane records sorted path/SHA-256 roots, harness, consumer, all transitive local imports, and canonical closure digest. Replay recomputes membership/digests; drift/inaccessible fails first.

Evaluator closure forbids production derivation/formula/helpers, QueryService, SQLite/database/replay, grading/expected rows, R1B. Both lanes run sentinel-mutated grading rows (grading sentinels) and grading data inaccessible with baseline unchanged. Canonical-fact mutation changes both; production-source mutation cannot alter independent truth.

**Invariants:** Synthetic; exact Decimal/`null`/order/grade/provenance; missing != empty; R2 unchanged; sdist <=2,000,000.
**Required tests/checks:** Schema/vectors; closure drift/inaccessible; both grading conditions both lanes; fact/production mutations; authority/DAG; `just v/vc`; reviewer/CI/exact-main.
**Acceptance:** Every field/source/join/missingness/boundary/exclusion/digest/mutation rule bound without implementation.
**Failure/rollback:** Ambiguity/unenforceable closure keeps R1B/C,R1,R4/RG/09 blocked.
**Handoff:** SHA/contract-vector digests/locks/gates/risks/R1B-C readiness.
**Cleanup/docs:** Dirty 80/80 attempt remains non-authoritative.
**Suggested commit:** `docs: freeze answer semantics`
