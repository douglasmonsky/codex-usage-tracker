# Dashboard Final Redesign Specification

Status: design contract for `experiment/dashboard-final-redesign`

This specification is the decision baseline for the final planned large
dashboard redesign before 1.0. Implementation PRs may refine details through an
ADR or an explicit spec update, but they must not drift into another collection
of page-local patterns.

## Product Position

Codex Usage Tracker is a local evidence workspace for answering:

- What is consuming my Codex usage?
- Which patterns are likely waste, and what should I change?
- Did my observed allowance behavior change, or is the counter noisy?
- Which calls, threads, tools, files, commands, and context events support that
  conclusion?
- What is observed, estimated, inferred, missing, or explicitly private?

The dashboard should feel instrument-grade and editorially clear: serious enough
for research, fast enough for daily use, and plain about uncertainty. It is not a
marketing surface and should not resemble a generic SaaS admin template.

## Non-Negotiables

- Remain local-first, unofficial, MIT-licensed, and explicit about estimate
  confidence and missing observations.
- Preserve feature parity and direct URL compatibility before the final switch.
- Keep loaded-row scope distinct from total indexed scope everywhere.
- Treat API/report payloads as the source of analytical truth. React renders and
  cross-filters; it does not invent a second diagnostics engine.
- Preserve explicit opt-in access for indexed/raw local content.
- Use synthetic data for tests, screenshots, visual contracts, and docs.
- Keep every chart linked to inspectable evidence and an accessible table.
- Do not merge the experiment into `main` until all exit gates pass.

## Experience Model

Every analytical view follows the same four-layer model:

1. **Answer**: the primary finding, movement, or comparison.
2. **Confidence**: evidence grade, scope, caveats, and freshness.
3. **Explanation**: the visualization or ranked evidence that supports it.
4. **Action**: open calls/threads, change workflow, export evidence, or verify a
   hypothesis.

This model replaces pages that begin with generic KPI cards or catalogs.

## Information Architecture

### Primary destinations

| Destination | User question | Included workspaces |
| --- | --- | --- |
| Overview | What changed and what needs attention? | Priority findings, usage pulse, recent calls |
| Explore | Where did usage go? | Calls, Threads, Tools and Files |
| Investigate | Why did it happen and what can I fix? | Findings, waste patterns, cache/context, diagnostics evidence |
| Limits | Did allowance behavior change? | Weekly allowance, 5-hour context, change reports, evidence export |
| Reports | What can I save or share? | Reproducible reports, methods, exports |

Settings, data-source health, pricing, content access, and lower-frequency tools
live under **More**. Call Investigator remains a first-class detail route opened
from any evidence surface.

### Compatibility routes

Existing `?view=` values remain valid. During migration they resolve to the new
route or redirect while retaining relevant search, filter, record, thread, and
snapshot parameters. Bookmarked `view=call&record=...` links must continue to
work without requiring the record to be in the loaded page.

### Desktop shell

- 232 px full-height rail, collapsible to a 64 px icon rail.
- Persistent 52 px command bar for global search, data scope, refresh progress,
  and route actions.
- Unofficial-project notice remains visually unmistakable but becomes a compact
  28-32 px trust strip, not a large card.
- Main workspace owns its heading and local controls. Global controls do not
  repeat inside the page.
- Details use a stable resizable inspector, not a page-local card pushed below
  unrelated content.

### Mobile shell

- Compact top bar with title, data freshness, and overflow menu.
- Five-item bottom navigation: Overview, Explore, Investigate, Limits, More.
- Search and Data Scope open as full-width sheets with explicit Apply/Cancel.
- No horizontally scrolling primary navigation.
- The first meaningful route heading or answer appears within the first 160 px
  after the browser chrome in normal loaded state.

## Data Scope And Loading

Data loading is a product concept, not an implementation detail.

- The compact Data Window control shows the selected time range, bounded evidence
  rows, exact matching-call total, history scope, and active refresh progress.
- `All time` is the live default. `Last 24h`, `Last 7 days`, and a typed recent-row
  window remain one action away without losing page/filter state.
- Uncapped time windows aggregate the complete selected scope server-side while
  materializing at most 500 recent evidence rows in the browser. Focused tables
  page the complete result set instead of downloading it all at once.
- API/CLI `limit=0` and `limit=None` keep their documented unbounded compatibility
  semantics; the dashboard no longer requires that memory-heavy path for All time.
- Refresh progress exposes phase, processed files/records, percent when known,
  elapsed time, and cancel/retry where supported.
- TanStack Query handles route-level reuse, and revision-validated IndexedDB
  snapshots survive normal page reloads. Explicit refresh bypasses the persistent
  snapshot; a new index revision invalidates old entries. The compact Overview
  endpoint bundle uses the same revision contract in browser storage so warm
  reloads do not repeat its full-history summary and recommendation scans.
- Stale data remains visible while background refresh runs; the application does
  not replace useful content with an empty loading page.

## Visual Language

The release target is a desktop-first professional workstation UI. Visual QA
and interaction budgets cover compact desktop (1280x800) and standard desktop
(1600x900). Narrower windows should remain recoverable, but tablet and mobile
polish are not release criteria for this dashboard.

### Character

The visual direction is **evidence cockpit**: restrained operational structure,
high-quality data graphics, clear typography, and semantic color used only to
communicate meaning.

### Palette

Initial semantic tokens, subject to contrast validation:

| Role | Token | Initial value |
| --- | --- | --- |
| Workspace | `--surface-canvas` | `#f6f7f9` |
| Panel | `--surface-panel` | `#ffffff` |
| Rail | `--surface-rail` | `#171a20` |
| Primary text | `--ink-strong` | `#18202a` |
| Secondary text | `--ink-muted` | `#5c6675` |
| Border | `--line-subtle` | `#d9dee7` |
| Selection | `--signal-selection` | `#2f6fed` |
| Efficient/cache | `--signal-positive` | `#16866b` |
| Uncertain | `--signal-caution` | `#b96f0b` |
| Waste/risk | `--signal-risk` | `#c84652` |
| Reasoning/context | `--signal-context` | `#7651c9` |

No gradients, decorative blobs, glass effects, or single-hue page themes. Color
must never be the only carrier of status or series identity.

### Typography and rhythm

- System UI sans-serif for interface text; tabular numerals for metrics, axes,
  timestamps, costs, percentages, and token counts.
- Four functional text tiers: 12 px metadata, 14 px controls/body, 18-20 px panel
  titles, 26-30 px page answer. No viewport-scaled typography.
- Letter spacing is zero. Uppercase is limited to short metadata labels.
- Spacing scale: 4, 8, 12, 16, 24, 32 px.
- Corners: 4 px controls, 6 px panels, 8 px only for modal/sheet containers.
- Shadows are reserved for overlays and sticky surfaces; panels use borders and
  surface contrast.

## Page Templates

### Answer workspace

Used by Overview, Investigate, and Limits:

- compact title/action row;
- answer band with confidence and scope;
- primary visualization occupying the strongest area;
- evidence ledger or linked table;
- method and caveats disclosed after the evidence;
- inspector for selected evidence.

### Explorer workspace

Used by Calls, Threads, Tools and Files:

- filter/query bar directly above the data surface;
- visualization and table as switchable or linked views, not stacked filler;
- virtualized data grid with frozen identity columns and headers;
- stable right inspector on desktop and full-screen detail sheet on mobile;
- row activation works from keyboard, pointer, and deep link.

### Report workspace

- selected report narrative appears first;
- report chooser is a compact switcher, not a page of cards above the report;
- each report records generated time, scope, method version, caveats, and export
  options;
- saved reports render the same visualization and evidence contracts as live
  views.

## Visualization System

### Technology decision

- Keep the existing D3 utilities for data transforms and small deterministic
  primitives during migration.
- Adopt modular Apache ECharts core for complex interactive visualizations, using
  only required chart/components and the SVG renderer. Wrap it in an internal
  React adapter rather than exposing ECharts options to feature modules.
- Reserve Three.js for the specialized, lazy Overview usage constellation in ADR
  0008; it is not a second general chart API.
- Lazy-load the visualization runtime and route-specific chart modules.
- Define an app-owned `VisualizationSpecV1` contract. API, MCP, tests, and features
  depend on this semantic contract; ECharts remains a replaceable renderer.
- Do not add a second general chart library.

ECharts is selected for linked interaction, brush/zoom, annotations, confidence
bands, large datasets, SVG output, and mature chart composition. The adapter and
bundle gates prevent it from becoming a new global dependency surface.

### `VisualizationSpecV1`

The contract includes:

- `schema`, `id`, `title`, `question`, and `description`;
- `data`, typed dimensions/measures, and source endpoint metadata;
- plot type, encodings, domains, units, and semantic series roles;
- annotations, uncertainty bands, candidate events, and reset/missing regions;
- linked entity keys such as record, thread, fact, file hash, or time bucket;
- scope, freshness, confidence grade, caveats, and estimate metadata;
- supported interactions and export policy;
- accessible summary and table columns.

Feature modules may request or compose a semantic spec. They may not construct
raw renderer options.

### Required visualizations

1. **Allowance change-point timeline**: observed weekly remaining, estimated
   credits, confidence envelope, resets, missing observations, and candidate
   regime changes. Weekly is primary; the 5-hour signal is secondary context.
2. **Token-flow waterfall**: uncached input, cache read, output, and reasoning by
   call, thread, or period, with totals and estimate confidence.
3. **Cache efficiency frontier**: context pressure or cache rate against token or
   credit cost, with selectable call/thread bubbles and direct evidence links.
4. **Thread lifecycle strip**: calls, gaps, compactions, cold resumes, model/effort
   changes, and token bursts on one aligned timeline.
5. **Waste fingerprint matrix**: repeated file rediscovery, shell churn, and large
   low-output calls by thread and time bucket.
6. **Model/effort efficiency frontier**: token/credit behavior by model and effort,
   explicitly avoiding unsupported claims about output quality.
7. **Diagnostic evidence ledger**: sortable confidence, scope, effect size,
   supporting-call count, freshness, and next verification action.
8. **Content-index trace**: opt-in local-only view for matched fragments, tool
   calls, commands, and file events along a thread timeline.
9. **Usage constellation**: a bounded spatial view of chronology, token volume,
   cache reuse, model families, waste pressure, and thread continuity with direct
   Call Investigator links and a synchronized table.

### Chart interaction and accessibility

- Crosshair and direct labels for precise values; tooltips supplement rather than
  replace visible meaning.
- Brush, zoom, and recent-window defaults for long time series; frozen axis/legend
  context while the plot scrolls or pans.
- Clicking a mark filters or opens the linked evidence ledger. Selection persists
  in the URL when useful.
- Every plot exposes a synchronized table, concise text summary, keyboard focus,
  non-color series markers, reduced-motion behavior, PNG/SVG export where valid,
  and aggregate CSV export.
- Empty, insufficient-data, stale, partial, loading, and error states are designed
  states, not blank 0-1 axes.

## Tables And Inspectors

- TanStack Table remains the table model.
- Use the existing TanStack Virtual dependency for row virtualization and column
  virtualization only where measured widths require it.
- Freeze header plus the identity column (`Call`, `Thread`, `Fact`, or `File`).
- Provide a visible horizontal continuation cue, keyboard-accessible column
  chooser, density control, and Restore defaults.
- Use semantic column groups for Tokens, Cache, Estimate, Context, and Provenance.
- Persist column order, visibility, width, sort, and density per view locally.
- On mobile, replace unusable wide grids with a two-line ranked list and a
  full-screen inspector; retain a deliberate table mode for users who need it.
- One inspector component owns selection, tabs, provenance, copy link, prior/next,
  and open-full-page behavior across evidence surfaces.

## Frontend Architecture

### Stack

- React 19, TypeScript strict, Vite, Lucide, TanStack Table, and TanStack Virtual
  remain.
- Add TanStack Router for typed route/search ownership and route-level lazy
  loading.
- Add TanStack Query for server state, polling, cancellation, stale-while-refresh,
  query invalidation, and bounded persisted cache metadata.
- Use React state and reducer/context only for ephemeral local UI. Do not add a
  global client-state library unless a later ADR proves a missing capability.
- Use CSS Modules plus cascade layers and semantic CSS custom properties. Sass is
  not needed: runtime tokens and explicit ownership solve the current problem
  better than compile-time variables.

### Package shape

```text
frontend/dashboard/src/
  app/                 # router, providers, shell, error boundaries
  data/                # transport, query keys, contracts, adapters
  design/              # tokens, primitives, layout, accessibility helpers
  visualization/       # semantic specs, renderer adapter, chart lab
  entities/            # call, thread, fact, allowance, report, source
  features/            # cross-entity user actions and workflows
  routes/              # thin route composition and loaders
  fixtures/            # synthetic contract fixtures
  test/                # route harness, visual contract harness
```

### Dependency rules

- `app` composes routes and providers; feature modules do not import `app`.
- `routes` may compose feature public APIs but contain no calculations.
- `features` may import `entities`, `data`, `design`, and `visualization` public
  APIs, never another feature's internals.
- `entities` may import `data` and `design`, never features or routes.
- `visualization/spec` is React-free and renderer-free.
- `data/contracts` is React-free and contains no fixture fallback behavior.
- `design` imports no app, route, feature, entity, or data-fetching modules.
- Every package directory exposes a deliberate public entry point.

Enforce these rules with dependency-cruiser. Python Tach remains responsible for
the backend boundary map; the two tools should be reported together by Agent
Maintainer rather than pretending Tach understands the TypeScript graph.

### State and data flow

1. A typed route owns URL search state.
2. A query module maps route scope to one stable API contract.
3. Query results remain canonical and cached by scope/version.
4. Entities normalize presentation-safe values without recomputing diagnostics.
5. Features compose entities, visualization specs, and user actions.
6. Selection updates the URL and linked evidence surfaces.
7. Background refresh invalidates affected query keys and leaves stale data
   visible until replacement succeeds.

The synthetic fixture adapter is an explicit data provider selected at startup.
It is not mixed into production transport code.

## API Integration Plan

Use existing focused routes first:

- `/api/status`, `/api/summary`, and `/api/recommendations` for Overview;
- `/api/calls`, `/api/call`, `/api/threads`, and `/api/thread-calls` for Explore;
- `/api/diagnostics/*` and `/api/reports/pack` for Investigate and Reports;
- `/api/allowance/history`, `/api/allowance/diagnostics`, and
  `/api/allowance/export` for Limits;
- `/api/refresh/start`, `/api/refresh/status`, and `/api/usage` compatibility for
  data scope and refresh.

Add or revise backend contracts only when the UI otherwise must duplicate report
logic. Anticipated additions are:

- a unified evidence/finding envelope shared by recommendations, diagnostics,
  allowance reports, and waste reports;
- localhost API routes for repeated file rediscovery, shell churn, large
  low-output calls, and investigation walks already available through MCP/report
  services;
- chart-ready time buckets and linked entity identifiers, without renderer
  options;
- cache validators or source revision IDs so unchanged data can avoid full payload
  transfer and normalization.

Every new contract requires schema/version metadata, Python contract tests,
frontend decoder tests, privacy tests, and documentation in `docs/cli-json-schemas.md`
or the appropriate API document.

## MCP Visualization Plus

This is a late experimental capability, not a release blocker.

- Add `usage_visualization_suggest(question, scope)` to return ranked supported
  visualization intents and required evidence.
- Add `usage_visualization_render(kind, filters, format="spec")` to return
  `VisualizationSpecV1`, a compact evidence table, narrative, and caveats.
- The default `spec` format lets Codex or another client render the result without
  receiving dashboard DOM or private raw content.
- SVG/PNG artifacts require a separately evaluated local renderer path and must
  not make Node a runtime requirement for the base Python package.
- Content-index visuals remain explicit opt-in and must identify when snippets or
  raw fragments are included.

The dashboard and MCP must share the semantic spec and report services. MCP should
never automate screenshots of the dashboard as its visualization contract.

## Quality System

### Maintained gates

- Agent Maintainer TypeScript lint, typecheck, test, and build providers.
- Agent Maintainer file and change baselines ratcheted downward as modules split.
- dependency-cruiser for TypeScript import boundaries and cycles.
- Knip for unused exports, files, and dependencies.
- Stylelint for CSS ownership, token use, selector complexity, and invalid rules.
- Bundle-size budgets with route chunk reporting.
- Playwright route/viewport matrix, axe checks, console/page errors, interaction
  overlap, sticky containment, and document overflow.
- Visual contract screenshots for shell, tables, all chart states, drawers, and
  empty/error/loading states.

### Initial budgets

- Initial shell JavaScript: <= 85 kB gzip.
- Normal route chunk: <= 65 kB gzip; visualization-heavy route: <= 110 kB gzip.
- No new source module over 400 nonblank lines; target 250 for feature modules.
- No new CSS module over 300 nonblank lines.
- Changed frontend coverage >= 90%; critical state reducers and contract adapters
  require focused tests.
- No document-level horizontal overflow at 390, 768, 1024, 1440, and 1600 widths.
- Primary route content visible without scrolling at desktop and within 160 px of
  the app shell on mobile.
- Core actions usable at 200% zoom and by keyboard.

Budgets can be tightened after the first architecture slice. They may not be
weakened merely to land a page.

## Feature-Parity Contract

Before the final switch, the new dashboard must preserve:

- all current destinations and bookmarked route parameters;
- active/all history, arbitrary finite limits, no cap, load more, progress, live
  refresh, and persisted scope settings;
- global and page filters, sorts, columns, exports, and copy-link behavior;
- Calls and Threads row-to-investigator paths;
- previous/next call navigation and hydration outside the loaded snapshot;
- token breakdown, cache/context evidence, source metadata, pricing/credit
  confidence, and raw-context gating;
- diagnostic refresh/snapshot/fact-call behavior;
- report generation, allowance evidence/export, Settings source health, i18n
  behavior currently shipped, static fixture mode, and package asset serving.

Parity is demonstrated by automated contracts and an explicit manual checklist,
not by retaining old component structure.
