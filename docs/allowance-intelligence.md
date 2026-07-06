# Allowance Intelligence

Allowance intelligence is an aggregate-only workflow for asking: did visible Codex allowance behavior change, or is the counter just noisy?

It uses observed `token_count.rate_limits` snapshots already present in local Codex logs. It does not read prompts, assistant text, tool output, raw command output, or OpenAI account internals.

## What It Can Say

- Normalize observed 5-hour and weekly usage snapshots into `allowance_observations`.
- Compare visible usage-percent movement with locally estimated Codex credits.
- Separate weekly evidence from 5-hour rolling-window behavior.
- Flag candidate allowance regime shifts when recent weekly credits-per-visible-percent drops sharply.
- Preserve the possibility that other Codex or ChatGPT usage outside local logs explains movement.

## Evidence Grades

- `insufficient_data`: not enough observations or positive usage spans.
- `counter_noise_likely`: usually used for 5-hour windows because rolling-window behavior is noisy.
- `no_change_detected`: enough weekly evidence exists, but no candidate shift was found.
- `possible_regime_change`: weekly evidence suggests a visible capacity change, but evidence is limited.
- `strong_local_evidence`: multiple weekly spans show a consistent drop in credits-per-visible-percent.
- `inconclusive_other_usage_possible`: observed movement could plausibly be explained by usage outside these local logs.

## Statistical Detector Direction

The detector now includes a `nonparametric-v1` evidence block for weekly candidate shifts. It adds:

- exact permutation p-values for mean credits-per-percent shifts when the split is small enough to enumerate locally;
- Cliff's delta effect size, where negative values mean recent spans bought less visible allowance movement per estimated credit;
- a stricter `research_readiness.ready_for_public_claim` flag that requires repeated weekly spans on both sides of the split, strong effect size, and p-value support.

This intentionally separates local diagnostics from public claims. A small sample can still produce `strong_local_evidence` when the direction is consistent, but the public-claim readiness flag stays false until there are enough weekly spans to make a more defensible statement.

## Commands

```bash
codex-usage-tracker allowance-history --window-kind weekly --json
codex-usage-tracker allowance-diagnostics --window-kind weekly --json
codex-usage-tracker allowance-export --output /tmp/codex-allowance-evidence.json
```

Use `--limit 0` to inspect all normalized observations. The export command always produces strict-privacy payloads.

## MCP Tools

- `usage_allowance_history(...)`
- `usage_allowance_diagnostics(...)`
- `usage_allowance_export(...)`

The MCP tools default to strict privacy for allowance work because these reports are likely to be copied into issues or community discussions.

## Local API

- `/api/allowance/history`
- `/api/allowance/diagnostics`
- `/api/allowance/export`

The dashboard can build an Allowance / Limit Intelligence surface from these payloads later without inventing a separate data contract.

## Privacy

Strict export omits prompts, assistant messages, tool output, file paths, thread names, session IDs, and record IDs. It includes anonymized observation dates, window kinds, visible usage movement, estimated credits, confidence labels, evidence grades, and caveats.

This project remains unofficial and local-first. The diagnostics are evidence for local investigation, not an official OpenAI usage ledger.
