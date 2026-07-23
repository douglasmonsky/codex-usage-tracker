# Upgrading to 0.22.0

Release 0.22.0 changes the default MCP tool profile from the historical broad
catalog to the seven-tool `core` profile. It does not remove the 0.21/PR290
tool names, change dashboard navigation, or require a database migration.

## Upgrade

Upgrade the package, then refresh the generated plugin wrapper:

```bash
pipx upgrade codex-usage-tracking
codex-usage-tracker upgrade-plugin
codex-usage-tracker doctor
```

Restart Codex or open a fresh task when the command asks you to. A clean plugin
installation should then expose these tools: `usage_status`, `usage_refresh`,
`usage_analyze`, `usage_query`, `usage_evidence`, `usage_allowance`, and
`usage_job_status`.

## Compatibility Profiles

Most conversations should stay on `core`. If an existing workflow directly
calls a legacy 0.21 tool, opt into the compatibility profile by setting:

```bash
CODEX_USAGE_TRACKER_MCP_PROFILE=full
```

Set that environment value on the `codex-usage-tracker` MCP server entry in
your Codex configuration. Use `developer` only when you also need the five
dogfood or visualization tools. Running `setup` or `upgrade-plugin` regenerates
the package-owned plugin configuration with `core` as the default, so reapply
an intentional override afterward.

## Behavioral Notes

- Core responses share one versioned envelope and point to optional local
  evidence instead of embedding unbounded records.
- Refresh and longer analysis operations can return a job handle; poll it with
  `usage_job_status`.
- Canonical totals, service-tier pricing, allowance calculations, subagent
  classification, privacy defaults, and existing dashboard routes are
  preserved.
- No dashboard navigation changed in 0.22.0. The browser UI is now described as
  the supporting Evidence Console rather than the primary analysis surface.

If a workflow cannot migrate immediately, keep the exact package version
pinned and use `full` while replacing direct legacy calls with their core
equivalents. See [the 0.22.0 release note](releases/0.22.0.md) for the profile
counts and contract inventory.
