# R1 — Freeze Agent Outcome And Performance Baselines

## Objective

Make the installed fresh-task agent outcome the primary product benchmark.
Freeze deterministic workloads, prompts, timing boundaries, usefulness rubric,
and production-shaped storage/build evidence before optimization.

## Depends On

R0.

## Owned Areas

- recovery benchmark configuration under `config/`
- synthetic workload generators and benchmark runners under `scripts/`
- agent-outcome and performance tests under `tests/kernel/` and `tests/e2e/`
- plugin/skill coherence smoke support
- R1 execution-ledger entry

R1 does not edit kernel behavior.

## Contract Added First

Add a benchmark contract that fails until it can:

1. identify one candidate wheel, plugin manifest, MCP server, skill, cached
   bundle, version, and source revision;
2. generate deterministic small-CI and production-shaped synthetic histories;
3. run the fixed prompt suite from genuinely fresh tasks in every advertised
   supported local host, including Codex CLI and Codex Desktop;
4. emit a bounded machine-readable scorecard without prompt or response text.

Record host name, host version or build, launch method, and candidate
registration. Background-created or generic orchestration tasks do not count as
fresh local-host qualification.

## Fixed Prompt Suite

- List my top threads by usage.
- What drove my usage this week?
- Compare this week with the previous week.
- Which models and reasoning efforts cost the most?
- Show my four token classes.
- How quickly is my allowance draining?
- Which tools added the most context?
- Open the evidence timeline for this thread.
- Show the most expensive calls in this thread.
- What changed after the latest incremental refresh?

Store prompt IDs and expected intent, not private transcripts.

## Scenarios

- no index;
- compatible warm committed generation;
- no-change refresh;
- small append-safe tail;
- larger bounded tail;
- JSONL appended while refresh runs;
- refresh already in progress;
- browser close and reopen;
- package/plugin upgrade;
- fresh Codex CLI and Codex Desktop tasks after install, where supported;
- current task with intentionally stale catalog.

## Measurements

- task start to final answer;
- first tool call and total tracker-tool time;
- MCP calls and query batches;
- response bytes;
- refresh starts, joins, polls, retries, and terminal state;
- committed generation used;
- deterministic oracle accuracy;
- evidence-selector resolution;
- human-label presence;
- fact/estimate/inference separation;
- usefulness rubric.

Do not store model chain of thought, raw prompts from private tasks, tool
arguments, raw Usage Tracker results, or local paths.

## Initial Gates

- warm top-threads tracker time: ≤1 second;
- warm top-threads final answer: ≤15 seconds;
- warm status: ≤100 ms;
- Console useful committed render: ≤500 ms;
- ordinary tail refresh: ≤500 ms;
- cold production-shaped build: ≤240 seconds;
- database: <700 MiB;
- deterministic answer correctness and selector validity: 100%.

R1 records failures as the baseline. It does not weaken targets to make the
current build pass.

## Parallel Execution

The R1 owner controls the scorecard contract and runner. Explicitly authorized
read-only subagents may independently audit:

- correctness fixtures;
- latency-boundary definitions;
- usefulness rubric;
- privacy of recorded artifacts.

They may not edit the runner or benchmark configuration concurrently. A
separate R8 documentation audit may begin after R0 because it owns disjoint
files, but it cannot publish product claims.

## Validation

- deterministic fixture regeneration;
- benchmark schema validation;
- small-CI run twice with identical structural results;
- one production-shaped unprofiled baseline;
- installed candidate coherence check;
- at least two genuinely fresh local-host task runs, covering every advertised
  CLI/Desktop host;
- separate proofs for installation, registration, handshake, supported-host
  catalog exposure, and fresh-task exposure;
- privacy scan of every persisted artifact.

## Acceptance

- Baseline results are reproducible.
- Fresh-task exposure is distinguished from installation and handshake.
- End-to-end time is separated from tracker-tool time.
- Scorecards can compare candidates without retaining private content.
- R2–R8 can reuse the same gates.

## Handoff

R2 receives the frozen data-volume and correctness oracle. R7 receives the
installed-task runner and scorecard.
