# Specialized Three.js Usage Constellation

Status: Accepted for the dashboard redesign experiment

## Context

The redesign's `VisualizationSpecV1` and ECharts renderer cover analytical 2D
charts, synchronized tables, exports, and MCP-compatible semantics. The final
design review also requested one genuinely spatial view that can reveal how call
volume, cache reuse, chronology, and thread continuity relate. Treating that as
another ECharts plot would flatten the question, while making Three.js a second
general chart system would violate ADR 0006.

## Decision

- Add one specialized Three.js renderer for the Overview usage constellation.
  It is not available as a general feature-level drawing API.
- Keep data preparation renderer-independent. The Overview feature produces
  deterministic points, links, legends, an accessible summary, and table rows;
  the Three.js module only renders that semantic model.
- Map chronology to x, token volume to y and point size, cache reuse to z, model
  family to color, waste pressure to glow, and thread continuity to links.
- Bound rendering to 800 representative calls. Sampling always keeps timeline
  edges, high-token calls, and high-waste calls before filling the remaining
  slots chronologically.
- Lazy-load the renderer when the section approaches the viewport. The scene is
  static while idle, renders on camera changes, caps device pixel ratio, and
  disposes all WebGL resources on unmount.
- Make point clicks open Call Investigator. Provide a synchronized keyboard
  accessible evidence table and automatically use it when WebGL is unavailable.
- Keep all fixtures, visual evidence, and pixel checks synthetic.

## Bundle Measurement

Three.js 0.185.1 plus OrbitControls and the application scene measure 131.16 kB
gzip in the production Vite build. The module is absent from the initial bundle
and loads only for the constellation view. A 140 kB gzip hard ceiling gives
bounded platform and patch-version headroom without weakening the 65 kB normal
route or 114 kB ECharts renderer limits. Any increase beyond 140 kB requires a
new measured decision.

## Consequences

- The dashboard gains one high-impact spatial evidence view without exposing a
  second general chart API or changing MCP payload contracts.
- The default initial JavaScript budget remains unchanged.
- WebGL support, camera interaction, pixel output, point drill-through, mobile
  framing, reduced motion, and table parity become release-candidate gates.
- Static image rendering through MCP remains out of scope; MCP continues to
  return semantic visualization specifications and evidence tables.
