# Kernel Stable Contract 0.28

Release 0.28 freezes the smallest proven Usage Tracker surface before 1.0.
The machine-readable source of truth is
`config/kernel-stable-contract-v1.json`. A breaking change to this inventory
requires an approved roadmap amendment.

## Stable Surface

The stable surface is six factual MCP tools, seven loopback HTTP routes, the
versioned SSE stream, eleven primary CLI commands, five logical evidence
selector kinds, JSON export, the versioned cache lifecycle, three calculation
grades, and four token classes. The tracker owns facts and deterministic
calculations; the consuming model owns inference and recommendations.

## Operations

`setup` initializes the owner-only cache. `status`, `query`, `evidence`,
`allowance`, and Console reads use the last committed generation and never
start refresh. `refresh` starts or joins one durable incremental job. The host
may wait through bounded `usage_job_status` calls; a model should not poll in a
tight loop. Reopening the Evidence Console reads the current generation and
does not rebuild it.

The default cache root is
`$CODEX_HOME/codex-usage-tracker/kernel-v1`. The analytical, operational, and
optional-content databases have fixed names in the machine contract. Override
the root only with `CODEX_USAGE_TRACKER_CACHE_ROOT`.

## Recovery

Refresh writes staging state and promotes one validated generation atomically.
Readers retain the prior published generation while a writer is active or
fails. Interrupted leases and jobs are recovered on the next bounded
operation. `repair` validates control state; `repair --rollback` activates the
preserved prior generation. A failure must never report success, replace the
active database with an invalid file, or require an unbounded polling loop.

## Privacy

Processing remains local. The exported analytical database contains
privacy-safe facts, not the source-path registry. Raw prompt, response,
reasoning, and tool-output content is disabled by default. Optional context
composition requires explicit confirmation, uses a separable owner-only
database, and can be disabled and deleted without changing accounting.
Release fixtures are synthetic.

## Query

`usage_query`, `POST /api/kernel/v1/query`, and CLI `query` share one bounded,
generation-consistent request contract. Results expose basis, coverage,
generation, and evidence selectors. Calculation grades are `exact`,
`deterministic`, or `estimated`; incomplete observations remain explicit in
coverage and do not create a fourth grade. The four token classes are uncached
input, cached input, reasoning, and output.

## Evidence

Selectors are logical identities, never SQLite row IDs. Stable kinds are
`thread`, `turn`, `call`, `tool`, and `allowance`. Valid views are `summary`,
`timeline`, `calls`, `tools`, `activities`, and `allowance`. Evidence routes
use `/evidence/{url_encoded_selector}?view={view}` and survive a clean rebuild.
The live stream publishes bounded `generation_committed` events, an explicit
`snapshot_required` event after a replay gap, and heartbeat comments.

## Installation and Upgrade

The distribution, CLI, plugin, and MCP server retain their current names.
Plugin installation replaces a complete same-version bundle atomically.
Upgrades from public 0.26.0 and 0.27.0 preserve the published cache bytes and
generation before the first candidate refresh. Schema changes build side by
side, preserve rollback state, and never open a legacy database as the current
schema.

## Export

The supported export format is bounded, deterministic JSON from the shared
query result. CSV is not part of the frozen 0.28 contract. Exports never
include the operational path registry or optional raw fragments.

## Experimental Capabilities

Optional context composition remains experimental and outside the stable
contract even though its privacy boundary is enforced. The overlay is a
read-only adapter contract only; 0.28 ships no overlay runtime, browser
injection, capture authority, or write surface.

## 1.0 Readiness Decision

The core factual surface is ready to remain stable, but 1.0 is deferred until
post-freeze dogfood validates the contract under normal use. Release 0.28 is
feature-free. Future work may improve implementation and performance without
breaking this inventory; a breaking change requires an approved roadmap
amendment.
