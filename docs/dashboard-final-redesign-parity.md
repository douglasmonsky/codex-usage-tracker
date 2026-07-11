# Dashboard Final Redesign Parity Ledger

This ledger is the review contract for the experimental dashboard redesign.
It records preserved behavior, intentional route aliases, and explicitly
deferred work so the final switch does not rely on an informal visual review.

Status meanings:

- **Complete**: implemented and covered by focused tests or browser evidence.
- **R11 gate**: behavior exists, but release-candidate evidence is still
  required. No ledger row remains in this state after the local R11 pass.
- **Deferred**: deliberately outside the redesign release, with the current
  behavior retained.

## Route Compatibility

| URL contract | Destination | Status | Compatibility notes |
| --- | --- | --- | --- |
| `view=overview` | Overview | Complete | Default route and invalid-view fallback. |
| `view=insights` | Overview | Complete | Historical alias is normalized to `overview`; `return=insights` is normalized too. |
| `view=investigator` | Investigate | Complete | Finding and investigation-walk state remain URL-backed. |
| `view=calls` | Calls | Complete | Search, source, sort, density, page, and legacy filter parameters remain supported. |
| `view=call&record=...` | Call Investigator | Complete | Direct records can hydrate outside the loaded page; return-route and context-option parameters remain valid. |
| `view=threads` | Threads | Complete | Selected thread, expansion aliases, call sort, and paging state remain supported. |
| `view=usage-drain` | Limits | Complete | Stable route identifier is retained while the visible navigation label is `Limits`. |
| `view=cache-context` | Cache And Context | Complete | Selected cache thread remains URL-backed. |
| `view=diagnostics` | Diagnostics Notebook | Complete | Source, fact, and snapshot state remain URL-backed. |
| `view=reports` | Reports | Complete | Selected report remains URL-backed through `report=...`. |
| `view=settings` | Settings | Complete | Selected settings group is local preference state; the route remains stable. |

No other historical `view` values are present in the maintained dashboard
documentation or compatibility tests. Unknown values continue to resolve to
Overview instead of producing a broken route.

## Shell And Data Scope

| Capability | Status | Evidence or disposition |
| --- | --- | --- |
| Unofficial-project notice | Complete | Persistent trust strip and sidebar status. |
| Global search | Complete | Filters compatible workspace evidence and exports. |
| Active/all-history scope | Complete | URL and session preference persistence; live refresh retains scope. |
| All-time/24-hour/7-day/recent-row windows | Complete | All time is the live default with exact full-scope totals and 500 bounded evidence rows; typed recent-row limits remain available. API `limit=0` remains compatible. |
| Loading progress, cancel, stale-data retention | Complete | Refresh keeps the stored snapshot visible and exposes phase/progress when available. |
| Static/live state, refresh, auto refresh | Complete | Static controls are honestly disabled; live token-gated requests stay local. |
| Current-view CSV and copy link | Complete | Route-specific exports and URL-backed state are tested. |
| Language and text direction | Complete | Existing catalog selection, local persistence, `lang`, and `dir` behavior remain in the shell. |
| Query/cache reuse across routes and reload | Complete | TanStack Query handles route reuse; revision-matched IndexedDB snapshots restore bounded usage evidence, and the small Overview endpoint bundle restores from revision-matched browser storage. Real-data warm reloads issue no usage, summary, or recommendation request. |

## Workspace Parity

| Workspace | Preserved or improved behavior | Status |
| --- | --- | --- |
| Overview | Loaded-call totals, four-part token accounting, recent-first scrollable trends, weekly-first remaining usage, findings, and investigator-linked recent calls | Complete |
| Investigate | Finding selection, queryable evidence, token-waste patterns, bounded investigation walks, linked calls, and URL-restorable state | Complete |
| Calls | Search and filters beside the table, stable sort/paging/density, frozen identity/header cells, token/cache/context/estimate fields, row and action-button investigator navigation, CSV export | Complete |
| Call Investigator | Aggregate identity, previous/next, source metadata, token accounting, gated raw context, compaction/tool-output controls, copy link, and source-aware return | Complete |
| Threads | Search/risk filters, dense sortable table, selected-thread lifecycle, child-call paging/sort, frozen identity/header cells, investigator links, call-grain export | Complete |
| Limits | Weekly-primary allowance evidence, explicitly secondary 5-hour context, detector grade, change candidates, exact available intervals, hypothesis test, strict export, linked supporting calls | Complete |
| Cache And Context | Cache segments, pressure/risk evidence, selected-thread calls, context controls, and investigator links | Complete |
| Diagnostics Notebook | Cached snapshots, refresh/stale/error states, facts and sections, source/fact selection, evidence tables, and investigator links | Complete |
| Reports | Selected-report-first narrative, compact switcher, report-specific visualization, source/generation metadata, methods, caveats, export, cached refresh states, and linked evidence | Complete |
| Settings | Data, Estimates, Content Access, Application, and Source Health groups; persisted group selection; pricing, allowance, parser, privacy, content, runtime, and i18n facts | Complete |

## Data And Contract Parity

| Contract | Status | Notes |
| --- | --- | --- |
| Static packaged dashboard | Complete | All workspaces retain fixture fallback; wheel install, package-resource, React-route, and legacy rollback smoke checks pass. |
| Localhost token-gated API | Complete | Server state is shared through typed clients and query caching; raw context is opt-in only. |
| Calls and threads APIs | Complete | Filtering, sorting, paging, `limit=0`, and linked identities retained. |
| Allowance history/diagnostics/export APIs | Complete | Limits renders the shared detector payload instead of reimplementing detection in React. |
| Diagnostics snapshots and facts APIs | Complete | Cached notebook data and linked evidence retained. |
| Reports pack API | Complete | Existing schema remains compatible; the UI adds presentation metadata without changing server semantics. |
| CSV/JSON exports | Complete | Aggregate exports retain compatibility headers; strict allowance export omits local identifiers. |
| MCP structured payloads | Complete | Existing structured tools remain compatible; suggestion and spec-first rendering tools add the shared visualization contract without raw fragments. |

## Explicit Non-Blockers And R11 Evidence

The following items are not silent omissions:

- R10 retained semantic visualization specs and explicitly deferred SVG/PNG
  artifacts so the base Python runtime remains browser- and Node-free.
- Raw prompts, assistant text, file content, and command output remain absent
  from aggregate dashboard payloads. Explicit Call Investigator content access
  stays local and gated.
- The redesign does not add writable pricing, allowance, privacy, or parser
  configuration controls. Settings reports the authoritative local state and
  points users to existing configuration workflows.
- R11 completed the desktop route matrix, axe and keyboard evidence, 200% zoom,
  reduced motion, contrast, large-row performance, reload/cache benchmarks,
  package verification, synthetic documentation screenshots, and rollback
  rehearsal.
- The final merge to `main` remains blocked on the R12 branch audit, PR checks,
  and maintainer approval.
