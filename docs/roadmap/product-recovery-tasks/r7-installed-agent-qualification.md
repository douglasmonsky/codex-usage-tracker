# R7 — Qualify The Installed Fresh-Task Agent Outcome

## Objective

Prove the actual product: an installed wheel, plugin, MCP server, and skill used
from genuinely fresh Codex tasks to produce fast, accurate, useful answers.

## Depends On

R1 creates the harness. R7 runs continuously and completes only after R3–R6.

## Owned Areas

- installed-package and plugin smoke runners;
- isolated Codex-home fixtures;
- fresh-task prompt orchestration;
- scorecard aggregation;
- installed browser and MCP qualification;
- candidate comparison reports.

R7 invokes public behavior. It does not patch product behavior.

## Contract Added First

Add a failing installed-candidate contract that verifies:

- wheel version;
- plugin manifest version;
- MCP server version and source revision;
- bundled skill version or content hash;
- cached plugin bundle identity;
- local Codex host name and version or build;
- fresh-task callable catalog;
- exactly six expected tools and no retired tools;
- terminal answer scorecard for the fixed prompt suite.

Installation, registration, server handshake, supported-host catalog exposure,
and current-task exposure are separate states and must be reported separately.

Qualifying tasks must be launched through every local Codex CLI and Codex
Desktop host that the product advertises as supported. Background-created,
generic orchestration, or unrelated-host tasks may be negative diagnostics, but
they do not count as release qualification.

## Required Runs

### Synthetic automated

- deterministic small fixture in CI;
- production-shaped scale outside normal CI;
- fresh local CLI/Desktop task on current generation;
- fresh task after small tail;
- concurrent JSONL append;
- refresh already active;
- browser close and reopen;
- upgrade from public `0.27.0`;
- failed build and recovery;
- two consecutive identical prompts for cache reuse.

### Maintainer dogfood

Run the same fixed prompts against the maintainer-owned aggregate index using
only structured MCP results. Do not read raw JSONL or persist private result
rows, labels, paths, or transcripts in repository artifacts.

## Scorecard

Every run records:

- candidate revision and coherent component identities;
- tool exposure;
- success or terminal failure;
- end-to-end time;
- tracker-tool time;
- MCP calls, batches, polls, retries, and refresh jobs;
- response bytes;
- generation and freshness;
- oracle correctness;
- evidence validity;
- human readability;
- usefulness;
- fact/estimate/inference quality.

The report may persist prompt IDs, scores, counts, durations, error codes, and
synthetic selectors. It must not persist private prompt or response text.

## Parallel Execution

After an exact candidate artifact exists, explicitly authorized qualification
subagents may run isolated lanes:

- warm common-query prompts;
- refresh, tail, and concurrency prompts;
- Console and evidence browser flows;
- upgrade, plugin cache, skill, and fresh-task exposure.

Each lane uses its own worktree, isolated state, ports, and task IDs. No lane
installs over another lane's environment. The R7 coordinator owns candidate
installation, scorecard schema, result aggregation, and termination.

Use host-side waits for long refreshes. Models never run status-poll loops.

## Release Gates

For warm top threads:

- tracker time ≤1 second;
- final answer ≤15 seconds;
- one query batch;
- no refresh when current;
- correct ranking;
- human names;
- four-token and cost/credit context;
- exact selectors.

For every deterministic synthetic prompt:

- answer correctness: 100%;
- selector validity: 100%;
- no duplicate refresh;
- no raw-content exposure;
- no missing or retired tools.

## Validation

- runner unit tests;
- isolated installation twice;
- fresh-task catalog proof;
- complete fixed prompt suite;
- production-shaped candidate comparison;
- browser qualification;
- privacy review of scorecard artifacts;
- failure-injection run;
- repeated exact candidate run.

## Acceptance

- Installed behavior matches source behavior.
- No old wheel, plugin cache, or skill can masquerade as the candidate.
- Common questions are fast and useful end to end.
- Failures are terminal and actionable.
- The scorecard improves or records an approved tradeoff against R1.

## Handoff

R8 receives approved facts and example outcomes. R9 receives the exact candidate
identity and blocking scorecard.
