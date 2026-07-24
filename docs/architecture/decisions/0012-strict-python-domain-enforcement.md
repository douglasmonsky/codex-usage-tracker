# Strict Python Domain Enforcement

## Context

The 0.24 foundation audit found eight direct Tach violations:

- two `core.conversational_readiness` imports from diagnostics;
- six `store.allowance_materialization` imports from allowance intelligence
  and pricing.

The initial GitNexus snapshot identified four Python file cycles: analytics
request/context imports, allowance observation migration imports, store refresh
facade imports, and the store allowance calculation. Re-indexing after those
splits exposed additional internal schema/write cycles that the original
strongly connected components had masked. Previous policy declared package
dependencies but deliberately left circular enforcement disabled, so the graph
could describe those problems without preventing them.

## Decision

- Enable `root_module = "forbid"`,
  `forbid_circular_dependencies = true`, and
  `layers_explicit_depends_on = true`.
- Give every Python source module one root or domain owner.
- Split CLI, HTTP, and MCP interfaces into independently owned nested domains
  where a single umbrella interface would create false bidirectional edges.
- Move shared request filters, time-window validation, version data, and
  diagnostic value types downward to `core`, preserving old import identities
  with re-exports.
- Give analytics a read-only context/path protocol instead of importing
  application classes.
- Inject runtime-readiness providers at interfaces rather than importing
  diagnostics from application.
- Run allowance materialization through the refresh derived-fact callback and
  keep the domain calculation in `allowance_intelligence`, outside store.
- Split allowance observation synchronization and refresh metadata from query
  and public store facades to remove file-level cycles.
- Split usage-event writes, compression revision state, source-record
  synchronization, and thread-summary rebuilds from schema-aware public facades
  so migration primitives never depend back on their callers.
- Keep only exact, tested compatibility leaves at historical module paths.
  Stable domains may not import the `compatibility` package.
- Treat the historical `store.api` public facade as an explicit compatibility
  leaf. Its refresh and rebuild entry points supply the upper allowance callback
  by default while the lower store refresh implementation remains callback-only.
- Run Tach as a named CI step before dead-code analysis, with AST regression
  tests as a second guard against configuration drift.

## Consequences

Tach now passes with zero violations and zero declared cycles, all Python
source modules are owned, and a fresh GitNexus index reports zero Python
file-level cycles. GitNexus still reports three pre-existing non-Python cycles:
two in the frontend source graph and one in generated dashboard assets. Those
are outside this Python-boundary decision and remain visible rather than being
allowlisted.

New cross-domain imports require an explicit, reviewable contract change.
Compatibility paths remain available through the 0.24 support window, but they
cannot become a route for stable packages to depend outward.

The current analytics catalog still delegates some algorithms to established
report and recommendation packages. That is an explicit 0.24 compatibility
dependency, not a transport dependency; later algorithm migration can contract
it without changing the enforced direction.

This decision supersedes the temporary choice in ADR 0003 to leave circular
dependency enforcement disabled.
