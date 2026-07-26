# Product Kernel Reset Implementation Plan

**Date:** 2026-07-26
**Status:** Approved implementation sequence
**Normative roadmap:** `docs/roadmap/product-kernel-reset.md`
**Approved design:**
`docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md`
**Execution ledger:** `docs/roadmap/product-kernel-reset-execution.md`
**Starting baseline:** `origin/main` at
`0a558dd328c1519c77fffe68b71a8bccdbd1a731`

## 1. Mission

Replace the experimental product shell with a lean, rebuildable local data
kernel that:

- incrementally normalizes Codex session logs into exact structural facts;
- answers bounded, generation-consistent usage questions quickly;
- resolves every row-level claim to stable evidence;
- streams live activity without forcing a rebuild or blocking reads;
- gives Codex efficient primitives for its own explanations and follow-up
  queries; and
- deletes the server-authored analysis, compression, recommendation, diagnostic,
  content-index, and compatibility systems that no longer justify their weight.

This is a clean-kernel transplant, not a blank rewrite. Existing code and
fixtures are an oracle. Code is reused only where it fits the new ownership,
privacy, and performance contracts.

## 2. Execution Protocol

For every task:

1. Start from current `main` on `kernel/<task-id>-<slug>`.
2. Read the active roadmap, design section, task entry, and latest execution
   ledger entry. Do not reopen the archived program as authority.
3. Measure the current synthetic baseline where the task has a latency, size,
   or equivalence gate.
4. Add the named failing contract, invariant, or benchmark before implementation.
5. Make the smallest implementation that satisfies only that task.
6. Run focused checks, then every cross-cutting gate named by the task.
7. Record branch, commits, measurements, deviations, review result, and residual
   risk in the execution ledger in the same changeset.
8. Give a meaningful stable diff one final read-only independent review after
   primary validation.
9. Merge only while `main` remains releasable. Through K8, public 0.25 defaults
   remain active and the kernel composition is reachable only through direct
   tests and an internal development selector. K9 activates the kernel and
   deletes the old runtime in one changeset.

Use synthetic fixtures only. Never inspect, print, commit, or profile the
maintainer's live usage database or raw session content.

## 3. Dependency Graph

```text
K0
 |
K1
 |
K2
 |
K3 ----+
 |     |
K4    K5
 |     |
 +--K6-+
     |
    K7
     |
    K8
     |
    K9
     |
   K10
     |
   K11
    / \
 K12 K13
    \ /
   K14
     |
   K15
     |
   K16
```

K4 and K5 may proceed in parallel after K3 only if they touch separate modules
and use the same frozen identities. K12 and K13 may proceed in parallel after
K11. No other task may skip its dependency.

## 4. Program-Wide Invariants

These are acceptance criteria for every implementation task, even when a task
does not repeat them:

- A query never starts a refresh.
- Browser open or reopen never starts an initial build.
- Startup never reports false zeroes while a valid committed generation exists.
- Parsing and normalization happen outside `BEGIN IMMEDIATE`.
- The single writer commits bounded micro-batches; readers continue against the
  last committed generation.
- One compatible refresh joins one durable job. A caller cannot create a second
  competing writer.
- Stable evidence identities do not depend on SQLite row IDs.
- Default storage excludes prompts, assistant text, reasoning text, tool
  arguments, tool output, shell bodies, secrets, and full local paths.
- Every returned measure declares grade, basis, coverage, generation, and
  freshness.
- `exact`, `deterministic`, and `estimated` values are never presented as
  interchangeable.
- The four token classes preserve upstream overlap semantics.
- Canonical accounting and conservative copied-row exclusion remain fail closed.
- Long work is awaited by the host or watched through SSE; models do not poll in
  short loops.
- Existing release build-once, byte-identical promotion, package coherence, and
  installed smoke contracts remain blocking.

## Task K0 — Archive The Old Program And Freeze The Reset

**Outcome:** One active roadmap, one approved design, one implementation plan,
one execution ledger, and stable archive redirects.

**Depends on:** none
**Branch:** `docs/kernel-reset-roadmap`
**Suggested commit:** `docs: reset product roadmap around lean data kernel`

**Files:**

- move the former roadmap, plan, design, ledger, and change-plan records into
  dated archive directories;
- create stable redirect files at their former paths;
- create the new roadmap, design, plan, ledger, and Agent Maintainer plan;
- update `AGENTS.md`, `README.md`, `docs/architecture.md`,
  `docs/deprecations.md`, and `docs/release-checklist.md`; and
- update `tests/packaging/test_public_docs.py`.

**Contract first:**

- Public-doc tests must identify the Product Kernel Reset as normative.
- Tests must require the ordered `0.25.x`, `0.26.0`, `0.27.0`, and `0.28.0`
  sequence.
- Tests must require exactly the six target MCP names and explicit removal of
  `usage_analyze`.
- Tests must prove the old documents remain available only as archived history.
- Agent guidance must allow and reserve `kernel/` task branches.

**Implementation:**

1. Preserve the full historical artifacts byte-for-byte except for an archive
   banner.
2. Add redirect documents so published links do not break.
3. Publish the ownership split, data model, cutover, removal boundary, and
   performance/privacy/recovery gates.
4. Replace the compatibility ledger with the beta-breaking kernel cutover
   ledger while archiving its previous contents.
5. Mark all older architecture detail as a 0.25 runtime reference, not target
   authority.

**Verification:**

```bash
python -m pytest tests/packaging/test_public_docs.py -q
python scripts/check_release.py
npx markdownlint-cli2 README.md "docs/**/*.md" \
  ".agent-maintainer/change-plans/*.md"
git diff --check
```

**Acceptance:**

- Every active pointer resolves to the reset program.
- Every historical pointer still resolves.
- No production code, package version, installed plugin, or database changes.

## Task K1 — Freeze The Accounting Oracle

**Outcome:** A small, explicit test oracle captures the semantics worth
transplanting before new storage work starts.

**Depends on:** K0
**Branch:** `kernel/k1-oracle-baseline`
**Suggested commit:** `test: freeze kernel accounting oracle`

**Create or modify:**

- `tests/kernel/fixtures/`
- `tests/kernel/test_oracle_equivalence.py`
- `tests/kernel/test_source_lifecycle_oracle.py`
- `tests/kernel/test_privacy_oracle.py`
- `config/kernel-retired-surfaces-v1.json`
- `tests/kernel/test_retired_surface_manifest.py`
- `scripts/benchmark_kernel.py`
- `config/kernel-performance-budget.json`
- execution ledger

**Contract first:**

Build deterministic fixtures covering:

- new, appended, partially appended, replaced, truncated, archived, and restored
  sources;
- physical duplicates, canonical copies, delayed parent attachment, subagents,
  compaction, abort, completion, and rollback;
- model, effort, service tier, rate-limit, and allowance observations;
- turns with model calls, local tools, MCP tools, skills, patches, tests, and
  errors; and
- malformed or unknown events that must be skipped or conservatively retained.

Freeze expected:

- physical and canonical counts;
- four token-class totals;
- per-thread/model/effort/time totals;
- canonical identities and parentage;
- source state and cursor results;
- allowance observation selection; and
- privacy-safe normalized fields.

Freeze every retired non-MCP and MCP public surface in one versioned manifest.
Each entry has `surface_type`, exact public name or route, current owner,
replacement or `none`, final supported release, removal release, and the
absence or migration test that will prove removal.

**Implementation:**

1. Select the smallest existing synthetic fixtures that express proven
   semantics.
2. Add missing cases without copying implementation-specific table layouts.
3. Export one versioned JSON oracle from the current runtime.
4. Add a benchmark workload at 10,000 and 100,000 calls with fixed seeds.
5. Record old-runtime latency, rows, tables, database size, package size, and
   writer-lock duration as comparison evidence, not future acceptance.
6. Generate and review the retired-surface manifest from the current MCP
   catalog, HTTP routes, CLI parser, schemas, tables, frontend routes/assets,
   package data, and documented aliases. Commit the frozen result.

**Verification:**

- oracle tests deterministic across two clean runs;
- fixture contains no absolute user path or real content;
- current runtime produces the frozen expected values;
- benchmark output includes environment and seed;
- release checks remain green.

**Acceptance:** K2 can implement from contracts without importing current table
definitions. K6 and K9 can consume a complete exact removal inventory. No
current oracle failure or surface omission is waived without a written semantic
decision.

## Task K2 — Define Kernel Schema V1 And Stable Identity

**Outcome:** A side-by-side schema-v1 database stores only foundational facts
and has an explicit operational sidecar boundary.

**Depends on:** K1
**Branch:** `kernel/k2-schema-identity`
**Suggested commit:** `feat: add kernel schema v1 and stable identities`

**Target modules:**

- `src/codex_usage_tracker/kernel/schema.py`
- `src/codex_usage_tracker/kernel/identity.py`
- `src/codex_usage_tracker/kernel/database.py`
- `src/codex_usage_tracker/kernel/operational.py`
- `src/codex_usage_tracker/kernel/models.py`
- `tests/kernel/test_schema.py`
- `tests/kernel/test_identity.py`
- `tests/kernel/test_database_lifecycle.py`
- `tests/kernel/test_cutover_control.py`
- `tests/kernel/test_source_registry_privacy.py`

**Contract first:**

- A fresh cache contains only the tables approved in the design:
  `sources`, `generations`, `refresh_runs`, `threads`, `turns`, `model_calls`,
  `tool_calls`, `activity_events`, and `allowance_observations`.
- Operational lease/job state is separate from committed analytical facts.
- All foreign keys and integrity checks are active on every connection.
- Public keys are stable across rebuilds and row-order changes.
- Safe labels and path-derived fields pass strict privacy tests.
- The analytical database schema has no full-path column, and a synthetic
  sensitive path does not appear in its file bytes or any export.
- Full path-to-source mappings exist only in the owner-only operational source
  registry and are unreachable from query, evidence, MCP, HTTP, exports, and
  support bundles.
- The active 0.25 database is never opened for read or mutation by kernel code.

**Implementation:**

1. Choose and document the final versioned kernel filename and operational
   sidecar filename.
2. Add schema creation, feature/capability metadata, and explicit schema
   version `1`; do not import the 39-version migration chain.
3. Implement logical IDs from safe source identity, source event identity, and
   canonical fingerprint inputs.
4. Add connection factories for read snapshots, short writer transactions, and
   integrity validation.
5. Add staging, active, rollback, and failed-build path metadata.
6. Define the atomically replaced cutover control record and operational source
   registry, including permissions, retention, non-exportability, and recovery.

**Verification:**

- schema, foreign-key, privacy, and ID stability tests;
- interrupted creation and reopening tests;
- deterministic schema dump;
- table-count and index-count budget;
- mypy, Ruff, architecture, release, and package checks.

**Acceptance:** The new database can be created and validated without importing
analysis, reports, recommendations, compression, content FTS, HTTP, MCP, CLI,
or frontend modules.

## Task K3 — Build One Incremental And Live Ingestion Path

**Outcome:** Initial hydration, explicit refresh, moving-tail catch-up, and live
watch share one cursor/normalization pipeline and one bounded writer.

**Depends on:** K2
**Branch:** `kernel/k3-ingest-tail`
**Suggested commit:** `feat: add incremental kernel ingestion`

**Target modules:**

- `src/codex_usage_tracker/kernel/discovery.py`
- `src/codex_usage_tracker/kernel/parser.py`
- `src/codex_usage_tracker/kernel/normalize.py`
- `src/codex_usage_tracker/kernel/ingest.py`
- `src/codex_usage_tracker/kernel/writer.py`
- `src/codex_usage_tracker/kernel/watcher.py`
- `tests/kernel/test_ingest_*.py`
- `tests/kernel/test_watcher.py`

**Contract first:**

- `no_changes`: no analytical-table writes and no generation bump.
- `new_source`: parses only the new source.
- `append_safe`: begins at the last complete committed byte offset.
- `moving_tail`: commits complete lines, records high water, and catches up.
- `replace_source` and `truncate_source`: reconcile only rows owned by that
  source.
- A partial final line is never committed.
- Parsing and normalization complete outside the writer transaction.
- Writer transactions meet the 50 ms p95 synthetic budget.
- Concurrent readers always see one complete generation.
- A compatible active job is joined, not duplicated.
- The first build starts only from explicit CLI `refresh`, MCP
  `usage_refresh`, or Console Refresh actions.
- Install, setup, status, query, evidence, allowance, service startup, and
  browser mount never start a build.
- `absent`, `building`, `ready`, `active`, and `failed` states have the
  behavior frozen in the design; no read opens staging.
- Failed promotion leaves the prior active pointer unchanged.

**Implementation:**

1. Transplant proven discovery, counter validation, source revision, and
   conservative canonicalization rules behind kernel-owned protocols.
2. Normalize one bounded batch in memory.
3. Commit a batch and its cursor atomically, with an idempotency key.
4. Publish one generation only after all batches for the refresh are complete.
5. Give live watch the same planner and writer lease as explicit refresh.
6. Record phase timings and counters without running any optional derived work.
7. Implement staging initial build plus high-water catch-up before promotion.
8. Atomically promote the cutover control record and implement prior-kernel
   pointer rollback. Preserve schema-39 metadata only for package downgrade.

**Verification:**

- full source-lifecycle matrix;
- process crash before, during, and after batch commit;
- two-process lease and stale-owner recovery;
- concurrent reads during a 100,000-call build;
- append-active source while hydration runs;
- clean install, 0.25.1 upgrade, explicit first-build trigger, failed build,
  failed promotion, prior-kernel rollback, and no-prior-kernel state;
- no compression, content FTS, analysis, or recommendation import in profiles;
- benchmark and writer-lock budgets.

**Acceptance:** Reopening a process or browser against a committed generation
returns immediately. No test path requires a total-history derived-state phase.

## Task K4 — Build The Bounded Query Engine

**Outcome:** `usage_query` can answer the valuable accounting and comparison
questions with one generation-consistent request or bounded batch.

**Depends on:** K3
**Branch:** `kernel/k4-query-engine`
**Suggested commit:** `feat: add bounded kernel query engine`

**Target modules:**

- `src/codex_usage_tracker/kernel/query/contracts.py`
- `src/codex_usage_tracker/kernel/query/catalog.py`
- `src/codex_usage_tracker/kernel/query/plans.py`
- `src/codex_usage_tracker/kernel/query/phases.py`
- `src/codex_usage_tracker/kernel/query/service.py`
- `tests/kernel/query/`

**Contract first:**

- datasets: calls, turns, threads, tools, activities, phases, and allowance;
- operations: rows, aggregate, share, comparison, distribution, time series,
  and timeline;
- allowlisted dimensions and measures from the design;
- single-generation snapshot for every subquery in a batch;
- stable plan ID/version, normalized scope, counts, cursor, truncation, elapsed
  time, grade, coverage, and evidence selectors;
- rejected unknown dimensions, measures, filters, cross products, cursors, and
  unbounded limits; and
- no implicit refresh or write.
- a pure versioned phase segmenter over activity facts, with basis, confidence,
  `unknown` fallback, and deterministic token-attribution semantics.

**Implementation:**

1. Define typed request/response contracts independent of MCP and HTTP.
2. Implement named SQL plans with explicit indexes; do not interpolate user
   identifiers.
3. Provide direct plans for common leaderboard, concentration, model/effort,
   time-comparison, tool, turn, and allowance questions.
4. Add bounded batch execution under one read transaction.
5. Implement the design's phase categories as a pure read-time segmenter; store
   no interpretive phase narrative or migrated phase row.
6. Add a result cache only if a measured plan misses budget and the cache key
   includes generation and normalized request.

**Verification:**

- property tests for filter normalization and cursor stability;
- oracle equivalence for accounting dimensions;
- 100,000-call focused plan benchmark;
- status <=100 ms p95, common queries <=500 ms p95, and bounded
  comparison/concentration <=1 second p95;
- explain-plan assertions preventing table scans where the budget requires an
  index;
- golden phase segmentation, basis/confidence, boundary, compaction, unknown,
  and deterministic token-attribution tests; and
- zero writes under query-only traces.

**Acceptance:** The verified dogfood report—leaderboards, concentration,
model/effort matrix, project families, and period comparisons—can be produced
with at most three batched query calls and no server-authored narrative.

## Task K5 — Build Exact Evidence And Live Timeline

**Outcome:** Stable selectors resolve to bounded timelines and a reconnectable
local event stream.

**Depends on:** K3
**Branch:** `kernel/k5-evidence-live`
**Suggested commit:** `feat: add live kernel evidence timelines`

**Target modules:**

- `src/codex_usage_tracker/kernel/evidence/contracts.py`
- `src/codex_usage_tracker/kernel/evidence/service.py`
- `src/codex_usage_tracker/kernel/live/journal.py`
- `src/codex_usage_tracker/kernel/live/stream.py`
- `tests/kernel/evidence/`
- `tests/kernel/live/`

**Contract first:**

- selectors: thread, turn, call, tool, and allowance;
- views: summary, timeline, calls, tools, activities, and allowance;
- stable route destination for every valid selector;
- bounded first page and cursor pagination;
- exact selector survival across a clean rebuild;
- SSE monotonic event IDs, generation, heartbeat, reconnect with
  `Last-Event-ID`, bounded replay, and snapshot fallback; and
- stream payload privacy parity with normal evidence reads.

**Implementation:**

1. Resolve selectors through logical IDs, never row IDs.
2. Build ordered timeline rows from foundational facts.
3. Add a small generation journal fed after committed batches.
4. Serve snapshot-then-stream semantics so reconnects cannot create gaps
   silently.
5. Keep live transport read-only; it cannot acquire the ingestion writer lease.

**Verification:**

- selector rebuild stability and invalid-selector tests;
- 100,000-row timeline first page <=500 ms p95;
- reconnect before, within, and after replay retention;
- burst, slow-client, disconnect, restart, and generation rollover tests;
- loopback/origin and privacy tests; and
- no stream-driven refresh.

**Acceptance:** “Launch evidence timeline for this thread” and “Live watch run
evidence” use the same selector and route, differing only by live mode.

## Task K6 — Build Kernel Interfaces Behind The Cutover

**Outcome:** A complete kernel plugin, localhost API, and operational CLI
composition exists behind a non-public internal selector. The shipping 0.25
composition and defaults remain unchanged until K9.

**Depends on:** K4 and K5
**Branch:** `kernel/k6-interface-cutover`
**Suggested commit:** `feat: add kernel interface composition`

**Target modules:**

- `src/codex_usage_tracker/interfaces/mcp/`
- `src/codex_usage_tracker/interfaces/http/`
- `src/codex_usage_tracker/interfaces/cli/`
- `src/codex_usage_tracker/kernel/plugin_manifest.py`
- kernel skill source and staged bundle, excluded from the public package until
  K9
- public JSON schemas and contract fixtures
- interface tests

**Contract first:**

- the isolated kernel composition contains exactly six MCP tools:
  `usage_status`, `usage_refresh`, `usage_query`, `usage_evidence`,
  `usage_allowance`, and `usage_job_status`;
- that composition contains no `usage_analyze`, `full`, `developer`, or
  historical tool aliases;
- the default installed/public 0.25 composition remains unchanged through K8;
- `usage_status`, query, evidence, and allowance are read-only;
- `usage_refresh` returns or joins one durable job;
- `usage_job_status` returns one internally consistent snapshot and optionally
  awaits on the host side;
- new HTTP route version has matching service semantics and SSE;
- CLI retains setup, status, refresh, query, export, open, service,
  configuration, repair, and package operations; and
- every new adapter and future removal maps to
  `config/kernel-retired-surfaces-v1.json`.

**Implementation:**

1. Choose and document the final new HTTP prefix.
2. Bind all three adapters to kernel application services once.
3. Generate small public schemas from typed contracts.
4. Rewrite the plugin skill around batched exploration, fact grades, evidence,
   and model-owned inference.
5. Build a kernel manifest and composition selected only by direct tests or an
   explicitly internal development selector; do not change public defaults.
6. Add host-side bounded await support without making the model poll.
7. Validate the new adapters against the frozen retired-surface manifest
   without deleting handlers yet.

**Verification:**

- exact MCP catalog and no legacy names;
- schema/implementation/catalog coherence;
- direct stdio handshake and localhost API parity;
- read-only calls during active refresh;
- two-process compatible refresh join;
- isolated kernel wheel/plugin smoke in two fresh test tasks;
- installed public 0.25 smoke proving defaults remain unchanged;
- package asset digest and same-version cache replacement; and
- CLI/help/public-doc snapshots.

**Acceptance:** An isolated kernel task sees exactly six coherent tools, while
the normal installed 0.25 task still sees the unchanged public runtime. An
existing kernel generation is queryable even if refresh, watcher, or another
task is active.

## Task K7 — Build The Focused Console Behind The Cutover

**Outcome:** A focused kernel Console becomes a thin client for Live, Explore,
Evidence, Limits, and Settings and renders committed data immediately. It
remains behind the same internal cutover selector until K9.

**Depends on:** K6
**Branch:** `kernel/k7-console-cutover`
**Suggested commit:** `feat: focus console on live usage evidence`

**Target modules:**

- `frontend/dashboard/src/kernel/`
- generated deterministic kernel dashboard assets excluded from the default
  package until K9
- dashboard route and browser tests
- frontend bundle budgets
- Console guides and screenshots

**Contract first:**

- only the five approved product areas are routable;
- initial render hydrates the committed generation before checking freshness;
- stale state is visible but never replaces valid totals with zero;
- catch-up is explicit or watcher-driven, not mount-driven;
- Live reconnects without duplicate timeline events;
- Explore uses the query contract rather than page-specific hidden reports;
- Evidence deep links are stable;
- Limits distinguishes observations, calculations, estimates, and caveats; and
- Settings exposes watcher, cache, privacy, pricing, rollback, and optional
  content state.

**Implementation:**

1. Create one small API client around K6 contracts.
2. Build a parallel kernel Console entrypoint with snapshot-first reads; leave
   the public 0.25 entrypoint and packaged target unchanged.
3. Implement live timeline bands and four token classes without inventing
   context-category attribution.
4. Implement guided query controls and saved local query specifications.
5. Give the kernel Console no analysis/recommendation/findings dependencies or
   navigation.
6. Rebuild deterministic assets from source.

**Verification:**

- frontend lint, typecheck, unit, accessibility, localization, governance,
  deterministic-assets, and bundle gates;
- Playwright fresh, warm, stale, active-refresh, restart, and reconnect flows;
- meaningful warm render <=1 second p95 on the synthetic benchmark;
- zero POST/refresh from browser reopen;
- exact deep-link round trips; and
- isolated kernel Console smoke; and
- installed public 0.25 Console smoke proving its default remains unchanged.

**Acceptance:** Closing and reopening the browser shows the prior committed
generation immediately and then visibly catches up, without a rebuild.

## Task K8 — Prove Allowance And Efficiency Measures

**Outcome:** Allowance movement and local-efficiency ratios are useful without
claiming unsupported causal billing attribution.

**Depends on:** K7
**Branch:** `kernel/k8-allowance-efficiency`
**Suggested commit:** `feat: add graded allowance efficiency measures`

**Target modules:**

- kernel allowance normalization and query plans
- Limits Console
- allowance schemas/docs/tests
- synthetic allowance fixtures

**Contract first:**

- exact observed remaining/used values and timestamps;
- deterministic reset-window selection and interval deltas;
- rate-card and credit estimates with provenance and coverage;
- percentage points per hour;
- local tokens, calls, and turns per observed percentage point;
- explicit outside-usage, missing-observation, and reset caveats; and
- no interpolation across incompatible windows.

**Implementation:**

1. Transplant the proven observation parser and reset-aware selection rules.
2. Calculate ratios only for valid adjacent observations.
3. Attach local event windows and coverage instead of claiming causality.
4. Expose query measures and a compact Limits presentation.

**Verification:**

- reset, missing interval, outside usage, unchanged percentage, and mixed
  window fixtures;
- oracle comparison with retained valid behavior;
- query and UI grade/coverage assertions;
- live observation update without full refresh; and
- pricing/rate-card provenance tests.

**Acceptance:** The Console and model can discuss usage per allowance percentage
with exact wording about what was observed and what remains estimated.

## Task K9 — Activate The Kernel And Delete The Experimental Spike

**Outcome:** The kernel package/plugin/HTTP/CLI/Console composition becomes the
public default and retired runtime code, persistence, assets, tests, routes,
tools, schemas, and packages are removed in the same audited changeset.

**Depends on:** K8
**Branch:** `kernel/k9-spike-deletion`
**Suggested commit:** `refactor: remove retired analysis product`

**Deletion manifest:**

- analysis catalog, strategies, application orchestration, results, and
  `usage_analyze`;
- Compression Lab computation, persistence, routes, tools, jobs, UI, and
  benchmarks;
- recommendation, attention-sort, diagnostic snapshot, investigation,
  workbench, report, and usage-drain systems not retained by export;
- any residual OTel/local telemetry ingestion, persistence, routes,
  diagnostics, and package assets;
- default content fragments, FTS, content refresh, and raw-content search;
- generic analysis jobs and their operational APIs;
- full/developer profiles and every compatibility handler;
- historical HTTP route families and CLI aliases;
- the old schema migration chain and schema-39 runtime reader, while retaining
  only external oracle/downgrade fixtures needed to prove file preservation;
  and
- frontend source, packaged assets, docs, screenshots, schemas, and tests that
  exist only for deleted surfaces.

**Preservation manifest:**

- source parsing and counter validation;
- canonical identity, copy exclusion, and source cursor semantics;
- privacy-safe structural activity extraction;
- subagent attachment;
- pricing provenance and allowance observation;
- selected CSV/JSON export;
- exact evidence links;
- synthetic oracle fixtures;
- plugin/package coherence; and
- build-once release promotion.

**Contract first:**

- forbidden import/name/route/tool/schema/table/asset inventories;
- six-tool installed catalog;
- exact equality with `config/kernel-retired-surfaces-v1.json`, including an
  absence or migration test for every entry;
- package-data allowlist;
- old-cache non-deletion and rollback metadata;
- export and evidence parity;
- package, source, bundle, route, schema, and table budgets.

**Implementation:**

1. Reconcile the K1 retired-surface manifest against current source and fail on
   an unclassified addition or omission.
2. Switch `.codex-plugin/plugin.json`, `.mcp.json`, the public application
   composition, HTTP server, CLI, skill bundle, and Console assets to the
   validated kernel implementation.
3. Remove leaves, compatibility adapters, and then unused domain modules in the
   same branch; no merge contains a half-migrated public default.
4. Delete old runtime migration code after the kernel composition is active in
   the staged artifact.
5. Update the upgrade guide with every manifest replacement or `none`.
6. Measure final outputs and set budgets no more than three percent above them.

**Verification:**

- forbidden inventory and dead-code/import scans;
- full Python/frontend/architecture/privacy/release suites;
- built wheel and sdist contents;
- installed CLI/plugin/Console smoke;
- old cache remains present and rollback metadata is valid;
- 0.25 defaults pass before activation and the six-tool kernel defaults pass
  after activation in the same cutover test;
- every retired-surface manifest entry is absent or emits only its documented
  install-time migration error;
- oracle, query, evidence, export, refresh, live, and allowance suites; and
- complexity/package/bundle budgets.

**Acceptance:** No runtime code path can start or import analysis, compression,
recommendations, diagnostics, content FTS, or compatibility profiles. Git
history and the retained old database—not shipping adapters—are the archive.

## Task K10 — Qualify And Publish 0.26.0

**Outcome:** The kernel cutover ships from one qualified artifact with recovery
evidence and installed dogfood.

**Depends on:** K9
**Branch:** `release/0.26.0`
**Suggested commits:** release preparation plus the repository's protected
release flow

**Release evidence:**

- clean staging build beside an old 0.25 cache;
- clean install remains `absent` until an explicit refresh action;
- 0.25.1 upgrade preserves schema 39 without reading it from 0.26;
- high-water catch-up while sources append;
- failed-build and failed-promotion state;
- atomic promote, prior-kernel pointer rollback, and installed-package
  downgrade to 0.25.1;
- no-change, append, replacement, concurrent-read, live reconnect, and restart
  benchmarks;
- two fresh-task MCP dogfood;
- warm Console reopen;
- exact six-tool catalog and route/schema/table inventories;
- distribution hashes, manifest, promotion evidence, and public smoke; and
- package/code/bundle reduction against the recorded K1 baseline.

**Required dogfood questions:**

- top threads and top-thread concentration;
- model by effort matrix;
- current versus previous seven-day comparison;
- top tools and per-turn tool intensity;
- exact thread evidence link;
- live timeline reconnect; and
- allowance efficiency with caveats.

**Acceptance:** No duplicate writer, lock error, implicit refresh, false zero,
nonterminal optional phase, or model polling loop. Every reported claim is
exactly traceable or explicitly graded.

## Task K11 — Add Guided Model-Driven Exploration

**Outcome:** The plugin skill and Console help a model compose efficient queries
without recreating a server analysis engine.

**Depends on:** K10
**Branch:** `kernel/k11-guided-exploration`
**Suggested commit:** `feat: add guided kernel exploration`

**Contract first:**

- capability discovery is static and compact;
- one batch can answer related dimensions at one generation;
- response size and row limits are explicit;
- follow-up suggestions are query templates, not findings;
- the skill distinguishes facts, estimates, hypotheses, and unsupported claims;
  and
- exact evidence is requested only after ranking narrows the candidate set.

**Implementation:**

1. Add concise dataset/measure/dimension metadata to `usage_query`.
2. Add curated query templates for concentration, period comparison,
   model/effort, tools, turns, subagents, and allowance.
3. Teach the skill a three-step loop: scope, batch, evidence.
4. Add Console query-builder affordances that emit the same typed request.

**Verification:**

- golden prompts complete in a bounded number of MCP calls;
- no hidden refresh or analysis job;
- model response cites generation and evidence;
- response-size and latency budgets; and
- repeated request determinism.

**Acceptance:** The model can produce a useful recurring usage report without
`usage_analyze` or a persisted finding.

## Task K12 — Add Optional Context-Composition Estimates

**Outcome:** Users can inspect how much observed context came from tools, MCP,
messages, and host material without making raw content or estimates part of the
base kernel.

**Depends on:** K11
**Branch:** `kernel/k12-context-composition`
**Suggested commit:** `feat: add optional context composition evidence`

**Contract first:**

- feature is off by default;
- content lives in a separate database and deletion lifecycle;
- exact bytes and event counts are distinct from tokenizer estimates;
- coverage and unattributed input are explicit;
- secrets and sensitive fields are redacted before persistence;
- disabling or deleting content leaves accounting intact; and
- no normal refresh waits on content processing.

**Implementation:**

1. Define the opt-in capability and privacy confirmation.
2. Store bounded category metadata and optional redacted fragments separately.
3. Run content work as a lower-priority consumer of committed kernel events.
4. Add category-byte and optional tokenizer-estimate query plans.

**Verification:**

- opt-in/out/delete lifecycle;
- redaction and shareable-export exclusions;
- accounting works with missing/deleted content database;
- normal refresh latency unchanged within noise;
- exact versus estimated UI language; and
- content worker failure isolation.

**Acceptance:** “How much context was tool output?” receives either an exact
observed-byte answer or an explicitly covered estimate, never a fabricated exact
token share.

## Task K13 — Freeze The Read-Only Overlay Boundary

**Outcome:** A later browser overlay or DOM integration can consume live
evidence without gaining write, refresh, capture, or raw-content authority.

**Depends on:** K11
**Branch:** `kernel/k13-overlay-boundary`
**Suggested commit:** `docs: define read-only live overlay contract`

**Contract first:**

- localhost read-only handshake;
- selector, generation, stream event, reconnect, and capability contract;
- no DOM capture in this task;
- no credentials, external transmission, refresh, or database writes;
- unknown host/version fails closed; and
- sidecar remains the canonical renderer and fallback.

**Implementation:** Publish the adapter contract and a synthetic protocol
fixture. Do not build or bundle an overlay.

**Verification:** Schema fixture, origin guard, replay behavior, version
negotiation, and privacy review.

**Acceptance:** Overlay implementation remains a separately approved future
decision and cannot expand kernel authority.

## Task K14 — Qualify And Publish 0.27.0

**Outcome:** Guided exploration and optional context composition ship without
regressing the 0.26 kernel.

**Depends on:** K12 and K13
**Branch:** `release/0.27.0`

**Required evidence:**

- K10 suite repeated;
- bounded golden-prompt MCP call counts and response sizes;
- opt-in content worker isolation and deletion;
- query/template schema compatibility;
- unchanged base refresh and warm-render budgets;
- package budgets with optional assets measured separately; and
- protected build-once public release evidence.

**Acceptance:** All 0.26 base workflows remain useful with content evidence
disabled.

## Task K15 — Fault, Recovery, And Scale Qualification

**Outcome:** A feature-free hardening pass proves failure behavior before
contract freeze.

**Depends on:** K14
**Branch:** `kernel/k15-fault-recovery`
**Suggested commit:** `test: harden kernel recovery and scale gates`

**Fault matrix:**

- corrupt/partial JSONL;
- file append during scan;
- replacement and truncation;
- process kill at every writer boundary;
- stale and live foreign leases;
- disk full and read-only cache directory;
- interrupted staging build and atomic promotion;
- watcher restart and replay expiry;
- slow or disconnected SSE client;
- malformed query/cursor/selector;
- optional content worker crash; and
- old-cache rollback.

**Scale matrix:**

- 100,000 calls;
- many small files and one large file;
- 1,000 active threads;
- high tool-call fan-out;
- concurrent Console, MCP, export, and refresh reads; and
- long-running append-active source.

**Verification:** Run the complete release candidate suite twice from clean
state and once from an upgraded 0.26 installation.

**Acceptance:** No data corruption, privacy regression, false success, infinite
polling, unbounded response, or unrecoverable promotion state.

## Task K16 — Freeze Contracts And Publish 0.28.0

**Outcome:** Freeze the smallest proven pre-1.0 public contract after a
feature-free release cycle.

**Depends on:** K15
**Branch:** `release/0.28.0`

**Freeze inventory:**

- six MCP tool names and schemas;
- HTTP route/version and SSE event schemas;
- CLI primary commands and machine-readable output;
- logical evidence selectors;
- kernel schema lifecycle and cache naming;
- calculation grades and four token classes;
- export formats selected for support;
- privacy/default-content posture; and
- package/plugin installation and upgrade behavior.

**Implementation:**

1. Convert release fixtures into explicit stable-contract tests.
2. Publish operations, recovery, privacy, query, evidence, and upgrade
   references.
3. Set product complexity, package, bundle, route, schema, and table budgets
   from final measured output with at most three percent headroom.
4. Record the 1.0 readiness decision and any intentionally experimental
   capability.

**Verification:** Full CI, clean build, installed smoke, upgrade/rollback,
two-task dogfood, browser release candidate, public artifact equality, and
reviewed contract inventory.

**Acceptance:** No feature work is smuggled into stabilization. Any post-freeze
breaking change requires a new approved roadmap amendment.

## Program Completion

The Product Kernel Reset is complete only when:

- K0–K16 have terminal ledger entries;
- the six-tool factual surface and Evidence Console work from a clean install
  and warm reopen;
- incremental ingestion has no default optional derived phase;
- exact evidence survives rebuild;
- old runtime compatibility is absent from shipped code and assets;
- optional content remains separable and deletable;
- all performance and privacy budgets are enforced, not merely documented; and
- Release 0.28.0 is publicly verified from byte-identical promoted artifacts.
