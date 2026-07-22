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
