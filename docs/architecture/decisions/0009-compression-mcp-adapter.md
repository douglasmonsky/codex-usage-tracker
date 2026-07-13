# Compression MCP Adapter Boundary

## Context

Compression Lab analysis already belongs to the `compression` application
domain, while MCP registration belongs to the `cli` adapter domain. PR 3 adds
five asynchronous MCP tools that must call the shared compression API instead
of duplicating run lifecycle, cache, payload, or privacy behavior in the CLI.
The existing CLI Tach contract did not declare that dependency.

## Decision

- `cli` may depend on `compression` to register thin MCP adapters around the
  shared Compression Lab API and payload contracts.
- Compression lifecycle, cache identity, pagination, evidence disclosure, and
  payload limits remain owned by `compression` and `store`.
- `compression` must not depend on `cli` or MCP runtime types.
- MCP adapters may select transport-specific payload ceilings, but they must not
  change detector results or bypass the shared privacy flags and evidence modes.

## Consequences

The dependency direction remains one-way from the delivery adapter to the
application domain. CLI and MCP callers share the same tested behavior as local
API callers, while Tach will reject a reverse dependency or unrelated domain
growth. Future dashboard or plugin consumers can use the compression API
without importing MCP infrastructure.
