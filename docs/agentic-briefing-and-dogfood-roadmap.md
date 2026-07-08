# Agentic Briefing And Dogfood Roadmap

This roadmap follows the agentic MCP and hypothesis-testing hardening work merged through
PR #114. The current backend can already suggest investigations, test hypotheses, inspect
large low-output calls, identify shell churn, rank repeated file rediscovery, and evaluate
allowance-change evidence. This phase is about making that flow repeatable, easier for
agents to use correctly, and more action-oriented for users.

Product stance stays unchanged:

- Local-first and unofficial.
- Aggregate/shareable evidence by default.
- No raw prompts, raw tool output, full paths, raw commands, or transcript snippets unless
  the user explicitly asks for deeper local content inspection.
- Dashboard UI is not the source of truth for this phase; backend/MCP payloads are.
- Recommendation language must separate exact facts, estimates, missing access, and next
  verification steps.

## Why This Phase Exists

Dogfooding the improved MCP flow surfaced two needs:

- The project needs a repeatable local experiment harness so future changes can be checked
  against the same old and new hypotheses instead of relying on ad hoc terminal snippets.
- The bundled skill/plugin guidance should teach agents the new investigation sequence and
  explain newer report concepts such as `unclassified_shell_script`.
- The MCP should be able to produce a concise action brief that translates diagnostics into
  practical workflow recommendations, including existing tools and custom helper ideas.

## PR Chunk 1: Dogfood Hypothesis Harness

Add a repeatable local experiment harness that runs the old and new hypothesis battery and
emits compact local artifacts.

Proposed command:

```bash
codex-usage-tracker dogfood-agentic
```

Initial behavior:

- Refresh active usage by default, with `--include-archived` opt-in.
- Run `usage_test_hypotheses` over the old hypothesis set:
  - token waste in large low-output calls
  - cache/cold-resume pressure
  - repeated file rediscovery
  - shell churn
  - model/effort choice
  - weekly allowance change
- Run the new follow-up hypothesis set:
  - large low-output calls as cleanup target
  - repeated file rediscovery concentrated in safe file identities
  - shell churn as repeated probing
  - context pressure driving expensive calls
  - local content-index/thread-trace follow-up needed for intent
  - allowance-change claims not ready without weekly spans
- Run direct evidence tools:
  - `usage_large_low_output_calls`
  - `usage_shell_churn`
  - `usage_repeated_file_rediscovery`
  - `usage_allowance_diagnostics`
  - `usage_suggest_investigations`
  - `usage_investigate` for `token_waste` and `workflow_churn`
- Write a compact JSON summary and optional Markdown brief.

Acceptance criteria:

- Harness output declares scope: refresh status, archived setting, privacy mode, evidence
  limit, and artifact paths.
- Harness asserts privacy invariants: no indexed content, no raw fragments, no raw command
  output, and no full paths in compact outputs.
- Harness records expected family routing for the old and new hypotheses.
- Harness can be run locally without publishing or contacting external services.
- Add focused tests for summary shape and privacy flags using synthetic data.

## PR Chunk 2: Skill And Plugin Guidance Refresh

Update bundled skills and docs so Codex agents use the improved investigation flow.

Guidance changes:

- Lead broad usage questions with `usage_suggest_investigations`.
- Use `usage_test_hypotheses` when the user frames the request as:
  - "I'd like to be able to..."
  - "I will accomplish this using..."
  - "I'm missing access to..."
  - "my hypothesis was true/false..."
- Use direct tools after the hypothesis result:
  - `usage_large_low_output_calls` for large low-output/context pressure.
  - `usage_repeated_file_rediscovery` for repeated safe file identities.
  - `usage_shell_churn` for command churn.
  - `usage_allowance_diagnostics` and `usage_allowance_export` for limit-change claims.
- Explain `unclassified_shell_script` plainly:
  - It is a mixed or legacy bucket where the tracker cannot safely recover one specific
    command root from aggregate indexed data.
  - It is still evidence of churn, but needs thread trace or future indexed command detail
    before prescribing a specific command-level fix.
- Recommend existing tools and possible custom solutions when diagnosing waste:
  - Headroom or similar context-pressure tools when available.
  - Project notes, handoff templates, helper scripts, test selectors, file summaries, or
    targeted commands when repeated rediscovery or shell churn appears.

Acceptance criteria:

- Bundled plugin skill files and source skill files stay in sync.
- MCP docs describe the recommended investigation sequence.
- Tests or docs snapshots prove the guidance mentions hypothesis testing, direct evidence
  follow-up, `unclassified_shell_script`, and existing/custom remediation options.

## PR Chunk 3: Actionable Recommendation Brief

Add a user-facing aggregate report/MCP tool that converts diagnostics into a compact
remediation brief.

Proposed tool:

```text
usage_action_brief(...)
```

Initial inputs:

- `goal`: optional, default `token_waste`
- `since`, `until`, `thread`
- `include_archived`
- `evidence_limit`
- `privacy_mode`

Output shape:

- `schema`
- `content_mode`
- `includes_indexed_content`
- `includes_raw_fragments`
- `privacy_mode`
- `filters`
- `summary`
- `actions[]`
  - `finding`
  - `confidence`
  - `evidence`
  - `likely_waste_pattern`
  - `recommended_workflow_change`
  - `recommended_existing_tool`
  - `recommended_custom_solution`
  - `how_to_verify`
  - `recommended_next_tools`
- `caveats`

Initial action families:

- Large low-output/context pressure:
  - recommend shorter handoffs, fresh thread with summary, context-pressure tooling, and
    direct verification with `usage_large_low_output_calls` and `usage_call_detail`.
- Repeated file rediscovery:
  - recommend durable file summaries, project notes, helper commands, and narrower reads.
- Shell churn:
  - recommend stopping repeated retry loops, summarizing failures, using test selectors or
    helper scripts, and inspecting thread traces.
- Allowance-change readiness:
  - recommend weekly diagnostics/export only when evidence is ready; otherwise explain why
    public claims are premature.

Acceptance criteria:

- New schema is documented in CLI JSON schema docs and MCP docs.
- MCP tool and CLI JSON path return the same payload builder.
- Payload remains aggregate/shareable by default.
- Tests cover at least one action from each initial action family using synthetic fixtures.
- Dogfood harness can optionally include the action brief.

## Phase Exit Criteria

This phase is complete when:

- The dogfood harness can be run before future MCP changes.
- The bundled skill/plugin teaches agents the intended investigation flow.
- The action brief can turn evidence into concrete user-facing remediation steps.
- Full local validation passes.
- No dashboard UI work has been started as part of this phase.

## Release Guidance

- If the phase only lands the harness and docs, ship as a patch.
- If `usage_action_brief` becomes a new public MCP/API surface, ship as the next minor
  release, likely `0.17.0`.
