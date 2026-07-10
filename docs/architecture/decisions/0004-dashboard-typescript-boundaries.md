# Dashboard TypeScript Boundaries

Status: Accepted for the dashboard redesign experiment

## Context

The current React dashboard has useful feature folders, but the dependency graph
is conventional rather than enforced. `App.tsx` owns routing, refresh, shell,
exports, URL state, and feature composition; feature pages import broad shared
modules; and API, fixture, presentation, and aggregation concerns meet inside a
few large files. Tach correctly governs Python and cannot validate TypeScript
imports.

The redesign needs a boundary contract before route migration starts. Otherwise
parallel work can produce another set of page-sized modules while still passing
typecheck and tests.

## Decision

The target frontend packages are:

1. `data`: transport, contracts, query keys, and fixture adapters.
2. `design`: tokens, primitives, layouts, and accessibility helpers.
3. `visualization`: React-free semantic specs plus renderer adapters.
4. `entities`: call, thread, fact, allowance, report, and source models/views.
5. `features`: user workflows that compose entities and shared services.
6. `routes`: thin route loaders and page composition.
7. `app`: router, providers, shell, and top-level error boundaries.

Dependencies point inward:

- `design` does not import application, route, feature, entity, or data-fetching
  modules.
- React-free `data/contracts` and `visualization/spec` do not import React or a
  renderer.
- `entities` may use `data` and `design`, never features or routes.
- `features` may use public APIs from entities, data, design, and visualization.
- Features do not import another feature's internal files.
- `routes` compose feature public APIs and contain no diagnostic calculations.
- `app` composes routes and providers; lower layers do not import it.

Each package exposes a deliberate public entry point. Internal deep imports are
blocked once a package is migrated. Existing source remains under its current
folders until the owning roadmap unit moves it; the governance baseline must not
pretend those moves are already complete.

The initial contract has two named compatibility bridges: feature modules may
import `app/i18nContext` until design primitives own localization context, and
Call Investigator may import `app/shellUrl` until typed routes own legacy return
URLs. No other feature-to-app import is allowed, and R2/R3 remove these two
bridges rather than expanding the exception.

`dependency-cruiser` owns the TypeScript import contract and cycle check. Tach
continues to own Python. Agent Maintainer and CI report both checks as one
repository hardening surface.

## Consequences

- New target-architecture code has an enforceable dependency direction from its
  first commit.
- Existing dependency debt is migrated in bounded route units rather than hidden
  behind broad exclusions.
- Cross-package changes require an explicit public API or an ADR update.
- TypeScript graph tooling is an additional development dependency, not a Python
  runtime dependency.
