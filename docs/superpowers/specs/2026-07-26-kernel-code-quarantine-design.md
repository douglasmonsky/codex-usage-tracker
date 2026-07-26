# Kernel Code Quarantine And Progressive Deletion Design

**Date:** 2026-07-26
**Status:** Approved Product Kernel Reset amendment
**Applies to:** K1, K1A, K2-K10
**Parent roadmap:** `docs/roadmap/product-kernel-reset.md`
**Parent design:**
`docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md`
**Implementation plan:**
`docs/superpowers/plans/2026-07-26-product-kernel-reset.md`

## 1. Decision

Kernel development will not carry the entire 0.25 runtime in its active
worktree until the final cutover.

After K1 freezes accounting behavior and classifies the repository, K1A creates
a temporary, non-publishable `kernel/0.26-integration` branch and worktree. In
that worktree:

- code classified `retire` is deleted immediately;
- code classified `transplant` is removed from the active tree after its exact
  v0.25.1 source reference and owning kernel task are recorded;
- code classified `historical` remains only in approved archives, oracle
  fixtures, or the detached v0.25.1 reference worktree; and
- only code classified `keep` plus the new kernel skeleton remains available to
  normal agent search and code intelligence.

Short-lived K2-K9 task branches start from and merge back into the temporary
integration branch. K10 combines the qualified integration head with audited
current `main` on `release/0.26.0` and opens that release branch to `main`. The
integration branch is never published.

This is a clean transplant from a tagged executable spike, not a blank rewrite
and not a legacy compatibility migration.

## 2. Why Quarantine Is Necessary

A late K9-only deletion would preserve release safety but leave more than
140,000 authored Python and TypeScript/TSX lines in the active development
tree. Agents could:

- follow retired analysis, compression, recommendation, diagnostic, content,
  route, or compatibility patterns;
- modify an obsolete owner instead of the kernel owner;
- expand context with irrelevant tests, assets, schemas, and migrations;
- create new dependencies on code already scheduled for deletion; and
- spend review time separating intended transplant work from accidental legacy
  preservation.

Documentation labels alone do not remove those failure modes. The active kernel
worktree must be physically smaller and machine-enforced.

## 3. Workspace And Branch Topology

### 3.1 Releasable line

`main` remains the releasable 0.25.1 line until K10. It may receive only scoped
0.25 blocker fixes, documentation, oracle fixtures, and release-safety work.

The public `v0.25.1` tag remains the immutable runtime source for:

- transplant provenance;
- behavior comparison;
- old-package downgrade smoke; and
- historical implementation inspection.

No Product Kernel Reset task rewrites that tag or deletes its existing
worktrees or branches.

### 3.2 Read-only reference worktree

K1A creates one detached worktree at `v0.25.1`, conventionally named
`codex-usage-tracker-v025-reference`. It is policy-read-only:

- no edits, commits, generated assets, environments, or databases;
- no activation as the default Serena/IntelliJ project;
- no GitNexus refresh from that worktree;
- no test or benchmark output written into it; and
- no deletion without explicit maintainer permission.

Agents inspect one named source path only when the owning task identifies an
approved `transplant` entry. Prefer `git show v0.25.1:<path>` for a bounded
read.

### 3.3 Temporary integration worktree

K1A creates `kernel/0.26-integration` from the K1 commit and a corresponding
worktree conventionally named `codex-usage-tracker-026-integration`.

This is the only approved temporary integration branch. It is an explicit
exception to the repository's no-long-lived-development-branch rule because it:

- prevents an incomplete kernel from replacing releasable `main`;
- lets the active agent workspace delete retired source early;
- receives only approved K1A-K9 task branches;
- is never tagged, published, or installed as a public release;
- records every merge and gate in the execution ledger; and
- is removed only after K10 and only with explicit maintainer permission.

K1A-K9 use short-lived branches named `kernel/<task-id>-<slug>` based on the
latest integration head. Their PR base is `kernel/0.26-integration`. K10 opens
`release/0.26.0` from an audited current-`main` SHA, incorporates the qualified
integration head once, and opens the final PR from `release/0.26.0` to `main`.
If `main` moves after that audit, K10 fails closed and restarts against the new
head rather than improvising an unclassified merge.

### 3.4 Main-line blocker fixes

If a 0.25 blocker lands on `main` after K1, the next integration task first
diffs the frozen K1 main SHA against current `main`. Every added, modified,
renamed, or deleted tracked path must already have a disposition entry or makes
the gate fail.

A required port uses a short-lived
`kernel/k<owner>-mainline-port-<issue>` branch based on and targeting
`kernel/0.26-integration`. That branch must:

1. amend the code-disposition manifest with the current-main source SHA, owner,
   oracle, target, and superseded K1 entry;
2. amend the retired-surface manifest when a public surface changed;
3. add or update the synthetic oracle before porting code;
4. port only behavior required by a kernel oracle or a `keep`/`transplant`
   entry;
5. rerun every affected phase gate; and
6. record the source commit, classification decision, and verification in the
   execution ledger.

The integration branch never merges the complete legacy main line. K10 repeats
the delta audit before creating the release branch. An unrepresented path
blocks cutover. No history rewrite, force push, or silent divergence repair is
allowed.

## 4. Machine-Readable Code Disposition

K1 creates `config/kernel-code-disposition-v1.json`. Its resolver input is
exactly every path returned by `git ls-files` at the frozen K1 commit,
including workflows, root package/release metadata, configuration, agent
instructions, runtime, frontend, tests, scripts, schemas, package assets, and
product documentation. Every tracked path resolves to exactly one entry.
Untracked/build output is outside the manifest only when Git already ignores
it and the worktree-clean gate proves it is not release input. Ordered glob
rules are permitted only when the resolver emits a deterministic per-file
inventory and rejects overlaps or explicit exclusions.

Each resolved entry contains:

- `path`;
- `disposition`: `keep`, `transplant`, `retire`, or `historical`;
- `reason`;
- `owner_task`;
- `source_ref`, normally `v0.25.1:<path>`;
- `target_path` or `none`;
- `public_surfaces`;
- `required_oracle_tests`;
- `removal_or_absence_test`; and
- `status`: `classified`, `removed`, `archived`, `implemented`, or `verified`.

### 4.1 `keep`

The file remains in the integration tree and final product because it already
fits the kernel contract. Examples may include release promotion, bounded
pricing configuration, safe parser primitives, or packaging infrastructure.

`keep` is not a blanket exemption. It requires a named final owner and test.

### 4.2 `transplant`

The behavior is valuable but its current module ownership or dependencies are
not. K1A removes the source file from the integration tree after recording:

- exact tag/path/commit provenance;
- the owning K2-K8 task;
- the oracle behavior that must survive; and
- the intended clean target module.

The owning task reads the bounded tagged source, implements the target contract,
and changes the entry from `removed` to `implemented` and then `verified`.
Copying an entire old module without dependency review is not a transplant.

### 4.3 `retire`

The behavior and implementation leave the product. K1A deletes the source,
tests, assets, schemas, documentation, and package data from the integration
tree. The retired-surface manifest records any user-facing removal.

No later task may reintroduce its symbol, route, schema, table, asset, or
dependency without an approved roadmap amendment.

### 4.4 `historical`

The file has evidence value but no runtime authority. It may remain only under
an approved archive/fixture path or the tagged reference worktree. Historical
code cannot be imported, packaged, indexed as active architecture, or used as a
compatibility layer.

### 4.5 Disposition state machine

`verified` is the only terminal status for every disposition:

| Disposition | Allowed transition | Terminal proof |
| --- | --- | --- |
| `keep` | `classified` -> `verified` | path remains, final owner is named, and required tests pass |
| `transplant` | `classified` -> `removed` -> `implemented` -> `verified` | old path is absent and clean target passes its oracle |
| `retire` | `classified` -> `removed` -> `verified` | path and public surface are absent and named absence test passes |
| `historical` | `classified` -> `removed` or `archived` -> `verified` | path is absent or confined to an approved non-importable, non-packaged archive/fixture |

The resolver rejects skipped transitions, a terminal entry whose proof is
missing, and any status invalid for its disposition. K1A advances entries only
to `removed` or `archived`; K2-K8 verify owned entries; K9 requires every
manifest entry to be `verified`.

## 5. K1A Quarantine Operation

K1A performs one reviewable quarantine commit on its task branch:

1. Verify the K1 accounting oracle, retired-surface manifest, and code
   disposition are complete and deterministic.
2. Create the detached v0.25.1 reference worktree and temporary integration
   worktree.
3. Set integration-only package identity to an unpublished 0.26 development
   version and add a branch/ref publication guard that rejects integration and
   every K1A-K9 task ref. The guard remains active through K9; only K10 may set
   the final version on `release/0.26.0`, and publication still requires the
   protected workflow from merged `main`.
4. Create the minimal `src/codex_usage_tracker/kernel/` package skeleton,
   kernel-local instructions, phased CI gates, and scope checker.
5. Retain all `keep` paths.
6. Delete all `retire` paths.
7. Delete active copies of all `transplant` paths after provenance and owner
   validation.
8. Move approved historical documentation or fixtures into their named archive
   locations; delete other historical runtime copies.
9. Regenerate package manifests and dependency graphs from the remaining tree.
10. Prove the active integration worktree contains no unclassified or
    forbidden path.

The K1A integration branch is expected to be feature-incomplete. It must never
masquerade as a working 0.25 or publishable 0.26 package.

## 6. Agent Scope Enforcement

K1A creates `docs/kernel-development-scope.md` and a more specific
`src/codex_usage_tracker/kernel/AGENTS.md`.

For K2-K9:

- activate only the integration task worktree in Serena/IntelliJ;
- refresh GitNexus only for the integration worktree;
- begin searches in `src/codex_usage_tracker/kernel`, `tests/kernel`, and the
  task's explicit allowlist;
- do not search the v0.25.1 reference broadly;
- do not import from a path absent from the integration tree;
- do not add compatibility shims, re-export packages, or legacy namespaces;
- use the disposition entry and oracle test before reading tagged source; and
- record every transplanted source path and rejected dependency in the ledger.

Machine gates enforce:

- complete and single-valued path classification;
- no `kernel` import of a retired, historical, or removed transplant path;
- no forbidden public names, routes, schemas, tables, or package assets;
- no unapproved source path outside the task change plan;
- branch/ref publication guard remains active and rejects every integration
  artifact through K9;
- no raw private fixture or local database data; and
- bounded source, package, schema, route, table, and bundle inventories.

## 7. Progressive Transplant And Deletion

K2-K8 no longer wait for K9 to clean their area.

Every task:

1. selects only its assigned `transplant` entries;
2. adds a failing target contract based on the oracle, not current module shape;
3. reads the smallest tagged source slice needed;
4. implements the clean kernel owner without importing old dependencies;
5. marks each disposition entry `implemented`;
6. passes equivalence, privacy, architecture, and task performance gates;
7. marks each entry `verified`; and
8. deletes any newly obsolete `keep` path in the same task after an explicit
   manifest reclassification.

A task cannot complete with an unowned compatibility adapter or a newly
discovered old dependency. It must classify the dependency, amend the plan if
needed, or stop.

## 8. Phase-Specific CI

The integration branch uses explicit phases:

| Phase | Blocking gates |
| --- | --- |
| K1A skeleton | manifests, classification, forbidden inventory, import graph, package metadata, build isolation, privacy, docs |
| K2 schema | K1A plus schema, identity, integrity, source registry, cutover control |
| K3 ingestion | K2 plus oracle ingestion, source lifecycle, concurrency, writer budgets |
| K4-K5 query/evidence | K3 plus focused query, phase, selector, timeline, SSE budgets |
| K6-K8 interfaces/Console/allowance | prior gates plus isolated package, MCP, HTTP, CLI, frontend, browser, allowance |
| K9 release candidate | complete full suite, exact retired-surface absence, deterministic assets, package budgets, installed smoke |

Removed 0.25 tests do not remain as permanently failing compatibility tests.
Their valuable assertions become oracle or target-contract tests before
deletion. CI configuration names the current phase and rejects advancing it
without the preceding phase's evidence.

## 9. K9 And K10 Responsibilities

K9 is no longer the first bulk cleanup. It:

- requires every `keep`, `transplant`, `retire`, and `historical` entry to be
  `verified` with its disposition-specific proof;
- verifies the tracked-path inventory still matches the manifest;
- removes temporary integration selectors and disposable phase-only
  scaffolding while retaining the branch/ref publication guard;
- activates the six-tool package/plugin/HTTP/CLI/Console composition;
- ratchets final source, package, route, schema, table, and bundle budgets; and
- produces the first complete 0.26 release candidate with a development version
  that remains unpublishable from integration.

K10:

- repeats the current-main delta audit and blocks on every unrepresented path;
- completes any required mainline port through the integration workflow and
  reruns affected K9 gates;
- creates `release/0.26.0` from the audited current-`main` SHA and incorporates
  the qualified integration head once;
- resolves only classified conflicts and sets the final version on the release
  branch;
- runs the complete qualification and upgrade/rollback matrix;
- opens the `release/0.26.0`-to-`main` PR and fails closed if `main` moves;
- preserves the v0.25.1 tag and old database rollback path;
- publishes only from merged `main` through protected release gates; and
- records the integration branch/worktree disposition without deleting either
  unless the maintainer explicitly authorizes it.

## 10. Acceptance Criteria

The quarantine amendment is successful when:

- normal K2-K9 agent search cannot see retired 0.25 runtime code;
- every tracked K1 path and every reviewed post-K1 main delta is classified
  exactly once;
- every disposition entry reaches `verified` through its allowed transition;
- every transplant has a tag reference, owner task, target path, and oracle;
- no kernel module imports an old runtime module;
- K1A removes retired and transplant source from the integration tree;
- main remains the releasable 0.25.1 line until K10;
- the branch/ref publication guard rejects every integration artifact through
  K9;
- task-specific CI remains useful while the kernel is incomplete;
- K9 has no giant first-time deletion surprise;
- K10 uses one audited `release/0.26.0`-to-`main` topology; and
- 0.26 ships no legacy runtime, compatibility profile, or schema-39 reader.
