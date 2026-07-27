# Change Plan: K6 Kernel Interface Composition

## Goal

Expose the qualified K4 query and K5 evidence/live services through exactly six
MCP tools, a new versioned loopback HTTP API, and a lean operational CLI while
keeping the integration branch non-publishable.

## Contract

- The MCP catalog is exactly `usage_status`, `usage_refresh`, `usage_query`,
  `usage_evidence`, `usage_allowance`, and `usage_job_status`.
- `/api/kernel/v1` is the frozen HTTP prefix. HTTP, MCP, and CLI bind one
  kernel application service and preserve the same structured result semantics.
- Read operations never refresh or write. Refresh starts or joins one durable
  job, and job status can wait on the host for a bounded interval.
- The CLI retains setup, status, refresh, query, export, open, service,
  configuration, repair, and package operations without historical aliases.
- Schemas, plugin assets, and bundle digests are deterministic. Same-version
  plugin cache replacement is exact and atomic.
- Integration refs remain non-publishable; no compatibility profile,
  server-authored narrative, or content evidence is introduced.

## Owned Paths

- `src/codex_usage_tracker/kernel/application/`
- `src/codex_usage_tracker/kernel/interfaces/`
- `src/codex_usage_tracker/kernel/plugin_manifest.py`
- `tests/kernel/interfaces/`
- root integration plugin metadata and kernel skill source
- K6 scope, manifest, package, CI, churn, and execution-ledger records

## Validation

- catalog/schema/implementation coherence and forbidden-name absence;
- direct stdio JSON-RPC handshake and tool calls;
- loopback HTTP parity, origin guards, and SSE;
- active-refresh reads, compatible two-process join, and host-side await;
- CLI/help/public-doc snapshots;
- isolated wheel/plugin smoke, asset digest, and same-version replacement;
- separate installed v0.25.1 reference smoke;
- one final read-only review after the diff is stable.

## Budget

- Maximum changed files: 55
- Maximum changed lines: 5,500

The file cap increased from 38 to 55 after the complete six-schema generator,
three adapter packages, installed-package smoke contracts, scope/disposition
records, and CI/release wiring were enumerated. The implementation remains
below the declared line budget and does not include K7 console work.
