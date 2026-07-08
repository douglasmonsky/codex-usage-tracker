# Agentic Investigation Hardening Roadmap

This roadmap follows the exploratory MCP experiments run on 2026-07-08. The goal is to make Codex Usage Tracker useful as an agent-facing investigation partner, not just a dashboard data source.

Product stance stays unchanged:

- Local-first and unofficial.
- Aggregate/shareable evidence first.
- Explicit local content-index tools only when the user asks for deeper local diagnosis.
- No raw context by default.
- Recommendations must name evidence, missing evidence, confidence, and next verification step.

## Experiment Findings

The agentic layer already identifies meaningful waste patterns:

- Large low-output calls are real and actionable.
- High context pressure dominates recent usage.
- Repeated file rediscovery is measurable and severe.
- Shell churn exists, but command labels are too cloudy.
- Allowance-change evidence is currently insufficient, which is the correct conservative result.

The rough edges are agent-facing rather than purely analytical:

- `usage_suggest_investigations(goal=...)` returns too few ideas for broad discovery.
- `usage_investigate(...)` returns large nested payloads that are hard for agents to consume.
- There is no first-class hypothesis-testing endpoint matching the preferred user framing.
- Shell churn command labels collapse too often into `unknown_command`.
- Local evidence export can report confusing aggregate fields for some branches.
- Some filters and archived-row behavior need targeted regression tests.

## Target Interaction Shape

When a user asks for exploratory analysis, the agent should answer in this shape:

```text
I'd like to be able to ...
I will accomplish this using ...
I'm missing access to ...
My hypothesis was true/false/partially true because ...
Next action ...
```

The MCP should make that easy by returning this structure directly, with compact evidence and explicit caveats.

## PR Chunk 1: Suggestions And Compact Investigation Payloads

Improve existing entry points before adding new tools.

Changes:

- Expand `usage_suggest_investigations(...)` so broad goals can return multiple useful suggestions instead of one sparse row.
- Add a compact mode or bounded evidence shape for `usage_investigate(...)` that avoids dumping full dashboard rows unless explicitly requested.
- Preserve current schema compatibility by adding fields rather than removing stable fields.
- Add tests proving broad suggestions include token waste, cache failure, workflow churn, allowance change, and overview.
- Add tests proving compact investigation payloads include enough fields for actionability: finding, evidence summary, confidence, missing access, next tools.

Acceptance criteria:

- A user asking "what should I investigate?" receives a menu, not a single option.
- A user asking "look through usage for token waste" receives concise findings that an agent can summarize without parsing massive nested rows.
- Existing MCP contract tests remain green.

## PR Chunk 2: Hypothesis Runner MCP/API Surface

Add a first-class hypothesis-testing tool.

Proposed tool:

- `usage_test_hypotheses(...)`

Initial inputs:

- `question`
- optional `hypotheses`
- `since`, `until`, `thread`, `include_archived`
- `evidence_limit`
- `privacy_mode`

Output shape:

- `schema`
- `content_mode`
- `includes_indexed_content`
- `includes_raw_fragments`
- `question`
- `hypotheses[]`
  - `id`
  - `hypothesis`
  - `status`: `true`, `false`, `partially_true`, `insufficient_evidence`
  - `confidence`
  - `i_would_like_to_be_able_to`
  - `i_will_accomplish_this_using`
  - `i_am_missing_access_to`
  - `evidence_summary`
  - `counter_evidence`
  - `next_action`
  - `recommended_next_tools`

Initial built-in hypothesis families:

- token waste
- cache/cold-resume failure
- repeated file rediscovery
- shell churn
- effort/model choice
- allowance change

Acceptance criteria:

- The tool can evaluate supplied hypotheses and default hypotheses.
- It returns explicit true/false/partial/insufficient decisions.
- It does not require raw context.
- It recommends lower-level MCP tools when evidence is insufficient.

## PR Chunk 3: Evidence Quality Hardening

Fix the diagnostic surfaces that made recommendations cloudy.

Changes:

- Improve shell command normalization so common command families do not collapse into `unknown_command`.
- Add tests for repeated `sed`, `rg`, `git`, `nl`, `npm`, `python`, `pytest`, and package-manager commands.
- Tighten `usage_local_evidence_export(...)` aggregate summaries so `occurrences`, `call_count`, and `total_tokens` are meaningful for every branch.
- Add regression tests for `include_archived=false` across the new agentic, low-output, shell, file, export, and hypothesis surfaces.
- Make repeated file rediscovery recommendations more specific when safe fields are available: basename, extension, operation mix, adjacent retouch count, and trace handles.

Acceptance criteria:

- Shell churn reports are readable without raw command output.
- Shareable local evidence export does not show confusing zero counts for supported branches.
- Active-only filters do not surface archived rows in evidence samples.

## Later Dashboard Work

Do not start with UI. Once the APIs are stable:

- Add a Diagnostics Notebook module for hypothesis testing.
- Show "hypothesis true/false/partial" cards.
- Link each card to Calls, Threads, Call Investigator, and local evidence export.

## Validation Plan

Each implementation PR should run:

```bash
.venv/bin/python -m ruff check .
PYTHONPATH=src .venv/bin/python -m mypy
PYTHONPATH=src .venv/bin/python -m pytest tests/cli/test_mcp_integration.py tests/cli/test_cli_release.py
.venv/bin/python scripts/check_release.py
git diff --check
```

Broader tests should be run when touching parser/indexing logic:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python -m compileall src
```
