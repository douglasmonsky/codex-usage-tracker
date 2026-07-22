# Evidence Console

The Evidence Console is the supporting verification interface for MCP-first
analysis. Deterministic application services calculate, classify, and select
evidence; the console displays the exact local records and time series behind
those results.

The stable Evidence Console direction is limited to these surfaces:

- `Home`: readiness, freshness, headline status, recent high-confidence
  findings, and suggested analysis questions.
- `Explore`: bounded Calls and Threads evidence browsing with shared scope and
  filtering.
- `Limits`: current allowance status, observed history, supported changes,
  methodology, and evidence.
- `Settings`: setup, local service state, language, paths, pricing status, and
  explicit compatibility controls.
- `Evidence`: contextual detail for a selected finding, call, thread, or
  allowance record.

## Evidence Targets

MCP results may include a structured dashboard target with an absolute
localhost URL, a relative URL, and fallback launch guidance. Prefer the absolute
URL when present. Otherwise, follow the fallback instruction before using the
relative target. Never invent a host or infer that an installed plugin or
healthy dashboard service proves MCP availability in the current task.

Targets preserve the analytical scope and use reviewed selectors. Opening a
target must not broaden a date range, switch from active sessions to all
history, or silently reveal indexed or raw content.

## Migration Status

The current release can still expose legacy dashboard workspaces during the
bounded compatibility window. Those routes are documented only through the
[Dashboard Guide compatibility pointer](dashboard-guide.md) and the normative
[Deprecations ledger](deprecations.md). They are not part of the stable Evidence
Console surface and receive no unplanned feature growth.

## Local And Shareable Data

The live console reads local SQLite-backed aggregate data and explicit bounded
evidence endpoints. Indexed snippets or selected raw context appear only through
documented local actions. Generated HTML, screenshots, exports, support bundles,
and other shareable outputs keep their existing aggregate-first boundaries.
Review [Data Posture](data-posture.md) and [Privacy](privacy.md) before sharing an
artifact.
