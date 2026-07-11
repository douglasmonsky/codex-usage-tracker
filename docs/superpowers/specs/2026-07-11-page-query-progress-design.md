# Page Query Progress Design

## Goal

Make full-scope dashboard loading visible at the page level so the shell's cached detail-row state is not mistaken for page readiness.

## Interaction

- Render a slim progress surface directly below each page header.
- Show it during initial endpoint loading, background refresh, and pagination that materially changes the page.
- Use completed query modules for determinate progress, such as `1 of 2 evidence modules ready`.
- Use an indeterminate bar when a page has one long-running query or cannot expose meaningful subdivisions.
- Never estimate progress from elapsed time.
- Remove the surface once all required page evidence is ready.
- Replace the loading state with a concise error state when required endpoint evidence fails; do not silently imply that fallback rows are full-scope data.

## Architecture

Add a reusable `PageLoadProgress` component with these inputs:

- `active`: whether page evidence is still loading.
- `completed` and `total`: optional module counts for determinate progress.
- `label`: page-specific loading description.
- `error`: optional endpoint failure message.

Pages remain responsible for defining which queries are required and calculating completed modules from their existing TanStack Query state. The component owns presentation, accessibility, and animation only. This keeps query ownership local and avoids a global registry coupled to route names.

## Initial Coverage

- Overview: summary and recommendation modules.
- Threads: thread summaries and selected-thread calls.
- Limits: allowance history and detector diagnostics.
- Cache and Context: summary, thread summaries, and selected-thread calls.
- Diagnostics: structured fact source plus diagnostic snapshot modules.
- Reports: report pack.
- Investigator: agentic report plus diagnostic snapshots.

Calls, Tools, and Files retain their existing table-level pagination indicators; the shared component can be adopted there later if route-level loading remains ambiguous.

## Visual Contract

- Reuse dashboard tokens and restrained blue/context colors.
- Keep the surface full-width within the page content, not a floating card.
- Use a fixed-height track so state changes do not shift surrounding content unexpectedly.
- Announce progress with `role="progressbar"` and a nearby polite status label.
- Respect reduced-motion preferences.

## Errors And Fallbacks

- Cached previous endpoint data may remain visible during refresh, with the bar labeled as updating.
- Initial endpoint failure must be visibly labeled as incomplete evidence.
- Static file mode may use snapshot data without showing a live-endpoint loading bar.

## Tests

- Component tests cover determinate, indeterminate, complete, error, and accessibility states.
- Focused page tests assert the bar appears while endpoint promises are pending and disappears after success.
- Existing route tests continue proving full-scope payloads and fallback behavior.
- Run dashboard typecheck, focused tests, governance, complete dashboard verification, and production build.
