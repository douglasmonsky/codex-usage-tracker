# Lifecycle Recommendations Roadmap

Branch: `feature/lifecycle-recommendations`
Base: stacked after `feature/task-receipt-signals` until the read-model stack reaches `main`.

## Goals

- Turn aggregate usage, session, context-epoch, usage-impact, and task-receipt signals into cautious lifecycle guidance.
- Help users decide whether to continue the current thread, start fresh, compact/summarize, lower reasoning effort, inspect low-evidence work, or compare subagent/review work.
- Keep the recommendations aggregate-only and explain the evidence class behind each suggestion.
- Expose stable JSON through CLI/API surfaces that Codex skills can use conversationally.

## Non-Goals

- No raw prompt, assistant, tool output, command, patch, compaction replacement, or JSONL text persistence.
- No exact billing or exact productivity claims.
- No automatic workflow changes inside Codex.
- No frontend rewrite.
- No publishing, tagging, or main-branch merge.

## Privacy Constraints

- Persist and expose only aggregate counters, ids, timestamps, categorical signals, hashes, confidence labels, and derived recommendation metadata.
- Treat task receipt signals as evidence of activity, not proof that work succeeded.
- Raw evidence remains explicit, on-demand, redacted, and never written back to SQLite or generated dashboard HTML.
- Fixtures and docs must use synthetic data only.

## Recommendation Scopes

V1 should support these aggregate scopes:

- `call`: one selected model call.
- `work_session`: a cold-cache-bounded segment of a thread.
- `context_epoch`: a compaction-bounded segment inside a work session.
- `thread`: a resolved thread rollup.

## Recommendation Categories

V1 categories should be conservative:

- `continue_thread`: warm cache, low context pressure, and recent receipt signals make continuing reasonable.
- `start_fresh`: high context pressure, cache collapse, or stale/cold resume makes a fresh thread worth considering.
- `summarize_or_compact`: context is large but receipt evidence suggests useful work should be preserved before continuing.
- `lower_reasoning`: reasoning output is high relative to visible output and receipt evidence is weak.
- `inspect_low_evidence`: high cost/usage impact with little or no task receipt evidence.
- `inspect_delegated_work`: subagent/review/attached-thread work is materially contributing to usage.

Recommendation copy must use "consider", "inspect", or "review"; never claim an action is objectively required.

## Data Sources

- `usage_events`: exact token callback counters, cache ratio, cost/credit estimates, context pressure, call origin, thread/source metadata.
- `usage_impact`: observed allowance movement estimates and confidence/status.
- `thread_work_sessions`: cold-cache session boundaries.
- `thread_context_epochs`: compaction/context epoch boundaries.
- `task_receipts`: aggregate durable-output/task activity signals.
- `thread_summaries`: thread-level aggregate rollups.

## CLI / API / JSON Contracts

- Add `codex-usage-tracker lifecycle-recommendations`.
- Support filters:
  - `--record-id`
  - `--thread-key`
  - `--work-session-id`
  - `--context-epoch-id`
  - `--scope`
  - `--limit`
  - `--json`
- Add `/api/lifecycle-recommendations` with equivalent filters.
- Add schema id `codex-usage-tracker-lifecycle-recommendations-v1`.
- Include compact lifecycle recommendations in `/api/call` where practical.

## Dashboard

- In the call investigator, add a compact **Lifecycle guidance** section near the investigation readout.
- Show at most three recommendations by default.
- Each item should include:
  - action label
  - evidence scope
  - confidence
  - short reason
  - source chips such as `usage impact`, `cache`, `context`, `receipt`, `session`, or `epoch`
- Avoid adding another wide dashboard table column in V1.

## Implementation Checklist

- [x] M0: Add this roadmap/checklist before implementation.
- [x] M1: Audit current recommendation, session, epoch, usage-impact, and task-receipt fields.
- [x] M2: Add aggregate lifecycle recommendation model and scoring.
- [x] M3: Expose lifecycle recommendations through CLI/API/JSON contracts.
- [x] M4: Include compact lifecycle recommendations in `/api/call`.
- [x] M5: Add call investigator lifecycle guidance UI.
- [x] M6: Add tests for recommendation categories, scopes, contracts, dashboard payload, and privacy.
- [x] M7: Run validation and benchmarks.
- [x] M8: Commit, push, and open the branch PR without merging to `main`.

## Tests

- Warm-cache rows with receipt signals produce `continue_thread`.
- High context pressure plus useful receipt evidence produces `summarize_or_compact`.
- High context pressure or cold resume with weak receipts produces `start_fresh`.
- High reasoning output with weak receipts produces `lower_reasoning`.
- High cost or usage impact with no receipts produces `inspect_low_evidence`.
- Attached subagent/review rows produce `inspect_delegated_work`.
- CLI/API payloads include only aggregate metadata.
- Generated dashboard HTML does not include raw transcript, command, tool output, or JSONL fragments.

## Validation

- `python -m pytest tests/test_recommendations.py`
- `python -m pytest tests/test_dashboard_server.py`
- `python -m pytest tests/test_dashboard_payload.py`
- `python -m pytest tests/test_json_contracts.py`
- `python -m pytest tests/test_privacy.py`
- `python scripts/check_release.py`

## Known Caveats

- Lifecycle recommendations are diagnostic hints, not proof of successful or failed work.
- V1 should prefer false negatives over noisy false positives.
- Later dashboard work can promote these recommendations into richer session/epoch views after the JSON contract stabilizes.
