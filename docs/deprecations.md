# Deprecations And Kernel Cutover

This is the normative removal and upgrade ledger for the
[Product Kernel Reset](roadmap/product-kernel-reset.md). The previous
compatibility ledger is preserved as
[historical evidence](roadmap/archive/2026-07-21-mcp-first-pivot/deprecations.md).

Codex Usage Tracker is still beta. Release 0.26.0 is an intentional breaking
cutover to a smaller factual data kernel. It provides migration documentation,
side-by-side cache construction, rollback metadata, and preservation of the old
cache file, but it does not ship runtime adapters for retired tools, routes,
commands, profiles, tables, or payloads.

## Removal Ledger

| Public name or route | Replacement | Owner | Deprecated release | Final supported release | Removal release | Compatibility test | Migration example |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `usage_analyze` and `analysis.v2` | Batched `usage_query`, exact `usage_evidence`, and model-authored inference | Kernel query and skill maintainers | `0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Six-tool catalog, forbidden-name, golden-query, and installed-plugin tests | Query rankings or comparisons, narrow the candidates, resolve exact selectors with `usage_evidence`, and let Codex explain the graded facts. |
| `full` and `developer` MCP profiles, deprecated aliases, compression tools, diagnostic tools, and recommendation tools | Exactly six default tools: status, refresh, query, evidence, allowance, and job status | MCP interface maintainers | `0.22.0`–`0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Installed catalog and package forbidden-inventory tests | Remove the profile environment variable and use the matching bounded `usage_query` dataset or operational core tool. |
| Analysis, investigation, diagnostics, reports, recommendations, compression, and usage-drain HTTP routes | New versioned kernel query, evidence, allowance, refresh/job, status, and live-stream routes | HTTP interface maintainers | `0.23.0`–`0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Route inventory, direct kernel API contract, and forbidden-route tests | Replace server-authored findings with a bounded query batch and open returned selectors in the Evidence Console. |
| Historical unversioned and `/api/v2/` route families | New kernel API version selected and frozen in K6 | HTTP interface maintainers | `0.23.0`–`0.26.0` upgrade notice | `0.25.x` | `0.26.0` | New-route schema fixtures plus absence tests for old route families | Update local clients to the 0.26 API reference; do not assume v2 payload names carry forward. |
| CLI command or alias: `analyze` and historical top-level names | `query`, `export`, `open`, explicit `refresh`, service, configuration, and repair operations | CLI interface maintainers | `0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Primary-help snapshot, removed-alias, and installed CLI smoke tests | Use `query` for structured facts, `export` for durable data, and `open` for the exact Evidence Console. |
| Experimental schema-version-39 cache and its migration chain | Side-by-side kernel schema-v1 cache | Kernel storage maintainers | `0.26.0` upgrade notice | `0.25.x` | `0.26.0` active-runtime use | Staging-build, equivalence, integrity, atomic-promotion, rollback, and old-file-preservation tests | Allow 0.26 to build the new cache beside the old file; keep the old file until qualification succeeds and delete it only through an explicit user action. |
| Default content fragments, FTS, context search, and content-index refresh | Base structural facts; optional separate content-evidence database no earlier than 0.27 | Privacy and evidence maintainers | `0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Default-schema, package forbidden-inventory, privacy, and optional-database isolation tests | Use exact structural bytes and activity facts in 0.26; explicitly opt in to the separately stored 0.27 content-composition capability if needed. |
| Persisted findings, analysis results/jobs, compression runs, diagnostic snapshots, recommendation state, and usage-drain state | Generation-consistent query results and disposable generation-keyed read caches only when measured | Kernel application maintainers | `0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Table inventory, import-boundary, forbidden-schema, and no-implicit-job tests | Save a typed query specification or export its rows; do not persist a server interpretation as product truth. |
| Retired Console workbenches and compatibility routes | `Live`, `Explore`, `Evidence`, `Limits`, and `Settings` | Evidence Console maintainers | `0.23.0`–`0.26.0` upgrade notice | `0.25.x` | `0.26.0` | Browser route inventory, deep-link, warm-reopen, and forbidden-asset tests | Open the focused Console and use Explore for bounded data or Evidence for an exact selector. |
| Legacy static dashboard | Evidence Console | Evidence Console maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `tests/compatibility/test_removed_static_dashboard.py` and installed server smoke | Run `codex-usage-tracker open`. The 0.26 cutover removes any remaining redirect or migration-only static route. |

## Exact Retired MCP Inventory

The profile row above covers every name in this inventory. They remain listed
so package and release checks can distinguish an intentional beta removal from
an accidental catalog omission. Listing a name does not preserve its runtime
handler.

- `subagent_usage`
- `refresh_usage_index`
- `usage_refresh_start`
- `usage_refresh_status`
- `usage_doctor`
- `usage_summary`
- `usage_calls`
- `usage_call_detail`
- `usage_threads`
- `usage_report_pack`
- `usage_dashboard_recommendations`
- `usage_allowance_history`
- `usage_allowance_diagnostics`
- `usage_allowance_status`
- `usage_allowance_series`
- `usage_allowance_evidence`
- `usage_allowance_analysis`
- `usage_allowance_analysis_status`
- `usage_compression_start`
- `usage_compression_status`
- `usage_compression_profile`
- `usage_compression_candidates`
- `usage_compression_candidate_detail`
- `usage_compression_simulate`
- `usage_recommendations`
- `session_usage`
- `most_expensive_usage_calls`
- `usage_pricing_coverage`
- `usage_source_coverage`
- `usage_repetition_scan`
- `usage_command_loop_scan`
- `usage_file_churn_scan`
- `usage_repeated_file_rediscovery`
- `usage_shell_churn`
- `usage_large_low_output_calls`
- `usage_suggest_investigations`
- `usage_investigate`
- `usage_action_brief`
- `usage_test_hypotheses`
- `usage_context_bloat_scan`
- `usage_investigation_walk`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

## Exact Cross-Surface Inventory

K1 creates `config/kernel-retired-surfaces-v1.json` before kernel implementation.
It is the versioned exact inventory for MCP names, HTTP routes, CLI commands and
aliases, schemas, tables, Console routes, source/assets, and package data. Every
entry records its surface type, exact name, replacement or `none`, final
supported release, removal release, and absence or migration test.

K6 must map every new adapter to that manifest. K9 must fail if the live source
contains an unclassified public surface or if a manifest entry lacks its named
test. The 0.26 upgrade guide is generated or checked against the same entries.

## Cutover Rules

- K6 freezes the new route prefix and machine-readable contracts behind an
  internal cutover selector. Historical schema identifiers cannot be reused
  with changed semantics, and public 0.25 defaults stay unchanged through K8.
- No CLI compatibility surface may be removed before its removal release. K9
  activates the kernel defaults and performs the documented removals in the
  same changeset, only after the replacement contracts pass.
- K9 owns the exact deletion/preservation inventory. A deprecated runtime name
  still present after K9 is a release blocker unless the roadmap is amended.
- K10 must prove side-by-side construction, accounting equivalence, integrity,
  atomic promotion, and rollback before Release 0.26.0.
- The old cache file is retained for rollback and is never silently deleted.
  Retaining the file does not require shipping code that reads its old schema.
- CSV/JSON exports selected by the K6 contract remain supported. Export
  semantics are tested against the accounting oracle, not assumed from old
  implementation paths.
- Exact Evidence Console logical selectors survive rebuild. SQLite row IDs and
  historical route URLs do not.
- Removal documentation is the beta migration surface. Runtime compatibility is
  not.

## Cutover State Machine

The operational sidecar owns one atomically replaced control record:

- `absent`: no active kernel; status reports that an explicit first build is
  required.
- `building`: a staging path and refresh job are visible, but queries never open
  staging.
- `ready`: staging passed equivalence, integrity, privacy, and performance gates
  but is not active.
- `active`: reads use the named kernel path and committed generation.
- `failed`: the failure is visible and the prior active pointer, if any, is
  unchanged.

Only CLI `refresh`, MCP `usage_refresh`, or the Console Refresh action starts the
first build. Install, setup, status, query, evidence, allowance, service
startup, and browser mount do not.

Promotion changes the active pointer only after `ready`. An explicit kernel
rollback may atomically restore a prior validated kernel path. On the first
0.26 upgrade, there is no prior kernel: rollback to schema 39 means reinstalling
0.25.1 and using the untouched old cache. The 0.26 runtime does not read the old
schema.

## User Upgrade Shape

The 0.26 upgrade is designed to be visible and recoverable:

1. Install a coherent package and plugin bundle.
2. Explicitly run CLI `refresh`, invoke MCP `usage_refresh`, or press Console
   Refresh to start the kernel staging build.
3. Continue reading the last valid committed data or show an explicit build
   state; never show false zeroes.
4. Catch up complete lines appended during the build.
5. Validate oracle totals, foreign keys, integrity, privacy, and performance.
6. Atomically promote the new cache and record any prior-kernel rollback
   pointer.
7. Keep the old cache until the user explicitly removes it.

No query, model call, browser mount, or evidence read may start this build
implicitly.
