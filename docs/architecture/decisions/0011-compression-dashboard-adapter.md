# ADR 0011: Compression Dashboard Adapter Boundary

## Status

Accepted

## Context

Compression Lab lifecycle, cache identity, progress, and compact profile
payloads belong to the `compression` application domain. The localhost
dashboard server needs authenticated HTTP adapters for those same services.
Keeping a second implementation in `server` would let dashboard and MCP
behavior drift and would duplicate privacy and payload-limit policy.

## Decision

- `server` may depend on `compression` for thin start, status, and profile
  adapters.
- The dependency remains one-way: `compression` must not import server or HTTP
  types.
- HTTP adapters parse transport scope and authentication, then delegate to the
  shared Compression Lab application API without rebuilding profiles.
- One registry belongs to each dashboard server process so active jobs survive
  browser observer cancellation and deduplicate identical requests.

## Consequences

Dashboard and MCP consumers render the same persisted compact profile and
share detector progress semantics. Tach permits the delivery adapter to depend
on the application domain while continuing to reject reverse coupling. New
compression transports should follow this adapter pattern instead of copying
detector or persistence logic.
