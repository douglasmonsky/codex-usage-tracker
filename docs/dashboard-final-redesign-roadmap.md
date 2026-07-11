# Dashboard Final Redesign Roadmap

Status: active experimental roadmap

Integration branch: `experiment/dashboard-final-redesign`

Base commit: `b89f0ca` (`chore: upgrade agent maintainer frontend governance`)

## Branch Contract

This is a long-running experiment by explicit maintainer direction. It is the
only integration branch for the redesign and must not be merged into `main` until
the final exit review passes.

- Each implementation unit uses a short-lived branch from the latest experiment
  head and opens a PR whose base is `experiment/dashboard-final-redesign`.
- Ordinary redesign PRs are squash-merged into the experiment after focused and
  branch gates pass.
- `main` remains releasable and may receive unrelated fixes. The experiment
  periodically merges current `main`; it does not rebase or rewrite shared
  history.
- The final main-targeting PR is opened only after parity, migration, visual,
  performance, accessibility, package, and release gates are green.
- No version bump, tag, TestPyPI publish, PyPI publish, default-route switch, or
  legacy dashboard deletion happens before the final release unit.
- Real logs, prompts, tool output, paths, databases, and screenshots remain out
  of commits. All visual evidence uses synthetic fixtures.

## Definition Of Success

The redesign is ready for `main` when a new user can load the dashboard, understand
the data scope, identify the most important finding, inspect its evidence, and
reach a specific call or thread without learning the implementation vocabulary.
An experienced user must retain dense tables, arbitrary row limits, deep links,
exports, report controls, and explicit local context access.

The code is ready when route, data, entity, feature, design, and visualization
boundaries are enforced; the old page-sized state owners are gone; no new
baseline debt is introduced; and the bundle is split within the agreed budgets.

## Roadmap Units

### R0. Audit, Specification, And Experimental Checkpoint

Status: in progress on the integration branch

Deliverables:

- measured current-state audit with synthetic screenshots;
- product, information architecture, visual, chart, frontend, API, and MCP spec;
- this staged roadmap and branch/merge contract;
- upgraded Agent Maintainer frontend governance inherited from PR #178.

Gate:

- documentation review;
- `python scripts/check_release.py`;
- `git diff --check`;
- commit and push the experiment branch.

### R1. Architecture And Design Governance

Target PR: `redesign/01-frontend-governance` -> experiment

Deliverables:

- ADRs for router/query ownership, visualization renderer, CSS strategy, and
  TypeScript boundaries;
- dependency-cruiser rules and graph report;
- Knip, Stylelint, route bundle report, and size budgets;
- Agent Maintainer provider/task integration for the new checks;
- source package skeleton with public entry points;
- ratchet baselines for existing frontend file, CSS, and bundle debt.

The unit may move files only when required to prove the dependency rules. It does
not redesign a production route.

Gate:

- Agent Maintainer doctor and CI-equivalent profile;
- dashboard lint, typecheck, tests, and build;
- dependency rules pass with no broad ignore pattern;
- check output is compact and documented for future agents.

### R2. Visual Contract Lab And Design Freeze

Target PR: `redesign/02-visual-contract-lab` -> experiment

Deliverables:

- dev-only fixture route for shell, navigation, controls, table states, inspector,
  charts, loading, empty, stale, partial, and error states;
- high-fidelity desktop, tablet, and mobile compositions for Overview, Calls,
  Investigate, Limits, and Call Investigator;
- semantic tokens, typography, spacing, grid, icon, motion, and interaction states;
- side-by-side review against current audit screenshots;
- approved visual inventory before route migration begins.

The lab uses real React primitives and synthetic contracts so it becomes a test
surface rather than a disposable mock.

Gate:

- Browser review at 390x844, 768x1024, 1024x768, 1440x900, and 1600x900;
- keyboard/focus pass, reduced-motion pass, 200% zoom pass, and axe scan;
- screenshot baselines accepted for every core state;
- no clipped text, incoherent overlap, or document overflow.

### R3. Router, Query Cache, And Data Scope

Target PR: `redesign/03-data-runtime` -> experiment

Deliverables:

- TanStack Router with typed routes/search parameters and legacy `?view=` adapter;
- TanStack Query provider, query keys, cancellation, stale-while-refresh, and
  bounded persisted cache metadata;
- production transport separated from synthetic fixture provider;
- compact Data Scope control and progress model;
- route-level lazy loading and error boundaries;
- source revision/cache-validator support where API changes are warranted.

Compatibility requirements:

- arbitrary finite limit, `limit=0`, `limit=None`, No cap, Load more, active/all
  history, live refresh, progress, and session-persistent preferences;
- direct call hydration outside the loaded snapshot;
- stale content remains visible during refresh and recoverable errors.

Gate:

- URL contract tests for every legacy route/search combination;
- refresh/cache/invalidation tests;
- reload and back/forward browser tests;
- initial shell bundle <= 85 kB gzip or an approved evidence-backed adjustment.

### R4. Visualization Grammar And Renderer

Target PR: `redesign/04-visualization-system` -> experiment

Deliverables:

- React-free `VisualizationSpecV1` plus contract fixtures;
- modular ECharts SVG adapter and Codex Usage Tracker theme;
- linked selection, annotations, confidence bands, brushing/zooming, export, and
  synchronized table primitives;
- chart accessibility summaries and keyboard interaction model;
- allowance change-point, token-flow, cache frontier, thread lifecycle, waste
  matrix, and evidence-ledger visual-contract examples;
- renderer chunk instrumentation and budget.

No feature may pass raw ECharts options. No visualization may ship without
loading, empty, partial, insufficient-data, error, and table-fallback states.

Gate:

- semantic spec unit/contract tests;
- deterministic screenshot tests for all chart states;
- keyboard/table-equivalence checks;
- renderer chunk <= 110 kB gzip unless the ADR records a measured exception.

### R5. Overview And Priority Findings

Target PR: `redesign/05-overview` -> experiment

Deliverables:

- answer-first Overview using `/api/summary` and `/api/recommendations`;
- prioritized finding rail with evidence grade, scope, freshness, and next action;
- compact usage pulse and token-flow visualization;
- loaded-total metrics with four-token-type breakdown;
- recent calls as an immediately reachable, virtualized evidence list;
- direct transitions to Investigate, Limits, Threads, and Call Investigator.

Remove generic cards that repeat data without changing the user's decision.

Gate:

- summary/recommendation contract tests;
- row-to-investigator browser test;
- mobile first-answer placement and loading-state tests;
- current Overview parity checklist signed off in
  [`dashboard-overview-parity.md`](dashboard-overview-parity.md).

### R6. Explore: Calls, Threads, Tools, And Files

Target PR: `redesign/06-explore` -> experiment

Deliverables:

- table-first Calls and Threads views using focused paged APIs;
- TanStack Virtual rows, sticky headers, frozen identity columns, deliberate
  horizontal continuation, persisted columns/density, and linked inspector;
- thread lifecycle and cache-efficiency frontier;
- tools/files explorer backed by diagnostic and content-index metadata where
  allowed;
- responsive ranked-list alternative on mobile;
- previous/next call, copy link, exports, and direct Call Investigator retained.

Gate:

- 100k-row synthetic table performance fixture;
- query/filter/sort/paging parity tests;
- sticky containment and keyboard grid tests;
- Calls, Threads, and Call Investigator manual parity review.

Implementation checkpoint (2026-07-11):

- Calls and Threads now prefer focused, paged localhost contracts while keeping
  the loaded dashboard model as the static/fallback source;
- the shared evidence grid virtualizes large result sets, persists density and
  visible columns, freezes the identity column, keeps headers sticky, exposes a
  compact mobile ranked list, and preserves keyboard row activation;
- Threads includes table, cache-frontier, and lifecycle views backed by
  `VisualizationSpecV1`, plus selected-thread call hydration;
- the Explore switcher now reaches Calls, Threads, Tools, and Files. Tools use
  focused diagnostic facts and supporting-call lookups; Files join stored file
  read/modification diagnostics by safe path hash;
- Calls, Threads, their inspectors, context evidence, filters, view components,
  and analysis/controller logic were split so every touched source module stays
  below the redesign's 400-nonblank-line budget;
- desktop inspectors are viewport-bounded with internal scrolling while tablet
  and mobile retain normal page flow; the strict desktop/tablet/mobile overflow
  and control-overlap matrix passes across all dashboard routes;
- focused contract, URL, i18n, paging, investigator, and 100k-row virtualization
  tests pass, along with the full 314-test dashboard suite, governance/build and
  bundle gates, 43 focused Python integration tests, Playwright workflow smoke,
  and release-readiness checks.

### R7. Investigate And Waste Intelligence

Target PR: `redesign/07-investigate` -> experiment

Deliverables:

- unified investigation workspace and evidence ledger;
- repeated file rediscovery, shell churn, large low-output, cache/context, tool
  output, file read/modification, concentration, and guided-summary findings;
- waste fingerprint matrix with linked calls/threads/facts;
- deterministic action recommendations, caveats, and verification actions;
- progressive diagnostics refresh and stored-snapshot state;
- explicit local-content trace when content access is enabled.

Backend scope, if needed:

- expose localhost routes that call the same report services as existing MCP
  waste tools and investigation walk;
- add one shared evidence envelope rather than page-specific response shapes;
- document contract and privacy behavior.

Gate:

- API/MCP/frontend contract equivalence tests;
- diagnostic snapshot/cache tests;
- privacy tests proving default aggregate surfaces omit indexed/raw content;
- evidence-to-call/thread browser flows.

### R8. Limits And Allowance Intelligence

Target PR: `redesign/08-limits` -> experiment

Deliverables:

- weekly allowance analysis as the primary Limits view;
- 5-hour rolling-window context as explicitly secondary/noisy evidence;
- change-point timeline with resets, missing spans, estimated credits, confidence
  intervals, candidate regimes, and outside-usage caveats;
- evidence grade, supporting calls/windows, method detail, and strict local export;
- hypothesis-oriented comparison workflow for community allowance claims.

Gate:

- stable/noisy/regime-shift/missing/outside-usage synthetic scenarios;
- API/MCP/dashboard payload parity;
- chart/table accessibility and export checks;
- copy review preventing unsupported allowance claims.

### R9. Reports, Settings, And Remaining Parity

Target PR: `redesign/09-reports-settings` -> experiment

Deliverables:

- selected-report-first narrative workspace using shared visualization specs;
- compact report switcher, generation metadata, methods, caveats, and exports;
- Settings grouped into Data, Estimates, Content Access, Application, and Source
  Health;
- current pricing, allowance, parser diagnostics, privacy modes, content access,
  and i18n behavior retained;
- compatibility redirects for old route names not already migrated.

Gate:

- report generation/stale/refresh/error tests;
- settings persistence and source-health tests;
- complete route and feature-parity ledger with no unexplained omission.

### R10. MCP Visualization Experiment

Target PR: `redesign/10-mcp-visualization` -> experiment

Status: optional for the final dashboard release; evaluate after R4 and R7

Deliverables:

- `usage_visualization_suggest` and spec-first
  `usage_visualization_render` prototypes;
- dashboard/MCP semantic-spec equivalence tests;
- compact Codex examples for token waste, allowance change, cache failure, and
  thread lifecycle;
- documented decision on optional SVG/PNG artifacts without adding Node to the
  base runtime.

Stop condition:

- If spec output is not materially more useful than existing structured MCP
  payloads, document the experiment and defer image artifacts without blocking
  the dashboard release.

### R11. Hardening, Migration, And Release Candidate

Target PR: `redesign/11-release-candidate` -> experiment

Deliverables:

- route/viewport Playwright matrix for every workspace;
- axe, keyboard, focus, zoom, reduced motion, contrast, containment, and chart
  table-equivalence gates;
- performance traces for startup, 5k rows, No cap, 100k synthetic rows, reload,
  cache hit, and single appended record;
- production bundle and package-asset verification;
- synthetic docs screenshots and dashboard guide updates;
- legacy/default switch plan, rollback path, migration notes, and known-limit list;
- dependency/security audit with reachable-risk disposition.

Required broad checks:

```text
Agent Maintainer full and CI-equivalent profiles
Python Ruff, Mypy, Pytest, coverage, compileall, Tach
Dashboard lint, typecheck, Vitest, build, dependency rules, Knip, Stylelint
Playwright visual and workflow matrices
Synthetic history benchmarks
Release readiness, package build/install smoke, diff check
```

### R12. Final Main PR And Release Decision

Open one PR from `experiment/dashboard-final-redesign` to `main` only after R11.

The PR must include:

- before/after workflow evidence at desktop and mobile;
- signed feature-parity and route-compatibility ledger;
- architecture graph and debt/bundle deltas;
- API/MCP contract changes and migration notes;
- performance, accessibility, security, package, and browser results;
- default-switch and rollback instructions;
- explicit list of deferred non-blockers.

Merge requires maintainer approval. Versioning and release happen on a separate
release branch after the merged `main` is revalidated.

## Parallel Delegation Plan

Use at most three child agents at once, each in a disjoint worktree with a capsule
that names allowed paths, forbidden paths, acceptance commands, and stop
conditions. The parent owns integration and public contracts.

Safe parallel lanes after R1:

| Lane | Owns | Must not edit |
| --- | --- | --- |
| Design system | `design/`, shell primitives, CSS Modules, visual lab | API contracts, feature calculations |
| Data runtime | `data/`, router/query adapters, server contracts/tests | design tokens, visualization renderer |
| Visualization | `visualization/`, chart fixtures/tests | routes, data transport, feature pages |

Feature-route PRs are integrated sequentially when they touch shared inspectors,
URL state, or evidence contracts. Multiple writing agents never share one
checkout. Agents stop after their bounded deliverable and do not create nested
delegations.

## Review Scorecard

Every redesign PR answers these questions in its description:

1. Which user question became easier to answer?
2. Which old behavior or route is preserved, redirected, or intentionally
   deferred?
3. Which API/report contract is the source of truth?
4. What module/dependency debt decreased, and what new dependency surface was
   added?
5. What are the loading, empty, partial, stale, error, mobile, keyboard, and 200%
   zoom states?
6. Which focused and broad gates passed?
7. Which synthetic screenshot or browser flow proves the result?

## Immediate Next Unit

After this roadmap commit is pushed, begin R1. Do not start page redesign work
until dependency boundaries, visual contract ownership, and bundle reporting are
in place. That order lets future agents move quickly without recreating the same
large modules and global styles the redesign is intended to remove.
