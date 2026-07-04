# React Dashboard 0.14.0 Release Roadmap

This roadmap tracks the next minor release target after `0.13.1`: shipping the React dashboard rewrite as the stable transition path while keeping the legacy dashboard available as the rollback surface.

## Release Position

- Target version: `0.14.0`
- Release type: minor feature release, not a patch
- Default posture: React dashboard becomes the preferred dashboard path only after release-candidate hardening passes
- Fallback posture: legacy `/dashboard.html` remains packaged and documented for the transition release
- Privacy posture: aggregate dashboard payloads stay aggregate-only; raw context remains explicit, local, gated, redacted, and on demand

## Phase 1: Feature Freeze

Goal: stop broad feature expansion and finish only parity, stability, and release-readiness work.

- [ ] Freeze new dashboard feature requests unless they fix transition safety or clear legacy parity gaps.
- [x] Keep React and legacy dashboards both runnable from the packaged wheel.
- [x] Confirm no raw prompts, assistant text, tool outputs, patch text, command arguments, or raw JSONL snippets are persisted or bundled in React fixtures, snapshots, docs, or generated assets.
- [ ] Review all untracked frontend files and either stage them intentionally for the release branch or remove generated/local-only files from the candidate.
- [x] Keep `docs/frontend-rewrite-roadmap.md` as the parity log, but use this file as the release gate checklist.

## Phase 2: Parity Closure

Goal: close the remaining user-visible transition gaps that make the React dashboard feel less capable than the legacy dashboard.

- [ ] Calls: verify large-row workflows, finite typed row limit, no-cap request, filters, sorting, column chooser, CSV export, row Open/Copy actions, and side-panel/full-page investigator handoff.
- [ ] Threads: verify related-call row actions, selected-thread URL state, aggregate detail columns, and latest-call investigator links.
- [ ] Call Investigator: verify live `/api/call` hydration, previous/next navigation, source-aware back links, thread context module, raw evidence controls, cached evidence state, and full serialized analysis follow-up.
- [ ] Diagnostics: verify snapshot matrix caching, individual snapshot reloads, structured facts source switching, fact-call pagination cache, fact expansion state, sorting, and investigator row actions.
- [ ] Reports: verify report pack loading, selected report evidence calls, live refresh, and row actions into Call Investigator.
- [ ] Usage Drain and Cache Labs: verify controls, evidence profiles, selected-thread/call actions, and large-history behavior.
- [ ] Settings and shell: verify status chips, live/static mode, pricing and allowance status, auto refresh, search shortcuts, back-to-top, exports, and view-link copying.

Current parity notes:

- 2026-07-03: Copied Call Investigator row links now run centralized inactive-workspace URL cleanup before setting `view=call`, preserving active return context such as `report=...` while dropping stale raw-context params like `mode`, `max_entries`, and `include_tool_output` from non-call workspace links.
- 2026-07-03: Topbar Copy link now shares the same inactive-workspace URL cleanup, keeping active view state such as selected Threads plus history scope and preserving Call Investigator return-workspace context while dropping stale hidden workspace params from copied dashboard links.
- 2026-07-03: Full-page Call Investigator Copy link now uses the same sanitized URL policy as the shell topbar and has a distinct accessible name, preserving raw-context options plus return workspace context while dropping unrelated stale workspace state.
- 2026-07-03: Open investigator row actions now use the same inactive-workspace URL cleanup as copied links, preserving return workspace context like selected Reports while dropping stale raw-context or Diagnostics params before entering full-page Call Investigator.
- 2026-07-03: Diagnostics evidence rows, snapshot rows, and structured fact rows now include Copy link actions next to Open investigator actions, backed by focused Vitest coverage for copied `return=diagnostics` call-investigator URLs.
- 2026-07-03: Threads and Cache Context latest-call rows and selected-call timelines now include Copy link actions next to Open investigator actions, backed by focused Vitest coverage for copied `return=threads` and `return=cache-context` call-investigator URLs.
- 2026-07-03: Overview preset top calls plus Reports, Usage Drain, and Investigator side evidence lists now include Copy link actions next to Open investigator actions, backed by focused Vitest coverage for copied `return=overview`, `return=reports`, `return=usage-drain`, and `return=investigator` call-investigator URLs.
- 2026-07-03: React Copy link actions now share the legacy dashboard textarea fallback when `navigator.clipboard` is unavailable, backed by unit coverage for the helper and integration coverage for copied call-investigator URLs.
- 2026-07-03: Diagnostics-specific CSS was extracted from `dashboard.css` into `styles/diagnostics.css` and converted to scoped CSS custom properties for repeated Diagnostics colors; broader CSS modularization remains open.
- 2026-07-03: Workspace layout, report/finding card, side evidence, and mini-timeline CSS was extracted from `dashboard.css` into `styles/workspaces.css` with native CSS custom properties; Sass remains deferred to avoid adding a build dependency during release hardening.
- 2026-07-03: App shell, sidebar navigation, topbar, row-limit controls, and generic page title/layout controls were extracted from `dashboard.css` into `styles/shell.css` with shared native CSS custom properties; Sass remains deferred unless mixins/nesting produce clearer release code.
- 2026-07-03: Shared theme variables, base reset, topbar/search controls, and row-limit controls were split into `styles/tokens.css`, `styles/base.css`, and `styles/controls.css`, shrinking `styles/shell.css` while keeping Sass deferred during release hardening.
- 2026-07-03: Shared metric, panel/card, toolbar, column-menu, table, chart, badge, filter, and density-toggle styles were extracted from `dashboard.css` into `styles/components.css` using the shared shell CSS variables, leaving `dashboard.css` focused on remaining call/cache/detail feature sections.
- 2026-07-03: Remaining dashboard CSS split into bounded component, chart, table, filter, investigation, context-evidence, detail-context, workspace, diagnostics, and shell modules; `dashboard.css` now holds residual generic/mobile rules, and Sass remains deferred in favor of native CSS variables during release hardening.
- 2026-07-03: Diagnostics snapshot matrix now keeps the last loaded live snapshot cards visible while full-notebook refresh/revalidation is pending, backed by focused Vitest coverage for the pending refresh state.
- 2026-07-03: React Calls now hydrates legacy `?view=calls&detail=first` URLs by selecting the first sorted row, promoting it into stable `record=...` URL state, and clearing the stale `detail` flag.
- 2026-07-03: React Threads now hydrates legacy `?view=threads&detail=first` URLs by selecting the first visible thread, promoting it into stable `thread=...` URL state, and clearing the stale `detail` flag.
- 2026-07-03: React Threads now maps legacy `expand=first`, `expand=all`, and `threads=...` expanded-row URL state into the selected-thread detail panel, promoting the selected thread into stable `thread=...` and clearing stale expansion params.
- 2026-07-03: Threads legacy URL parsing, `detail`/`expand`/`threads` normalization, selected-thread link building, table filtering/sorting, and child-call paging state moved into tested `features/threads/threadsUrlState.ts`, preserving explicit `direction=asc` sort URLs while reducing `ThreadsPage.tsx`.
- 2026-07-03: React Calls now hydrates legacy `pricing=...` URLs as the confidence filter, normalizing them into stable `confidence=...` state and clearing the stale `pricing` alias.
- 2026-07-03: Calls URL/link tests were split so `App.calls-url.test.tsx` keeps sort/filter/preset URL coverage while `App.calls-links.test.tsx` owns call-investigator copy/open link coverage, keeping both files below the 600-line maintenance threshold.
- 2026-07-03: Calls legacy URL parsing and link normalization moved into tested `features/calls/callsUrlState.ts`, covering `pricing`/`time` aliases, `detail=first`, safe dates, sort/density/page fallback, and stale param cleanup.
- 2026-07-03: Calls table filtering, date-range matching, attention scoring, deterministic sorting, and thread timeline time ordering moved into tested `features/calls/callsFilterSort.ts`, preserving legacy custom date labels while reducing `CallsPage.tsx` component size.
- 2026-07-03: React shell now maps legacy `view=insights` and `return=insights` URLs to the renamed Overview route, normalizing the query string while preserving Call Investigator back navigation.
- 2026-07-03: React shell now maps numeric shortcut `1` to Overview, preserving the old dashboard's `1 -> Insights` behavior through the new Insights-to-Overview route mapping.

- 2026-07-03: React non-Calls workspaces now honor legacy shell URL filters `model`, `effort`, `confidence`/`pricing`, and `date`/`from`/`to` by deriving scoped dashboard models and keeping topbar exports aligned with copied legacy links.
- 2026-07-03: React shell URL compatibility helpers moved out of `App.tsx` into tested `app/shellUrl.ts`, covering legacy Insights aliases, safe call return views, history-scope URL preservation, and shell label lookup.
- 2026-07-03: React row-limit helpers moved out of `App.tsx` into tested `app/rowLimit.ts`, covering no-cap payloads, typed finite counts, slider expansion, Load more increments, and loaded/available status labels for large histories.
- 2026-07-03: React active/all-history scope derivation and archived-call status labels moved out of `App.tsx` into tested `app/historyScope.ts`, preserving legacy hidden/included archived-call messaging.
- 2026-07-03: React current-view topbar CSV routing and Runtime State export rows moved out of `App.tsx` into tested `app/currentViewExport.ts`, preserving view-scoped exports while shrinking the shell.
- 2026-07-03: React call CSV exports now use legacy-compatible aggregate field names such as `record_id`, `timestamp`, `estimated_cost_usd`, `usage_credits`, `cache_ratio`, and `context_window_percent`, backed by shell export coverage while retaining expanded React-only source/thread/context fields.
- 2026-07-03: React call CSV exports now preserve legacy timing columns `call_started_at` and `previous_call_event_timestamp`, backed by focused CSV coverage.
- 2026-07-03: React call CSV exports now keep the legacy timing/filtering column sequence as the CSV prefix, then append React-only enrichment columns for source/thread/context metadata.
- 2026-07-03: React call row mapping now keeps legacy `event_timestamp` distinct from `call_started_at`; visible/exported `timestamp` uses the event timestamp while `call_started_at` remains the call-start value.
- 2026-07-03: React shell date filters now restore the legacy live date-range status, including active custom ranges, preset start/end dates, and explicit invalid-range feedback instead of silently showing empty filtered tables.
- 2026-07-03: React legacy shell filters now accept `time=` as a date-preset alias while preserving `date=` precedence, keeping copied filter links from silently dropping date scope.
- 2026-07-03: React shell Confidence controls now clear stale legacy `pricing=` aliases when rewritten to `confidence=...` or All confidence, preventing invisible copied-link filters from lingering.
- 2026-07-03: React shell navigation now clears stale `finding=` state when leaving Investigator, preventing copied links from carrying irrelevant investigator context into other workspaces while preserving Investigator return links through Call Investigator.
- 2026-07-03: React shell navigation now clears stale Threads-only URL state (`thread`, `expand`, `threads`, `thread_q`, `risk`, and child-call paging/sort params) when leaving Threads, preventing copied links from leaking thread context into unrelated workspaces.
- 2026-07-03: React shell navigation now clears stale Cache And Context URL state (`cache_thread`) when leaving Cache And Context, preventing copied links from carrying unrelated selected-cache-thread context into other workspaces.
- 2026-07-03: React shell navigation now clears stale Reports URL state (`report`) when leaving Reports, preventing copied links from carrying unrelated report-library selection into other workspaces.
- 2026-07-03: React shell navigation now clears stale Usage Drain URL state (`usage_plan`, `usage_effort`, `usage_subagents`, `usage_sample`, `usage_confidence`) when leaving Usage Drain, preventing copied links from carrying unrelated drain-lab controls into other workspaces.
- 2026-07-03: React shell navigation now clears stale Diagnostics URL state (`diagnostic_source`, `diagnostic_fact`) when leaving Diagnostics, preventing copied links from carrying unrelated notebook fact selection into other workspaces.
- 2026-07-03: React shell navigation now clears stale Calls table URL state (`detail`, `call_q`, `source`, `sort`, `direction`, `density`, `page`, plus selected `record` via existing call cleanup) when leaving Calls, while preserving shared shell filters such as model, effort, confidence, and date scope.
- 2026-07-03: React shell inactive-workspace URL cleanup moved into tested `app/shellUrl.ts`, centralizing stale state ownership for Calls, Threads, Diagnostics, Reports, Usage Drain, Cache And Context, Investigator, and Call Investigator while preserving shared shell filters.
- 2026-07-03: React full-page Call Investigator now hydrates legacy raw-context option URL params (`mode`, `max_entries`, `max_chars`, `include_tool_output`, `include_compaction_history`) into evidence controls, preserving copied investigator links that request full/no-limit/tool-output context views without persisting raw context.
- 2026-07-03: React shell now treats Call Investigator raw-context option URL params as Call-owned state, preserving them on `view=call` but clearing them after leaving Call Investigator so copied non-call workspace links do not carry hidden raw-context controls.
- 2026-07-03: React Call Investigator evidence option controls now serialize non-default raw-context options back into the current `view=call` URL, so copied call links preserve changed full/no-limit/tool-output evidence settings.
- 2026-07-03: React direct navigation helpers for Investigator findings and preset actions now route through centralized inactive-view URL cleanup, so stale Call Investigator/context params do not leak when entering Investigator outside sidebar navigation.
- 2026-07-03: Overview direct finding Review actions now have regression coverage proving stale Call Investigator/context/report params are cleared while entering Investigator with the selected `finding` state.
- 2026-07-03: React Threads shell and page CSV exports now emit filtered thread call rows as `codex-thread-filtered-calls-*.csv`, matching legacy export behavior instead of exporting only grouped thread summary rows; the local Threads toolbar now labels this action `Export calls`.
- 2026-07-03: Call Investigator selected-record resolution, live `/api/call` hydration precedence, previous/next navigation rows, thread timeline rows, position labels, and current-view export row selection moved into tested `features/call-investigator/callInvestigatorState.ts`, so shell exports no longer import the full page component.
- 2026-07-03: Call Investigator exact accounting, previous-call deltas, evidence-state summaries, serialized-evidence bounds, next diagnostic move text, and hydrated-position detail moved into tested `features/call-investigator/callInvestigatorReadout.ts`, pinning legacy investigation language outside the page component.
- 2026-07-03: Side-panel Calls evidence and full-page Call Investigator evidence now share tested `features/shared/contextEvidenceState.ts` for runtime gate messages, default context options, error formatting, load-older depth, and local evidence notes, keeping raw-context investigation behavior aligned across surfaces.
- 2026-07-03: Calls drill-down and full-page Call Investigator now share tested `features/shared/callPresentation.ts` for cache-state labels, source-line formatting, context-window labels, and thread/model/effort count summaries, keeping aggregate call readouts aligned across surfaces.
- 2026-07-03: Release checker now scans React dashboard source, fixtures, docs, and bundled React assets for raw-context persistence flags, local Codex session JSONL paths, patch transcript markers, and raw assistant/user message JSONL shapes; `tests/cli/test_cli_release.py` covers the privacy scan.

## Phase 3: Stability Gates

Goal: prove the release candidate works from source checkout and installed package shapes.

- [x] `npm --workspace frontend/dashboard run typecheck`
- [x] `npm --workspace frontend/dashboard run test -- --reporter=json`
- [x] `npm run dashboard:build`
- [x] `npm run dashboard:smoke`
- [x] `.venv/bin/python scripts/check_release.py`
- [x] `git diff --check`
- [x] `.venv/bin/python -m pytest`
- [x] `.venv/bin/python -m compileall src`
- [x] `.venv/bin/python -m build`
- [x] `.venv/bin/python -m twine check dist/*`
- [x] `.venv/bin/python scripts/check_release.py --dist`
- [x] Installed-wheel smoke: create a clean temp environment, install the built wheel, launch `codex-usage-tracker serve-dashboard --context-api explicit`, and verify React and legacy dashboard assets load.

Current execution notes:

- 2026-07-03: full frontend validation passed after Call Investigator URL/share cleanup and bundled asset rebuild: 40 Vitest files / 234 tests, `npm --workspace frontend/dashboard run typecheck`, `npm --workspace frontend/dashboard run lint`, `.venv/bin/python scripts/check_release.py`, and `git diff --check`.
- 2026-07-03: repeated untracked inventory with `git status --porcelain=v1 -uall`; expanded output remains source/test/doc-only with 97 files and no generated/cache/private-data-looking files.
- 2026-07-03: source-checkout frontend gates passed: typecheck, full Vitest JSON suite, production dashboard build, Playwright dashboard smoke, release check, and `git diff --check`.
- 2026-07-03: Python source gates passed: `.venv/bin/python -m pytest` and `.venv/bin/python -m compileall src`.
- 2026-07-03: temporary package shape check passed with `.venv/bin/python -m build --outdir /tmp/codex-usage-tracker-0.14-build` and `.venv/bin/python -m twine check /tmp/codex-usage-tracker-0.14-build/*`.
- 2026-07-03: installed-wheel smoke found `/react-dashboard.html` missing from packaged server routes; fixed alias routing to bundled React `index.html`, rebuilt into a temp wheel, installed in a clean temp venv, and verified `/react-dashboard.html`, `/dashboard.html`, React JS, and React CSS all return 200 from the installed CLI server.
- 2026-07-03: rebuilt packaged React assets from current `frontend/dashboard` source after Call Investigator link cleanup, verified bundled JS contains the new `Copy investigator link` path, and reran `scripts/check_release.py` plus focused shell/workspace URL tests.
- 2026-07-03: follow-up React parity fix committed in `d05575e`: Overview Usage Remaining prefers weekly observed/configured windows over 5-hour windows, shell row loading exposes explicit loading state plus Load all rows, Overview Recent Calls exposes local show-more plus live Load more rows/Load all rows controls, and shared data tables freeze header rows plus the Thread column.
- 2026-07-03: post-commit stability gates passed: full frontend suite 40 files / 234 tests, `npm --workspace frontend/dashboard run typecheck`, `npm --workspace frontend/dashboard run lint`, `npm --workspace frontend/dashboard run build`, `.venv/bin/python -m pytest` 544 tests, `.venv/bin/python -m compileall src`, dashboard JS `node --check`, `.venv/bin/python scripts/check_release.py`, and `git diff --check && git diff --cached --check`.
- 2026-07-03: clean package-shape gates passed from detached temp worktree at commit `d05575e`: `.venv/bin/python -m build --outdir <temp-worktree>/dist <temp-worktree>`, `.venv/bin/python -m twine check <temp-worktree>/dist/*`, and `.venv/bin/python scripts/check_release.py --dist`. Repository `dist/` still contains old ignored `0.13.1` artifacts and was intentionally not overwritten during this branch pass.
- Merge-readiness snapshot: implementation source/installed smoke/dist gates are close, but do not merge blind while one untracked frontend orphan still needs an explicit keep/remove decision, plus release-branch version bump and final known-limitations review.
- 2026-07-03: refreshed untracked-file inventory after commit shows exactly one untracked file: `frontend/dashboard/src/features/overview/InvestigationPresetsPanel.tsx`. The file defines the removed Overview "Investigation Presets" panel, is not imported by tracked React code, and conflicts with the product direction to remove presets from the home page; it should be removed with maintainer approval or intentionally restored before release.

## Phase 4: Real-Data QA

Goal: validate the transition on real local aggregate data without exposing private context.

- [x] Launch live dashboard against cached real local data from the updated source checkout.
- [x] Verify React dashboard opens by preferred route and legacy dashboard still opens by `/dashboard.html`.
- [x] Exercise desktop and mobile widths for Overview, Calls, Threads, Diagnostics, Reports, Usage Drain, Cache Lab, Settings, and Call Investigator.
- [x] Exercise large row counts: initial limited load, Load more, typed limit, and no-cap request.
- [x] Confirm Diagnostics Notebook does not re-run expensive loads after navigating away and back.
- [x] Confirm Call Investigator row links preserve return paths and copy stable URLs.
- [x] Confirm raw context requests require explicit enablement and send the local API token only to localhost endpoints.
- [x] Capture desktop browser console/network failures for Overview, Calls, Threads, Diagnostics, Reports, Usage Drain, Cache Lab, and Settings; current source-server route sweep has zero console errors and zero failed/4xx/5xx dashboard requests.

Current real-data QA notes:

- 2026-07-03: current branch source server on `127.0.0.1:8776` served rebuilt React JS/CSS byte-for-byte while older `8765` process served stale assets; real-data Playwright sweep covered 20 desktop/mobile route checks including direct Call Investigator with zero console errors, page errors, failed local requests, or 4xx/5xx dashboard responses.
- 2026-07-03: fixed React live shell boot so `/react-dashboard.html` receives the aggregate-only `usage-data` API token payload with zero embedded rows and the finite server default limit instead of `limit_label: All`; this prevents accidental no-cap startup loads on massive histories.
- 2026-07-03: real-data large-row QA on current source server covered finite startup load `limit=5000`, typed load `limit=1200`, Load more `limit=2200`, and explicit No row cap `limit=0` on a 75k-row aggregate dataset; UI showed clear no-cap state and zero console errors, page errors, failed local requests, or bad dashboard responses.
- 2026-07-03: Diagnostics Notebook SPA leave/return check produced zero diagnostic API requests on return after cached load, confirming route navigation does not replay expensive notebook loads in the current branch server.
- 2026-07-03: real-data Calls table workflow verified row click opens full Call Investigator with `return=calls`, Back returns to Calls, and Copy link emits a same-origin stable `view=call&record=...&return=calls` URL; zero console errors, page errors, or bad dashboard responses.
- 2026-07-03: raw-context gate QA on a fresh `--no-context-api` server verified `/api/context-settings?enabled=1` rejects missing local API token, `/api/context` rejects while disabled, tokenized settings enable flips `context_api_enabled`, and a minimal explicit context request reports `loaded_on_demand: true` with `raw_context_persisted: false`; no context text was printed.
- 2026-07-03: `frontend/dashboard/src/api/context.test.ts` now pins the React client boundary: static file mode, missing token, and disabled context API do not call `fetch`; enabled settings/context requests use same-origin `/api/...` paths and attach `X-Codex-Usage-Token`.
- 2026-07-03: restarted `127.0.0.1:8765` from updated source checkout with `--no-refresh` to avoid an expensive rescan while preserving real cached aggregate data.
- 2026-07-03: bounded Playwright route sweep first exposed stale-server `/api/reports/pack` 404s, then passed after restart: eight React routes returned 200, mounted `#root`, and produced zero console errors or bad responses.
- 2026-07-03: Chrome smoke against refreshed `127.0.0.1:8765` verified Usage Drain, Reports, and Investigator headings plus new side-evidence Copy link buttons; zero console errors and zero failed/4xx/5xx dashboard requests.
- 2026-07-03: source server returned 200 for `/react-dashboard.html?view=reports`, `/dashboard.html`, and `/api/reports/pack?limit=25&evidence_limit=2`.

## Phase 5: Release Prep

Goal: prepare the minor release without changing production publishing state from the working branch.

- [x] Update `CHANGELOG.md` under Unreleased with React dashboard transition notes, fallback route, privacy notes, and known limitations.
- [x] Update README/development docs with the preferred dashboard launch command and fallback guidance.
- [x] Decide whether `serve-dashboard` should open React by default in `0.14.0`; if yes, document the legacy fallback explicitly before changing defaults.
- [ ] Bump version only on a release branch after stability and real-data QA pass.
- [ ] Do not tag, push release tags, or publish PyPI/TestPyPI without explicit maintainer approval.

Current release-prep notes:

- 2026-07-03: `serve-dashboard --open` now prints and opens `/react-dashboard.html` as the preferred route while keeping legacy `/dashboard.html` available and documented; `serve-dashboard --json` exposes both `dashboard_url` and `legacy_dashboard_url`.
- 2026-07-03: token-protected `/api/open-investigator` now accepts legacy `/dashboard.html?view=call&record=...` inputs but opens `/react-dashboard.html?view=call&record=...`, preserving fragments and return-view query state.

## Go / No-Go Criteria

Ship `0.14.0` only when all of these are true:

- [ ] React dashboard handles the normal live-dashboard workflow without relying on the legacy dashboard.
- [ ] Legacy dashboard remains available as a documented rollback path.
- [ ] Source checkout and installed-wheel dashboard launches both pass smoke checks.
- [ ] Full frontend, backend, release, build, and dist checks pass from a clean release branch.
- [ ] Real-data QA finds no privacy leaks, raw-context persistence, broken row actions, or recurring expensive reload loops.
- [ ] Remaining gaps are documented as known limitations and do not block stable transition use.
