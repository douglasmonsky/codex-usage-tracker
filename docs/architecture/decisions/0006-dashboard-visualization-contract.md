# Dashboard Visualization Contract And Renderer

Status: Accepted for the dashboard redesign experiment

## Context

The dashboard currently owns three small D3-based chart components. They render
basic line, bar, and donut views but do not provide a shared model for confidence
intervals, change points, linked selection, brushing, evidence keys, accessibility
summaries, or exports. Building each new analytical graphic directly in a route
would duplicate interaction and renderer details.

The API and MCP layers now expose allowance, cache/context, thread, diagnostic,
and waste evidence that can support substantially richer visuals. MCP may also
benefit from requesting a chart without depending on dashboard DOM.

## Decision

- Define a renderer-independent, React-free `VisualizationSpecV1` owned by the
  application. It carries semantic encodings, units, uncertainty, annotations,
  evidence keys, scope, freshness, caveats, interactions, accessible summary,
  and table columns.
- Use modular Apache ECharts core with the SVG renderer for complex interactive
  charts. Import only required chart and component modules.
- Keep existing D3 helpers during migration for data transforms and small stable
  primitives. Do not add another general chart library.
- Hide ECharts options behind one internal adapter. Features and API payloads
  must not expose renderer options.
- Lazy-load the renderer and visualization-heavy routes. Enforce a measured
  renderer-chunk budget.
- Every visualization ships loading, empty, partial, insufficient-data, stale,
  and error states plus a synchronized table and concise text summary.
- MCP experiments return `VisualizationSpecV1` plus compact evidence. Static
  artifact rendering must not make Node a requirement of the base Python package.

## Consequences

- Dashboard and MCP can share one analytical graphic contract while retaining
  replaceable renderers.
- Complex charts gain mature zoom, brush, annotation, and linked-interaction
  support without hand-rolling a chart framework.
- Accessibility remains an application responsibility; renderer ARIA alone is
  not considered sufficient.
- Contract changes require versioned fixtures and compatibility tests.
