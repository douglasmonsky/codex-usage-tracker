# Dashboard Guide Compatibility Pointer

The dashboard is transitioning to a focused
[Evidence Console](evidence-console.md) that supports MCP-first analysis. The
Evidence Console is the stable direction for Home, Explore, Limits, Settings,
and contextual Evidence. It verifies deterministic claims; it is not the
primary analysis interface.

## Current Compatibility Window

The current release may still expose the legacy dashboard workspaces and static
dashboard described by older documentation. During the bounded migration
window, those surfaces remain compatibility entry points only:

- existing direct links continue to work for the release window recorded in
  [Deprecations](deprecations.md);
- compatibility routes may show replacement guidance as the pivot progresses;
- the legacy static dashboard receives no new features;
- no new dashboard workspace is added during the pivot.

In `0.24.x`, direct links to Investigate, Compression Lab, Cache and Context,
Diagnostics Notebook, and Reports render one shared notice-only page. That page
does not load the retired workbench modules, call their historical API
endpoints, or start their background jobs. It names the core MCP replacement,
offers a copyable Codex prompt, and links to Evidence, Explore, and Limits.
The underlying compatibility API and export operations remain available through
`0.24.x`; their scheduled removal release is `0.25.0`.

Open the current Evidence Console for a new workflow with:

```bash
codex-usage-tracker open
```

Use `codex-usage-tracker service serve --open` when the persistent service is
not installed and you intentionally want a foreground server.

Generated static output remains available during its recorded compatibility
window:

```bash
codex-usage-tracker dashboard --output usage-dashboard.html
```

For new workflows, begin with [MCP And Codex Skills](mcp.md) and open an
Evidence Console target only when you want to inspect the supporting records.
Exact bookmark mappings are in
[Evidence Console Route Migration](evidence-console-route-migration.md).
See [Data Posture](data-posture.md) and [Privacy](privacy.md) before sharing any
generated output or screenshot.
