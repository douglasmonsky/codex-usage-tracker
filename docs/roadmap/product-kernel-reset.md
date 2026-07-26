# Product Kernel Reset

This document is the normative product and release sequence for Codex Usage
Tracker after Release 0.25.1. The approved
[design](../superpowers/specs/2026-07-26-product-kernel-reset-design.md) and
[implementation plan](../superpowers/plans/2026-07-26-product-kernel-reset.md)
define the detailed contracts. Progress is recorded in the
[execution ledger](product-kernel-reset-execution.md).
The approved
[code-quarantine amendment](../superpowers/specs/2026-07-26-kernel-code-quarantine-design.md)
defines how active kernel development physically excludes the retired spike.

The prior MCP-first program is complete historical input, not active authority.
Its [roadmap and evidence](archive/2026-07-21-mcp-first-pivot/README.md) remain
available for accounting, release, migration, and implementation lessons.

## Executive Decision

Codex Usage Tracker will become a lean local observability kernel over Codex
session logs.

The tracker owns:

- exact source discovery and incremental hydration;
- canonical usage accounting and conservative copied-row exclusion;
- normalized thread, turn, model-call, tool-call, skill, lifecycle, and
  allowance facts;
- bounded deterministic calculations and evidence selectors;
- a generation-consistent query engine;
- a local live evidence stream and Evidence Console; and
- explicit calculation grade, coverage, freshness, and provenance.

Codex owns:

- hypothesis formation;
- explanation and synthesis;
- guided follow-up queries;
- recommendations; and
- causal or productivity judgments, only when the available evidence supports
  them.

The tracker will not maintain a server-authored narrative-analysis product while
the factual surface is still evolving. `usage_analyze`, Compression Lab,
recommendation materialization, diagnostic snapshots, usage-drain models, and
their background jobs are scheduled for deletion at the kernel cutover. The
retired local OTel/telemetry ingestion path is not reintroduced.

## Why The Program Reset Is Necessary

Installed dogfood established four product facts:

1. Exact accounting, ranking, concentration, time comparison, model/effort
   breakdowns, allowance observations, and deep links are useful.
2. The automatic diagnostic layer can return unsupported summaries without
   findings, selectors, or evidence.
3. A normal refresh can couple incremental ingestion to content indexing and
   optional derived-state construction while holding the single SQLite writer.
4. Compatibility preservation has kept dozens of tools, routes, schemas,
   migrations, report builders, and frontend workbenches in the development
   path even though this remains a beta product.

The current repository is therefore treated as an executable spike and test
oracle. Its accounting and safety lessons are retained. Its physical schema,
compatibility shell, and interpretation systems are not presumptively retained.

## Product Principles

### Facts below inference

Every value exposed by the kernel has one calculation grade:

| Grade | Meaning | Examples |
| --- | --- | --- |
| `exact` | Directly observed or losslessly normalized from the source | token counters, timestamps, tool name, tool output bytes |
| `deterministic` | Reproducible calculation over exact facts | uncached input, counts, ratios, bounded time comparisons |
| `estimated` | Reproducible approximation with named assumptions and coverage | cost, credits, tokenized tool-output share |
| `model_inference` | Interpretation performed by the consuming model | likely waste, workflow diagnosis, recommended behavior |

No server response may promote an estimate or model inference to an exact fact.

### One append path

Initial hydration, explicit refresh, moving-tail catch-up, and live watch use
one source cursor and normalization path. Reopening the browser never rebuilds
the database. A model query never starts refresh implicitly.

### The host waits; the model does not poll

Long refresh work exposes one durable job and bounded host-side waiting.
Browser live updates use a local server-sent event stream. The model does not
issue short-interval status loops.

### Base facts are durable; interpretations are disposable

Foundational normalized facts survive process restarts. Rankings, summaries,
phase groupings, and report layouts are calculated from the selected generation
or stored only in a generation-keyed disposable cache.

### Beta means removal is allowed

The project will publish a breaking upgrade guide and preserve the old database
file during cutover, but it will not carry runtime adapters for retired beta
tools, routes, schemas, or tables. Git history and archived roadmap evidence are
the compatibility record.

## Target Product Surface

### MCP

The default plugin exposes exactly six tools:

1. `usage_status`
2. `usage_refresh`
3. `usage_query`
4. `usage_evidence`
5. `usage_allowance`
6. `usage_job_status`

`usage_analyze` is removed. No `full` or `developer` compatibility profile is
shipped after cutover.

`usage_query` owns bounded single and batched reads. `usage_evidence` owns exact
thread, turn, model-call, tool-call, and allowance selectors plus canonical
Evidence Console destinations. Live viewing is a property of an evidence
timeline, not a seventh analytical tool.

### Evidence Console

The retained application has five product areas:

- `Live`: current activity, phase segments, token composition, context pressure,
  tool activity, and allowance burn;
- `Explore`: guided bounded queries over calls, turns, threads, tools, phases,
  projects, models, and time;
- `Evidence`: exact thread, turn, call, tool, and allowance timelines;
- `Limits`: allowance observations, consumption rate, reset boundaries, and
  local-attribution coverage; and
- `Settings`: privacy, pricing, watcher, retention, content evidence, and local
  service controls.

“Launch evidence timeline for this thread” resolves one stable selector and
opens the exact loopback route. “Live watch run evidence” opens the same route
with streaming enabled. A later overlay or DOM adapter may consume the same
read-only event stream but does not own ingestion or accounting.

### CLI and HTTP

CLI operations remain for setup, status, explicit refresh, bounded query,
export, service lifecycle, configuration, and repair. The `analyze` command and
legacy aliases are removed at cutover.

The Evidence Console uses one versioned localhost API over the same application
services as MCP. Historical unversioned and v2 compatibility route families are
removed rather than adapted.

## Foundational Data

The new cache begins at kernel schema version 1 and uses a small authoritative
model:

- source files and parser cursors;
- refresh generations and runs;
- threads/tasks;
- turns;
- model calls and four token classes;
- tool calls;
- structured activity events such as skills, compactions, patches, completion,
  abort, and rollback; and
- allowance observations.

Pricing configuration remains external input. Costs and credits are calculated
with explicit rate-card provenance. Raw or tokenized conversation content is
not part of the default database. Optional content evidence uses a separate
database and lifecycle.

The new database is built beside the old cache, catches up source lines appended
during its initial scan, passes equivalence and integrity gates, and is then
atomically promoted. The old cache is retained for rollback until the maintainer
explicitly removes it.

## Core Measurements

The kernel must make these dimensions and measures cheap:

- four token classes: uncached input, cached input, reasoning output, and normal
  output;
- calls, turns, tool calls, skills, compactions, aborts, and completions;
- query-to-completion duration and observed completion basis;
- model calls, tool calls, reads, writes, searches, patches, and tests per turn;
- tokens, duration, and tool-output bytes per thread, task, turn, phase, model,
  effort, tool, project, and time bucket;
- cache reuse, context pressure, output ratios, and subagent fan-out;
- allowance percentage change, burn rate, local tokens per observed percentage
  point, and local calls per observed percentage point; and
- exact source and calculation coverage for every estimate.

The kernel can report exact tool-output bytes. Attribution of billed input
tokens to user text, assistant history, tool output, MCP schemas, or host system
context is estimated unless the source provides exact category counters.

## Release Sequence

| Release | Outcome | Runtime state |
| --- | --- | --- |
| `0.25.x` | Operational bridge and roadmap reset | `main` remains the releasable 0.25.1 line while a non-publishable integration worktree builds the clean kernel. No new analysis feature is added. |
| `0.26.0` | Kernel cutover and live evidence foundation | New schema-v1 database, incremental/live ingestion, exact query engine, six-tool MCP, exact evidence timelines, focused Console, and legacy spike deletion. |
| `0.27.0` | Guided exploration and measured context composition | Batched model-driven exploration, expanded tool/phase/turn metrics, allowance efficiency views, optional content-composition estimates, and overlay adapter contract. |
| `0.28.0` | Feature-free stabilization and contract freeze | Fault injection, upgrade/recovery proof, performance ratchets, installed dogfood, public-contract freeze, and pre-1.0 decision. |

Another patch release may ship for an installed blocker. It must not add a
feature or extend the retired architecture.

## Program Sequence

```text
K0  Archive old roadmap and approve kernel reset
 |
K1  Freeze oracle fixtures and measurable invariants
 |
K1A Quarantine the old tree and create the clean 0.26 integration worktree
 |
K2  Define schema-v1 facts, identities, and privacy contract
 |
K3  Build side-by-side incremental and live ingestion
 |
K4  Build bounded generation-consistent query engine
 |\
 | K5  Build evidence timeline and live event stream
 |/
K6  Build kernel MCP, CLI, and HTTP adapters in the integration tree
 |
K7  Build the focused Evidence Console in the integration tree
 |
K8  Prove allowance and efficiency calculations
 |
K9  Complete the release candidate and prove retired surfaces absent
 |
K10 Build audited release branch, qualify, and publish 0.26.0
 |
K11-K14 Guided exploration, optional estimates, and 0.27.0
 |
K15-K16 Stabilization, contract freeze, and 0.28.0
```

Tasks K1A-K9 may not be combined into one unreviewable rewrite. K1A-K9 use
short-lived branches targeting the temporary `kernel/0.26-integration` branch;
`main` remains the releasable 0.25.1 line. K10 creates the audited
`release/0.26.0` cutover branch that combines current `main` with qualified
integration and opens that branch to `main`.

## Non-Negotiable Gates

### Accounting equivalence

On synthetic and retained anonymized fixtures, the new kernel must match the
approved oracle for:

- physical and canonical call counts;
- copied-row exclusion and canonical promotion;
- token totals by thread, model, effort, service tier, and time;
- subagent parentage;
- source replacement and archive state; and
- allowance observation selection.

Differences require an explicit semantic decision and golden fixture update.

### Active-worktree quarantine

- K1 classifies every path returned by `git ls-files` at its frozen commit as
  `keep`, `transplant`, `retire`, or `historical`, including workflows, root
  metadata, configuration, and agent instructions.
- K1A deletes `retire` and active `transplant` source from the temporary
  integration tree after recording tag provenance, oracle coverage, owner task,
  and target path.
- The detached v0.25.1 reference worktree is read-only and never the default
  code-intelligence project.
- Kernel agents search and edit only the integration worktree and their
  task-specific allowlist.
- Kernel code cannot import a retired, historical, or removed transplant path.
- Each K2-K8 task verifies its assigned transplants and deletes any newly
  obsolete retained leaf immediately.
- `verified` is the only terminal state, with proof required for all four
  dispositions before K9 completes.
- The branch/ref publication guard rejects every integration artifact through
  K9.

### Incremental and live behavior

- No-change refresh performs no usage writes.
- A new source file is append-safe and does not request a full rebuild.
- A growing source parses only complete newly appended lines.
- A replaced or truncated source reconciles only its owned rows.
- Parsing occurs outside the write transaction.
- Write transactions are bounded micro-batches.
- Reads remain available from the last committed generation.
- Initial build records high-water marks and catches up moving tails before
  promotion.
- Browser reopen hydrates the committed generation before any catch-up.

### Performance budgets

On the committed synthetic benchmark:

- warm status: p95 at or below 100 ms;
- common bounded query: p95 at or below 500 ms;
- bounded comparison or concentration query: p95 at or below 1 second;
- evidence timeline first page: p95 at or below 500 ms;
- writer transaction: p95 at or below 50 ms during live watch;
- no-change refresh: p95 at or below 100 ms after source discovery cache
  warm-up; and
- Console meaningful existing-generation render: p95 at or below 1 second.

Every optimization claim requires the identical unprofiled workload. CPU
profiles attribute work but do not prove speedup.

### Privacy

- Synthetic fixtures only in the repository.
- Default normalized facts contain no prompt, assistant, reasoning, raw tool
  argument, raw tool output, shell command body, secret, or full local path.
- Content evidence is separate, local, opt-in, bounded, and never required for
  exact accounting.
- Loopback request guards and explicit raw-context controls remain fail closed.
- Shareable exports identify whether indexed content or raw fragments are
  included.

### Recovery

- The old database is never overwritten during side-by-side qualification.
- Only explicit `refresh`, `usage_refresh`, or Console Refresh actions may
  start the first kernel build.
- Interrupted initial build resumes or restarts without changing the active
  cache.
- An atomic control record names staging, active, and prior validated kernel
  files; queries never read staging.
- The single writer lease is recoverable without marking a live foreign worker
  interrupted.
- Integrity and foreign-key checks pass before promotion.
- Failed promotion leaves the active pointer unchanged.
- Kernel rollback atomically restores a prior validated kernel file. Rollback
  from the first 0.26 cutover to schema 39 means reinstalling 0.25.1 and using
  the preserved old cache; the 0.26 runtime does not read that schema.
- Promotion, kernel rollback, and installed-package downgrade are tested.

## Scope Freeze

Until 0.28.0:

- do not add a server-authored narrative-analysis goal;
- do not add another MCP tool;
- do not add a new default persisted fact table outside the schema-v1 design
  without an approved amendment;
- do not reintroduce a compatibility profile;
- do not reintroduce local OTel/telemetry ingestion;
- do not make optional content indexing part of normal refresh;
- do not build an overlay before the sidecar timeline contract is stable; and
- do not claim exact category-level context tokens when only bytes or tokenizer
  estimates are available.

## Execution

K1 starts from current `main`. It freezes the oracle, retired-surface inventory,
and per-path code disposition. K1A then creates:

- a detached, policy-read-only v0.25.1 reference worktree; and
- the temporary `kernel/0.26-integration` branch and active development
  worktree.

Use one `kernel/<task-id>-<slug>` branch per K1A-K9 task. Start from the latest
integration head, write the named failing contract or benchmark first,
implement only the task contract, and update the
[execution ledger](product-kernel-reset-execution.md) in the same changeset.

The integration branch is explicitly non-publishable and may be
feature-incomplete. `main` continues serving 0.25.1. K9 produces the first
complete kernel release candidate. K10 audits current `main`, creates
`release/0.26.0` from that recorded SHA, incorporates the qualified integration
head once, and opens `release/0.26.0` to `main`.

Every post-K1 tracked-path delta on `main` must be represented in the
disposition manifest. Required blocker behavior is ported through a named
integration-targeting branch with oracle and ledger updates; the legacy line is
never merged into integration. If `main` moves after the K10 audit, cutover
fails closed and restarts against the new head.

Repository-changing tasks with meaningful diffs receive one final independent
read-only review after primary validation. Release, privacy, schema, identity,
and destructive-deletion checkpoints require explicit maintainer approval.
