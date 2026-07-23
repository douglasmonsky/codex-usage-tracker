# Evidence Console

The Evidence Console is the supporting verification interface for MCP-first
analysis. Deterministic application services calculate, classify, and select
evidence; the console displays the exact local records and time series behind
those results.

The stable Evidence Console direction is limited to these surfaces:

- `Home`: a Usage Pulse summary of calls, tokens, cache reuse, and estimated
  cost, followed by readiness, freshness, recent high-confidence findings, and
  suggested analysis questions.
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

Use `codex-usage-tracker open --target-json '<dashboard-target-v2 JSON>'` when
an MCP result supplies only structured target data. Exact historical bookmark
normalization and all four selector forms are documented in
[Evidence Console Route Migration](evidence-console-route-migration.md).

Limits labels observed facts, descriptive estimates, and statistically
supported changes explicitly. Persisted allowance intervals and supported
change rows link to the contextual Evidence route when the matching persisted
analysis and interval identifiers are available. The default history controls
remain bounded; all-history, custom-range, granularity, and legacy static
controls sit under an Advanced disclosure. These presentation changes do not
alter allowance calculations or introduce another detector.

Settings reports the local installation and launcher state without claiming
that MCP tools are exposed in the current Codex task. It also shows the
configured MCP profile, local source/index roles, pricing and rate-card status,
language and history defaults, and localhost service state. Temporary Labs
routes are off by default and appear only in Settings → Advanced after enabling
the browser-local **Show compatibility and Labs links** preference. Each Labs
entry identifies its maturity, lifecycle, replacement MCP operation, and
direct compatibility link; Labs never join persistent navigation.

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
