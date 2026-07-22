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

Use the current compatibility dashboard when an existing workflow requires it:

```bash
codex-usage-tracker serve-dashboard --open
```

Generated static output remains available during its recorded compatibility
window:

```bash
codex-usage-tracker dashboard --output usage-dashboard.html
```

For new workflows, begin with [MCP And Codex Skills](mcp.md) and open an
Evidence Console target only when you want to inspect the supporting records.
See [Data Posture](data-posture.md) and [Privacy](privacy.md) before sharing any
generated output or screenshot.
