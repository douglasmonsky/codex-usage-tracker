# Changelog

## Unreleased

- Ingest aggregate `response.completed` telemetry from local
  `codex-completions*.jsonl` exporter files and conservatively reconcile exact
  Fast/Standard service-tier evidence to canonical calls without retaining raw
  response bodies or arbitrary OTLP attributes.
- Show exact service tier separately from the existing Fast proxy in Calls,
  details, and CSV exports; older or unmatched history remains Unknown.
- Apply documented model-family Fast multipliers to confirmed Codex credit
  estimates with explicit provenance while leaving USD token-cost estimates and
  standard-credit allowance calibration unchanged.

## 0.20.0 - 2026-07-16

- Reinvent the Threads tab around inline row expansion, progressively loading and virtualizing every call in the selected thread while preserving explicit investigator actions, deep links, responsive layouts, retry recovery, and aggregate-first privacy boundaries.
- Complete the Simplified Chinese dashboard experience across React views, visualization metadata, tables, accessibility text, CLI help, and dashboard lifecycle messages while preserving user-provided data verbatim.
- Improve the Overview token-flow chart at constrained desktop widths with a taller single-column layout, larger Sankey node gaps, and label-safe padding; keep virtualized evidence-table actions on one row.
- Apply official long-context input, cached-input, and output price multipliers to concrete calls above 272K input tokens when the selected OpenAI service tier publishes long-context rates, while keeping aggregate summaries from being incorrectly thresholded.

## 0.19.0 - 2026-07-15

- Redesign Limits Intelligence around weekly credits-per-percentage capacity
  history, a compact current-status row, automatic revision analysis, and zero,
  one, or multiple family-wise-controlled capacity changes. Rejected split
  statistics stay hidden, five-hour usage remains observed context, and the v2
  API/MCP contracts expose capacity points, regimes, provenance, and copied-row
  diagnostics by default.

## 0.18.0 - 2026-07-15

- Exclude exact historical calls copied by cloned Codex tasks from default dashboard, CLI, MCP, report, allowance, compression, recommendation, and export totals while retaining every physical source row for local provenance.
- Add aggregate deduplication diagnostics across the CLI, MCP server, localhost API, and dashboard status strip, including physical, canonical, and excluded row/token counts with bounded provenance metadata.
- Preserve new post-clone calls as normal usage, promote a surviving copy when an original source disappears, and migrate existing local indexes without losing usage history.
- Restore large-history dashboard performance with canonical query indexes and explicit SQLite join/scan plans; the 100,000-row route budget now passes for summaries, recommendations, diagnostics, threads, and thread-call paging.

## 0.17.2 - 2026-07-09

- Add GPT-5.6 Sol, Terra, and Luna API pricing and Codex credit-rate support, including the official `gpt-5.6` alias and compatibility with OpenAI's new cache-write pricing column.

## 0.17.1 - 2026-07-09

- Stabilize async dogfood cache fingerprints so repeated unchanged MCP dogfood runs can reuse cached reports even when SQLite file metadata changes during read/report activity.

## 0.17.0 - 2026-07-08

- Add agentic MCP investigation tools for hypothesis-driven usage diagnostics, compact evidence briefs, and actionable recommendation reports.
- Add repeated file rediscovery, shell churn, and large low-output usage diagnostics to identify avoidable local workflow waste.
- Improve bundled skill guidance so Codex can route vague usage questions into concrete tracker endpoints, Headroom suggestions, and custom remediation ideas.
- Add async dogfood progress polling and warm result caching so longer usage investigations can report progress and rerun faster.
- Speed up content indexing with incremental append metadata, parallel source parsing, and batched FTS rebuilds.
- Add dashboard refresh progress bars, no-cap paged loading, loaded-call metrics, token breakdowns, persisted loading preferences, and restored usage-drain chart data.

## 0.16.2 - 2026-07-08

- Restore Usage Drain, Investigator Workbench, Reports, and related dashboard charts by deriving shared usage-drain series from loaded aggregate rows again.
- Keep sparse line charts expanded to their panel width so low-point datasets do not collapse into the left edge.

## 0.16.1 - 2026-07-08

- Add async refresh progress polling and dashboard progress bars for long all-row loads.
- Speed up local content index refreshes with batched writes and parallel source extraction.
- Load uncapped dashboard rows in finite pages so no-cap mode stays responsive on large histories.
- Show loaded-call counts and call-level token breakdowns on Overview metric cards.
- Restore session row/history loading preferences after browser refresh without storing large row payloads.

## 0.16.0 - 2026-07-07

- Add allowance intelligence foundation with normalized allowance history, evidence-graded change diagnostics, local evidence exports, and API/MCP report surfaces for weekly-vs-5-hour usage analysis.
- Add local content-indexed MCP/API exploration surfaces, including content search, thread trace, pattern scans, investigation walks, and strict local evidence exports.
- Add roadmap for default local content indexing, SQLite FTS5 search, parser drift handling, and future diagnostics for repeated file rediscovery, shell churn, and large low-output calls.
- Fix schema initialization so already-applied migrations are not rerun during read/report calls on migrated local databases.

## 0.15.1 - 2026-07-05

- Fix the PyPI wheel package resources by tracking the React dashboard `index.html` entrypoint used by `serve-dashboard` and installed-package smoke tests.

## 0.15.0 - 2026-07-05

- Make the companion plugin/skills remediation-aware for token-waste investigations, including Headroom suggestions when available, dashboard verification paths, and custom local automation ideas.
- Fix React dashboard package verification for public release readiness, including bundled React dashboard resources in local wheel smoke coverage and refreshed synthetic Calls/Details README screenshots.
- Harden React dashboard context evidence and diagnostics smoke tests against current row-selection and duplicate-heading behavior.
- Recenter the README around talking with the plugin/skill about local aggregate usage, with example conversation docs for token-waste and remediation workflows.

## 0.14.1 - 2026-07-04

- Harden React dashboard responsive chrome, including topbar control wrapping, table containment, sticky table affordances, mobile nav polish, and refreshed synthetic dashboard screenshots.

## 0.14.0 - 2026-07-04

- Make `serve-dashboard --open` prefer the React dashboard route while keeping legacy `/dashboard.html` available as a localhost fallback, and expose both URLs in `serve-dashboard --json`.
- Restore major legacy dashboard parity in the React dashboard, including overview recent-call loading controls, sticky thread/header table affordances, row-to-investigator actions, diagnostics fact-call pagination, report and call sorting state, and legacy URL/filter normalization.
- Add local-only transition safeguards: the prominent unofficial-project banner, aggregate-only privacy boundaries, rebuilt dashboard assets, and release-gate documentation for the React bundle.
- Prioritize weekly usage windows in Overview and Settings so weekly remaining usage is surfaced ahead of short 5-hour windows.
- Expose dashboard-shaped MCP payloads for status, calls, call details, threads, report packs, and dashboard recommendations, and teach bundled skills concrete token-waste investigation prompts.

## 0.13.1 - 2026-06-30

- Add guided usage-summary diagnostics across CLI, API, and dashboard to explain the largest aggregate drivers behind usage.

## 0.13.0 - 2026-06-30

- Add first-run onboarding docs covering install, setup, live-dashboard launch, empty-dashboard troubleshooting, plugin discovery, and safe issue diagnostics.
- Improve `doctor --json` first-run environment reporting so support requests can distinguish missing logs, empty history, and plugin/runtime path issues faster.
- Add safe support-bundle issue-report fields and issue-template guidance so users can attach diagnostics without leaking prompts, tool outputs, commands, patches, or raw paths in strict mode.
- Strengthen installed-wheel lifecycle smoke coverage across setup, doctor, dashboard generation, strict support bundles, and plugin resources.
- Harden strict support-bundle redaction for nested diagnostic paths, Python executable paths, and resolved `/private/var`-style platform path aliases.

## 0.12.1 - 2026-06-29

- Ship the package-domain boundary refactor behind compatibility facades so existing CLI, imports, dashboard routes, JSON payloads, and MCP entrypoints keep working while the source tree is organized by responsibility.
- Add Tach domain configuration files, refreshed Agent Maintainer baselines, and package-boundary documentation for the new module layout.
- Restore `python -m codex_usage_tracker.cli` after the CLI package split and add regression coverage for both module entrypoints.
- Split allowance pricing helpers into smaller modules while preserving the public allowance facade.

## 0.12.0 - 2026-06-29

- Refactor CLI, dashboard server routing, SQLite store/query boundaries, context parsing, diagnostics, and usage-drain modeling into smaller modules with compatibility facades.
- Add local Agent Maintainer ratchet configuration, strict local `tach check`, maintainability boundary docs, and a maintainability scorecard for future cleanup work.
- Harden Diagnostics dashboard behavior for projected weekly credits charts, command expansion, live row status, and desktop/mobile smoke coverage.
- Clean up warning-sensitive tests so the full suite runs without SQLite/resource-handle `ResourceWarning` noise.
- Validate the refactor against a frozen local JSONL rebuild comparison before release.

## 0.11.4 - 2026-06-27

- Fix `codex-usage-tracker setup` on large local histories by batching stale diagnostic-fact deletes so SQLite does not exceed bound-variable limits during usage index refresh.
- Add synthetic regression coverage for large diagnostic fact refreshes under a low SQLite variable ceiling. Thanks to `@gevikhn` for the Windows setup failure report.

## 0.11.3 - 2026-06-23

- Fix Windows `serve-dashboard` asset loading by forcing JavaScript, CSS, JSON, and SVG MIME types in the localhost server instead of trusting OS registry MIME mappings.

## 0.11.2 - 2026-06-23

- Fix served dashboard shell hydration so `serve-dashboard --no-refresh` reliably populates the calls table from `/api/usage` when the initial HTML contains zero rows but indexed rows are available.
- Harden the synthetic source-log benchmark smoke test so shared-runner timing noise does not leave a stale red release check.
- Improve benchmark smoke test failures so future threshold failures report the parsed JSON payload and threshold details instead of only a generic subprocess error.

## 0.11.1 - 2026-06-23

- Move projected weekly credits to the top of the Diagnostics tab and add the 95% CI range to the projection table.
- Add per-section `Reload` controls for stale or missing diagnostic snapshot cards so one failed or missing section can be recomputed without a full diagnostics refresh.

## 0.11.0 - 2026-06-22

- Add usage-drain diagnostic reports for token accounting, allowance breakpoints, predictive model highlights, weekly visible usage, weekly projected credits, and cumulative thread cost curves.
- Add dashboard Diagnostics charts for weekly usage remaining and projected weekly credits, including per-plan trend lines, confidence bars, compact date labels, and large-history horizontal scaling.
- Add CLI/API support for usage-drain diagnostics with stable JSON contracts and synthetic report-generation tests.
- Add usage-drain modeling documentation and a synthetic README screenshot focused on the new diagnostics charts.
- Harden diagnostic table alignment, parser-warning visibility, file-modification rendering, and Python 3.14 type-check coverage.

## 0.10.1 - 2026-06-21

- Add lightweight action timing metadata to context evidence so call investigations can show elapsed time for parsed tool and command actions without persisting raw command text or outputs.
- Add synthetic README diagnostics coverage for the Git Interactions panel and package the screenshot with installed plugin docs.

## 0.10.0 - 2026-06-21

- Add Git/GitHub CLI diagnostic snapshots with safe operation labels, coarse categories, mutability buckets, and terminal token-count coverage.
- Add file-modification diagnostic snapshots for structured patch events, modified-path aggregates, extension counts, and largest modification events without storing patch text or raw paths.
- Add derived call timing fields for call start, duration, previous-call timestamp, and previous-call gap across dashboard rows, details, CSV/export actions, live API sorting, and thread aggregates.
- Surface `Duration`, `Prev gap`, `Longest duration`, and `Longest gap` in the dashboard with localized labels and focused regression coverage.
- Reconcile all diagnostics panels into one release so `overview`, `tool-output`, `commands`, `git-interactions`, `file-reads`, `file-modifications`, `read-productivity`, and `concentration` can refresh together from the live dashboard.

## 0.9.0 - 2026-06-21

- Add persisted aggregate diagnostic snapshots with explicit on-demand refresh metadata and schema-versioned CLI/API contracts.
- Add dashboard Diagnostics panels for overview, tool output, commands, file reads, read productivity, and concentration.
- Add tool-output and command reports with terminal token-count buckets, missing-count coverage, command roots, and expandable command children.
- Add file-read and read-productivity reports with token allocation, largest read commands, read-to-modify correlation, and privacy-safe path labels.
- Add concentration reports for top source/session, project/cwd, and day shares without leaking raw source-log paths.
- Keep Diagnostics refresh isolated from normal live dashboard refresh so regular usage updates do not recompute or blink diagnostic panels.
- Add Playwright diagnostics smoke coverage and release documentation for the snapshot pipeline, privacy boundary, and on-demand refresh behavior.

## 0.8.1 - 2026-06-20

- Make Diagnostics fact tables easier to scan by widening and pinning the Fact column while horizontally scrolling.
- Add API-backed sortable headers to top-level Diagnostics fact tables, including cached input, output, cache ratio, largest call, latest call time, occurrence, call-count, and fact-name sorts.

## 0.8.0 - 2026-06-20

- Add an aggregate Diagnostics dashboard for inspecting diagnostic facts, associated calls, token totals, and on-demand evidence without persisting raw transcript text.
- Add diagnostic fact extraction, reporting APIs, dashboard drilldowns, sortable associated-call tables, and load-more controls for larger diagnostic result sets.
- Add source byte offsets and context seek diagnostics so on-demand evidence loading can seek when offsets are valid and fall back safely when they are missing or stale.
- Harden dashboard startup so visiting Diagnostics before other views load no longer prevents Calls, Threads, or Overview from hydrating.
- Make Live refresh use the cached/indexed append path and fetch only newly visible leading rows instead of running the full manual refresh reset cycle.

## 0.7.0 - 2026-06-18

- Parse latest observed Codex usage snapshots from local rate-limit and token-count log events without persisting raw transcript text.
- Store observed 5h and weekly usage snapshot fields in aggregate rows and expose a latest-observed usage summary for dashboard and API consumers.
- Add a dashboard card for latest observed 5h and weekly usage with wording that distinguishes local observations from authoritative account limits.
- Default the dashboard table experience to time-sorted Calls, replace the visible Signals column with Reasoning Output, and keep the Signals field out of the table for now.
- Ignore known non-token parser events so refreshes stay focused on usage-bearing records.

## 0.6.1 - 2026-06-13

- Polish the README landing screenshots with matched dashboard/investigator previews and an additional lower investigator evidence view.
- Restore the companion plugin prompt preview near the companion skill section and package companion screenshots with installed docs assets.
- Keep dashboard toolbar links styled like buttons in the call investigator.

## 0.6.0 - 2026-06-13

- Remove low-value call/thread anchor diagnostics from the experimental call investigator to avoid an extra source-log scan per context load.
- Persist call-origin metadata as categorical aggregate fields during indexing so normal dashboard payloads do not reopen source JSONL logs to infer user-vs-Codex initiation.
- Persist archived-session scope, conservative thread keys, and per-thread previous/next call links as aggregate helper fields for faster dashboard filtering and investigator navigation.
- Add opt-in localhost API timing diagnostics for `/api/usage` and `/api/context` without exposing raw transcript content.
- Reduce explicit context loading to a quick default mode that omits tool output and serialized buckets, with full serialized JSONL bucket analysis still available on demand.
- Add source-log-aware synthetic benchmark coverage that verifies normal dashboard payload assembly does not open generated source JSONL files.
- Add SQL-backed live dashboard API slices for status, calls, one call, threads, thread calls, summary, and recommendations while preserving the compatibility `/api/usage` endpoint.
- Materialize active and all-history thread summaries in SQLite so live thread APIs can read pre-aggregated totals.
- Add source-file refresh cursors so live refresh skips unchanged logs, seeks to appended JSONL bytes when safe, and safely replaces aggregate rows for changed or truncated source logs.
- Hydrate direct call-investigator links from the aggregate `/api/call` endpoint when the selected record is outside the currently loaded table slice or filter state.
- Replace placeholder non-English dashboard locale catalogs with translated UI catalogs and add regression coverage for core visible labels.

## 0.5.0 - 2026-06-10

- Add the dashboard localization foundation, including initial locale catalogs, language metadata, local browser language selection, `--lang`, and `CODEX_USAGE_TRACKER_LANG`.
- Add Vietnamese dashboard localization and focused validation coverage for translated dashboard labels.
- Keep the README landing page focused on dashboard screenshots and companion usage workflows before detailed localization guidance.
- Stabilize the CI synthetic benchmark smoke so coverage instrumentation does not create false release failures.
- Pin the marketplace MCP runtime launcher to the exact `codex-usage-tracking==0.5.0` package.

## 0.4.1 - 2026-06-09

- Harden the production PyPI workflow so manual publishing must run from `main` or a tag ref before artifacts are downloaded and uploaded.
- Skip TestPyPI/PyPI uploads when the exact distribution version already exists on the target index, allowing a GitHub Release to be reconciled after a workflow-dispatch publish.
- Strengthen `scripts/check_release.py` so it validates the publish-ref preflight inside both the TestPyPI and PyPI jobs.
- Check off completed 1.0 readiness items with evidence for migration coverage, localhost dashboard smoke testing, and the protected GitHub `pypi` environment.
- Pin the marketplace MCP runtime launcher to the exact `codex-usage-tracking==0.4.1` package.

## 0.4.0 - 2026-06-09

- Add official Python 3.14 support across CI, package classifiers, README/install docs, and installed-package Docker smoke coverage.
- Add a release recovery runbook for failed publish workflows, stale PyPI/TestPyPI pages, Trusted Publishing issues, bad artifacts, and patch-forward recovery.
- Add synthetic large-history benchmark thresholds for active/all-history dashboard queries, date filtering, model/effort filtering, recommendations, pricing coverage, and project summaries.
- Add stricter privacy regression coverage for generated dashboards, CSV exports, API payloads, and support bundles.
- Redact sensitive strings and local diagnostic paths in support bundles, including nested doctor output in redacted and strict privacy modes.
- Add aggregate schema migration, JSON contract parity, installed-package smoke, and protected-main workflow readiness coverage.
- Pin the marketplace MCP runtime launcher to the exact `codex-usage-tracking==0.4.0` package.

## 0.3.2 - 2026-06-08

- Make `open-dashboard` and `serve-dashboard` refresh active-session logs by default, with `--no-refresh` as the explicit cached-index mode.
- Add a token-protected dashboard action for enabling context loading without restarting a localhost server that started with context loading off.

## 0.3.1 - 2026-06-08

- Fix packaged Codex Usage Tracker skills so dashboard-open requests start the live localhost dashboard instead of a static snapshot.
- Mirror live-dashboard skill guidance between source-tree skills and packaged plugin-data copies so release and wheel checks stay green.
- Use the valid explicit context API flag form, `serve-dashboard --refresh --context-api explicit --open`, for live dashboard launches.

## 0.3.0 - 2026-06-08

0.3.0 is a stabilization and public-preview release for the dashboard, CLI, MCP tools, local privacy model, packaged Codex plugin, and companion usage skills. The PyPI/TestPyPI distribution name is now `codex-usage-tracking`; the GitHub repository remains `douglasmonsky/codex-usage-tracker`, the Python import package remains `codex_usage_tracker`, and the installed CLI command remains `codex-usage-tracker`.

- Add tested JSON contract validation for stable CLI and MCP payload schemas.
- Add schema markers to doctor, pricing coverage, MCP dashboard/export/config, and opt-in context payloads.
- Add ranked CLI/MCP recommendations with severity score, primary recommendation, secondary signals, and thread rollups.
- Add offset-aware localhost dashboard usage API responses for paged aggregate-row automation.
- Add a synthetic large-history benchmark script for 10k, 100k, and 500k aggregate-row SQLite fixtures.
- Add focused mypy coverage for core JSON contract, recommendation, report, schema, model, and store modules.
- Add Ruff, coverage, and dashboard JavaScript syntax checks to CI.
- Split dashboard JavaScript helpers into formatting, data, state, and rendering/runtime assets.
- Add issue templates for bugs, parser compatibility, pricing/allowance issues, and feature requests.
- Expand security guidance for project metadata privacy, support bundles, and localhost dashboard tokens.

## 0.2.0

- Add project metadata privacy modes for dashboard, query, session, summary, CSV export, MCP, and support-bundle surfaces.
- Add Codex credit estimates and optional local allowance-window context to the dashboard.
- Add prominent unofficial-project disclaimers to docs, dashboard output, and plugin metadata.
- Harden malformed token-count parsing, SQLite concurrency, MCP raw-context opt-in, pricing parser diagnostics, bundled dashboard docs, and schema migrations.
- Fix Python 3.10 compatibility for UTC timestamps and release checks.
- Add package-owned Codex plugin installation with `codex-usage-tracker install-plugin`.
- Package plugin assets and the Codex skill into the Python wheel.
- Add a companion `codex-usage-api` skill for conversational analysis through aggregate-only API/MCP data.
- Add distribution metadata, source distribution manifest, and CI build checks.
- Add `python -m codex_usage_tracker` support and CLI `--version` output.
- Add release-readiness checks for version alignment, required docs, package data, built wheels, and tracked secret patterns.
- Harden marketplace MCP runtime bootstrapping so cached runtimes refresh when the bundled package pin changes.
- Harden local dashboard server responses with browser security headers and safer IPv6 localhost URLs.
- Tighten the dashboard header copy, add click/keyboard row inspection, and keep detailed usage guidance out of the primary UI.
- Keep call details sticky while scrolling and render timestamps as local human-readable date/time values.
- Prefer non-review models in mixed thread model summaries, add fit-to-width model labels, and add a scroll-aware `Top` button.
- Hide single-page dashboard pagination and keep multi-page controls compact in the toolbar.
- Render fetched and refreshed timestamps as local human-readable date-times and make the call details scrollbar visible.
- Rewrite the README around practical usage investigations, long-chat context growth, and pre-release limitations.
- Add a screenshot-driven dashboard guide built from synthetic aggregate fixture data.
- Preserve requested virtualenv Python paths during plugin install instead of resolving through interpreter symlinks.
- Keep generated dashboards, SQLite databases, CSV exports, and raw Codex logs out of git.

## 0.1.13

- Add dashboard load limits, API limits, and pagination for larger Codex histories.
