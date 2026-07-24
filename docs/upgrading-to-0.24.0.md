# Upgrading to 0.24.0

Release 0.24.0 hardens architecture, storage integrity, context retrieval,
analysis-job recovery, and release delivery without changing the core MCP,
focused Evidence Console, or primary CLI workflows introduced in 0.23.

No manual database step is required. The first command that opens the store
applies additive migrations through schema version 37. Existing usage rows,
accounting totals, prices, credits, allowance evidence, and dashboard
selectors remain compatible.

## Upgrade

```bash
pipx upgrade codex-usage-tracking
codex-usage-tracker setup
codex-usage-tracker doctor
```

Restart Codex or open a fresh task if setup requests it. Existing local
configuration and the usage database remain in place.

## What Changes Automatically

- New and refreshed source records store byte offsets so selected-call context
  can seek directly to relevant evidence. Older rows keep the safe sequential
  fallback until their source is reindexed.
- Analysis jobs and reusable results persist in SQLite. Interrupted running
  jobs recover explicitly instead of remaining process-local.
- Normal SQLite connections enforce foreign keys, and schema upgrades fail
  atomically rather than leaving partially applied migration state.
- The default seven-tool MCP core, 11-command primary CLI, focused localhost
  APIs, JSON contracts, and accounting semantics remain stable.

## Legacy Workbench Links

Direct links for Investigator, Compression Lab, Cache and Context, Diagnostics,
and Reports now open a small compatibility notice instead of loading the old
workbench code. Each notice supplies a replacement core request and links to
Evidence, Explore, and Limits.

CLI, HTTP API, CSV export, and full-profile MCP compatibility remain supported
through 0.24.x. Replace those compatibility entry points before upgrading to
0.25.0, when the deprecations ledger schedules their removal.

If a workflow cannot migrate immediately, pin this compatibility release:

```bash
pipx install --force "codex-usage-tracking==0.24.0"
codex-usage-tracker setup
codex-usage-tracker doctor
```

See the [0.24.0 release note](releases/0.24.0.md) and
[deprecations ledger](deprecations.md) for the full contract and timeline.
