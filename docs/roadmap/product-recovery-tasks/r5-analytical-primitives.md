# R5 — Restore Analytical Primitives And Human Semantics

## Objective

Restore the facts people need to make useful inferences while preserving the
kernel rule that Codex—not the server—does the interpretation.

## Depends On

R3 and R4.

## Owned Areas

- allowance interval calculations and service;
- rate-card cost and credit calculations;
- human thread-label metadata boundary;
- tool operation and bounded target classification;
- turn and tool-impact facts;
- evidence and query fields required by these primitives;
- focused correctness, privacy, and performance tests.

## Contract Added First

Add failing golden contracts for:

- total tokens with uncached input, cached input, reasoning, and output;
- configured dollar cost and estimated credits with coverage;
- allowance drain assigned to intervals, never the revealing call;
- local tokens, calls, and turns within each allowance interval;
- time-first recent token and allowance bands;
- thread label plus stable selector;
- turn ordinal and completion basis;
- tool operation, target label, duration, output bytes, and impact grade;
- copied-row exclusion across every aggregate.

## Cost And Credit Semantics

Keep three concepts separate:

1. **Configured token cost:** deterministic when a dated rate card covers the
   model and token classes.
2. **Estimated Codex credits:** calculated from an explicit local credit rate
   card with source, date, confidence, and coverage.
3. **Observed allowance drain:** upstream cumulative state measured over an
   interval, with possible out-of-band activity.

No view may label one as another. Unpriced usage remains visible.

## Thread Labels

- Read bounded thread-name metadata from Codex's session index.
- Return `thread_label` alongside the stable `thread` selector to MCP and
  Console consumers.
- Bound length, collapse controls and whitespace, and treat the label as
  untrusted display data.
- Keep selectors exact and copyable.
- Disclose that agent-facing thread names are prompt-derived metadata.
- Do not store message bodies to obtain a label.

## Tool Semantics

Extract only bounded structural meaning:

- operation such as read, write, search, patch, test, browser, or MCP;
- safe project-relative target label when available;
- tool and server name;
- start, end, duration, status;
- output bytes;
- turn and nearest model call;
- observation confidence.

Do not persist commands, raw arguments, file contents, tool output, secrets, or
full local paths.

Tool token impact must distinguish:

- exact tool-output bytes;
- exact adjacent model-call token classes;
- deterministic interval totals;
- estimated tool/context attribution;
- consuming-model inference.

## Parallel Execution

R5 begins only after R3 and R4 integrate because it touches both fact
production and query/evidence contracts.

After the R5 field contract is frozen, explicitly authorized subagents may
implement disjoint lanes:

- allowance and rate-card calculations;
- thread-label metadata;
- tool classification and impact.

Each lane must have separate files and tests. The R5 coordinator alone changes
shared query/evidence schemas and integrates the lanes. If ownership overlaps,
run sequentially.

## Validation

- four-token accounting oracle;
- cost and credit coverage matrix;
- allowance interval and reset golden tests;
- out-of-band and concurrent-call caveats;
- thread-label sanitation and selector preservation;
- tool classification fixtures;
- no raw-content persistence assertions;
- aggregate deduplication;
- common-query latency after adding fields;
- response-byte ceilings.

## Acceptance

- Agent and Console results use human names.
- Total tokens always expose their breakdown.
- Dollar cost and credits return with explicit coverage.
- Limits can render a truthful usage-over-time graph.
- Tool and turn facts support useful model inference.
- No estimate is promoted to exact.
- Warm query gates remain green.

## Handoff

R6 receives frozen presentation fields and fixtures. R7 adds analytical prompts
to the installed fresh-task suite.
