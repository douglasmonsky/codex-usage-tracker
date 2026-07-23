# Upgrading to 0.23.0

Release 0.23.0 focuses the browser and CLI surfaces around the MCP-first product
model. It does not remove compatibility commands, tools, or routes, and it does
not require a manual database step. The first start upgrades the local schema
to version 34 with additive query indexes; stored usage rows are not rewritten.

## Upgrade

```bash
pipx upgrade codex-usage-tracking
codex-usage-tracker setup
codex-usage-tracker doctor
```

Restart Codex or open a fresh task if setup requests it. Then ask a usage
question conversationally and use the returned Evidence Console target only
when you want to verify the supporting records.

`service serve --refresh` now opens the stored snapshot immediately and
refreshes local history in the background. The Home progress indicator and
Refresh control report explicit refresh work without blocking the server from
accepting dashboard requests.

## Open Evidence

Use the target returned by MCP when it has an absolute loopback URL. Otherwise
start or verify the local service and pass the target to the stable opener:

```bash
codex-usage-tracker service status
codex-usage-tracker open --target-json '<dashboard-target-v2 JSON>'
```

`codex-usage-tracker open` without a selector opens Home. It also accepts exact
call IDs, thread keys, and target IDs.

## CLI Migration

Primary help now lists 11 commands. Configuration, service, and maintenance
operations moved under `config`, `service`, and `admin`. For example:

```bash
codex-usage-tracker config pricing update
codex-usage-tracker service status
codex-usage-tracker admin source-coverage --json
codex-usage-tracker admin mcp serve --profile full
```

Historical top-level spellings remain parseable through 0.24.x. Interactive
aliases print a migration notice to stderr; JSON stdout remains valid. Existing
query scripts using old-only pricing, credit, token, or unbounded filters retain
their v1 output contract during the compatibility window.

## Route Migration

Bookmarks for Overview, Calls, Threads, and Call Investigator normalize to
Home, Explore, and contextual Evidence. Direct legacy workbench links remain
available but no longer appear in primary navigation. See the exact mapping in
[Evidence Console Route Migration](evidence-console-route-migration.md).

If a workflow cannot migrate immediately, pin 0.23.x and replace compatibility
entry points before their final supported release, 0.24.x. The normative dates
and owners are in the [Deprecations ledger](deprecations.md).
