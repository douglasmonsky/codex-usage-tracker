# Parallel Backfill Parser Roadmap

Branch: `perf/parallel-backfill-parser`

## Goal

Speed up initial and large backfill refreshes by parsing multiple changed source files concurrently while keeping SQLite writes and read-model maintenance serialized and deterministic.

## Non-Goals

- Do not parallelize SQLite writes.
- Do not persist raw evidence, prompts, assistant text, tool output, raw JSONL fragments, or reconstructed transcript content.
- Do not add filesystem watchers.
- Do not change live refresh semantics for small append-only updates.
- Do not change existing CLI/API output contracts except for additive refresh-worker controls or stats.

## Privacy Constraints

- Worker inputs are source paths and parser cursor metadata only.
- Worker outputs are `ParsedUsageFile` aggregate events, parser stats, parser state, and metadata.
- No raw line text, prompt text, assistant text, tool output, command text, or JSONL fragments may be stored in SQLite, fixtures, generated dashboard HTML, or new worker result structures.
- Raw evidence remains explicit and on-demand through the existing context/evidence path.

## Design

- Keep the existing sequential parser path for small live refreshes.
- Use a worker pool only when refresh planning finds enough parse work to make concurrency worthwhile.
- Keep database writes in the main process and inside the existing controlled transaction.
- Aggregate worker parser statistics in deterministic file order.
- Preserve existing append cursor behavior: `parsed_until_byte`, `parsed_until_line`, parser adapter invalidation, truncation/full-reparse fallback, and restored `parser_state_json`.
- Fail clearly if a worker parse fails; do not silently drop files.

## Configuration

- Add `--refresh-workers N` to refresh-capable CLI paths where appropriate.
- Add `CODEX_USAGE_TRACKER_REFRESH_WORKERS` as an environment fallback.
- Default to sequential for normal live append refresh unless many files need parsing.
- Use a conservative automatic cap such as `min(4, os.cpu_count())`.

## Validation

- Parallel output must match sequential output for synthetic source logs.
- Stats aggregation must match sequential totals.
- Parser errors must surface with the source file path.
- No SQLite connection crosses worker boundaries.
- Small append refreshes should remain sequential by default.
- Large multi-file refreshes should use parallel parsing when configured or above threshold.

## Implementation Checklist

- [x] M0: Add this roadmap/checklist before implementation.
- [x] M1: Inspect current refresh planning and parser result boundaries.
- [x] M2: Add parser worker-pool helpers with deterministic result ordering.
- [x] M3: Add CLI/config controls for refresh worker count.
- [x] M4: Integrate worker parsing into the refresh delta path without parallel DB writes.
- [x] M5: Add tests for sequential/parallel equivalence, stats aggregation, worker errors, and default threshold behavior.
- [x] M6: Add benchmark coverage for multi-file backfill refresh.
- [x] M7: Run validation and document results.
- [ ] M8: Commit, push, and open the branch PR without merging to `main`.
