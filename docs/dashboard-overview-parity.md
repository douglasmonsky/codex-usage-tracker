# Dashboard Overview Parity

Status: Signed off for R5 on the dashboard redesign experiment.

The answer-first Overview replaces the legacy card grid while preserving the
workflows users could complete from the old page. The focused API payloads are
the source of ranked conclusions; loaded call rows remain the source of loaded
totals and row-level navigation.

| Legacy capability | R5 behavior | Evidence |
| --- | --- | --- |
| Unofficial-project disclosure | Retained in the shell before dashboard content | App and browser smoke tests |
| Loaded call total | `Calls loaded` uses the current loaded call array, not the theoretical database total | `App.overview.test.tsx` |
| Token total and breakdown | Total tokens includes cached input, uncached input, output, and reasoning output detail | `App.overview.test.tsx` and `overviewModel.test.ts` |
| Cache and credit summary | Compact loaded-scope readouts remain available | `OverviewMetrics.tsx` |
| Findings | `/api/recommendations` drives the answer and ranked evidence rail; static snapshots retain a labeled fallback | Endpoint contract and page tests |
| Trend chart | Replaced generic token/cost cards with a focused daily usage pulse backed by `/api/summary` when live | Visualization contract and page tests |
| Token composition | Replaced the donut with synchronized chart/table token accounting and an overlap caveat | `overviewModel.test.ts` |
| Global filters | Kept beside Recent Calls rather than above the page answer | Browser review |
| Global search | Filters the loaded Recent Calls evidence list | `overviewCallsForQuery` export compatibility |
| Recent calls | Virtualized list keeps sticky headers and thread identity, plus keyboard row activation | Overview Playwright spec |
| Open and copy call | Row, open icon, and copy icon remain available | Overview Playwright and App tests |
| Load more / load all | Both controls remain adjacent to the evidence list and preserve shell loading state | `App.overview.test.tsx` |
| CSV export | Shell export compatibility and a scoped Recent Calls export remain | `currentViewExport.ts` and Overview component |
| Refresh | Shell refresh remains available; desktop Overview also exposes a direct refresh action | Overview component |
| Investigation routes | Direct actions reach Investigator, Limits, Threads, and Call Investigator | Overview Playwright and component tests |
| Static/live behavior | Static snapshots render immediately; live focused endpoints show loading, partial, and fallback states without hiding loaded evidence | Overview Playwright and query tests |

The old Overview-only estimated-cost chart is intentionally not duplicated.
Cost remains available in Calls, Threads, Investigator, Reports, and exports;
the Overview now reserves chart space for usage movement and decision-changing
evidence.
