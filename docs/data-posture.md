# Data Posture

Normal refresh indexes aggregate counters and the existing bounded local content/event index; aggregate-only commands retain the older posture; shareable outputs follow existing behavior.

This is a documentation clarification, not a runtime or privacy change. Codex
Usage Tracker remains local-first and does not upload logs, indexed content, or
reports.

## Normal Refresh

Normal `refresh`, `rebuild-index`, setup refresh, and MCP refresh behavior can
populate both:

- aggregate usage accounting, model and effort metadata, source provenance,
  thread summaries, pricing and allowance facts, diagnostic labels, and other
  deterministic derived records; and
- the existing bounded local content/event index for explicit local
  investigation, including normalized turns, bounded fragments, tool calls,
  command labels, file-event identities, parser metadata, and source provenance.

These records stay in the user-owned SQLite database. The bounded content/event
index is not a hosted collection system and does not move the original Codex
logs.

## Aggregate-Only Posture

Use either command when the older aggregate-only SQLite posture is required:

```bash
codex-usage-tracker refresh --aggregate-only
codex-usage-tracker rebuild-index --aggregate-only
```

For MCP refresh, use the documented `aggregate_only=True` option. This changes
what the refresh indexes; it does not redefine the normal default.

## Shareable Outputs

Existing shareable-output behavior remains aggregate-first. Default CSV,
generated dashboard HTML, support bundles, screenshots, aggregate JSON reports,
recommendation reports, allowance exports, and source-coverage reports omit
indexed snippets and raw context.

Explicit local content investigation and selected-context actions are separate
surfaces. Treat their results as private unless reviewed for the intended
recipient. See [Privacy](privacy.md) for field-level storage, redaction modes,
localhost controls, raw-context opt-ins, and the sharing checklist.

## Deterministic Analysis

MCP, CLI, and the Evidence Console consume deterministic application results.
The model does not calculate totals or infer statistical decisions from raw
transcript rows. Material conclusions should state scope and limitations and
link to bounded local evidence when verification is useful.
