# Architecture Boundary Map

This repository uses `tach` for local architecture visibility and enforcement.
The current local gate is:

```bash
tach check
```

`tach check` now passes locally and should be treated as a blocking local gate
for maintainability work. Remote CI remains untouched until explicitly approved.

## Current Strictness

- `layers_explicit_depends_on = true`
- `forbid_circular_dependencies = false`
- `source_roots = ["src"]`
- tests, docs, build artifacts, virtualenvs, and caches are excluded

The explicit dependency setting is enabled because the current boundary map can
validate module dependencies cleanly. Circular dependency blocking is still
deferred: enabling `forbid_circular_dependencies` currently reports broad cycles
across the coarse module groups. That should be handled in a later, smaller
architecture branch after the groups are split more precisely.

## Intended Direction

The current map uses coarse file-level module groups. The intended dependency
direction remains:

1. `core`: shared models, schema, paths, formatting, privacy helpers.
2. `pricing`: pricing and allowance helpers, depending only on core.
3. `parsing`: JSONL parsing, diagnostic fact extraction, raw context loading.
4. `persistence`: SQLite schema, migrations, refresh cursors, query helpers.
5. `reports`: application report assembly and stable JSON payloads.
6. `diagnostics`: diagnostic snapshots and aggregate-only analysis.
7. `dashboard_api`: dashboard generation, localhost API, HTTP helpers.
8. `adapters`: CLI, MCP, package entrypoint, plugin installer wrappers.

Adapters may call inward. Dashboard/API may call reports, diagnostics,
persistence, parsing, pricing, and core surfaces. Reports and diagnostics may
call lower-level layers. Low-level modules should avoid reaching upward.

## Local Commands

```bash
tach check
tach report src/codex_usage_tracker/usage_drain_reports.py --dependencies --usages
tach map -o /tmp/codex-usage-tracker-tach-map.json
```

Use `tach report` and `tach map` for diagnosis. Use `tach check` as the local
blocking gate.

## React Dashboard Boundaries

Tach does not inspect TypeScript. The React dashboard uses
`dependency-cruiser.config.cjs` as its import-graph contract and
`scripts/check_dashboard_source_budgets.py` as its file-size ratchet. The target
dependency direction and migration rules are recorded in
[`0004-dashboard-typescript-boundaries.md`](architecture/decisions/0004-dashboard-typescript-boundaries.md).

Run the complete frontend governance surface with:

```bash
npm run dashboard:governance
```

Backend and frontend checks are complementary: a clean Tach graph does not prove
the React graph is clean, and a clean dependency-cruiser report does not permit a
new Python dependency edge.
