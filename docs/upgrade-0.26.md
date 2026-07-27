# Upgrade to 0.26

Version 0.26 replaces the beta spike with one local fact kernel. It does not
carry compatibility handlers for the removed analysis, Compression Lab,
recommendation, diagnostics, OTel, content-index, workbench, or legacy
dashboard systems.

The exact per-name migration ledger is
`config/kernel-retired-surfaces-v1.json`. It is the authority for all 1,194
retired public names and package paths. Every entry records one of these
replacements:

- `six-tool kernel MCP`
- `kernel HTTP API`
- `kernel operational CLI`
- `kernel fact schemas`
- `kernel database schema`
- `kernel timeline`
- `lean kernel package`
- `none`

The manifest covers `mcp_tool`, `http_route`, `cli_command`, `schema_id`,
`table`, `console_route`, `frontend_asset`, `package_data_rule`, and
`source_module` entries.

## What to expect

- MCP exposes exactly `usage_status`, `usage_refresh`, `usage_query`,
  `usage_evidence`, `usage_allowance`, and `usage_job_status`.
- The model explores exact or explicitly graded facts and owns inference.
  There is no `usage_analyze` replacement.
- The HTTP API is rooted at `/api/kernel/v1`.
- The Console has Live, Explore, Evidence, Limits, and Settings only.
- Opening the Console or reading a tool never starts a refresh.
- The first explicit refresh against a pre-K8 development cache builds a
  separate current-schema artifact. It does not delete the old cache.
- CSV/JSON export is the bounded query result selected by the caller.

## Removed without replacement

Entries marked `none` are archived in Git history and the v0.25.1 tag only.
They are not importable or served by 0.26. This includes the old runtime source
modules and frontend-only assets for deleted product surfaces.
