# Pricing, Credits, And Allowance

Codex Usage Tracker has three related but different concepts:

- `Estimated Cost`: optional USD estimates from a local pricing file.
- `Codex Credits`: calculated usage credits from aggregate token counters and Codex credit rates.
- `Usage Remaining`: optional user-provided 5-hour and weekly allowance snapshots.

## Cost Estimates

Enable optional cost estimates:

```bash
codex-usage-tracker update-pricing
```

This fetches OpenAI text-token pricing from `https://developers.openai.com/api/docs/pricing.md`, parses the selected tier, and writes a source-stamped local cache to `~/.codex-usage-tracker/pricing.json`. The default tier is `standard`; other supported tiers are `batch`, `flex`, and `priority`.

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

## Usage Remaining

`Usage Remaining` is different from `Codex Credits`. The tracker cannot currently read your logged-in ChatGPT plan, live remaining credits, reset windows, or usage from other agentic surfaces automatically.

A plan name such as Free, Plus, Pro, Business, or Enterprise can provide context, but it is not enough to know the current remaining allowance. The dashboard shows remaining values only when you copy them into `~/.codex-usage-tracker/allowance.json`.

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
- Live account allowance cannot be read automatically by this local tracker, and the dashboard does not infer live remaining allowance from the logged-in account plan.
- Pricing can change after a report is generated. Use `pin-pricing` when you need reproducible historical cost estimates.
- Rows with direct model/rate-card matches are more trustworthy than inferred aliases or local overrides.
- Cost and credit calculations use aggregate counters; the tracker does not re-tokenize prompts or reconstruct usage from raw text.
- Cost and credit estimates are not guaranteed to match exact billing.
