# Codex Usage Tracker Product Kernel Reset Design

**Date:** 2026-07-26
**Status:** Approved product-direction contract
**Repository baseline:** `origin/main` at
`0a558dd328c1519c77fffe68b71a8bccdbd1a731`
**Operational evidence branch:** `fix/313-core-fast-path` at
`96cc1546aa20b36d1a93945dc11cc88e6b19aa42`
**Published baseline:** `codex-usage-tracking==0.25.1`
**Companion roadmap:** `docs/roadmap/product-kernel-reset.md`
**Companion implementation plan:**
`docs/superpowers/plans/2026-07-26-product-kernel-reset.md`
**Supersedes:** the 2026-07-21 MCP-first design for all post-0.25 work

## 1. Task Card

**ID:** `K0-ROADMAP-RESET`

**Request:** Archive the current roadmap, replace it with a lean product-kernel
roadmap, and pursue a product centered on extremely fast exact data access,
model-driven inference, live evidence timelines, guided exploration, and a
smaller disposable-cache architecture.

**Goal:** Establish a decision-complete contract that lets implementation delete
the experimental analysis and compatibility shell without losing canonical
accounting, privacy, incremental freshness, evidence identity, or release
integrity.

**In scope:**

- target product responsibility split;
- kernel fact model and database lifecycle;
- incremental and live ingestion;
- bounded query and evidence contracts;
- MCP, HTTP, CLI, Console, and sidecar target surfaces;
- exact versus estimated measurement rules;
- deletion and cutover strategy;
- performance, privacy, recovery, package, and release gates; and
- task sequence through feature-free stabilization.

**Out of scope for this documentation task:**

- production code changes;
- database creation or migration;
- deleting the current cache;
- changing the installed plugin;
- merging or releasing a runtime;
- collecting real local usage samples; and
- committing to a browser overlay implementation before the sidecar contract is
  proven.

**Acceptance criteria:**

- one active roadmap replaces the old normative links;
- the old roadmap, design, plan, and ledger remain available as historical
  evidence;
- the new plan names exact preservation and deletion boundaries;
- foundational facts support turns, tools, skills, phases, timelines, token
  classes, and allowance efficiency;
- the design prevents implicit refresh, long model polling, repeated rebuilds,
  and unsupported server narratives;
- the cutover is side by side and recoverable; and
- repository documentation tests fail if old authority becomes normative again.

**Primary risks:**

- rewriting proven accounting semantics accidentally;
- treating a physical cache schema as public identity;
- overclaiming context-category token attribution;
- building another broad generic query path that regresses focused plans;
- letting live watch create a second competing writer;
- deleting oracle fixtures with the retired implementation; and
- expanding the reset into new feature work before the kernel is qualified.

## 2. Evidence Behind The Decision

The 0.24 foundation audit found coherent accounting and identity ownership but
an overgrown shell. Subsequent installed dogfood changed the product decision:

- the exact index and focused queries repeatedly produced useful results;
- `usage_analyze` could complete with no findings, evidence, or selectors while
  still emitting a declarative summary;
- incremental refreshes over a large cache spent minutes in optional
  derived-state work;
- analysis could start or wait on refresh work that did not improve the
  requested result;
- browser and MCP startup paths created a user perception of repeated rebuilds;
  and
- compatibility preservation kept retired routes, tools, schemas, and
  persistence in the normal development path.

The current source contains approximately:

- 90,500 Python lines under `src/codex_usage_tracker`;
- 52,000 authored TypeScript/TSX lines under the dashboard workspace;
- SQLite schema version 39;
- more than fifty catalogued historical MCP names; and
- dozens of localhost routes spanning active, compatibility, diagnostic,
  investigation, compression, report, and analysis responsibilities.

A 10,000-event synthetic benchmark on the operational evidence branch measured:

| Mode | Parallel cold refresh | Writer lock | Structural/content rows |
| --- | ---: | ---: | --- |
| Normal default | 3.073 s | 3.040 s | turns, tools, commands, fragments, FTS, compression |
| Aggregate-only | 1.742 s | 1.711 s | usage, source, diagnostic, summary, compression |

The default path captured valuable turns and tool calls but coupled them to
content fragments, FTS, and diagnostic materialization. A bounded Scalene
profile found distributed store work rather than one dominant Python parser
hotspot. The first application-owned entries included compression manifest
accumulation, refresh orchestration, content persistence, and deferred index
maintenance. The architectural seam is therefore:

> retain privacy-safe structural activity facts, but remove default content
> indexing and interpretation-specific materialization from ingestion.

All benchmark inputs were synthetic.

## 3. Product Responsibility Boundary

### 3.1 Kernel responsibilities

The kernel answers factual questions:

- what sources and complete lines were observed;
- what thread, turn, model call, tool call, skill, compaction, completion,
  abort, or allowance observation occurred;
- which logical call is canonical;
- how many tokens of each reported class were used;
- what bounded deterministic aggregation follows from those facts;
- what generation and filters produced the result; and
- where the exact supporting evidence can be opened.

### 3.2 Model responsibilities

The consuming model:

- decides which query to run next;
- compares results;
- forms hypotheses;
- explains alternative interpretations;
- recommends workflow changes; and
- asks for explicit content evidence only when aggregate facts are insufficient.

The model must not infer conversation content from token counts or call
something wasteful solely because it is expensive.

### 3.3 Removed responsibility

The server no longer owns a general “tell me why this was wasteful” narrative.
There is no persisted finding catalog, recommendation snapshot, compression
candidate run, usage-drain model, or generic analysis job in the kernel.

## 4. Truth And Coverage Contract

Every measure includes:

- `grade`: `exact`, `deterministic`, or `estimated`;
- `basis`: named source fields or calculation;
- `coverage`: numerator, denominator, and percentage where incomplete;
- `source_generation`;
- `observed_through`;
- `limitations`; and
- a stable evidence selector when row-level evidence exists.

Model-authored text is outside the data payload and is understood to be
`model_inference`.

### 4.1 Four token classes

The primary composition is:

- `uncached_input_tokens`;
- `cached_input_tokens`;
- `reasoning_output_tokens`; and
- `output_tokens`.

The payload must state whether upstream `output_tokens` includes or excludes
reasoning output. Display code cannot imply that overlapping counters add to a
larger total.

### 4.2 Context composition

The source does not currently expose exact billed input tokens by user text,
assistant history, tool output, MCP schema, system instruction, or host-added
context. The kernel may expose:

- exact observed bytes by structural category;
- deterministic observed event counts;
- tokenizer estimates by category;
- observed-content coverage; and
- unattributed input tokens when a safe comparison is possible.

UI and MCP payloads must label category token shares `estimated` unless the
upstream log later supplies exact counters.

### 4.3 Cost, credits, and allowance percentage

Cost and credit estimates include rate-card identity, effective date,
pricing-model match, and coverage. Allowance efficiency may report:

- percentage points consumed per hour;
- locally observed tokens per percentage point;
- locally observed calls or turns per percentage point; and
- reset-aware rolling and weekly trends.

These are ratios between local facts and observed allowance movement. They are
not exact causal billing attribution when outside usage or missing observations
exist.

## 5. Kernel Domain Model

The database is a rebuildable local cache. Public identities derive from source
semantics, not SQLite row numbers.

### 5.1 `sources`

Purpose: discovery, append cursor, replacement detection, and audit.

Required fields:

- stable privacy-safe `source_id`;
- source kind and archive state;
- device/file identity where available;
- current size and modified timestamp;
- parsed byte offset and line number;
- trailing incomplete-line length/hash;
- prefix/replacement fingerprint;
- parser adapter and version;
- first and last observed timestamps;
- last seen generation; and
- parse warnings and unsupported-shape counts.

Full source paths do not appear in the analytical kernel database. Ingestion
keeps the minimum path-to-`source_id` mapping in a separate operational source
registry with owner-only permissions where the platform supports them. That
registry is excluded from MCP, HTTP, evidence, query, export, support-bundle,
and shareable-diagnostic payloads. It is retained only while a source is tracked
and can be reconstructed by explicit source discovery. The kernel stores an
opaque stable source ID and privacy-safe display fields only.

### 5.2 `generations`

Purpose: one immutable committed read boundary.

Required fields:

- monotonic generation;
- source revision digest;
- created timestamp;
- high-water mark set digest;
- inserted, updated, deleted, canonical, and excluded counters;
- latest event timestamp;
- parser version set; and
- integrity status.

### 5.3 `refresh_runs`

Purpose: durable operational progress and recovery without analytical jobs.

Required fields:

- job/run ID and normalized request hash;
- owner/lease identity;
- input and output generation;
- state, stage, heartbeat, and progress;
- planned high-water marks;
- changed source and row counters;
- stage timings;
- bounded terminal error; and
- completed result.

Refresh jobs live in a small operational sidecar or isolated operational tables.
They do not initialize the full analytical schema during status polling.

### 5.4 `threads`

Purpose: one stable Codex task/thread identity.

Required fields:

- logical thread key;
- session identity and source;
- privacy-safe display name and project identity;
- created, updated, and archived timestamps/state;
- parent thread/session;
- subagent type, role, and nickname where observed;
- first/last generation; and
- identity basis and confidence.

### 5.5 `turns`

Purpose: the interval from a user request to terminal completion, abort, or the
latest observed open state.

Required fields:

- stable turn key and source turn ID;
- thread key and ordinal;
- started and ended timestamp;
- `open`, `completed`, `aborted`, or `rolled_back` status;
- start and completion basis;
- basis confidence;
- first/last source offsets;
- model-call, tool-call, skill, compaction, patch, and error counts; and
- first/last generation.

Counts may be queried rather than duplicated if indexed joins meet the budget.

### 5.6 `model_calls`

Purpose: canonical billable usage fact.

Required fields:

- stable physical and logical/canonical identities;
- source, thread, and turn keys;
- event timestamp and within-turn ordinal;
- model, effort, service tier, and origin;
- model context window;
- four token classes plus upstream total/cumulative validation counters;
- rate-limit observation link where present;
- duplicate state, reason, and fingerprint version; and
- source offset and generation.

Ratios such as cache reuse and context pressure are query expressions unless a
measured index requirement justifies a generated column.

### 5.7 `tool_calls`

Purpose: privacy-safe tool activity.

Required fields:

- stable tool-call key and upstream call ID;
- thread, turn, and nearest model-call keys;
- tool, server, namespace, and deterministic tool category;
- start/end timestamps, duration, status, and bounded error category;
- exact serialized output byte size where observed;
- privacy-safe argument shape, not raw arguments;
- source offsets and generation; and
- observation confidence.

Begin/end records are folded idempotently. An unmatched begin remains visible as
incomplete rather than being invented as successful.

### 5.8 `activity_events`

Purpose: small structured lifecycle facts not represented as calls.

Kinds include:

- user request;
- assistant activity/completion;
- skill selected/started/completed;
- context compacted;
- patch completed;
- task completed;
- turn aborted;
- thread rolled back; and
- subagent activity.

Each row has stable identity, thread/turn, timestamp, safe label/category,
source offset, and generation. It stores no prompt, response, reasoning, tool
body, or secret-bearing payload.

### 5.9 `allowance_observations`

Purpose: normalize upstream rate-limit observations without prematurely
materializing forecasts.

Required fields:

- observation identity and timestamp;
- window kind, limit ID, plan type, used percentage, duration, and reset;
- source model/service tier where relevant;
- source call/generation;
- copied-row exclusion state;
- observation provenance; and
- validation warnings.

Cycles, intervals, burn rates, and forecasts are deterministic read models or
generation-keyed caches.

## 6. Database Lifecycle

### 6.1 New cache, not migration 40

The kernel uses a new filename and schema version 1. It does not migrate the
39-version experimental cache in place. The authoritative rebuild input is the
source JSONL plus external pricing/configuration files.

### 6.2 Cutover control state

A small record in the operational sidecar is the only authority for cache
activation. Updates use atomic replace and contain:

- `state`: `absent`, `building`, `ready`, `active`, or `failed`;
- active kernel path, schema, generation, and integrity digest when present;
- staging path and refresh job ID while building or ready;
- prior validated kernel path when one is available for rollback;
- preserved legacy-cache path and version as opaque rollback metadata; and
- last transition, failure, and promotion evidence.

The first build starts only from an explicit CLI `refresh`, MCP
`usage_refresh`, or Console Refresh action. `setup`, install, status, query,
evidence, allowance, service startup, and browser mount never start it.

State behavior is deterministic:

- `absent`: status reports that a first build is required; reads return an
  explicit unavailable/build-required result, never zero totals.
- `building`: status and job state expose bounded progress; reads use an active
  kernel if one exists and otherwise retain the explicit building state.
- `ready`: the staging cache passed integrity and equivalence checks but is
  still invisible to reads.
- `active`: all reads use the named kernel file and generation.
- `failed`: the error and retry action are visible; the active pointer, if any,
  is unchanged.

Promotion atomically replaces the control record only after `ready`. No query
opens a staging path. A failed promotion leaves the prior active pointer
unchanged. An explicit kernel rollback can repoint to a prior validated kernel
file. On the first 0.26 upgrade there is no prior kernel: release rollback means
reinstalling 0.25.1, which can use the preserved schema-39 cache. The 0.26
runtime does not ship a schema-39 reader.

### 6.3 Initial build

1. Create a staging database beside the active cache.
2. Discover sources and capture newline-aligned high-water marks.
3. Parse outside SQLite write transactions.
4. Write bounded batches and checkpoint source cursors.
5. Build only indexes required by approved queries.
6. Re-read source metadata and append complete lines beyond the original
   high-water marks.
7. Repeat catch-up until one bounded quiet checkpoint or configured cap.
8. Run accounting equivalence, integrity, foreign-key, and query-budget gates.
9. Atomically promote the staging database.
10. Preserve the previous cache and promotion evidence.

### 6.4 Incremental refresh

Source discovery selects `no_changes`, `append_safe`, `replace_source`, or
`new_source`. Parsing never occurs while holding the database writer.

The writer:

- takes one lease per database;
- commits small file/row/time-bounded batches;
- advances a generation only after a coherent checkpoint;
- publishes committed changes to the live journal; and
- releases the write transaction before optional work.

There is no compression, recommendation, content-FTS, or narrative-analysis
phase.

### 6.5 Live watch

Live watch is optional host work:

- a single watcher owns source notifications/polling;
- it reads only complete appended lines;
- it uses the same parser and writer as explicit refresh;
- it coalesces bursts into bounded micro-batches;
- it emits generation/journal events after commit; and
- it pauses and reports backpressure rather than growing memory without bound.

The browser receives server-sent events. Reconnect uses `Last-Event-ID` and a
bounded replay window, then falls back to a generation snapshot.

## 7. Query Contract

`usage_query` accepts one request or a bounded `queries` array. All requests in
one call read the same generation.

### 7.1 Datasets

- `calls`
- `turns`
- `threads`
- `tools`
- `activities`
- `phases`
- `allowance`

### 7.2 Operations

- rows/ranking;
- aggregate;
- share/concentration;
- period comparison;
- distribution;
- time series; and
- timeline.

### 7.3 Dimensions

Allowlisted dimensions include:

- time bucket;
- project, thread, turn;
- model, effort, service tier;
- origin and agent role/type;
- tool, server, namespace, category, and status;
- activity or phase category; and
- allowance window/plan.

### 7.4 Measures

Allowlisted measures include:

- each token class and exact total;
- calls, turns, tools, activities, completions, aborts, and compactions;
- duration and output bytes;
- cache reuse, context pressure, and output/reasoning shares;
- estimated cost and credits;
- allowance used percentage and burn rate; and
- locally observed tokens/calls/turns per percentage point.

### 7.5 Query planning

The request is compiled into a named plan, not interpolated SQL. Every response
reports:

- plan ID and version;
- generation;
- normalized scope and filters;
- scanned/returned/matched counts;
- truncation and cursor;
- elapsed server time;
- grade/coverage metadata; and
- evidence selectors.

The planner rejects unsupported cross products and unbounded scans. Existing
focused query behavior is used as an oracle, not automatically reused as code.

## 8. Evidence Contract

Selectors are stable logical identities:

- `thread:<id>`
- `turn:<id>`
- `call:<id>`
- `tool:<id>`
- `allowance:<id>`

`usage_evidence` supports:

- `summary`;
- `timeline`;
- `calls`;
- `tools`;
- `activities`; and
- `allowance`.

It returns bounded structured rows plus one canonical loopback destination.
Thread and turn timelines support `live=true`. Exact deep links survive
database rebuild because selectors derive from logical source identity.

Optional raw/content context is not part of this tool's default surface. A
separate explicit local-content mode may resolve bounded source offsets after
the kernel release.

## 9. Phase Classification

The kernel stores activity, not interpretive phase narratives. A pure,
versioned segmenter may group a turn into:

- `user_input`;
- `planning_reasoning`;
- `discovery`;
- `implementation`;
- `verification`;
- `waiting_external`;
- `delivery`;
- `compaction_recovery`; and
- `unknown`.

Classification uses tool category, command root/category, patch, test/build,
completion, compaction, and timestamp ordering. Each segment includes basis and
confidence. Source activity stays queryable so a changed classifier requires no
fact migration.

Tokens can be assigned to the preceding or enclosing segment
deterministically, but the response labels this phase attribution
`deterministic`, not upstream-exact.

## 10. Evidence Console

### 10.1 Live

The default view renders the committed generation immediately, then subscribes
to changes. It shows:

- current thread and turn state;
- segmented activity timeline;
- four token bands;
- calls/tools/turns and elapsed time;
- reads, writes, searches, patches, and verification activity;
- compaction and context pressure;
- allowance movement; and
- watcher lag and source freshness.

### 10.2 Explore

Explore is a thin query client with:

- guided dataset/measure/dimension discovery;
- bounded tables and charts;
- saved local query specifications;
- comparison presets; and
- direct evidence actions.

It does not host a separate analysis engine.

### 10.3 Evidence

Evidence renders one selector and can enter live mode. The route shape is
versioned and deterministic so MCP responses can open it exactly.

### 10.4 Limits

Limits distinguishes:

- exact observations;
- deterministic reset-aware intervals;
- estimated rate-card/credit calculations; and
- outside-usage or missing-observation limitations.

### 10.5 Settings

Settings owns:

- live watcher state;
- retention and cache paths;
- pricing/rate-card provenance;
- privacy and optional content evidence;
- service lifecycle; and
- database promotion/rollback status.

## 11. Interface Surface

### 11.1 MCP

Exactly six default tools ship after K9. There are no compatibility profiles.
K6 builds and tests this catalog behind an internal development selector while
the public 0.25 composition remains unchanged. K9 activates the catalog and
removes the former one atomically.

### 11.2 HTTP

The new Console API is versioned separately from historical v1/v2 contracts.
Required operations are:

- status/capabilities;
- query;
- evidence;
- allowance;
- refresh start/status; and
- live event stream.

The final route prefix is chosen in Task K6 and then frozen. It may not reuse a
historical schema identifier with changed meaning.

### 11.3 CLI

The retained CLI supports operational workflows. `analyze` and historical
aliases are removed. Export remains because durable machine-readable data is a
core use case.

## 12. Privacy And Security

- The default database contains structured metadata and aggregate counters only.
- Tool arguments, tool output, prompts, assistant text, and reasoning are never
  persisted in the default kernel.
- Safe labels use strict length and character allowlists.
- Paths are hashed or reduced to explicitly safe project/display fields.
- Local HTTP remains loopback-only with origin/request guards.
- SSE contains only data allowed by the same endpoint contract.
- Evidence URLs never contain raw prompt or path material.
- Optional content evidence has a separate database, feature flag, API
  capability, and deletion lifecycle.
- Tests and docs use synthetic fixtures only.

## 13. Deletion Boundary

After the new kernel, adapters, and Console pass cutover gates, delete:

- analysis catalog/strategies/application service and `usage_analyze`;
- Compression Lab domain, persistence, routes, tools, jobs, benchmarks, and UI;
- recommendation-engine persistence and attention-sort dependencies;
- diagnostic snapshots, investigations, workbenches, and report builders not
  used by retained exports;
- usage-drain predictive models;
- any residual OTel/local telemetry ingestion, persistence, routes, or
  diagnostics;
- default content fragment/FTS persistence and content-index refresh;
- generic analysis jobs and results;
- full/developer MCP profiles and compatibility handlers;
- legacy HTTP route families and CLI aliases;
- the old runtime schema migration chain and schema-39 reader, while keeping
  external oracle/downgrade fixtures needed to prove old-file preservation; and
- frontend source, package assets, docs, screenshots, schemas, and tests that
  exist only for those surfaces.

Preserve or transplant:

- token parsing and counter validation;
- stable logical identity and conservative deduplication;
- source cursor/replacement logic;
- privacy-safe tool/activity extraction;
- subagent attachment rules;
- pricing provenance and allowance observations;
- CSV/JSON export semantics selected for the new contract;
- exact evidence-link behavior;
- synthetic oracle fixtures;
- release artifact promotion; and
- package/plugin installation coherence checks.

The old source remains available through Git history and release tags. Runtime
compatibility code is not an archive.

## 14. Performance And Reliability

The roadmap budgets are release blockers. Representative tests include:

- initial build at 100,000 calls;
- no-change refresh;
- one new source;
- small append;
- append-active moving tail;
- replacement/truncation;
- concurrent query during refresh;
- live burst and reconnect;
- 100,000-row focused queries;
- evidence timeline first page and pagination;
- browser reopen against a stale generation;
- watcher/process restart;
- interrupted staging build and promotion rollback; and
- installed plugin two-task smoke.

Performance claims use identical unprofiled workloads. Agent-perf or another
profiler identifies attribution only.

## 15. Packaging And Upgrade

The cutover upgrade:

1. installs the new plugin bundle and schemas coherently;
2. leaves the old cache untouched and records it as opaque downgrade metadata;
3. reports `absent` until the user explicitly runs CLI `refresh`, invokes
   `usage_refresh`, or presses Console Refresh;
4. builds the kernel cache in the background with visible progress;
5. keeps staging invisible and serves an existing active kernel or an explicit
   building state, never a blank false zero;
6. validates and atomically promotes the new cache;
7. records a prior-kernel rollback pointer when one exists; and
8. requires explicit user action before deleting the old cache.

Clean-install, 0.25.1-upgrade, failed-build, failed-promotion, prior-kernel
rollback, and installed-package downgrade paths are release tests. The 0.26
runtime never reads schema 39; a downgrade test proves the preserved cache is
still usable by 0.25.1.

The wheel excludes retired assets and code. Package, Python, frontend, MCP,
route, schema, and database-table budgets ratchet downward from measured output
with at most three percent headroom.

## 16. Rejected Alternatives

### Continue incremental cleanup only

Rejected because optional interpretation systems remain coupled to ingestion and
compatibility remains the dominant development constraint.

### Rewrite everything from a blank repository

Rejected because accounting, deduplication, cursor, privacy, packaging, and
synthetic oracle work are valuable and expensive to relearn.

### Preserve the 39-version database through migrations

Rejected because the database is a rebuildable cache and migration retention
would preserve experimental physical design as product contract.

### Keep `usage_analyze` as a thin model prompt

Rejected because a server-authored narrative is unnecessary. The plugin skill
can teach Codex how to query and distinguish facts from hypotheses.

### Make raw content indexing the default

Rejected for privacy, performance, and product-boundary reasons.

### Add a dedicated live-watch MCP tool

Rejected because evidence timelines and the host sidecar already own live
viewing. A seventh tool would duplicate state and orchestration.

## 17. Open Decisions With Scheduled Owners

These do not block the roadmap reset:

| Decision | Owner task | Default until resolved |
| --- | --- | --- |
| Final kernel database filename | K2 | side-by-side versioned filename |
| Local API route version/prefix | K6 | new version, never semantic reuse |
| SSE replay window and retention | K5 | bounded generation journal |
| Query-cache implementation | K4 | none until a measured query misses budget |
| Content tokenizer/model | K12 | no category token estimate |
| Overlay/DOM transport | K13 | read-only consumer of sidecar contract |

## 18. Success Definition

The reset succeeds when:

- users can reopen the Console and immediately see the existing generation;
- explicit refresh hydrates only new or replaced source data;
- live watch shows a growing run without blocking reads;
- a model can answer broad usage questions with a few exact bounded queries;
- every factual claim can open exact supporting evidence;
- unsupported causal claims remain model hypotheses;
- turns, tools, phases, token classes, and allowance efficiency are cheap to
  explore;
- normal ingestion performs no analysis, content FTS, compression, or
  recommendation work;
- package and code size fall materially;
- old runtime compatibility code is deleted; and
- installed two-task dogfood meets the latency, accuracy, efficiency, and
  restart gates.
