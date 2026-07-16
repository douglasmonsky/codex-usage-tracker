# Pricing, Credits, And Allowance

Codex Usage Tracker has three related but different concepts:

- `Estimated Cost`: optional USD estimates from a local pricing file.
- `Codex Credits`: calculated usage credits from aggregate token counters and Codex credit rates.
- `Usage observed`: optional latest local-log 5-hour and weekly allowance snapshots, falling back to copied allowance config when logs do not include rate-limit snapshots.

## Cost Estimates

Enable optional cost estimates:

```bash
codex-usage-tracker update-pricing
```

This fetches OpenAI text-token pricing from `https://developers.openai.com/api/docs/pricing.md`, parses the selected tier, and writes a source-stamped local cache to `~/.codex-usage-tracker/pricing.json`. The default tier is `standard`; other supported tiers are `batch`, `flex`, and `priority`.

The updater supports both the older four-value pricing rows and the newer five-value rows used by GPT-5.6 for input, cached input, cache writes, and output. GPT-5.6 Sol, Terra, and Luna are loaded from the published table, and the documented `gpt-5.6` alias resolves to `gpt-5.6-sol`. Current Codex logs do not expose a separate cache-write token counter, so cost estimates use the logged uncached input, cached input, and output counters without adding an explicit cache-write charge.

If a pricing file already exists, the updater leaves a timestamped `.bak` copy next to it before replacing the active cache.

The updater also includes marked best-guess estimates for Codex labels that are not finalized in the public pricing table. `codex-auto-review` uses OpenAI's published `codex-mini-latest` Codex pricing from `https://openai.com/index/introducing-codex/`: `$1.50` per 1M input tokens, a 75% prompt-cache discount (`$0.375` per 1M cached input tokens), and `$6.00` per 1M output tokens. `gpt-5.3-codex-spark` is listed by OpenAI as a research preview with non-final Codex rates, so the tracker estimates it as `gpt-5.3-codex` at `$1.75` per 1M input tokens, `$0.175` per 1M cached input tokens, and `$14.00` per 1M output tokens.

Use `--no-estimates` when you want only pricing rows parsed from the OpenAI pricing table.

For reproducible historical reports, pin the current pricing cache and pass the pinned file later:

```bash
codex-usage-tracker pin-pricing --output ~/.codex-usage-tracker/pricing-2026-06-05.json
codex-usage-tracker dashboard --pricing ~/.codex-usage-tracker/pricing-2026-06-05.json
```

For a manual template:

```bash
codex-usage-tracker init-pricing
```

Edit `~/.codex-usage-tracker/pricing.json` with USD-per-million-token rates for local overrides or models that are not present in the OpenAI pricing table. Normal reports never contact the network; only `update-pricing` refreshes the local pricing cache.

## Codex Credits

`Codex Credits` is a calculated usage number, not a dashboard-only unit. The tracker uses Codex's logged aggregate token counters and the bundled OpenAI Codex rate-card snapshot to estimate credits consumed by local Codex calls.

The bundled rate card includes the published GPT-5.6 Sol, Terra, and Luna credit rates from the current Codex pricing documentation.

The estimate uses:

- input tokens
- cached input tokens
- output tokens
- the matched model's credit rates

Direct model matches are the highest-confidence rows. Local aliases and inferred labels, such as code-review usage mapped to GPT-5.3-Codex, are marked `estimated`. Local `credit_rates` overrides are marked `user_override`. Rows without a matching model rate are marked as missing credit rates.

To copy the bundled source-stamped rate card into a local snapshot:

```bash
codex-usage-tracker update-rate-card
```

The local snapshot is written to `~/.codex-usage-tracker/rate-card.json`. Each bundled rate and alias includes source URL, fetched date, tier, confidence, and alias rationale where applicable. Use `--source-file` only when you have a reviewed replacement JSON snapshot you want the tracker to validate and use.

### Confirmed Fast Usage

When a call has exact OTel evidence that `fast=1`, the tracker first computes
`standard_usage_credits`, then applies the documented model-family Fast
multiplier to produce `usage_credits`:

- GPT-5.6 family: `2.5x`
- GPT-5.5 family: `2.5x`
- GPT-5.4 family: `2.0x`

The row also exposes `usage_credit_multiplier` and
`usage_credit_multiplier_source` so the adjustment is auditable. A confirmed
Fast call whose model has no documented multiplier stays at `1.0x` and is
marked `no_documented_fast_multiplier`; the tracker does not guess. Standard
and Unknown-tier calls also stay at `1.0x`.

This adjustment applies only to Codex/ChatGPT usage-credit estimates. It never
changes USD token-cost estimates, because those continue to use the selected
pricing tier and aggregate token counters. Allowance-drain calibration uses the
standard-credit baseline so a newly observed Fast label does not redefine the
historical credit-to-percentage relationship.

## Usage Observed

`Usage observed` is different from `Codex Credits`. The tracker cannot currently read your logged-in ChatGPT plan, live remaining credits, reset windows, or usage from other agentic surfaces automatically.

A plan name such as Free, Plus, Pro, Business, or Enterprise can provide context, but it is not enough to know the current remaining allowance. When local Codex logs include `token_count.rate_limits`, the dashboard shows the latest observed 5-hour and weekly percentages from those logs. Otherwise, the dashboard shows remaining values only when you copy them into `~/.codex-usage-tracker/allowance.json`.

Enable optional allowance context:

```bash
codex-usage-tracker init-allowance
codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"
```

The tracker can store `remaining_percent`, `reset_at`, `remaining_credits`, and `total_credits` for each window. If `total_credits` is present, call and thread details show the estimated share of that allowance. Otherwise, the dashboard shows the copied remaining percentages and reset context.

Configure the usage component:

1. Run `codex-usage-tracker parse-allowance "5h 79% 6:50 PM Weekly 33% Jun 7"` with current copied values.
2. Or run `codex-usage-tracker init-allowance` and open `~/.codex-usage-tracker/allowance.json`.
3. Copy current `remaining_percent` and `reset_at` values from Codex Settings, `/status`, or another trusted usage display.
4. Add `remaining_credits` and `total_credits` only if your plan or workspace exposes exact credit numbers.
5. Leave fields as `null` when you do not have a trustworthy value.

## Accuracy Notes

- Codex upstream log formats can change, and parser compatibility may require tracker updates before new event shapes are fully understood.
- Pricing and rate-card sources can change outside this project. Refresh or pin local files when reports need a known source snapshot.
- Local Codex logs may not include usage from other ChatGPT agentic surfaces that share the same allowance.
- Service tier is exact only when a local completion explicitly reports it or
  Codex `0.143.0` or newer establishes Standard through omission. Older or
  unmatched history remains Unknown; latency and reasoning effort cannot prove
  Fast usage.
- Live account allowance cannot be read automatically by this local tracker, and the dashboard does not infer live remaining allowance from the logged-in account plan.
- Observed local-log snapshots may be stale until Codex records another model call, and may omit other agentic surfaces that share the same allowance.
- Pricing can change after a report is generated. Use `pin-pricing` when you need reproducible historical cost estimates.
- Rows with direct model/rate-card matches are more trustworthy than inferred aliases or local overrides.
- Cost and credit calculations use aggregate counters; the tracker does not re-tokenize prompts or reconstruct usage from raw text.
- Cost and credit estimates are not guaranteed to match exact billing.
