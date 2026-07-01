# Experimental Frontend Rewrite Roadmap

This branch is the experimental React rewrite track for Codex Usage Tracker. It must not be merged to `main`, made the default dashboard, released, or published without explicit approval.

## Current Branch Status

As of 2026-07-01, this branch contains a reviewable React + TypeScript + Vite dashboard prototype that builds into `src/codex_usage_tracker/plugin_data/dashboard/react/`. The legacy Python package, server, CLI, APIs, and legacy dashboard remain intact and unchanged as the default surface.

Implemented in this slice:

- React app shell with dark local-only navigation rail, status chips, top search, refresh actions, and URL-backed view state.
- Cohesive white analytical canvas using compact metric cards, dense tables, chart panels, right-side detail panels, and mobile-responsive layout.
- Feature workspaces for Overview, Investigator, Calls, Threads, Usage Drain Lab, Cache And Context Lab, Diagnostics Notebook, Reports, and Settings.
- Typed aggregate boot-payload normalization from existing embedded `usage-data` rows, with synthetic fallback fixtures.
- Shared chart, card, table, badge, panel, and formatting primitives.
- Vitest unit coverage and Playwright desktop/mobile smoke coverage for the experimental React dashboard.
- Vite production build output and package-data globs for the experimental React asset bundle.
- Pasted design references copied into `docs/assets/frontend-rewrite-references/`.

Not implemented yet:

- React default switch or legacy fallback routing.
- Backend report APIs under `/api/reports/*`.
- Full parity for every legacy filter, export, selected-call, language, and call-investigator workflow.
- Table virtualization for large live histories.
- Dedicated call investigator privacy-gated raw-context workflow.
- Legacy cleanup. That must happen only after React default acceptance on a later branch.

## Non-Negotiables

- Branch: `experiment/frontend-rewrite`.
- Base: current `origin/main`.
- Merge rule: no merge to `main` without explicit approval.
- Release rule: no release branch, release tag, TestPyPI publish, or PyPI publish from this branch without explicit approval.
- Legacy rule: current dashboard remains default until parity is proven and default switch is approved.
- Cleanup rule: legacy JS/CSS can be removed only in a later cleanup branch after React dashboard acceptance.
- Privacy rule: fixtures, screenshots, report payloads, docs, and tests must stay aggregate-only or synthetic. Do not commit raw prompts, assistant text, raw tool output, raw patch text, secrets, or real private records.

## Product Direction

The rewrite should feel like a serious local analytics workspace: dense, fast, legible, calm, and work-focused. Avoid marketing-page composition, decorative hero sections, oversized typography, one-off report styling, and dark/neon novelty treatment.

Visual language:

- White and near-white dashboard surfaces.
- Dark navy local-only navigation rail.
- Soft blue-gray borders.
- Navy primary text.
- Restrained blue, green, teal, and purple chart series.
- Orange and red only for warnings, candidate flags, and negative values.
- Compact cards with stable dimensions.
- Dense tables with aligned headers and numeric cells.
- Scrollable charts for long histories instead of overlapping labels.
- Clear disclosure icons, status chips, right-side detail panels, and notebook-style report rows.

## Visual Reference Catalog

These references are inspiration, not exact mockups to clone. The React implementation should use one cohesive Codex Usage Tracker design system.

| Reference | File | Use In React Dashboard | Design Requirements |
| --- | --- | --- | --- |
| Overview dashboard | [overview-dashboard-reference.png](assets/frontend-rewrite-references/overview-dashboard-reference.png) | Overview landing workspace | Summary cards, high-level chart grid, recent calls table, status and refresh controls. |
| Cache And Context Lab | [cache-context-lab-reference.png](assets/frontend-rewrite-references/cache-context-lab-reference.png) | Cache/context analysis workspace | Cache trends, cold resume candidates, context pressure, heatmap, recommended actions. |
| Command palette dashboard | [command-palette-dashboard-reference.png](assets/frontend-rewrite-references/command-palette-dashboard-reference.png) | Overview and Calls control density | Search, quick filters, compact cards, command-oriented workflow ideas. |
| Usage Drain Lab | [usage-drain-lab-reference.png](assets/frontend-rewrite-references/usage-drain-lab-reference.png) | Usage Drain Lab and Reports > Weekly Credits | Weekly credits, visible usage remaining, model controls, fast-mode controls, method caveats. |
| Thread Efficiency | [thread-efficiency-reference.png](assets/frontend-rewrite-references/thread-efficiency-reference.png) | Threads workspace | Thread leaderboard, selected thread panel, productivity and cold-resume signals. |
| Investigator Workbench | [investigator-workbench-reference.png](assets/frontend-rewrite-references/investigator-workbench-reference.png) | Investigator workspace | Ranked findings, selected-finding details, evidence table, confidence and caveats. |
| Diagnostics Notebook | [diagnostics-notebook-reference.png](assets/frontend-rewrite-references/diagnostics-notebook-reference.png) | Diagnostics Notebook and Reports narrative layout | Executive findings, report index, chart/evidence/caveat rows, notebook navigation. |
| Calls High Density | [calls-high-density-reference.png](assets/frontend-rewrite-references/calls-high-density-reference.png) | Calls table workspace | Dense table, column controls, heatmap-like numeric cells, side detail workflow. |
| Projected weekly credits overlap | [projected-weekly-credits-overlap-reference.png](assets/frontend-rewrite-references/projected-weekly-credits-overlap-reference.png) | Negative reference | Avoid x-axis label collisions with horizontal scrolling or tick thinning. |
| Generated exploration references | `generated-*.png` in reference folder | Archived design exploration | Preserve for context; do not copy dark/neon marketing style into the dashboard. |

## App Information Architecture

Top-level React navigation:

- Overview: high-level telemetry, status, summary cards, primary trends, recent calls.
- Investigator: current needs-attention cards, selected finding details, evidence, root-cause workflow.
- Calls: model-call table, filters, column/export controls, details entry points.
- Threads: grouped thread view, cost concentration, cache efficiency, cold-resume signals.
- Usage Drain Lab: weekly credits, visible usage remaining, model controls, fast-mode controls.
- Cache And Context Lab: cache behavior, cold resumes, context pressure, optimization recommendations.
- Diagnostics Notebook: operational diagnostics as a technical notebook.
- Reports: research-style generated reports from local aggregate data.
- Settings: local configuration and privacy state.

Diagnostics ordering target:

1. Projected weekly credits.
2. Usage remaining over time.
3. Existing diagnostics sections: Overview, Tool Output, Commands, Git Interactions, File Reads, File Modifications, Read Productivity, Concentration, What Is Driving Usage?

## API Plan

React should consume existing APIs where shapes are already suitable:

- `GET /api/status`
- `GET /api/usage`
- `GET /api/calls`
- `GET /api/call`
- `GET /api/threads`
- `GET /api/thread-calls`
- `GET /api/summary`
- `GET /api/diagnostics/*`

Add report APIs only when needed with smaller, stable, report-specific payloads:

- `GET /api/reports/index`
- `GET /api/reports/weekly-credits`
- `GET /api/reports/usage-remaining`
- `GET /api/reports/cost-curves`
- `GET /api/reports/usage-drain-model`
- `GET /api/reports/fast-mode-proxy`
- `GET /api/reports/token-cost-correlation`
- `GET /api/reports/allowance-change`
- `POST /api/reports/refresh`

Report payload contract:

- `schema_version`
- `generated_at`
- `history_scope`
- `filters`
- `warnings`
- `summary_cards`
- `charts`
- `tables`
- `metadata`

Report refresh must be on-demand only. Normal dashboard live refresh must not recompute heavy reports.

## Frontend Package Layout

```text
frontend/dashboard/
  index.html
  package.json
  tsconfig.json
  tsconfig.node.json
  vite.config.ts
  vitest.config.ts
  src/
    app/
    api/
    charts/
    components/
    features/
      cache-context/
      calls/
      diagnostics/
      investigator/
      overview/
      reports/
      settings/
      shared/
      threads/
      usage-drain/
    styles/
    test-fixtures/
```

Root `package.json` delegates dashboard scripts into `frontend/dashboard`.

## Implementation Milestones

| Milestone | Status | Notes |
| --- | --- | --- |
| Roadmap and inventory | Done | Roadmap, visual reference catalog, branch rules, parity checklist, and feature inventory added. |
| Build system | Done | React, Vite, TypeScript, Vitest, Testing Library, Playwright, TanStack Table, D3 helpers, Lucide, ESLint, package scripts, and package-data globs added. |
| React shell | Prototype done | Shell, navigation, status chips, search, metric cards, mobile responsive behavior, URL view state, and synthetic fallback fixtures implemented. |
| API client layer | Prototype done | Existing embedded `usage-data` rows normalize into calls, cards, and thread summaries. Live fetch helpers and report APIs remain future work. |
| Calls and Threads | Prototype done | Calls table, chart panels, thread leaderboard, and selected thread panel implemented with synthetic/boot aggregate data. Full legacy filtering, export, and virtualization remain future work. |
| Usage Drain and Cache Labs | Prototype done | Weekly credits, usage remaining, confidence intervals, controls, cache heatmap, and thread diagnosis surfaces implemented. |
| Diagnostics Notebook | Prototype done | Notebook layout, executive findings, section index, evidence rows, and status chips implemented. Exact legacy diagnostics ordering and expansion parity remain future work. |
| Reports workspace | Prototype done | Report library, weekly credits, cost curves, usage drain model, and confidence table surfaces implemented. Backend `/api/reports/*` remains future work. |
| Call investigator | Not started | Needs dedicated privacy-gated workflow and context API integration. |
| Default switch candidate | Blocked pending approval | Requires parity tests, live API integration, static fallback checks, and explicit approval. |
| Legacy cleanup | Blocked pending acceptance | Separate cleanup branch only after React default is approved. |

## Feature Inventory

| Area | Legacy Reference | React Owner | API Dependency | Required Tests | Status |
| --- | --- | --- | --- | --- | --- |
| Header/status chips | `dashboard_template.html`, `dashboard_status.js` | `app/` | `/api/status`, embedded payload | shell smoke, static mode | Prototype done |
| Global search and top controls | `dashboard_filters.js`, `dashboard.js` | `app/` | `/api/usage`, `/api/calls` | URL state, responsive layout | Prototype done |
| Metric cards | `dashboard.js`, `dashboard_analysis.js` | `components/MetricCard.tsx` | embedded payload, `/api/usage` | totals render, boot fallback | Prototype done |
| Overview charts | `dashboard.js`, `dashboard_analysis.js` | `features/overview/` | embedded payload, `/api/usage` | chart render, mobile screenshot | Prototype done |
| Investigator findings | `dashboard_insights.js` | `features/investigator/` | future `/api/recommendations`, `/api/summary` | cards render, selected finding | Prototype done with fixtures |
| Calls table | `dashboard_tables.js`, `dashboard_cells.js` | `features/calls/` | `/api/calls` | table render, navigation smoke | Prototype done; virtualization pending |
| Detail panel | `dashboard_details.js` | future `features/call-investigator/` | `/api/call` | selected call, empty state | Not started |
| Threads | `dashboard_tables.js`, `dashboard_details.js` | `features/threads/` | `/api/threads`, `/api/thread-calls` | grouping parity | Prototype done |
| Usage Drain Lab | current diagnostics usage-drain views | `features/usage-drain/` | future report payloads | CI table, long axis, controls | Prototype done |
| Cache And Context Lab | diagnostics/cache references | `features/cache-context/` | `/api/diagnostics/*` | heatmap, selected thread | Prototype done |
| Diagnostics snapshot panels | `dashboard_diagnostics.js`, `dashboard_diagnostics_snapshots.js` | `features/diagnostics/` | `/api/diagnostics/*` | stale, refresh, expansion | Prototype done with fixtures |
| Diagnostic facts | `dashboard_diagnostics_facts.js` | `features/diagnostics/` | `/api/diagnostics/facts`, `/api/diagnostics/fact-calls` | drilldowns | Not started |
| Reports index | generated report artifact references | `features/reports/` | `/api/reports/index` | report cards, status chips | Prototype done with fixtures |
| Weekly credits report | usage-drain report reference | `features/reports/` | `/api/reports/weekly-credits` | CI table, long axis | Prototype done |
| Cost curves report | cost curves report reference | `features/reports/` | `/api/reports/cost-curves` | thread ranking, chart | Prototype done |
| Fast mode report | fast mode report reference | `features/reports/` | `/api/reports/fast-mode-proxy` | histogram, scatter | Planned |
| Usage drain model report | usage drain predictor reference | `features/reports/` | `/api/reports/usage-drain-model` | actual/predicted, correlations | Prototype done |
| Call investigator | `dashboard_call_investigator.js` | future `features/call-investigator/` | `/api/context`, `/api/open-investigator` | privacy, context gating | Not started |
| i18n | `dashboard_i18n.js`, locales | `app/`, `api/` | packaged locale JSON | language switch | Not started |

## Parity Checklist

- Legacy dashboard still loads at `/dashboard.html`.
- React dashboard opt-in loads without changing legacy default.
- Overview, Investigator, Calls, Threads, Usage Drain Lab, Cache And Context Lab, Diagnostics Notebook, Reports, and Settings are reachable.
- Current UI screenshots can be recreated from synthetic local aggregate data.
- Projected weekly credits is first in the Usage Drain and Reports prototype.
- Usage remaining is second in the Usage Drain prototype.
- Diagnostics refresh remains on-demand in product direction; live recomputation is not wired in this prototype.
- Normal live refresh must not recompute diagnostics reports.
- Charts keep readable axes on desktop and mobile widths.
- Long weekly histories scroll or thin ticks instead of overlapping.
- Numeric table columns align headers and values.
- Money values show two decimals.
- Unknown plan rows do not pollute projected-credit trend lines unless explicitly enabled.
- Installed wheel includes required React assets.
- Static dashboard mode degrades gracefully when live APIs are unavailable.

## Dead Code Controls

- TypeScript `noUnusedLocals` and `noUnusedParameters` stay enabled.
- ESLint runs on React source.
- Build output must be inspected for unexpected legacy imports before any default switch.
- Use `rg` checks before removing legacy files.
- Keep legacy cleanup separate from feature migration.

## Verification Gates

Python:

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m pytest
.venv/bin/python -m compileall src
.venv/bin/python scripts/check_release.py
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
.venv/bin/python scripts/check_release.py --dist
```

Frontend:

```bash
npm ci
npm run dashboard:typecheck
npm run dashboard:lint
npm run dashboard:test
npm run dashboard:build
npm run dashboard:smoke
```

Checks run for this prototype slice:

- `npm run dashboard:typecheck`
- `npm run dashboard:lint`
- `npm run dashboard:test`
- `npm run dashboard:build`
- `npm run dashboard:smoke`
- `.venv/bin/python scripts/check_release.py`
- `git diff --check`
- Manual Playwright screenshots at desktop and mobile widths for Overview, Reports, and Usage Drain Lab.
