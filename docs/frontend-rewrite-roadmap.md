# Experimental Frontend Rewrite Roadmap

0.14.0 release hardening update: React dashboard transition release gates now live in `docs/react-dashboard-0.14-release-roadmap.md`; new rewrite work should clear that checklist before the minor release branch.

React live shell boot update: `/react-dashboard.html` now injects the same aggregate-only `usage-data` API token shell payload as the dashboard route, with zero embedded rows and the finite server default limit. This keeps the preferred React route live-enabled while preventing accidental no-cap startup loads on large histories; real-data QA covered finite startup, typed finite load, Load more, and explicit No row cap requests on a 75k-row dataset.

React default launch update: `serve-dashboard --open` now prints and opens `/react-dashboard.html` as the preferred dashboard while preserving legacy `/dashboard.html` on the same localhost server; JSON startup output exposes both URLs for tooling.

Open-investigator transition update: token-protected `/api/open-investigator` now accepts legacy `/dashboard.html?view=call&record=...` targets but normalizes the opened tab to `/react-dashboard.html?view=call&record=...`, preserving fragments and return-view query state.

Real-data route QA update: current branch source server on `127.0.0.1:8776` served rebuilt React assets while older `8765` process was stale; real-data Playwright sweep covered desktop/mobile Overview, Investigator, Calls, Threads, Usage Drain, Cache And Context, Diagnostics, Reports, Settings, and direct Call Investigator with zero console errors, failed local requests, or bad dashboard responses. Mobile workspace layout regression fixed in `styles/workspaces.css` so Cache/Context and related workspace titles no longer collapse to zero width after CSS module load order.

Diagnostics row-action parity update: Diagnostics evidence rows, snapshot rows, and structured fact calls now expose Copy link actions alongside Open investigator, preserving stable `view=call&record=...&return=diagnostics` links from notebook drilldowns.

Threads and Cache Context row-action parity update: thread leaderboard latest-call rows, selected-thread timelines, and Cache Context selected-thread calls now expose Copy link actions beside Open investigator, preserving workspace-aware return links from dense thread/cache review surfaces.

Workspace row-action parity update: Overview investigation preset top calls plus Reports, Usage Drain, and Investigator Workbench side evidence lists now expose Copy link actions beside Open investigator, preserving stable `view=call&record=...&return=...` links from modular side-panel evidence.

Clipboard fallback update: React Copy link actions now share the legacy dashboard textarea fallback when `navigator.clipboard` is unavailable, covering topbar view links, Calls view links, row call-investigator links, and full-page Call Investigator links.

Diagnostics CSS modularity update: Diagnostics-only snapshot, fact, source-tab, and evidence-row styles moved from the monolithic `dashboard.css` into `styles/diagnostics.css` with scoped CSS custom properties for repeated Diagnostics colors.

Workspace CSS modularity update: workspace layout, report/finding cards, side evidence, and mini-timeline styles moved from the monolithic `dashboard.css` into `styles/workspaces.css` with native CSS custom properties; Sass remains deferred to avoid adding build dependencies during release hardening.
Shell CSS modularity update: app shell, sidebar navigation, topbar, row-limit controls, and generic page title/layout controls moved from the monolithic `dashboard.css` into `styles/shell.css` with shared native CSS custom properties; Sass remains deferred unless mixins/nesting produce clearer release code.
CSS token/control modularity update: shared theme variables, base reset, topbar/search controls, and row-limit controls now live in `styles/tokens.css`, `styles/base.css`, and `styles/controls.css`, shrinking `styles/shell.css` without adding a Sass build dependency.
Shared component CSS modularity update: metric grids, panel/card primitives, toolbar buttons, column menu, table, chart, badge, filter, and density-toggle styles moved from the monolithic `dashboard.css` into `styles/components.css` using shared shell CSS variables, reducing dashboard feature CSS to call/cache/detail sections.
CSS split hardening update: remaining dashboard feature styles are now split into bounded `charts.css`, `tables.css`, `filters.css`, `investigation.css`, `context-evidence.css`, and `detail-context.css` modules; `dashboard.css` is reduced to responsive and generic residual styles, and Sass remains deferred in favor of native CSS variables plus smaller files during release hardening.
Calls detail-first URL parity update: React Calls now hydrates legacy `?view=calls&detail=first` URLs by selecting the first sorted row, promoting it into stable `record=...` URL state, and removing the stale `detail` flag.
Threads detail-first URL parity update: React Threads now hydrates legacy `?view=threads&detail=first` URLs by selecting the first visible thread, promoting it into stable `thread=...` URL state, and removing the stale `detail` flag.
Threads expanded URL parity update: React Threads now maps legacy `expand=first`, `expand=all`, and `threads=...` expanded-row URL state into the new selected-thread detail panel, promoting the selected thread into `thread=...` and clearing stale expansion params.
Threads URL/table-state modularity update: React Threads legacy URL parsing, `detail`/`expand`/`threads` normalization, selected-thread link building, table filtering/sorting, and child-call paging state now live in tested `frontend/dashboard/src/features/threads/threadsUrlState.ts`, reducing `ThreadsPage.tsx` while preserving explicit `direction=asc` sort URLs.
Calls pricing-alias URL parity update: React Calls now hydrates legacy `pricing=...` URLs as the current confidence filter, normalizing them into stable `confidence=...` state and clearing the stale `pricing` alias.
Legacy Insights URL parity update: React shell now maps legacy `view=insights` and `return=insights` URLs to the renamed Overview route, normalizing the query string while preserving Call Investigator back navigation.
Legacy keyboard shortcut parity update: React shell now maps numeric shortcut `1` to Overview, preserving the old dashboard's `1 -> Insights` behavior through the new Insights-to-Overview route mapping.
Legacy shell filter parity update: React non-Calls workspaces now derive scoped dashboard models from legacy shell URL filters `model`, `effort`, `confidence`/`pricing`, and `date`/`from`/`to`, keeping old copied links and topbar exports aligned outside the Calls table.
Global shell filter control update: React non-Calls workspaces now expose compact global Model, Effort, Confidence, Time, and custom date controls that write the same legacy URL params; Calls keeps its detailed table-specific filter row to avoid duplicate controls.
Shell URL modularity update: legacy shell URL compatibility helpers now live in `frontend/dashboard/src/app/shellUrl.ts` with focused unit coverage for Insights aliases, return-view safety, history-scope URLs, and route labels instead of remaining embedded in `App.tsx`.
History scope modularity update: React active/all-history payload scope derivation and archived-call status labels now live in tested `frontend/dashboard/src/app/historyScope.ts`, preserving legacy hidden/included archived-call messaging outside `App.tsx`.
Current-view export modularity update: React shell topbar CSV routing and Runtime State export rows now live in tested `frontend/dashboard/src/app/currentViewExport.ts`, preserving view-scoped exports while continuing to reduce `App.tsx`.
CSV header parity update: React call CSV exports now use legacy-compatible aggregate field names such as `record_id`, `timestamp`, `estimated_cost_usd`, `usage_credits`, `cache_ratio`, and `context_window_percent` while retaining expanded React-only source/thread/context fields.
CSV timing parity update: React call CSV exports now preserve legacy `call_started_at` and `previous_call_event_timestamp` timing columns.
CSV order parity update: React call CSV exports now keep the legacy timing/filtering column sequence as the prefix, then append React-only source/thread/context metadata columns.
CSV value parity update: React call row mapping now keeps legacy `event_timestamp` distinct from `call_started_at`; visible/exported `timestamp` uses event time while `call_started_at` preserves call start time.
Shell filter parity update: React shell date filters now show the legacy live date-range status for active custom ranges, preset start/end dates, and invalid ranges, making filtered charts and tables explain empty states.
Shell filter URL-alias update: React legacy shell filters now accept `time=` as a date-preset alias while keeping `date=` precedence, so copied filter links preserve date scope.
Shell confidence cleanup update: React shell Confidence controls now clear stale legacy `pricing=` aliases when rewritten to `confidence=...` or All confidence, preventing invisible copied-link filters from lingering.
Shell finding-state cleanup update: React shell navigation now clears stale `finding=` state when leaving Investigator, preventing copied links from carrying irrelevant investigator context into other workspaces while preserving Investigator return links through Call Investigator.
Shell thread-state cleanup update: React shell navigation now clears stale Threads-only URL state (`thread`, `expand`, `threads`, `thread_q`, `risk`, and child-call paging/sort params) when leaving Threads, preventing copied links from leaking thread context into unrelated workspaces.
Shell cache-state cleanup update: React shell navigation now clears stale Cache And Context URL state (`cache_thread`) when leaving Cache And Context, preventing copied links from carrying unrelated selected-cache-thread context into other workspaces.
Shell reports-state cleanup update: React shell navigation now clears stale Reports URL state (`report`) when leaving Reports, preventing copied links from carrying unrelated report-library selection into other workspaces.
Shell usage-drain-state cleanup update: React shell navigation now clears stale Usage Drain URL state (`usage_plan`, `usage_effort`, `usage_subagents`, `usage_sample`, `usage_confidence`) when leaving Usage Drain, preventing copied links from carrying unrelated drain-lab controls into other workspaces.
Shell diagnostics-state cleanup update: React shell navigation now clears stale Diagnostics URL state (`diagnostic_source`, `diagnostic_fact`) when leaving Diagnostics, preventing copied links from carrying unrelated notebook fact selection into other workspaces.
Shell calls-state cleanup update: React shell navigation now clears stale Calls table URL state (`detail`, `call_q`, `source`, `sort`, `direction`, `density`, `page`, plus selected `record` via existing call cleanup) when leaving Calls, while preserving shared shell filters such as model, effort, confidence, and date scope.
Shell URL cleanup modularity update: React shell inactive-workspace URL cleanup moved into tested `app/shellUrl.ts`, centralizing stale state ownership for Calls, Threads, Diagnostics, Reports, Usage Drain, Cache And Context, Investigator, and Call Investigator while preserving shared shell filters.
Call Investigator context-option URL parity update: React full-page Call Investigator now hydrates legacy raw-context option URL params (`mode`, `max_entries`, `max_chars`, `include_tool_output`, `include_compaction_history`) into evidence controls, preserving copied investigator links that request full/no-limit/tool-output context views without persisting raw context.
Call Investigator context-option cleanup update: React shell now treats raw-context option URL params as Call-owned state, preserving them on `view=call` but clearing them after leaving Call Investigator so copied non-call workspace links do not carry hidden raw-context controls.
Call Investigator context-option URL sync update: React Call Investigator evidence option controls now serialize non-default raw-context options back into the current `view=call` URL, so copied call links preserve changed full/no-limit/tool-output evidence settings.
Shell direct-navigation cleanup update: React direct navigation helpers for Investigator findings and preset actions now route through centralized inactive-view URL cleanup, so stale Call Investigator/context params do not leak when entering Investigator outside sidebar navigation.
Overview direct-finding URL cleanup coverage update: Overview Review actions now have regression coverage proving stale Call Investigator/context/report params are cleared while entering Investigator with selected `finding` state.
Threads export parity update: React Threads shell and page CSV exports now emit the call rows behind the filtered thread list as `codex-thread-filtered-calls-*.csv`, matching the legacy dashboard behavior instead of exporting only thread summary rows; the local Threads toolbar labels this action `Export calls` so the downloaded grain is explicit.

Diagnostics facts expansion update: Structured Diagnostic Facts now remember Show more expansion depth per source and sort while navigating away and back, preserving legacy-style drilldown review state across notebook visits.

Diagnostics notebook cache update: selected Diagnostic Fact Calls now restore the expanded merged result after leaving and returning to Diagnostics, preserving Load more work without another fact-calls API round trip.
Diagnostics snapshot cache update: live snapshot matrix cards now keep the last loaded snapshot rows visible during full-notebook refresh and revalidation instead of falling back to static cards while refresh is pending.

Thread timeline modularity update: Calls side-panel Thread tab and full-page Call Investigator now share one rich timeline renderer, keeping row Open/Copy actions, context-pressure bars, pricing labels, initiator/duration/gap details, and recommendation display aligned across both investigation surfaces.

Side-panel thread timeline update: Calls drill-down Thread tab now matches full-page Call Investigator timeline rows with initiator, duration, previous-gap, context-window, pricing-confidence, recommendation, context-pressure bar, and row Open/Copy actions.

Thread context signal-detail update: full-page Call Investigator thread timeline rows now include legacy-style initiator, duration, previous-gap, context-window, pricing-confidence, recommendation, and context-pressure bar modules alongside row Open/Copy actions.

Thread context copy-link update: full-page Call Investigator thread timeline rows now expose Copy link actions alongside Open, matching legacy detail panels and preserving return/query URL state through the existing call-link copier.

Context attribution follow-up update: full-page Call Investigator Context Attribution now exposes the same deferred serialized-analysis follow-up as the legacy investigator and React side panel, routing the module action through the cached raw-evidence loader.

Context attribution modularity update: full-page Call Investigator now reuses the shared React Context Attribution module used by the Calls side panel, keeping serialized evidence group rendering and hidden-context estimates aligned across investigator surfaces.

Context entry display-depth update: React side-panel and full-page Call Investigator evidence now remembers whether a record is showing compact returned context entries or all returned entries, preserving the reviewer-selected depth across tab switches and investigator transitions.

Context entry UI-state update: React side-panel and full-page Call Investigator evidence now remembers opened context-entry disclosures and per-entry text scroll positions in memory by record, matching the legacy investigator's review-state restoration across tab and surface transitions.

Context option memory update: React side-panel and full-page Call Investigator evidence now remembers per-record context request options such as full mode, entry depth, tool output, compaction history, and char limits, allowing cached non-default evidence views to reopen consistently across investigator surfaces.

Context evidence cache update: React side-panel and full-page Call Investigator evidence now reuse loaded local context payloads in memory per record/options across tab returns and investigator transitions, matching the legacy dashboard's per-record context cache without persisting raw context.
Context evidence state modularity update: side-panel Calls evidence and full-page Call Investigator evidence now share tested `frontend/dashboard/src/features/shared/contextEvidenceState.ts` for runtime gate messages, default context options, error formatting, load-older entry depth, and local evidence notes, preventing drift between the two investigation surfaces.

Context disclosure persistence update: React side-panel and full-page Call Investigator evidence now preserves opened context-entry disclosures across compact/all entry toggles and stable re-renders, matching the legacy investigator's remembered entry review workflow.

Usage Drain live snapshot row-action update: usage-drain diagnostic thread cost curves now attach representative aggregate `record_id` values, using the costliest/latest call per thread so React snapshot rows can open Call Investigator on real live data.

Diagnostics live snapshot representative-id update: source-log diagnostic snapshots now attach representative aggregate `record_id` values to tool-output, command, git, file-read, file-modification, and read-productivity rows when a matching usage row is indexed, enabling React snapshot row Open actions on real data instead of only fallback/concentration rows.

Diagnostics snapshot row-action update: React Diagnostics Snapshot Matrix now preserves representative aggregate record ids on fallback/live-like snapshot rows and opens the full Call Investigator from snapshot card rows when an id is available.

Call Investigator topbar export update: React shell Export CSV now respects the active full-page Call Investigator `record=` URL state and exports only that selected loaded call row.
Call Investigator state modularity update: selected-record resolution, live `/api/call` hydration precedence, previous/next navigation rows, thread timeline rows, position labels, and current-view export row selection now live in tested `frontend/dashboard/src/features/call-investigator/callInvestigatorState.ts`, so shell exports no longer import the full page component.
Call Investigator readout modularity update: exact accounting, previous-call deltas, evidence-state summaries, serialized-evidence bounds, next diagnostic move text, and hydrated-position detail now live in tested `frontend/dashboard/src/features/call-investigator/callInvestigatorReadout.ts`, keeping legacy investigation language pinned outside the page component.
Call presentation modularity update: Calls drill-down and full-page Call Investigator now share tested `frontend/dashboard/src/features/shared/callPresentation.ts` for cache-state labels, source-line formatting, context-window labels, and thread/model/effort count summaries, keeping call readouts aligned across investigation surfaces.

Usage Drain topbar export update: React shell Export CSV now respects active Usage Drain URL controls and exports the active evidence-call sample.

Cache Context topbar export update: React shell Export CSV now respects active Cache And Context selected-thread URL state and exports selected thread evidence calls.

Diagnostics topbar export update: React shell Export CSV now respects active Diagnostics structured-fact URL state and exports selected fact evidence calls.

Reports topbar export update: React shell Export CSV now respects active Reports report URL state exports selected report evidence rows.

Shell i18n update: React shell now reads embedded dashboard locale metadata, exposes the legacy language selector, updates document language/direction, and translates primary navigation/topbar/status/load labels where legacy catalog keys exist.

Reports API update: Local dashboard server now exposes aggregate-only `/api/reports/pack` report summaries and capped evidence rows for live report-pack workflows.

Investigator live-findings update: React live model building now derives aggregate Investigator findings for long threads, cache misses, high effort/reasoning, and output-heavy calls from loaded rows instead of leaving the Workbench empty on real-data launches.

Calls model-cost update: React live model building now derives Cost by Model bars from loaded aggregate rows, matching the existing Calls workspace chart for real-data launches instead of leaving it empty.

Overview live-trends update: React Overview now derives token, cost, and cache-rate trend series from loaded live aggregate rows instead of rendering empty charts for real-data launches.

Usage remaining card update: React Overview metric cards no longer reuse the fixture `32.4%` value for live payloads; Usage Remaining now derives from observed usage windows, then configured allowance windows, with an explicit unavailable state.

Cache heatmap label update: React Cache And Context no longer hard-codes fixture May/June heatmap labels; cache-window labels now come from heatmap row data with generic fallbacks and an explicit empty state for live snapshots without heatmap rows.

Overview cache-composition update: React Overview no longer hard-codes the fixture total in the Cache Composition donut; it uses live aggregate Total Tokens with a call-sum fallback for real data.

Overview recent-calls basis update: React Overview now explains the Recent Calls subset with shown rows, loaded/available rows, active/all-history scope, row request, and row-click Call Investigator behavior.

Investigator evidence-basis update: React Investigator Workbench now explains selected-finding evidence selection, ordering, and top-row cap in the Evidence Table subtitle and selected-finding side panel before users open workbench evidence calls.
Settings privacy-boundary update: React Settings now surfaces live privacy-boundary state, including payload mode, project metadata handling, raw-context gate state, and local API token scope alongside aggregate-only policy notes.
Cache/context diagnosis-basis update: React Cache And Context Lab now explains selected-thread suggested actions with a Diagnosis Basis module covering cold-resume risk, cache threshold, cost-per-call threshold, loaded calls, and heatmap availability.
Usage Drain evidence-basis update: React Usage Drain Lab now exposes an Evidence Basis module and evidence-table subtitle summary for the active sample, making effort/subagent scope, credit ordering, and sample/table caps explicit before users open evidence calls.
Reports evidence-basis update: React Reports now exposes an Evidence Basis module and table subtitle summary for the active report, making the selected aggregate-row rule, ordering, and top-row cap explicit before users open evidence calls.
Threads filter summary update: React Threads now mirrors Calls with a legacy-style active filter readout in the Thread Leaderboard subtitle, including search terms, cold-risk filter, and selected thread context while preserving URL-backed table state.
Calls filter summary update: React Calls now restores a legacy-style active filter readout in the Model Calls module subtitle, including search terms, model, effort, confidence, source, date range, and investigation preset context while keeping URL-backed controls synced.
Diagnostics fact-module update: React Structured Diagnostic Facts now ports legacy Top Facts, Tool and Function Activity, and Compaction Activity modules via selectable live sources backed by `/api/diagnostics/facts`, `/api/diagnostics/tools`, and `/api/diagnostics/compactions`.

Diagnostics fact-call table update: React Diagnostic Fact Calls now ports the legacy associated-call table readout with time, thread, model, effort, total, uncached, cache, and row-sized Open investigator actions.

Diagnostics fact-list depth update: React Structured Diagnostic Facts now loads legacy-sized fact sets, 50 top facts and 25 tool/compaction facts, and exposes a Show more control instead of silently stopping at the first six cards.

Diagnostics fact-card metadata update: React Structured Diagnostic Facts cards now expose legacy category, occurrences, total, cached, output, and latest timestamp readouts before opening the associated-call drilldown.

Diagnostics fact sorting update: React Structured Diagnostic Facts now ports legacy sort controls across loaded fact cards for uncached input, total tokens, associated calls, cache ratio, latest time, occurrences, and fact name with ascending/descending toggles.

Diagnostics fact-call sorting update: React Diagnostic Fact Calls now ports legacy associated-call columns for input, cached, output, and reasoning tokens plus local sort controls for token, cache, time, thread, model, and effort fields.

Diagnostics fact-call paging update: React Diagnostic Fact Calls now ports legacy associated-call paging by preserving live `total_matched_rows`, showing loaded-vs-total counts, and loading additional `/api/diagnostics/fact-calls` pages with offsets instead of silently capping the drilldown.

Diagnostics snapshot reload update: React Diagnostics Snapshot Matrix now ports legacy per-section Reload controls backed by named refresh endpoints, merging refreshed cards into the live notebook cache instead of forcing a full notebook refetch.

Side-panel serialized-analysis update: React Calls side-panel Serialized Evidence now ports the legacy Run full serialized analysis follow-up when quick evidence reports deferred bucket grouping.

Side-panel context attribution update: React Calls side-panel Raw Evidence now ports the Call Investigator visible-context versus serialized/hidden input estimate module after runtime evidence loads.

Side-panel evidence metadata update: React Calls side-panel Raw Evidence entries now share the Call Investigator timing, token-usage, compaction, and omitted-tool-output metadata chips.

Context entry visibility update: React side-panel and full-page Call Investigator evidence no longer silently hide returned context entries beyond the compact initial view; users can reveal all returned entries and collapse back.

Context entry modularity update: React side-panel and full-page Call Investigator Raw Evidence now ports legacy per-entry disclosure, keeping the first visible entry open and surrounding evidence collapsed for scan-first review.

Context note update: React side-panel and full-page Call Investigator evidence now port legacy loaded-context status note for local redaction, tool-output state, source file line, omitted older entries, omitted char budget, and no-char-limit state.

Compaction follow-up update: React side-panel and full-page Call Investigator evidence now port legacy Show compacted replacement entry action when local context entries report replacement history available but deferred.

Tool-output follow-up update: React side-panel and full-page Call Investigator evidence now port legacy Show tool output entry action when local context entries report omitted tool output.

Context follow-up update: React side-panel and full-page Call Investigator evidence now port legacy Load older context action when the local context API reports omitted older entries.

Calls source filter update: React Calls now ports source-aware filtering with URL-backed project/cwd, session, git, source-file, and missing-source scopes over aggregate metadata.

Row activation update: React Calls table now uses hover/Space for side-panel preview; single-click rows open the full Call Investigator without losing detail-panel selection.

Call decision update: React Calls drill-down and full-page Call Investigator now port legacy pricing status, next action, why-flagged, allowance-impact, and context-use fields from aggregate rows.

Call accounting update: React Calls selected-call Summary now surfaces the legacy token/pricing/credit/cache-savings breakdown as an Accounting Snapshot module without requiring the Tokens tab.

Diagnostics cache update: React Diagnostics Notebook now caches live structured facts, fact-call rows, and the snapshot matrix across route navigation; main dashboard Refresh invalidates the cache and explicit snapshot Refresh replaces it.

Live shell launch update: React no longer falls back to fixture rows for live shell boot payloads with zero embedded rows; it builds a real empty aggregate model and auto-loads `/api/usage` once without forcing an index refresh.

Call readout update: React full-page Call Investigator now ports the legacy four-card investigation readout for exact accounting, previous-call comparison, evidence state, and next diagnostic move.

Context attribution update: React full-page Call Investigator now ports the legacy visible-context versus serialized/hidden input estimate module after runtime evidence loads.

Serialized evidence update: React full-page Context Attribution now ports the legacy serialized evidence group breakdown for upper-bound local JSONL buckets.

Evidence metadata update: React full-page Raw Evidence entries now port legacy timing, token-usage, compaction, and tool-output-omitted metadata chips.

Call narrative update: React Calls side-panel Thread tab now ports legacy thread narrative fields: initiator, initiator reason, parent thread/session, timestamp, duration, previous gap, and source line.

Row limit update: React shell row loading keeps a finite quick slider but removes the typed count cap; entering 0 or checking No cap requests all aggregate rows, and the count field stays editable to return to any finite value.

Row range update: React shell quick slider no longer caps itself at available row totals; it expands past the current requested count while the typed count remains unlimited.
Row limit modularity update: React shell row-limit parsing, no-cap handling, slider span, Load more increment, and loaded/available status labels now live in tested `frontend/dashboard/src/app/rowLimit.ts` instead of remaining embedded in `App.tsx`.

Call source update: React Calls drill-down and full-page Call Investigator now share a visible Call Source module with legacy source line, project tags, thread attachment, session, parent, cwd, and git metadata from aggregate rows.

Agent metadata update: React Call Source now preserves legacy full-page investigator fields for turn id, thread source, subagent type, agent role/nickname, parent update time, and credit note.

Cache accounting update: React Calls Cache tab and full-page Call Investigator now port the legacy previous-call cache delta module for input, cached, uncached, output, reasoning, and cache-ratio changes.

Cache verdict update: React Cache Accounting now ports legacy cache diagnostic labels, explanatory verdicts, and next-step guidance alongside previous-call deltas.

This branch is the experimental React rewrite track for Codex Usage Tracker. It must not be merged to `main`, made the default dashboard, released, or published without explicit approval.

Latest parity slices: selected Thread detail ports child-call sorting and Load more paging; full-page Call Investigator keeps source/session/git metadata behind a legacy-style expandable detail block and source-aware return links; Calls side-panel Evidence now exposes full mode, entry-depth, and compaction-history context controls; Calls and Threads workspaces add Clear filters recovery actions for local filters and URL-backed selection state; row loading keeps granular finite controls while exposing an explicit no-cap all-rows request and a finite Load more rows action; Calls table restores legacy previous-gap, initiated-by, needs-attention sorting, and dense token/cache/credit/context columns; Threads table restores legacy latest activity, duration/gap, initiator, model/effort mix, token breakdown, credit, context columns, and direct latest-call investigator row actions.

Thread status update: React selected-thread detail now ports legacy pricing and credit status, cache/context status, and next-action signals from loaded aggregate calls.

Thread impact update: React selected-thread detail now ports legacy Codex credits, allowance-impact fallback, attention score, and cost-per-call impact fields from aggregate thread rows.

Thread timeline update: React selected-thread calls now port legacy timeline context bars plus context, pricing, duration, and credit meta while preserving row investigator actions.

Row range update: the React shell row slider now derives its span from available and typed aggregate row counts instead of a fixed 10k ceiling, while the explicit no-cap checkbox remains the all-rows request.

Calls modularity update: React Calls restores the legacy persistent Call Details visibility toggle so the drill-down can be hidden for full-width table review without losing row selection or investigator actions.

Calls date-filter update: React Calls now ports legacy date-range status feedback, including custom range labels and invalid-range zero-row behavior.

Calls URL-state update: React Calls now mirrors legacy live URL replacement for filter, sort, date, density, selected call record, table page, and table-header sort clicks, keeping copy/reload state current without history spam.
Calls URL-state modularity update: React Calls legacy URL parsing and link normalization now live in tested `frontend/dashboard/src/features/calls/callsUrlState.ts`, covering `pricing`/`time` aliases, `detail=first`, safe dates, sort/density/page fallback, and stale param cleanup.
Calls filter/sort modularity update: React Calls table filtering, date-range matching, attention scoring, deterministic sorting, and thread timeline time ordering now live in tested `frontend/dashboard/src/features/calls/callsFilterSort.ts`, preserving legacy custom date labels and reducing `CallsPage.tsx` component size.

Calls copy-link update: React Calls drill-down copied investigator links now preserve `return=calls` and the active Calls filter/sort URL state, matching row-action link behavior.

Calls CSV-depth update: React shared call exports now include legacy diagnostic/source fields including record/session/turn identity, source file and line, project and git metadata, thread attachment/source, pricing model, credit confidence, model context, cumulative tokens, cache savings, tags, and efficiency flags.

Calls topbar export update: React shell Export CSV now respects active Calls URL filters and sort state instead of exporting every loaded call.

Overview topbar export update: React shell Export CSV now respects the active Overview global search query instead of exporting every loaded call.

Investigator topbar export update: React shell Export CSV now respects the active Investigator finding URL state and exports that finding's evidence rows.

Threads topbar export update: React shell Export CSV now respects active Threads URL filters and sort state instead of exporting every grouped thread.

Threads URL-state update: React Threads now hydrates and live-syncs thread search, risk filter, selected thread, table sort, sort direction, and table page URL state while clearing stale call records.

Thread row activation update: React Threads and Cache And Context thread tables now match the Calls table interaction model: hover previews/selects the thread, while a single row click opens the latest call in the full Call Investigator.

Table page reset update: React Calls and Threads now reset URL-backed table pages to the first row window when user filter/search/sort controls change, matching legacy `resetVisibleRows()` behavior.

Thread detail URL update: React Threads now hydrates and live-syncs selected-thread child-call sort and paging through `thread_call_sort` and `thread_call_page` URL state.

Thread lifecycle update: React selected-thread detail now ports the legacy lifecycle summary for first expensive turn, largest token jump, cache/context trend, and subagent-before-spike signals from loaded aggregate calls.

Thread relationships update: React selected-thread detail now ports the legacy relationship summary for spawned-from, subagent, auto-review, attached, spawned-thread, and spawned-child-call counts from loaded aggregate calls.

Thread fields update: React selected-thread detail now ports the legacy secondary thread fields module for latest activity, total tokens, loaded calls, efficiency signals, model mix, and effort mix.

History scope update: the React shell now ports the legacy active/all history archived-call sentence, including hidden/included archived call counts from live payload metadata.

Shell status-chip update: the React shell now ports legacy environment status chips for the unofficial-project disclaimer, live/static mode, pricing configuration, allowance/rate-card health, project metadata privacy, and actionable parser diagnostics.

Settings source-health update: React Settings now ports legacy pricing snapshot warnings, allowance/rate-card errors, actionable parser diagnostics, and project metadata privacy flags.

Settings allowance update: React Settings now ports legacy observed usage and configured allowance windows with remaining percent, credit, and reset details.

Large table update: shared React tables now window large sorted row sets, expose a Show more rows control, and support controlled URL-backed page windows to avoid rendering every loaded call/thread at once.

## Current Branch Status

As of 2026-07-01, this branch contains a reviewable React + TypeScript + Vite dashboard prototype that builds into `src/codex_usage_tracker/plugin_data/dashboard/react/`. The legacy Python package, server, CLI, APIs, and legacy dashboard remain intact and unchanged as the default surface.

Implemented in this slice:

- React app shell with dark local-only navigation rail, status chips, top search, refresh actions, and URL-backed view state.
- Cohesive white analytical canvas using compact metric cards, dense tables, chart panels, right-side detail panels, and mobile-responsive layout.
- Feature workspaces for Overview, Investigator, Calls, Threads, Usage Drain Lab, Cache And Context Lab, Diagnostics Notebook, Reports, and Settings.
- Typed aggregate boot-payload normalization from existing embedded `usage-data` rows, with synthetic fallback fixtures.
- Aggregate row compatibility for newer dashboard/query fields including `call_started_at`, `cache_ratio`, thread attachment labels, usage-credit confidence, and recommendation signals.
- Shared chart, card, table, badge, panel, and formatting primitives.
- Working global search, Calls and Threads local filters, column choosers, sortable table headers, aggregate CSV exports, selected-call drill-down with Summary/Tokens/Cache/Thread/Evidence modules, gated Evidence context loading, hidden full-page `view=call&record=...` investigator route, and selected-thread detail panels.
- Quick links and prototype action controls now perform local aggregate actions or focus relevant controls instead of acting as inert placeholders.
- Vitest unit coverage and Playwright desktop/mobile smoke coverage for the experimental React dashboard.
- Vite production build output and package-data globs for the experimental React asset bundle.
- Pasted design references copied into `docs/assets/frontend-rewrite-references/`.

Not implemented yet:

- React default switch or legacy fallback routing.
- Deeper report-specific APIs under `/api/reports/*` beyond aggregate report pack.
- Full parity for every legacy advanced filter, language, and exact legacy call-investigator workflow.
- Table virtualization for large live histories.
- Dedicated full-page call investigator parity is in prototype: React now supports `view=call&record=...`, gated `/api/context`, and token-gated `/api/call` hydration for direct records outside the loaded snapshot; remaining exact legacy controls remain future work.
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
| Calls Analyst View | [calls-analyst-view-reference.png](assets/frontend-rewrite-references/calls-analyst-view-reference.png) | Calls table workspace | Dense table, column controls, heatmap-like numeric cells, shortcuts panel, side detail workflow. |
| Call Drill-Down Menu Concept | [call-drilldown-menu-concept-reference.png](assets/frontend-rewrite-references/call-drilldown-menu-concept-reference.png) | Calls selected-call side panel | Tabbed aggregate drill-down with Summary, Tokens, Cache, Thread, Evidence, locked raw-context actions, and compact token/cache/thread metadata readouts. |
| Projected weekly credits overlap | [projected-weekly-credits-overlap-reference.png](assets/frontend-rewrite-references/projected-weekly-credits-overlap-reference.png) | Negative reference | Avoid x-axis label collisions with horizontal scrolling or tick thinning. |
| Generated exploration references | `generated-*.png` in reference folder | Archived design exploration | Preserve for context; do not copy dark/neon marketing style into the dashboard. Exact duplicate overlap reference removed 2026-07-01. |

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
| API client layer | Prototype done | Existing embedded `usage-data` rows normalize into calls, cards, and thread summaries. Live `/api/usage` refresh, `/api/call` hydration helpers, and aggregate `/api/reports/pack` report-pack API are implemented; deeper report-specific APIs remain future work. |
| Calls and Threads | Parity slice in progress | Calls table, chart panels, thread leaderboard, selected call drill-down with Thread context module, selected thread panel, filters, column choosers, sorting, aggregate CSV export, gated side-panel Evidence context loading, and Calls-to-investigator action implemented. Virtualization remains future work. |
| Usage Drain and Cache Labs | Prototype done | Weekly credits, usage remaining, confidence intervals, controls, cache heatmap, and thread diagnosis surfaces implemented. |
| Diagnostics Notebook | Prototype done | Notebook layout, executive findings, section index, evidence rows, and status chips implemented. Exact legacy diagnostics ordering and expansion parity remain future work. |
| Reports workspace | Prototype done | Report library, weekly credits, cost curves, usage drain model, confidence table surfaces, live refresh, and aggregate `/api/reports/pack` endpoint implemented. Deeper report-specific APIs remain future work. |
| Call investigator | Prototype full-page route done | Hidden React `view=call&record=...` route loads one aggregate call, supports previous/next navigation, back-to-Calls, copy-link affordance, token accounting, aggregate identity, gated redacted context loading through `/api/context`, and live `/api/call` hydration when the selected record is outside the boot payload. Exact legacy parity remains future work. |
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
| Calls table | `dashboard_tables.js`, `dashboard_cells.js` | `features/calls/` | `/api/calls` | table render, navigation smoke, sorting, search, export | Aggregate filters, sorting, CSV export done; virtualization pending |
| Detail panel | `dashboard_details.js` | `features/calls/`, `features/call-investigator/` | `/api/call`, `/api/context` | selected call, empty state, gated evidence | Aggregate selected-call drill-down, Thread context module, side-panel context Evidence bridge, full-page investigator route, and `/api/call` hydration done |
| Threads | `dashboard_tables.js`, `dashboard_details.js` | `features/threads/` | `/api/threads`, `/api/thread-calls` | grouping parity, selected thread, export | Filters, sorting, CSV export, selected thread, and legacy aggregate detail columns done |
| Usage Drain Lab | current diagnostics usage-drain views | `features/usage-drain/` | future report payloads | CI table, long axis, controls | Prototype done |
| Cache And Context Lab | diagnostics/cache references | `features/cache-context/` | `/api/diagnostics/*` | heatmap, selected thread | Prototype done |
| Diagnostics snapshot panels | `dashboard_diagnostics.js`, `dashboard_diagnostics_snapshots.js` | `features/diagnostics/` | `/api/diagnostics/*` | stale, refresh, expansion | Prototype done with fixtures |
| Diagnostic facts | `dashboard_diagnostics_facts.js` | `features/diagnostics/` | `/api/diagnostics/facts`, `/api/diagnostics/tools`, `/api/diagnostics/compactions`, `/api/diagnostics/fact-calls` | drilldowns | Top Facts, Tools, Compactions source tabs and fact-call paging done |
| Reports index | generated report artifact references | `features/reports/` | `/api/reports/index` | report cards, status chips | Prototype done with fixtures |
| Weekly credits report | usage-drain report reference | `features/reports/` | `/api/reports/weekly-credits` | CI table, long axis | Prototype done |
| Cost curves report | cost curves report reference | `features/reports/` | `/api/reports/cost-curves` | thread ranking, chart | Prototype done |
| Fast mode report | fast mode report reference | `features/reports/` | `/api/reports/fast-mode-proxy` | histogram, scatter | Planned |
| Usage drain model report | usage drain predictor reference | `features/reports/` | `/api/reports/usage-drain-model` | actual/predicted, correlations | Prototype done |
| Call investigator | `dashboard_call_investigator.js` | `features/call-investigator/` | `/api/call`, `/api/context`, `/api/open-investigator` | privacy, context gating | Prototype React full-page route, Calls menu action, and server-side one-record hydration done; exact legacy parity remains pending |
| i18n | `dashboard_i18n.js`, locales | `app/`, `api/` | packaged locale JSON | language switch | Shell selector and topbar/nav labels started; full workspace translation pending |

## Parity Checklist

- Legacy dashboard still loads at `/dashboard.html`.
- React dashboard opt-in loads without changing legacy default.
- Overview, Investigator, Calls, Threads, Usage Drain Lab, Cache And Context Lab, Diagnostics Notebook, Reports, and Settings are reachable.
- Top search filters Overview recent calls and table-heavy workspaces.
- Calls workspace supports local search, model filter, effort filter, column chooser, sortable headers, aggregate CSV export, hover/click selected-call drill-down, and gated Evidence context loading through `/api/context`.
- Calls workspace now ports legacy previous-gap and initiated-by aggregate fields into the table, CSV export, column chooser, and `sort=gap`, `sort=initiator`, and `sort=attention` URL-backed sort presets.
- Calls workspace now restores legacy table density for total tokens, cached input, uncached input, reasoning output, Codex credits, and context-window percent as visible/sortable table columns and CSV fields.
- Calls workspace exposes an updated Open investigator action, and direct `?view=call&record=...` URLs render a full-page single-call investigator without embedding raw context.
- Direct call investigator URLs hydrate through `/api/call` with `X-Codex-Usage-Token` when the selected aggregate record is outside the loaded boot payload.
- React shell live controls now refresh `/api/usage` with the selected active/all-history scope and row load limit.
- React shell row loading now shows loaded/available aggregate row counts and ports a legacy-style Load more rows action that raises the finite live limit without switching to no-cap mode.
- Full-page Call Investigator includes a Thread Context module with relationship metrics, nearby-call timeline, peer-call Open actions, and source-aware return links.
- Overview Recent Calls rows now expose Open actions and single-click row activation into the full Call Investigator.
- Shared call action columns now port legacy per-row Copy link actions for direct `view=call&record=...` investigator URLs.
- Threads selected-detail panel now lists loaded related calls with row-sized Open actions into the full Call Investigator.
- Investigator Workbench scopes evidence calls by selected finding, shows modular evidence profile/call modules, and opens full Call Investigator from evidence table and side-panel evidence rows.
- Cache And Context Lab selected-thread diagnosis now updates from table row selection, lists related calls with row-sized Open actions, and adds latest-call investigator actions on thread rows.
- Usage Drain Lab controls now filter weekly windows/evidence calls, show a modular drain evidence profile, and open full Call Investigator from row-sized top usage-drain calls.
- Reports workspace now scopes evidence calls by selected report, includes a modular evidence profile, and opens full Call Investigator from report evidence table and side-panel rows.
- Diagnostics sections now list aggregate evidence calls with row-sized Open actions into the full Call Investigator.
- Diagnostics Notebook now includes structured diagnostic facts with live `/api/diagnostics/facts` support, fallback aggregate facts, and fact-call drilldown into the full Call Investigator.
- Diagnostics Notebook now ports the legacy diagnostics snapshot grid as a modular React matrix with live `/api/diagnostics/*` snapshot loading, fallback aggregate cards, and row-sized largest-impact Open actions.
- Settings now ports legacy runtime/source status with live/static mode, row load state, history scope, context gating, pricing/allowance source, and privacy boundary indicators.
- Overview now keeps the home surface focused on high-level metrics, scrollable trend charts, and Recent Calls row actions; preset-style investigation remains available through Calls URL filters and the Investigator workspace rather than homepage cards.
- React shell now ports the legacy Clear Preset control, removing `preset=` from the URL without leaving the current workspace.
- Topbar now ports legacy all-history URL state via `history=all`, global Copy view link, current-view CSV export, and replaces coarse row presets with a quick range plus uncapped typed row-limit control.
- Full-page Call Investigator Raw Evidence now ports legacy context option controls for full mode, entry depth, tool output, compaction history, and no-char-limit loading.
- React shell now ports the legacy Auto refresh toggle for live API dashboards, including immediate refresh, 10-second polling, and refresh-on-visible behavior.
- React shell now ports legacy scroll-aware Back to top control with smooth scroll restoration.
- React shell now ports legacy `/` search focus and `1`/`2`/`3`/`4` view shortcuts for Overview, Calls, Threads, Diagnostics while ignoring form fields.
- Calls now ports the legacy pricing/credit confidence filter for exact cost, estimated cost, unpriced cost, exact credit, estimated credit, user credit override, and missing credit-rate review.
- Calls now ports the legacy time preset filter for all time, today, this week, last 7 days, and this month.
- Calls now ports legacy custom date ranges with URL-backed `date`, `from`, and `to` state.
- Calls now ports legacy sort presets with URL-backed `sort` and `direction` state.
- Calls now ports legacy shareable view links for call search, model, effort, confidence, time/date, sort, and density state.
- Threads workspace supports local search, cold-risk filter, URL-backed selected thread state via `thread=`, column chooser with Escape/outside close, sortable headers, aggregate CSV export, selected-thread detail panel, legacy aggregate detail columns, and direct latest-call investigator row actions.
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
- Before completion, run repeated functional exploration across every top-level workspace, quick links, filters, buttons, tabs, column menus, exports, desktop/mobile layouts, and console/network error capture.
- Mocked localhost context API integration must prove the React Evidence tab and full-page investigator send `X-Codex-Usage-Token`, include `record_id`, and render only redacted on-demand context.

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
- 2026-07-01 call investigator slice: repeated MCP Playwright exploration across Overview, Investigator, Calls, Thread Efficiency, Usage Drain Lab, Cache And Context Lab, Diagnostics Notebook, Reports, Settings, Calls/Threads column menus, Calls drill-down tabs, full-page call investigator open/next/back/direct URL, mocked context evidence, and mobile Calls/Call Investigator screenshots. Console errors: 0. Failed requests: 0.
- 2026-07-01 call detail hydration slice: MCP Playwright direct `view=call&record=...` with selected row outside boot payload verified one `/api/call` request, `X-Codex-Usage-Token`, `record_id`, hydrated aggregate display, no raw context embedding, console errors 0, failed requests 0.
