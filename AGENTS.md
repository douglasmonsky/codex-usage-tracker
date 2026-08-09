# Codex Usage Tracker Instructions

## Product and authority

This repository is replacing the released 0.28 spike with a clean, local,
Codex-first workflow-observability kernel. The kernel owns exact facts,
identity, ordering, deduplication, calculations, freshness, coverage,
allowance, valuation, bounded queries, and stable evidence. The consuming
model owns interpretation, hypotheses, prioritization, caveats, and
recommendations.

Start at `docs/INDEX.md`. The only implementation roadmap is
`docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md`; its checkbox ledger is
`docs/roadmap/TASK_PACKETS.md`. The remaining dependency graph, delegation
readiness, ownership locks, and allowed parallelism are controlled by
`docs/roadmap/REMAINING_EXECUTION_PLAN.md`. Each delegable unit has one file
under `docs/roadmap/tasks/`. Archived documents and historical release notes
are evidence, not authority.

CK-07C additionally owns
`docs/architecture/PLAN_OPERAND_AND_FACT_CONTRACT.md` and the versioned
`config/agent-kernel/plan-operand-contract-v1.json`. CK-07D merged the
effective-dated rate-card valuation correction at `e49531b`. CK-07E is the
admitted test-only prerequisite for independent structural and query-only
database-v1 fact adapters. CK-07A consumed CK-07B through CK-07E and is
complete with 80 / 80 structural-v2 variants requalified. CK-08 is complete on
merge with all 21 plans and 42 variants qualified as fact-backed mechanism
evidence. A downstream architecture audit found that the expected-answer lane
shares production evaluation, runtime keyset pagination follows complete
Python materialization, projection classification combines execution stages,
and publication/evidence scale plus replacement maintainability need
corrective proof. CK-08R0 froze `corrective-gates-v1`; CK-08R2 is complete and
CK-09 remains blocked. CK-08R1A froze corrected answer meaning and recursive
closure; R1C is accepted at exact main `fb0c578`, and R1B is accepted at exact
main `9e9332b3`; final R1 requalification is the sole Ready packet.
CK-QG1A removed the two R2 page-executor complexity findings without changing
behavior or the frozen baseline and is accepted at exact main `30983d4`;
existing QG1 PR #392 is Ready to resume from corrected main. CK-07R1A corrected
the exact hosted Python 3.14 lifecycle-tail blocker; the linked CK-07R1A0
authorities, including argv correction, are merged through `479cbdb`. The
existing CK-07R1 worker remains stopped pending coordinator disposition of the
preserved `prelaunch_failed` witness incident and a clean exact-main
reapplication path. PR #394 remains stale failed read-only.
Retained R3 evidence proved the EvidenceService outer query
physically unbounded; CK-08R3A owns that isolated fix and R3 awaits its
accepted, merged, exact-main-verified result.

Advance only child tasks marked Ready in
`docs/roadmap/REMAINING_EXECUTION_PLAN.md`. Parent CK-09 through CK-16 packets
are umbrellas and must never be delegated directly. Do not begin a dependent
task before its prerequisites are merged and exact-main verified. Update the
task status, master ledger, measurements, deviations, and residual risks in
the same change that completes a task.

## Cross-packet semantic continuity

A packet is connected to its prerequisites by executable semantics, not only
by document links, identifiers, hashes, counts, or a prior `Completed` status.
Before a packet may consume an upstream artifact as truth, its contract must
name:

- the producer artifact and exact identity;
- the consumer path that uses it;
- an independent truth source or reference evaluator;
- the executable seam check that compares producer meaning with consumer
  behavior;
- the downstream packets and evidence that require requalification if the seam
  changes.

For fact-backed behavior, preserve a three-way proof: one scenario declaration
emits canonical typed facts, an independent reference evaluator calculates the
expected result for the exact typed request, and the production consumer
calculates the same result from its permitted facts. A database table
containing expected answers, a copied oracle row, internal formula
consistency, or a matching digest does not prove fact lineage.

When a downstream packet exposes an upstream semantic mismatch, stop the
affected packet, record exact reproduction evidence, and add a corrective
packet to the dependency graph. Preserve historical packet evidence; amend it
through a linked requalification record rather than silently changing its
meaning. Do not resume dependents until the corrective packet replays every
affected seam against the actual downstream implementation.

## Packet task handoff

Operate in convergence mode: one durable coordinator, one existing user-owned
task per active child packet, and at most one shared-authority task. A new
user-owned task is justified only for a newly Ready distinct packet, a
genuinely independent parallel lane, or a new policy/contract decision that
cannot be resolved inside the active packet's accepted authority. Reuse the
existing packet task for ordinary implementation defects, tests, environment
setup, validation corrections, review findings, and exact-main reapplication.
Do not split freezing and implementation mechanically.

Follow the machine DAG in `docs/roadmap/REMAINING_EXECUTION_PLAN.md`. After
acceptance, merge, and exact-main verification, the coordinator reconciles the
packet/DAG/ledger and creates only uncreated newly Ready distinct packets.
Fan out only disjoint work, hold joins, and deduplicate packet/frontier.
Blocked, gated, incident-pending, or unverified work creates no successor.

Use bounded subagents inside an active task for focused read-only research,
tests, or one independent review when they materially help. Keep durable
cross-task ownership with the coordinator. Sol at medium reasoning is the
default coordinator profile for collision handling and readiness judgment;
bounded deterministic workers should normally use the less costly Luna profile
at max reasoning, escalating only when ambiguity requires it.

Use `<role> <short-scope>` task names. Every delegation names its parent thread
ID. As its final action on completion, blocking, or fail-closed stop, the task
must proactively message the parent with outcome, exact base/head and
worktree, changed scope, validation, PR/merge/exact-main state, blockers, and
the next authorized action. The parent treats that handoff as a continuation
trigger; it does not create polling or wait-only tasks.

Repository exact-main state and repository-relative artifact paths are the
identity source of truth. The receiving task recomputes hashes from those paths
before acting. Do not relay long hashes, commands, or fixture identities
through multiple task prompts when they can be verified from committed
manifests. Before a one-shot or irreversible operation, run a real
non-consuming integration preflight through the exact entry point and process
boundary, not only a stubbed or in-process proof.

Classify blockers as implementation, authority, environment, or external. An
implementation bug stays in the active packet task. Create a corrective
authority task only when a genuinely new policy or contract decision is
required. Once crash integrity is restored, leave recovery mode and return to
this convergence topology.

## Implementation boundary

- Build the replacement under `src/codex_usage_tracker/agent_kernel/`.
- The 0.28 spike under `src/codex_usage_tracker/kernel/` is a frozen executable
  oracle until CK-14. Do not import it, open or migrate its database, or add new
  MVP behavior to it.
- The replacement database identity is
  `codex-usage-tracker.agent-kernel.v1`; its canonical and operational files
  are separate.
- Do not add compatibility views, migration paths, server-authored narrative
  findings, free-form SQL tools, or generic dashboard framework behavior.
- The active frontend, Console routes, Node toolchain, and browser tests remain
  only to keep 0.28 usable. Do not extend them. CK-14 removes them after CK-13
  approves the qualified replacement.
- Preserve exact-byte release primitives and useful synthetic oracles until
  their owning packet ports or retires them.
- CK-15 is optional and never blocks the MVP unless the maintainer explicitly
  promotes it.

## Domain rules

- Store signed UTC microseconds as integers. Missing is `NULL`, never zero.
- Keep uncached input, cached input, reasoning, and output tokens separate.
- Separate transport tool name, semantic operation, target, invocation intent,
  tool completion, and observed resource mutation.
- Never attribute a state change solely to the immediately preceding call or
  tool; cumulative preceding activity can contribute.
- Preserve every exact allowance observation and its compatibility interval.
- Keep facts canonical and projections current-only. Normal tails update dirty
  keys; they do not copy a generation or rebuild the complete database.
- Query never refreshes. Long work is host-waited; the model never polls.
- Keep result envelopes compact, bounded, capability-aware, and suitable for a
  less-capable model.
- Do not encode qualitative conclusions such as waste, productivity, churn,
  goodness, badness, or skill candidacy in schema fields.

## Data handling

- Use synthetic fixtures only in tests, benchmarks, screenshots, and committed
  examples. Never inspect or commit a contributor's real Codex logs.
- Do not commit prompts, responses, reasoning, command bodies, patches, tool
  output bodies, credentials, secrets, private paths, or local databases.
- The replacement does not promise sanitization, redaction, or secret
  filtering. Local metadata returned by a query can still be sensitive; users
  are responsible for reviewing anything they share.
- Do not copy raw prompt, response, reasoning, command, patch, or tool-output
  bodies into the replacement SQLite database. Extract only the structural
  facts required by an accepted question contract.
- Keep all services local-only. Do not add telemetry or transmit local usage
  data.

## Working method

1. Read the current packet and only its controlling authority documents.
2. Name the observable contract, upstream producer artifact, consumer path,
   independent truth source, and executable seam check.
3. Add or select the failing synthetic oracle.
4. Implement the smallest complete change inside the packet's ownership.
5. Run focused checks, then the smallest complete repository profile covering
   every touched contract.
6. Record correctness, latency, storage, response-byte, MCP-call, and model-token
   measurements required by the packet.
7. Stabilize the diff, then use at most one final read-only reviewer.

Prefer direct functions, explicit data structures, cohesive modules, and clear
dependency direction. Add abstraction only when it removes present
duplication, isolates an external boundary, clarifies ownership, or creates a
test seam required now. Keep mechanical moves separate from behavior changes.
Fix the behavior a gate is meant to protect; if a gate proves no maintainability
or correctness property, adjust the gate rather than churning unrelated code.

Wemake is retired from repository governance. Do not install, run, or restore
it locally or in CI without a new maintainer decision. Do not use
`agent_maintainer verify` as an acceptance gate. Agent Maintainer remains
available for doctor, context, change plans, guidance, and host-side waiting.

## Execution delegation

The maintainer authorizes execution subagents for this roadmap:

- Before spawning a writing agent into a fresh or reused worktree, the root
  integrator runs `python3 scripts/bootstrap_dev_environment.py` from that exact
  root. The command repairs `.venv` from the repository `dev` extra, verifies
  every active PEP 508 requirement, the exact editable worktree source, and the
  declared Scalene pin. It installs integrity-locked GitNexus 1.6.9 under
  `tools/gitnexus/node_modules/` and creates or refreshes that worktree's index.
  It never installs a global or transient GitNexus CLI. It serializes GitNexus
  analysis across worktrees; let the host wait for the command instead of
  assigning model-driven polling.
- On entry, the execution agent runs
  `python3 scripts/bootstrap_dev_environment.py --check` once before tests,
  profiling, or semantic work. The check verifies the GitNexus registry's
  physical worktree, branch, commit, and bounded compare result against
  `origin/main`; a merely "up-to-date" status is insufficient. If a later
  branch transition makes GitNexus stale, rerun the bootstrap in that exact
  worktree. Never install Scalene or another declared dev tool ad hoc with pip.
  Generated `.venv/` and `.gitnexus/` state stays untracked.
- Invoke Python profiling as
  `PATH="$PWD/.venv/bin:$PATH" agent-perf run ...`; agent-perf resolves the
  pinned `scalene` console entry point from `PATH`, not from the workload
  interpreter argument. Keep Python 3.14 test qualification separate from any
  profiling-interpreter compatibility claim.
- Use as many execution agents as materially help, while preserving roadmap
  dependency order and packet boundaries.
- Before concurrent writing begins, name each owner, worktree, immutable base
  SHA, file allowlist, expected artifact, and merge checkpoint. Writers may
  share a checkout only when their file ownership is explicit and
  non-overlapping.
- Coordinate shared contracts, integration order, acceptance, primary
  validation, review accounting, CI, PR/merge operations, and packet/ledger
  accounting across the participating agents.

## Tools

Use `rg` for exact paths, strings, routes, schema fields, and documentation
claims. Use GitNexus first for unfamiliar cross-cutting architecture, execution
flows, or impact. For exact symbols, callers, references, diagnostics, and
edits, use GitNexus with native repository tools such as `rg`, the editor,
type-checker diagnostics, and focused tests. Do not repeat the same lookup
across tools without a concrete uncertainty.

Before editing a function, class, or method, run upstream GitNexus impact and
report any HIGH or CRITICAL blast radius. Before committing, rerun
`python3 scripts/bootstrap_dev_environment.py --component gitnexus --check`,
then run GitNexus `detect_changes` against `origin/main` with the exact physical
root and branch:
`node tools/gitnexus/node_modules/gitnexus/dist/cli/index.js detect_changes --scope compare --base-ref origin/main --repo "$(pwd -P)" --branch "$(git branch --show-current)"`.
Never target the ambiguous repository alias or a potentially stale local
`main` branch.

Use `agent-perf` for every CPU or speed claim. Profile a deterministic synthetic
workload, also run the identical workload without a profiler, and compare one
suspected cause at a time. The kernel performance objectives and early-stop
rules are in the qualification and bakeoff documents.

## Branches, issues, and review

- Do not commit directly to `main`.
- Start each packet from current `main` or the exact merged dependency named by
  the packet, using a focused branch/worktree.
- Use Conventional Commit prefixes and the ordinary branch prefixes
  `feature/`, `fix/`, `docs/`, `chore/`, `test/`, `release/`, or `hotfix/`.
- Keep one packet per PR unless the packet explicitly defines measured commit
  boundaries.
- Never delete a branch or worktree, rewrite history, force-push, publish, tag,
  or change an external account without the required authority.
- Linear is the intended program tracker. `docs/roadmap/LINEAR_BACKLOG.md` is
  the source record, but do not create or update Linear work without explicit
  maintainer direction.
- The delegation policy above is standing maintainer authorization for this
  roadmap. A parallel lane still requires explicit eligibility in the
  controlling roadmap, design document, or packet contract.
- After implementation and primary validation, use at most one comprehensive
  read-only reviewer. Record total findings, accepted findings, reviewer token
  status, and tokens per accepted finding.

## Validation

Run focused tests first. Use the repository-owned profiles:

```bash
just vp  # fast maintained checks
just v   # complete local CI profile
just vc  # release/build candidate profile
```

For documentation-only authority work, at minimum run:

```bash
.venv/bin/python scripts/check_release.py
git diff --check
```

Broaden to `just v` or `just vc` whenever scope, packaging, release,
database/schema, CLI, MCP/plugin/skill, generated assets, or public contracts
change. Never bypass hooks. If project tools are missing from `PATH`, retry once
with `.venv/bin` prepended.

Before completion, inspect `git status`, the diff stat, the stable diff,
relevant checks, and staged files for secrets or private data. A packet is done
only when its acceptance criteria and measurements pass, its checkbox/status
are updated, and every remaining risk or approval gate is named.

## Release safety

Publication occurs only from merged `main` or its exact release tag through the
protected build-once workflow. Do not publish from a local machine. Do not
create or push tags, change package/plugin/public schema identities, or rename
the distribution without explicit maintainer approval. CK-16 owns versioning,
release notes, exact artifact hashes, promotion evidence, and public-install
smoke.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **codex-usage-tracker** (2777 symbols, 5498 relationships, 236 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> Index stale or pinned tool missing? Run `python3 scripts/bootstrap_dev_environment.py` from the exact project root. It uses only the integrity-locked repository-private GitNexus 1.6.9 tool; never use `npx`, `latest`, or a global install.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows. For regression review, use the exact physical worktree, current branch, and remote base `origin/main`; never use an ambiguous repository alias or stale local `main`.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `query({search_query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `context({name: "symbolName"})`.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method without first running `impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit changes without running `detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/codex-usage-tracker/context` | Codebase overview, check index freshness |
| `gitnexus://repo/codex-usage-tracker/clusters` | All functional areas |
| `gitnexus://repo/codex-usage-tracker/processes` | All execution flows |
| `gitnexus://repo/codex-usage-tracker/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
