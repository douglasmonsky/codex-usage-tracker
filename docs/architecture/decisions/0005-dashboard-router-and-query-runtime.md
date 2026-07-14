# Dashboard Router And Query Runtime

Status: Accepted

## Context

The current dashboard manually parses `?view=` state in `App.tsx` and owns most
live refresh behavior in one component. Data is frequently normalized from the
large `/api/usage` payload even when a focused API exists. Route changes,
refreshes, selected records, and fixture fallback therefore share hidden state
and are difficult to cache or test independently.

The server already provides SQLite persistence, async refresh progress, focused
calls/threads/allowance/diagnostics routes, and direct call hydration. The
frontend needs to use those contracts without creating a second source of truth.

## Decision

- Use TanStack Router for typed routes, search parameters, loaders, error
  boundaries, and route-level lazy imports.
- Keep a compatibility adapter for every shipped `?view=` value and relevant
  filter, record, thread, snapshot, and return parameter.
- Use TanStack Query for server state, cancellation, stale-while-refresh,
  polling, invalidation, and query-key ownership.
- Keep ephemeral selection and disclosure state local to the owning component or
  reducer. Do not add a general global-state library.
- Separate production HTTP transport from the synthetic fixture provider at app
  startup. Production client code must not silently fall back to fixtures after
  a failed live request.
- Persist data-scope preferences and server revision/cache metadata locally.
  Full raw-context and indexed-content payloads are not persisted by the browser
  query cache. Aggregate query persistence, if later justified by reload timing,
  requires bounded size, schema/revision invalidation, and an explicit privacy
  test.
- Keep stale aggregate content visible while a refresh runs or a replacement
  request retries.
- Register query identities and response schemas in the checked-in dashboard
  query contract manifest. Duplicate identities and contract drift fail tests.
- Load tabbed analytical modules on selection unless they are simultaneously
  visible. Returning to a tab reuses its source-revision-keyed query result.
- Keep bounded interactive reads on indexed query services. Full-scope detector
  work uses the shared start/status/profile job lifecycle.

## Consequences

- Routes, URL compatibility, and server queries become independently testable.
- The SQLite index remains the durable cache; the browser cache prevents
  redundant work within a session and uses revision-aware refetch after reload.
- Feature modules consume focused contracts rather than recomputing report logic
  from the boot payload.
- TanStack Router and Query add bundle cost, so the shell and route chunks have
  explicit gzip budgets and lazy-loading gates.
- Deterministic synthetic route budgets cover cold and warm behavior in CI.
  Budget changes require measured evidence rather than threshold relaxation.
