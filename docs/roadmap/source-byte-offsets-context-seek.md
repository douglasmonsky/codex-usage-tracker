# Source Byte Offsets And Context Seek Roadmap

Branch: `refactor/source-byte-offsets-context-seek`

## Goals

- Persist safe source byte offsets for aggregate `usage_events` rows.
- Let explicit call-investigator evidence loading seek directly to the selected turn instead of scanning large JSONL logs from the beginning.
- Keep old databases usable when offset fields are null.
- Add diagnostics that prove whether a seek path or fallback scan was used.

## Implementation Checklist

- [x] M0: Create this roadmap/checklist before implementation.
- [x] M1: Add nullable source byte and turn-start offset fields to `usage_events`.
- [x] M2: Bump schema/parser adapter versions so existing indexes repair and reparse safely.
- [x] M3: Capture source byte offsets and turn-start cursors during binary JSONL parsing.
- [x] M4: Make context loading seek to selected turns when offsets and source metadata are valid.
- [x] M5: Keep safe fallbacks for missing offsets, changed source metadata, and compaction-history loads.
- [x] M6: Add parser, context, migration, privacy, and source-log benchmark coverage.
- [x] M7: Run full branch validation.
- [x] M8: Commit, push, and open the branch PR without merging to `main`.

## Non-Goals

- No task receipts.
- No Sessions tab.
- No frontend read-model rewrite.
- No raw evidence cache.
- No raw text persistence.
- No publishing, tagging, or main-branch merge.

## Privacy Constraints

- Do not persist prompts, assistant messages, tool output, raw JSONL fragments, compaction replacement text, or reconstructed transcript content.
- Persist only aggregate counters, categorical metadata, stable ids, timestamps, line numbers, byte offsets, and derived diagnostics.
- Raw evidence remains explicit, on-demand, redacted, and not written back to SQLite or generated dashboard HTML.
- `parser_state_json` must remain aggregate-only and must not include prompt, assistant, or tool text.

## Schema Changes

Add nullable, repairable fields to `usage_events`:

- `source_byte_start INTEGER`
- `source_byte_end INTEGER`
- `turn_start_line INTEGER`
- `turn_start_byte INTEGER`

Migration requirements:

- Bump the SQLite schema version.
- Add columns without breaking existing databases.
- Leave old rows with null offsets and route them through the existing fallback scan.

## Parser Work

- Read JSONL in binary mode and track each line's byte start/end.
- Store current turn line and byte cursor when parsing `turn_context`.
- Attach source byte offsets and turn-start offsets to emitted token-count usage events.
- Include current turn line/byte cursor in `parser_state_json`.
- Never persist raw JSONL line text.

## Context Loader Work

- Use `turn_start_byte` and `source_byte_end` when both are available and source metadata still matches.
- Seek directly to the turn start and read only through the selected token-count event.
- Fall back to the existing line scan when offsets are missing, source metadata changed, seek fails, or the offset points to invalid JSON.
- Return diagnostics:
  - `seek_used`
  - `seek_fallback_reason`
  - `source_scan_ms`
  - `bytes_scanned`
  - `lines_scanned`

## Tests

- `source_byte_start` and `source_byte_end` point to a valid JSONL token-count line.
- `turn_start_byte` points to a valid `turn_context` line.
- Context loading uses the seek path when offsets are available.
- Context loading falls back when offsets are missing.
- Context loading falls back when source file metadata changed.
- `parser_state_json` does not contain raw prompt, assistant, or tool text.
- Migration from the previous schema leaves old rows usable.

## Benchmarks

- Compare context load for early, middle, and late token-count lines using synthetic source logs.
- Assert the late-line seek path is materially faster than scanning from the beginning on large synthetic logs.
- Keep benchmark data synthetic-only; do not read real Codex logs.

## Known Fallback Behavior

- Existing indexed rows without byte offsets continue to work through line scanning.
- If the source JSONL file changes after indexing, context loading should fall back safely and report refresh-recommended diagnostics.
- If byte offsets are corrupt or stale, context loading should fall back rather than returning partial or misleading evidence.
