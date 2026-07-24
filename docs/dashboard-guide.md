# Evidence Console Guide

Codex Usage Tracker 0.25 uses the live, localhost
[Evidence Console](evidence-console.md) as its only dashboard product. Open it
with:

```bash
codex-usage-tracker open
```

If the persistent service is not installed, start a foreground server:

```bash
codex-usage-tracker service serve --open
```

The console provides Home, Explore, Limits, Settings, and contextual Evidence.
CSV and JSON exports remain available from the CLI, and exact call or thread
links continue to open the corresponding Evidence Console record.

## Static dashboard migration

The `dashboard` and `open-dashboard` commands and the MCP
`generate_usage_dashboard` tool were removed in 0.25. Static HTML generation is
no longer packaged or served. For one release, `/dashboard.html` returns a
data-free `410 Gone` page that points to `/react-dashboard.html`; `/` redirects
to the same live console.

See [Upgrading to 0.25.0](upgrading-to-0.25.0.md) for replacements and
[Deprecations](deprecations.md) for the compatibility ledger.

## Privacy and freshness

The console remains loopback-only and requires its per-server token for
refresh and context operations. Raw context remains an explicit action and is
not written to SQLite or exports. Use `--privacy-mode redacted` or
`--privacy-mode strict` before sharing screenshots or exported data.

By default, serving refreshes active-session logs before opening. Use
`--no-refresh` only when you intentionally want the cached local index. The
removal of static output does not change canonical accounting, schema
migrations, incremental freshness, or raw-context controls.
