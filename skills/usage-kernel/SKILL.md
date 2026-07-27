---
name: usage-kernel
description: Use the six Codex Usage Tracker tools for exact local usage facts, bounded exploration, allowance observations, and evidence timelines.
---

# Codex Usage Tracker

Use the tracker as a factual local data plane. The tools return exact or
explicitly graded facts; the model owns inference, explanation, and
recommendations.

1. Call `usage_status` once. If a committed generation exists, query it
   immediately even when refresh is active or recommended.
2. Call `usage_refresh` only when freshness matters. Reuse the returned job;
   never start a duplicate.
3. Prefer one batched `usage_query` request with only the dimensions, measures,
   filters, and limits needed for the question.
4. Use returned grades, coverage, counts, and selectors. Do not infer waste or
   productivity from token totals alone.
5. Call `usage_evidence` only with an exact logical selector. Use `live=true`
   for the same timeline in live mode.
6. Use `usage_job_status` with a bounded `wait_seconds` value so the host waits;
   do not short-interval poll from the model.
7. Use `usage_allowance` for observed allowance facts and preserve its
   provenance and limitations.

Never inspect raw logs as a fallback, invent missing selectors, claim narrative
findings the tools did not return, or expose prompts, reasoning, tool
arguments/output, secrets, or local paths.
