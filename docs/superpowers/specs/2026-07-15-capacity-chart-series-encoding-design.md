# Capacity Chart Series Encoding Design

## Goal

Make the Limits capacity chart immediately distinguish subscription tier from
statistical role without relying on color alone.

## Visual Encoding

Subscription tier remains the primary hue:

- Pro uses blue.
- Pro Lite uses orange.
- Other explicit, mixed, and unknown tiers retain their existing stable hues.

Each tier uses two related shades and two distinct mark styles:

- Observed reset-window capacity uses the lighter tier shade, a thin line, and
  hollow circular markers.
- The trailing eight-window median uses a darker tier shade, a thick solid line,
  and no markers.

The darker median shade must remain recognizably related to its tier and meet the
dashboard's contrast expectations against the chart background.

## Legend

Replace the repeated four-series legend with two compact explanatory keys:

1. **Observed plans** lists each tier once with its hue.
2. **Chart marks** shows a thin line with a hollow dot for observed capacity and
   a thick marker-free line for the trailing median.

The keys use visible text and mark shape/weight, so the distinction remains
understandable for users who cannot reliably distinguish colors.

The chart's internal ECharts legend is hidden for this visualization only. Other
charts keep their existing legend behavior.

## Accessibility And Responsive Behavior

- Plan names and statistical roles are written out in the keys.
- Observed and median series differ by markers and line weight as well as shade.
- Screen-reader chart descriptions continue to identify each plan and statistic.
- Keys wrap onto additional rows at narrow widths without truncating labels or
  reducing touch targets elsewhere.

## Implementation Boundaries

- Extend the Cartesian visualization contract only as needed to support a hidden
  internal legend and explicit series line/marker styling.
- Generate plan-related shades through the Limits presentation layer rather than
  hard-coding colors in the generic renderer.
- Keep subscription-tier provenance, capacity calculations, and change detection
  unchanged.
- Rebuild packaged dashboard assets from `frontend/dashboard`; do not edit them
  directly.

## Verification

- A visualization-model test proves observed and median series receive distinct
  shades and mark styles.
- A renderer test proves the internal legend can be suppressed without affecting
  default chart legends.
- A Limits-page test proves both explanatory keys render with their accessible
  labels.
- Run focused tests first, then the full frontend suite, typecheck, lint,
  production build, release-readiness check, and a local screenshot inspection.
