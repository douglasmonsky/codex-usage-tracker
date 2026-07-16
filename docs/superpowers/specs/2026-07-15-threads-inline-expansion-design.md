# Threads Inline Expansion Design

**Date:** 2026-07-15
**Status:** Approved
**Scope:** React dashboard Threads workspace

## Problem

The Threads workspace currently separates the leaderboard from a large selected-thread inspector. A thread row selects that inspector, while row activation can open one representative call in Call Investigator. This makes the primary task—reviewing every call that belongs to a thread—feel indirect and makes an individual call appear to represent the whole thread.

The redesigned workspace must make a thread itself the unit of interaction. Clicking its leaderboard row must reveal the calls belonging to that thread in place. Opening Call Investigator must remain an explicit action on an individual call.

## Goals

- Make thread-to-call exploration immediate and spatially clear.
- Let the user reach every aggregate call in the selected thread without leaving Threads.
- Preserve cross-thread comparison by keeping the leaderboard visible.
- Keep large threads responsive while their calls load.
- Preserve stable URL state, sorting, filtering, exports, privacy boundaries, and explicit Call Investigator navigation.
- Provide complete keyboard, screen-reader, narrow-screen, loading, empty, partial, and error behavior.

## Non-goals

- Changing `/api/threads` or `/api/thread-calls` response schemas.
- Exposing prompts, assistant text, tool output, or other raw context.
- Redesigning Call Investigator.
- Replacing Cache Frontier or Lifecycle visualizations.
- Supporting multiple simultaneously expanded threads.
- Changing thread identity or parent/subagent attachment semantics.

## Chosen Interaction Model

The default Table view becomes a single-open inline accordion.

1. Clicking anywhere on a collapsed thread row expands a full-width detail region immediately beneath that row.
2. Clicking the expanded row again, or its explicit **Collapse** control, closes it.
3. Clicking another thread closes the previous region, cancels or ignores its obsolete in-flight work, and opens the new thread.
4. A parent thread row never opens Call Investigator, including on double-click or keyboard activation.
5. Each child call exposes an explicit **Open investigator** action and a secondary **Copy link** action.
6. The selected thread remains encoded as `thread=<name>` in the URL. Closing the expansion removes the thread-only child-call paging state.
7. Legacy `detail`, `expand`, and `threads` URL forms continue to normalize into the single selected-thread state.

This model was chosen over a persistent side inspector and a dedicated thread-detail route. It keeps calls attached to their source row, preserves comparison context, and removes ambiguous navigation without adding a new workspace.

## Information Architecture

### Leaderboard

The leaderboard remains the default Threads surface and retains search, risk filtering, sorting, column preferences, export, focused API status, and pagination. Its most decision-useful columns remain visible by default:

- thread identity;
- call count;
- total tokens;
- uncached input or cache ratio;
- Codex credits/cost confidence where available;
- peak context pressure;
- latest activity;
- cold-resume or attention risk.

The row receives a visible disclosure affordance and `aria-expanded`. The row’s selected styling is replaced or supplemented by a clear expanded state so selection is not confused with navigation.

### Expanded thread region

The current oversized side inspector is removed from Table view. Its useful content moves into the expanded region in this order:

1. A compact header with thread name, loaded/total call progress, and **Collapse**.
2. A concise summary strip for calls, total tokens, cached/uncached input, cache ratio, credits/cost, peak context, duration, and latest activity.
3. Sort controls for calls, retaining the existing sort keys and directions.
4. A dense call list showing time, model/effort, total tokens, cached/uncached balance, context pressure, duration/gap, cost or credits, and aggregate signals.
5. Explicit **Open investigator** and **Copy link** actions for every call.

The current inspector's lifecycle, relationship, impact, donut, status, and secondary-field cards do not move into the accordion. Cache Frontier and Lifecycle already preserve the deeper analytical views; the expanded Table region stays focused on choosing a call.

## Loading And Performance

Expansion paints immediately with any calls already available in the boot payload. When the live focused endpoint is available, the client requests `/api/thread-calls` pages in the current sort order and progressively loads the remaining pages until all matched calls are available.

- Progress is announced as `N of M calls loaded`.
- Switching or collapsing invalidates the old expansion. Late responses may populate the query cache but must not render into the new selection.
- A page failure preserves already loaded aggregate calls, labels the result partial, and provides **Retry loading calls**.
- An empty successful response shows a local empty state inside the expansion.
- The call list uses the repository's virtualization primitives so rendered call elements stay bounded for very large threads.
- The expanded region must not auto-scroll the page unexpectedly as pages arrive.
- Export continues to operate on the calls represented by the filtered Threads result, not only the currently expanded thread.

No API schema change is required. The existing 100-row `/api/thread-calls` pagination contract is sufficient.

## View Modes

Table remains the practical default. Cache Frontier and Lifecycle remain secondary modes. Selecting evidence in those visual modes may update `thread=<name>`, but inline expansion renders only after returning to Table. Visual-mode selections must never open a representative call implicitly.

## Responsive Behavior

On wide screens, the expanded region spans the full leaderboard width. The call list uses a compact tabular layout with horizontally safe column priorities.

On narrow screens, each call reflows to a stacked summary card. Primary evidence and **Open investigator** remain visible; lower-priority metadata follows without horizontal scrolling. Interactive touch targets are at least 44 CSS pixels, and expansion does not create nested scroll traps.

## Accessibility

- The thread disclosure is keyboard reachable and responds consistently to Enter and Space.
- The parent row or disclosure exposes `aria-expanded` and an accessible name such as `Expand calls for <thread>` or `Collapse calls for <thread>`.
- The expanded region is associated with its controlling row and has a useful accessible label.
- Loading, partial completion, retry, and completion are announced through a polite live region.
- Focus remains on the activating row/disclosure when expansion changes.
- Per-call buttons stop row propagation and have record-specific accessible names.
- Visible focus, non-color expanded state, semantic table/list structure, and reduced-motion preferences follow existing dashboard primitives.

## State And URL Contract

- `thread=<name>` identifies the one expanded thread.
- Existing `thread_call_sort`, `thread_call_direction`, and child-call paging compatibility remain supported.
- The UI uses an explicit internal `loading-all` state and does not encode an unbounded numeric page count in the URL.
- Sorting calls resets visible positioning and begins or resumes progressive loading in the new order.
- Filtering or paging the leaderboard collapses a thread that is no longer in the displayed result while preserving unrelated global filters.
- Leaving Threads clears Threads-only state through the existing shell URL cleanup.

## Error And Empty States

- No matching threads: retain the leaderboard empty state and show no detached inspector.
- Thread with zero calls: show `No aggregate calls are available for this thread.`
- Live endpoint unavailable: show boot-payload calls when present and label the source as a stored snapshot.
- Later page fails: keep loaded calls, show `Partial result`, and offer retry.
- Retry succeeds: remove the partial label and continue until the total is loaded.

## Implementation Boundaries

The design should preserve existing focused query and URL-state modules while separating three responsibilities:

- page orchestration: selected thread, query lifecycle, filters, sorting, and URL synchronization;
- expandable leaderboard presentation: parent rows and one full-width child region;
- expanded call evidence: summary, progress, sorting, virtualized rows, and explicit call actions.

The implementation should reuse existing formatting, signal, copy-link, query, and design-system helpers. It should avoid a broad EvidenceGrid rewrite unless a narrowly tested expansion seam is required.

## Testing And Acceptance Criteria

The change is complete when automated tests prove:

1. Clicking a collapsed parent row expands that thread’s calls inline and keeps the user on `view=threads`.
2. Clicking the same row collapses it; clicking another row leaves only the new thread open.
3. Parent-row click, double-click, Enter, and Space never open Call Investigator.
4. Every call retains explicit Open and Copy actions with correct return URLs.
5. Progressive pagination reaches all matched calls, reports progress, and does not duplicate rows.
6. Switching threads prevents stale responses from rendering under the new thread.
7. Partial failures preserve loaded rows and retry continues successfully.
8. Sorting, legacy URL hydration, direct `thread=` links, and shell state cleanup remain correct.
9. Large synthetic threads keep rendered call elements bounded.
10. Desktop and narrow-screen layouts preserve readable evidence and accessible actions.
11. The built plugin dashboard assets match the TypeScript source and pass source-budget, lint, typecheck, unit, browser-smoke, and release checks required for dashboard behavior changes.

## Privacy

All expanded content remains aggregate-only. The redesign must not call the raw-context endpoint, embed indexed snippets, or change static HTML privacy behavior.
