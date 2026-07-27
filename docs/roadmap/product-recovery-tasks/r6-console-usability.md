# R6 — Rebuild Console Usability

## Objective

Make the Evidence Console fast and understandable when a person opens it
directly or follows a link from Codex.

## Depends On

R4 and R5.

## Owned Areas

- `frontend/kernel-console/**`
- deterministic generated Console assets
- Console contract and browser tests
- localhost Console smoke
- synthetic screenshot fixtures

R6 does not change analytical semantics or MCP contracts.

## Contract Added First

Add failing browser and presentation contracts for:

- committed-generation Live render ≤500 ms;
- useful default Threads and Calls Explore views;
- every visible table heading sortable when the field supports ordering;
- pagination and filtering;
- human-first column ordering;
- exact evidence navigation;
- responsive layout and keyboard access;
- Limits usage-over-time graph;
- no rebuild or refresh on navigation or reopen.

## Live

Show:

- calls;
- total tokens with four-class breakdown;
- cache reuse;
- configured cost and estimated credits;
- recent token/allowance graph;
- freshness and refresh action without making freshness the main product.

Remove:

- “Snapshot truth”;
- “Tool-independent facts”;
- raw selector columns from the primary view.

## Explore

- Open on curated Threads and Calls views.
- Make switching datasets return a valid result or an actionable explanation.
- Put time, human label, and meaningful totals before internal fields.
- Keep the generic typed-query composer available but secondary.
- Support sortable headers, pagination, filters, and saved local views.
- Preserve one-generation consistency across a view.

## Evidence

Default order:

1. time;
2. turn number;
3. event or tool;
4. four-token or tool-impact facts;
5. cost or credits;
6. duration;
7. evidence action.

Long event IDs, selectors, generation IDs, and provenance details belong in an
expandable detail area or copy control. Timeline rows distinguish model calls,
tools, activities, and allowance observations without redundant category
columns.

## Limits

- Render compact interval data.
- Restore the usage-over-time graph.
- Show observed drain, local tokens, estimated credits, credits per usage
  point, reset boundaries, and coverage.
- Put time first.
- Do not synchronously scan foundational calls.

## Parallel Execution

After R5 freezes fixtures, R6 may run in parallel with:

- final R7 installed-runner work;
- R8 documentation copy.

Within R6, explicitly authorized subagents may own disjoint areas:

- Live and shared cards;
- Explore and reusable table interactions;
- Evidence and Limits;
- browser accessibility and responsive qualification.

Only the R6 coordinator edits shared model utilities, styles, generated assets,
and the deterministic asset manifest. Subagents work in separate worktrees and
return commits at named fixture checkpoints.

## Validation

- frontend unit, lint, type, and bundle checks;
- deterministic generated assets;
- Chromium desktop and mobile flows;
- keyboard sorting and pagination;
- direct evidence deep links;
- cached reopen with request-count assertion;
- page-level latency on production-shaped synthetic data;
- no implicit refresh;
- localhost installed-wheel Console smoke;
- synthetic screenshot inspection.

## Acceptance

- A person can understand every primary table without reading internal IDs.
- Sort, filter, paginate, and evidence actions work.
- Live and Limits pass latency gates.
- Explore never silently returns an empty broken view.
- Cost, credits, four tokens, turn order, and tool impact are visible.
- Final screenshots are ready for R8.

## Handoff

Record route-level timings, request counts, screenshots, accessibility results,
and final asset hashes. R8 may then publish the qualified visuals.
