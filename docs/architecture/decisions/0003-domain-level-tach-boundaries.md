# Domain-Level Tach Boundaries

## Context

The initial root Tach inventory declared every Python leaf module with an empty
dependency list. That made normal imports inside a package look like boundary
violations and obscured the three actual cross-domain findings. The repository
already had one `tach.domain.toml` contract per package domain, but the redundant
leaf declarations prevented those contracts from being the useful source of
truth.

## Decision

- Package-level `tach.domain.toml` files own dependencies among `core`, `store`,
  `parser`, `pricing`, `reports`, `diagnostics`, `allowance_intelligence`, and
  the other package domains.
- The root `tach.toml` declares only top-level entry-point and compatibility
  modules that do not belong to a package domain.
- `reports` may depend on `allowance_intelligence` because report composition is
  an application-level consumer of allowance diagnostics.
- Command normalization shared by diagnostics and content indexing belongs in
  `core.command_parsing`; `store` must not depend on `diagnostics`.
- Circular-dependency enforcement remains disabled until the existing domain
  graph is audited separately. New direct dependency edges are still blocked.

## Consequences

`tach check` now validates the current domain graph without leaf-level false
positives. New cross-domain imports require an explicit contract change, and
the store-to-diagnostics cycle found during migration is removed rather than
allowlisted.

## 2026-07-13 Amendment

The compression domain no longer declares a dependency on `core`. Detector-ready
fact loading now depends only on the store contract, and no compression module
imports `core`. Removing the stale edge keeps the declared graph aligned with
the implementation and lets Tach continue detecting accidental dependency
growth.
