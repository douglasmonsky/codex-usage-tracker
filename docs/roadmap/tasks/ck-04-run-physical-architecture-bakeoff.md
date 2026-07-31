# CK-04 — Run A/C/D physical bake-off and decide

**Status:** Completed with an explicit growth-evidence exception
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement bounded Candidates A, C, and D and select one physical
architecture through measured gates.

**Why:** The pivotal schema choice must be evidence-driven before production
code creates migration pressure.

**Controls:** `PHYSICAL_ARCHITECTURE_BAKEOFF.md`, CK-02/CK-03.
**Dependencies:** CK-03.

**Scope and expected files:**

- `experiments/physical-architecture/shared/**`;
- `candidate_a/**`, `candidate_c/**`, `candidate_d/**`;
- benchmark output schemas and ignored raw measurement directory;
- `docs/decisions/PHYSICAL_ARCHITECTURE_DECISION.md`;
- pinned DBHub v0.24.0 disposable research config;
- agent-perf workload definition.

**Schema/API changes:** Experimental DDL only; decision freezes selected
production table/index/projection shape.
**Non-goals:** Production imports, plugin/CLI, generic DBHub product access,
Semantic Kernel.

**Invariants:** Identical logical records/oracles/queries/evidence; no candidate
omits a slice or changes grades; failures stop early; prior valid publication
survives injected crashes.

**Tests/benchmarks:** Complete workload matrix, scales/history ranges,
parallel-worker experiments, query plans, storage/WAL/pages, crash matrix,
two-route local DBHub comparison, repeated unprofiled timings, agent-perf
attribution. Installed-model operability is deferred to CK-11.

**Acceptance:** At least one candidate passes every hard gate; selection score
and sensitivity analysis are reproducible; decision names exact tables,
indexes, sequence authority, lifecycle storage, publication mechanism,
projections, rejected alternatives, risks, and follow-ups.

**Failure/rollback:** If none passes, publish a failed decision artifact naming
the smallest contract-preserving experiment to rerun. Do not start CK-05 or
choose Candidate C by preference.

**Cleanup/docs:** Experimental code remains isolated or is removed after
decision; no production copy/paste without a clean implementation packet.

**Parallelism:** A/C/D directories are disjoint and parallel-eligible after the
shared harness is frozen. One integrator owns shared files and scoring.

**Suggested commits:**

1. `test: freeze physical architecture bakeoff harness`
2. `perf: implement candidate a`
3. `perf: implement candidate c`
4. `perf: implement candidate d`
5. `docs: select agent-kernel physical architecture`

## Execution record

**Status:** Completed with an explicit growth-evidence exception
**Selected direction:** Candidate A mechanisms
**Decision:** [PHYSICAL_ARCHITECTURE_DECISION.md](../../decisions/PHYSICAL_ARCHITECTURE_DECISION.md)
**Production schema contract:** [AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md](../../architecture/AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md)

The final read-only review identified seven accepted gaps in the first
qualification pass. Candidate A now has real crash/recovery execution,
database-derived query answers, per-case planner eligibility gates, real
1/2/4/8-worker parsing, an exact Agent Perf standard-build workload, a complete
production database-v1 contract, and a strict canonical decision-evidence
validator.

The current evidence commit
`95492032373beeaa700af90b542a0a07f4220c74` passed the standard,
production/history, ordinary-tail, 69-query, 25-case recovery, DBHub, Agent
Perf, and current Candidate C/D elimination lanes. After three successful
current-commit growth samples, the maintainer directed the run to stop after
repetition 2 and waived repetitions 3 and 4.

The committed
[growth-evidence exception](../../decisions/evidence/ck04/aggregate-evidence.json)
records that limitation, authenticates the partial current bundle, and links a
prior complete five-run bundle whose Candidate A and shared Git trees are
identical. The strict canonical v2 aggregate was not emitted and is not claimed
to have passed.

The CK-04 DBHub benchmark is deterministic and local: five samples each
deliberately execute the `generic` and `named_preset` routes in alternating
global order. It does not ask a model to select a route, and the current runner
invokes no model. Exact model identity, host/runtime versions, reasoning effort,
synthetic-prompt artifact identity/hash, token source, and authorization for
billed calls were never frozen; CK-11 owns that installed-model operability
record.

CK-08 later established that Candidate A's “database-derived” query proof read
`question_cases.observed_facts_json`, populated from `oracle_case` grading
records. The physical measurements, recovery evidence, selected database-v1
shape, and growth waiver remain historical evidence, but that query proof does
not establish canonical-fact lineage. Corrective packet
[CK-07A](ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md) must
replace and requalify it before CK-08 resumes.

## Cross-task execution handoff

**Recorded:** 2026-07-29, America/New_York

**Authority:** Historical operational checkpoint, superseded by the completed
execution record above. It is retained to explain the implementation and
review provenance; the packet and its controlling documents decide behavior.

### Goal

The continuing task must create and retain this full goal:

> Implement the full Codex Usage Tracker Agent-First Clean-Cutover Roadmap
> (CK-00 through CK-16, with CK-15 remaining optional unless explicitly
> admitted), completing each packet's acceptance criteria, qualification
> gates, review accounting, clean cutover, and release.

Do not start CK-05 before CK-04 is merged, and do not mark the goal complete
until the entire roadmap is proven complete.

### Integration worktree

- Repository: `https://github.com/douglasmonsky/codex-usage-tracker`
- Worktree basename: `codex-usage-tracker-ck04-harness`
- Branch: `perf/ck04-bakeoff-harness`
- Baseline HEAD before this handoff commit:
  `336bb48071de82ec07e367157ea12f88f7736dd8`
- Resume HEAD: the current branch HEAD containing this handoff
- Recorded `origin/main`:
  `b928f78512b4378c4b5192385d0eccdde9bd1f2a`
- Root status: clean before this documentation update
- Remote state: CK-04 has not been pushed, opened as a PR, or merged

Exact contributor-local paths belong only in the ignored
`.codex/CK04_RESUME.md` file and the private task handoff. Use the physical
worktree path for GitNexus identity. Do not delete historical worktrees or
branches. Do not run `git clean`: two paused lanes contain deliberate
untracked fail-first tests.

Read `AGENTS.md`, `docs/INDEX.md`, this packet, the bakeoff authority, the
decision, and the database-v1 schema contract before resuming.

### Execution policy

- The user disabled Serena. Do not use or restore it. Root `AGENTS.md` now
  uses GitNexus plus `rg`, editor diagnostics, type diagnostics, and focused
  tests.
- Assign each implementation task to a dedicated execution subagent.
- Run only explicitly disjoint, dependency-safe lanes in parallel.
- Give every writing agent a dedicated worktree, branch, immutable base, exact
  file allowlist, expected artifact, and merge checkpoint.
- Before spawning a writer, root runs
  `python3 scripts/bootstrap_dev_environment.py` in that worktree. The agent
  runs it once with `--check`.
- Use only repository-private GitNexus 1.6.9. Run impact before existing-symbol
  edits and exact `detect_changes` against `origin/main` before commits.
- Use synthetic fixtures only. Never inspect or commit real Codex logs or raw
  prompts, responses, reasoning, commands, patches, or tool-output bodies.
- Query never refreshes. Long work is host-waited; the model never polls.

### Integrated commits

| Commit | Purpose |
| --- | --- |
| `1b2f009` | Harden Candidate A production tails. |
| `5a34ab9` | Classify tail-hardening tests. |
| `b8676ac` | Prove Candidate A eligibility gates. |
| `00da27a` | Harden qualification evidence. |
| `bd50e81` | Freeze the multi-producer-ready schema seam. |
| `bb98070` | Retain real Candidate A crash execution evidence. |
| `ae85dda` | Make DBHub and aggregate evidence contracts truthful. |
| `336bb48` | Remove Serena workflow guidance. |

The multi-producer work is a schema seam only: opaque producer identity,
stable source/file lineage, producer-local clocks, publication coverage,
copy-stable semantic identities, and source-keyed dirty hints. It adds no
remote collector, service, authentication, or multi-machine runtime.

Candidate A is selected as the CK-05 design and contract reference. CK-05 must
implement it cleanly under `src/codex_usage_tracker/agent_kernel/`; it must not
copy or import experimental Candidate A or the frozen spike runtime.

Completed checks include:

- root combined contract suite: **211 passed in 35.95 seconds**;
- crash lane: 48 recovery/runner plus 23 Candidate A tests, Ruff, Pyright,
  focused Mypy, release, diff, and secret checks;
- DBHub contract lane: 163 focused tests, Ruff, compile, release, diff,
  allowlist, and secret checks;
- database-v1 seam: two focused schema tests, Ruff, and release checks;
- Serena guidance removal: release and diff checks.

The one allowed final CK-04 reviewer was already used: seven findings, seven
accepted, token accounting pending. Do not spawn another CK-04 reviewer.

### Paused DBHub runner

- Worktree basename: `codex-usage-tracker-ck04-dbhub-runner`
- Branch: `test/ck04-dbhub-runner`
- HEAD: `ae85dda3958a304335ea8c00302c8e7d46cfd8e8`
- Commit/push: none
- Untracked red test:
  `tests/experiments/physical-architecture/test_dbhub_runner.py`
- Ignored resume file: `.codex/CK04_DBHUB_RUNNER_RESUME.md`
- Expected failure: `ModuleNotFoundError: shared.dbhub_runner`
- Blocker: none

Verified before pause: live npm integrity for
`@bytebase/dbhub@0.24.0` matched the pin, and a disposable stdio probe
completed MCP initialize, `tools/list`, and `top_sessions`.

Next: implement `shared/dbhub_runner.py` against the red tests, add the CLI and
direct `psutil==7.2.2` dev pin, run a bounded standard synthetic smoke, and
commit. Keep one process and alternate sequence indexes `0..9`:

- `generic` → `search_objects+execute_sql`, two MCP calls;
- `named_preset` → `top_sessions`, one MCP call.

Measure wall time, process-tree CPU, response bytes, row count, and result
hash. Keep scan/statement counts explicitly unavailable when DBHub does not
report them. Require identical 25-row results and an unchanged snapshot.

### Paused Agent Perf runner

- Worktree basename: `codex-usage-tracker-ck04-agent-perf-evidence`
- Branch: `test/ck04-agent-perf-evidence`
- HEAD: `ae85dda3958a304335ea8c00302c8e7d46cfd8e8`
- Commit/push: none
- Untracked red test:
  `tests/experiments/physical-architecture/test_agent_perf_evidence.py`
- Ignored resume file: `.codex/CK04_AGENT_PERF_RUNNER_RESUME.md`
- Expected failure: `ModuleNotFoundError: shared.agent_perf_runner`
- Blocker: none

Next: implement `shared/agent_perf_runner.py`, add the CLI, and run the real
standard synthetic collection. Validate the checked-in workload, run the exact
command five times unprofiled in distinct roots, capture wall/process-tree CPU
and exact result identity, require all results to agree, then profile the
identical command once with `agent-perf run --runtime python`. The profile is
attribution only, never a speed sample.

Do not use `agent-perf detect`; it has no runtime selector and rejects this
mixed Python/Node repository as ambiguous.

### Paused qualification suite

- Worktree basename: `codex-usage-tracker-ck04-qualification-suite`
- Branch: `test/ck04-qualification-suite`
- HEAD: `ae85dda3958a304335ea8c00302c8e7d46cfd8e8`
- Tracked status: clean
- Commit/push: none
- Ignored resume file: `.codex/CK04_QUALIFICATION_SUITE_RESUME.md`
- Blocker: none

Next: add fail-first group/watchdog tests, then the bounded outer
orchestrator. Preserve the workload matrix digest. Existing elapsed gates stay
success gates; other finite watchdogs are operational censored-abort ceilings.
Timeouts must terminate, reap, preserve canonical partial evidence, and never
be passed or averaged away.

The three paused branches predate only the documentation commit `336bb48`.
Honor the no-Serena instruction without editing their `AGENTS.md`; their
implementation commits should cherry-pick cleanly.

### Historical integration sequence

1. Run full bootstrap in each reused worktree, then spawn one writer per lane.
2. Resume the three lanes above in parallel using their ignored resume files.
3. Inspect and cherry-pick each clean commit into the integration worktree.
4. Run the combined focused suite and refresh root GitNexus.
5. Freeze the missing seven-dimension score-input extraction formulas. Do not
   copy arbitrary test-helper values.
6. Produce current-commit C/D elimination artifacts: C must prove the required
   process-termination observation failed; D must prove production build time
   exceeded five seconds.
7. Implement the aggregate evidence builder.
8. Run final qualification, write canonical v2 evidence, complete the
   decision/packet/ledger, and run `just vc`.
9. Push, open the PR, monitor green CI, and merge CK-04.
10. Create a clean CK-05 Codex task from the verified merged dependency.

Steps 1–7 were completed. Step 8 completed all qualification lanes except the
two maintainer-waived growth repetitions, so the strict canonical v2 aggregate
was replaced by the explicit exception artifact rather than weakened or
misrepresented. Steps 9–10 are the closeout actions owned by this task.

### Aggregate evidence contract

The later lane should own only:

- new `experiments/physical-architecture/aggregate_decision_evidence.py`;
- new `tests/experiments/physical-architecture/test_aggregate_decision_evidence.py`;
- optional usage-only experiment README update.

It accepts explicit immutable fixture, qualification, Agent Perf, DBHub, and
C/D artifact paths. Local paths never enter evidence. Authenticate canonical
encoding, invocation/measurement/detail/summary digest chains, commit,
fixture, environment, matrix, counts, and completion before deriving rows.

For queries, derive one row per exact case from five repetitions, using maxima
for plan counters/response bytes and nearest-rank p95 latency. For crashes,
copy authenticated real process/recovery evidence; injected faults project
`{"status":"not_applicable"}` only for the process while retaining real
recovery hashes and stage/action.

Do not invent selection scores, C/D results, DBHub telemetry/model facts,
Agent Perf telemetry, decision date, or destination. Use a new no-overwrite
aggregate directory, write `COMPLETE` last, invoke the existing writer without
`--replace`, then independently validate the SHA.

### Tooling caveats

- Root GitNexus is stale relative to `336bb48`; run full bootstrap first.
- One incremental GitNexus refresh hit a corrupt generated FTS index. Cleaning
  only that worktree's `.gitnexus` index and running full bootstrap recovered
  it without touching source or Git history. Automatic recovery is not yet
  implemented.
- `scalene==2.3.0` is a direct dev dependency. `psutil==7.2.2` currently
  arrives transitively; the DBHub lane owns making it direct.
- Standard Mypy can encounter a NumPy stub using Python 3.12 syntax against
  the repository's Python 3.10 target. Do not weaken the final type gate;
  diagnose it if the complete profile fails.

Stop instead of guessing if a worktree has unexpected changes, `origin/main`
changes the dependency, result identities differ, a sample is profiled or
shares output state, C/D evidence is absent, score formulas remain undefined,
a watchdog expires, or any test would require real user data.

## CK-07A requalification

CK-07A replaced the invalid `question_cases` correctness lane with 80 / 80
fact-backed structural-v2 comparisons through Candidate A's permitted
database-v1 fact/planner path. Query sources/plans, response bytes, timings,
eligible-only score `100`, rank 1, and standard/production/growth sensitivity
are recorded in the
[canonical CK-07A evidence](../../decisions/evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json).
Candidate C/D remain eliminated before scoring; no score is fabricated. Growth
repetitions 3 and 4 remain waived and the strict five-repetition aggregate is
not claimed.
