# Deprecations

This is the normative compatibility ledger for the
[MCP-first product pivot](roadmap/mcp-first-pivot.md). Every deprecated public
surface must have an owner through its final supported release, a deterministic
compatibility test, and a concrete migration example.

| Public name or route | Replacement | Owner | Deprecated release | Final supported release | Removal release | Compatibility test | Migration example |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Deprecated compatibility MCP tools | The matching core tool named in each catalog entry | MCP interface maintainers | `0.22.0` | `0.24.x` | `0.25.0` | `tests/mcp/test_compatibility_tools.py` plus existing semantic adapter tests | Select profile `full` temporarily, follow each tool description to its replacement, and retain the corresponding CLI or HTTP workflow when automation needs that interface. |
| Diagnostics Notebook route | MCP analysis and contextual Evidence route | Evidence Console maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Direct-route browser compatibility test | Ask the MCP analyst for diagnostics, then open the returned evidence target. |
| Investigate route | `usage_analyze` and `usage_evidence` | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Direct-route browser compatibility test | Run the corresponding analysis goal and follow its evidence identifiers. |
| Compression Lab route | MCP analysis strategies and contextual Evidence route | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Direct-route browser compatibility test | Ask for compression analysis and inspect the returned evidence target. |
| Cache and Context route | MCP analysis goals and Explore evidence | Analysis service maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Direct-route browser compatibility test | Ask about cache reuse or context pressure, then open Explore at the returned selector. |
| Reports route | `usage_analyze`, `usage_query`, and CLI export | Analysis and CLI maintainers | `0.23.0` | `0.24.x` | `0.25.0` | Direct-route browser compatibility test | Use analysis for explanation, query for bounded rows, or CLI export for automation. |
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
