# Deprecations

This is the normative compatibility ledger for the
[MCP-first product pivot](roadmap/mcp-first-pivot.md). Every deprecated public
surface must have an owner through its final supported release, a deterministic
compatibility test, and a concrete migration example.

| Public name or route | Replacement | Owner | Deprecated release | Final supported release | Removal release | Compatibility test | Migration example |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Deprecated compatibility MCP tools | The matching core tool named in each catalog entry | MCP interface maintainers | `0.22.0` | `0.24.x` | `0.25.0` | `tests/mcp/test_compatibility_tools.py` plus existing semantic adapter tests | Select profile `full` temporarily, follow each tool description to its replacement, and retain the corresponding CLI or HTTP workflow when automation needs that interface. |
| Diagnostics Notebook route | `usage_query` plus contextual `usage_evidence` | Evidence Console maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `test_dashboard_sunset_parity.py` plus direct-route browser compatibility | Run `usage_query(entity="call", measures=["tokens"])`, then open the returned canonical selector with `usage_evidence`. |
| Investigate route | `usage_analyze` and `usage_evidence` | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `test_dashboard_sunset_parity.py` plus direct-route browser compatibility | Run `usage_analyze(goal="usage_spike")` and follow its exact evidence identifiers. |
| Compression Lab route | Core token-waste analysis; full-profile compression operations through `0.24.x` | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `test_dashboard_sunset_parity.py` plus direct-route browser compatibility | Run `usage_analyze(goal="token_waste")`; use the full-profile compression tools only when exact candidate ranking is required. |
| Cache and Context route | Context/cache analysis plus contextual Evidence | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `test_dashboard_sunset_parity.py` plus direct-route browser compatibility | Run `usage_analyze(goal="context_bloat")` or `usage_analyze(goal="cache_failure")`, then open the returned selector. |
| Reports route | `usage_analyze`, `usage_query`, and CLI export | Analysis and CLI maintainers | `0.23.0` | `0.24.x` | `0.25.0` | `test_dashboard_sunset_parity.py` plus direct-route browser compatibility | Use analysis for explanation, query for bounded rows, or the existing CLI export for automation. |
| Experimental Usage Constellation | Bounded Home summaries plus Explore and contextual Evidence | Evidence Console maintainers | `0.23.0` | `0.22.x` | `0.23.0` | Release dependency, source, asset, and bundle-budget checks | Use Home for current status and open exact calls or threads through Explore/Evidence; the 3D view has no compatibility surface. |
| Legacy static dashboard | Evidence Console | Evidence Console maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Static-output compatibility smoke | Run the local Evidence Console and use its stable Home, Explore, Limits, Settings, and Evidence surfaces. |
| Legacy CLI command or alias | Simplified stable command or advanced namespace equivalent | CLI interface maintainers | `0.23.0` | `0.24.x` | `0.25.0` | CLI alias parity and help snapshot tests | Replace the alias with the documented stable command or namespaced advanced operation. |
| HTTP API v1 route | Versioned HTTP API v2 equivalent | HTTP API maintainers | `0.23.0` | `0.24.x` | `0.25.0` | v1-to-v2 semantic adapter contract tests | Change the client to the documented `/api/v2/` endpoint and its shared response contract. |

## Retained advanced MCP operations

The following aggregate/local operations have no one-call core parity and remain
active in `full`; they are not part of the 0.22 deprecation set:

- `usage_dedupe_diagnostics`
- `usage_allowance_export`
- `usage_call_context`
- `usage_content_search`
- `usage_thread_trace`
- `usage_local_evidence_export`
- `export_usage_csv`

Dogfood and visualization tools have `developer` disposition and are available
only in the `developer` profile. Their names remain in the historical 0.21
fixture so the move is explicit rather than an accidental disappearance.

## MCP compatibility details

The complete deprecated MCP alias inventory is:

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
- `generate_usage_dashboard`
- `init_usage_pricing_config`
- `update_usage_pricing_config`
- `init_usage_allowance_config`

- Warning starts in `0.22.0` through each deprecated tool's MCP description.
- Direct removal is permitted no earlier than `0.25.0`, after final support in
  `0.24.x` and only when the named compatibility test remains green.
- CLI and HTTP alternatives remain supported independently during the migration
  window; moving a tool between profiles does not remove those interfaces.
- Compatibility handlers keep their historical public names and FastMCP schemas.
  The declarative catalog supplies profile and lifecycle metadata without wrapping
  the callable in a generic `*args, **kwargs` signature.

No CLI compatibility surface may be removed before its removal release. The
same rule applies to MCP tools, dashboard routes, static output, and HTTP APIs.
If semantic equivalence cannot be proven, preserve the old behavior through its
final supported release or publish a documented breaking-change notice.

## CLI compatibility mapping

The primary CLI help lists only `setup`, `status`, `doctor`, `refresh`,
`analyze`, `query`, `open`, `export`, `config`, `service`, and `admin`.
Historical top-level names remain accepted through `0.24.x`. When stderr is an
interactive terminal, an alias prints one concise migration notice to stderr;
stdout is never used for deprecation text.

| Historical operation | Stable replacement |
| --- | --- |
| Static dashboard and report entry points | `open`, `analyze`, `query`, or `export` |
| `dashboard-service install/status/uninstall` | `service install/status/uninstall` |
| `serve-dashboard` | `service serve` |
| Pricing, allowance, rate-card, projects, and thresholds commands | The matching `config` namespace |
| Index repair, source coverage, support bundle, and dogfood commands | The matching `admin` namespace |
| Manual MCP process | `admin mcp serve --profile core\|full\|developer` |

The stable `query` spelling keeps its old-only filters and unbounded `--limit 0`
form as a v1 compatibility mode. New bounded query options return
`codex-usage-tracker.query.v2`.

## HTTP API v1 compatibility mapping

All unversioned `/api/*` responses advertise `Deprecation: true` and link back
to this ledger. They remain compatibility routes through `0.24.x`; new
dashboard code must not add dependencies on them.

| Compatibility route family | v2 replacement | Current dashboard use |
| --- | --- | --- |
| `/api/usage` | `/api/v2/query` for bounded reads; `/api/v2/refresh` for index refresh | Removed from stable Home timeframe changes in `0.23.0`; retained by legacy snapshot hydration and legacy routes only. |
| `/api/refresh/start`, `/api/refresh/status` | `/api/v2/refresh`, then `/api/v2/jobs/{job_id}` | Compatibility refresh flow pending migration. |
| `/api/status`, `/api/readiness`, `/api/health` | `/api/v2/status` and `/api/v2/capabilities` | The bounded Home bootstrap still uses the compatibility status envelope while its component payloads move independently. |
| `/api/calls`, `/api/call`, `/api/threads`, `/api/thread-calls` | `/api/v2/query` plus `/api/v2/evidence` | Explore Calls and Threads remain explicit compatibility exceptions until their richer display fields have v2 parity. |
| `/api/summary`, `/api/recommendations` | `/api/v2/query` and `/api/v2/analyze` | Legacy Overview routes only. Stable Home uses the bounded status summary and focused v2 usage queries. |
| `/api/allowance/*` | `/api/v2/allowance` and `/api/v2/jobs/{job_id}` | Limits migration is incremental; focused compatibility endpoints remain supported through `0.24.x`. |
| `/api/investigations/*`, `/api/reports/*`, `/api/diagnostics/*`, `/api/compression/*` | `/api/v2/analyze`, `/api/v2/query`, and `/api/v2/evidence` where semantic parity exists | Compatibility and deprecated lab routes only; operations without proven parity remain supported through the final compatibility release. |
| `/api/context`, `/api/context-settings`, `/api/open-investigator` | `/api/v2/evidence` or direct Evidence Console navigation | Compatibility helpers pending removal with the legacy dashboard surface. |

Deprecation does not mean an endpoint may be removed early. Each family keeps
its current contract until the final supported release, and removal still
requires the parity and direct-route checks named above.
