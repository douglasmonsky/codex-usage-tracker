# Usage Drain Modeling

This is an exploratory aggregate-only analysis for comparing visible Codex usage
drain with token-derived Codex credit estimates.

It is not a billing reconciliation. The useful question is narrower: when local
logs show a visible usage percentage increase, do the calls in that span explain
the drain after controlling for model, token mix, cached input, output, and any
fast-mode proxy labels we have?

## Documentation Checked

Official Codex documentation says:

- Codex credits are calculated from input, cached input, and output tokens.
- Fast mode increases supported model speed by 1.5x.
- Fast mode currently supports GPT-5.5 and GPT-5.4.
- Fast mode consumes 2.5x the Standard credit rate for GPT-5.5 and 2x for GPT-5.4.
- With API-key authentication, Codex uses standard API pricing and fast-mode
  credits are not available.

Sources:

- [Codex Speed](https://developers.openai.com/codex/speed)
- [Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)

Tracker documentation and schema show that these fields are readily available
from aggregate local data:

- `model`, `effort`, session/thread metadata, timestamps, and cwd/project context
- `input_tokens`, `cached_input_tokens`, `uncached_input_tokens`,
  `output_tokens`, `reasoning_output_tokens`, and `total_tokens`
- `rate_limit_plan_type`, `rate_limit_limit_id`, observed usage percentages,
  window lengths, and reset timestamps when Codex logs include them
- derived timing fields such as call duration and previous-call gap through
  dashboard/live call APIs
- Codex credit estimates from the bundled or local rate-card config, including
  confidence/source metadata

What is not readily available today:

- a direct per-call fast-mode flag
- exact live account allowance or exact remaining credits for every plan
- usage from other agentic surfaces that share the same allowance
- proof that a visible usage percentage delta belongs only to one local call

## Model Shape

The model groups chronological aggregate calls into closed positive usage-delta
spans:

1. Establish a baseline from the first visible `rate_limit_primary_used_percent`.
2. Accumulate calls while the visible usage percentage is unchanged.
3. When the percentage increases, close the span and assign all accumulated calls
   to that positive delta.
4. If the usage percentage goes down, the limit bucket changes, or reset metadata
   changes, censor the pending span instead of pretending it was zero cost.

This preserves zero-change calls instead of dropping them. They are part of the
work that may have caused the next visible usage-drain jump.

For optional fast-mode proxy analysis, pass a CSV containing at least
`record_id`, `fast_proxy_label`, and `timing_confidence`. The model reports
separate fits for:

- `all_candidates`
- `strong_only`
- `high_medium_candidates`
- `high_confidence_only`

## Current Finding From Local Analysis

The original ad hoc report using the all-call fast-mode proxy found:

| proxy | candidate spans | implied multiplier | best grid multiplier | caveat |
| --- | ---: | ---: | ---: | --- |
| all candidates | 292 | 2.87x | 2.75x | closest to the documented GPT-5.5 2.5x rate, but noisy |
| strong only | 176 | 1.60x | 1.50x | below documented GPT-5.5 fast rate |
| high/medium candidates | 30 | 0.27x | 1.00x | too little reliable signal |

All analyzed calls in that proxy file were `gpt-5.5`, so the relevant documented
fast-mode benchmark is 2.5x rather than 2x.

The reproducible script in this repo uses stricter bucket/reset censorship and
the current refreshed aggregate index. On the same proxy CSV, it produced:

| proxy | candidate spans | implied multiplier | best grid multiplier | documented weighted multiplier |
| --- | ---: | ---: | ---: | ---: |
| all candidates | 258 | 1.92x | 2.00x | 2.50x |
| strong only | 161 | 1.60x | 1.50x | 2.50x |
| high/medium candidates | 31 | 0.94x | 1.00x | 2.50x |

The broad proxy is still directionally compatible with fast mode costing more
credits, but the span-level fit is weak: candidate-share correlation with usage
drain is near zero or negative and the overall fit is poor. Treat this as a
modeling hypothesis, not a confirmed classifier.

## Run It

Refresh the aggregate index first, then run:

```bash
PYTHONPATH=src python scripts/model_usage_drain.py \
  --include-archived \
  --fast-proxy-csv /tmp/codex-fast-mode-inference-all-calls-v1/all_call_fast_mode_features.csv \
  --output-dir /tmp/codex-usage-drain-model \
  --json
```

Outputs:

- `/tmp/codex-usage-drain-model/usage_drain_model_summary.json`
- `/tmp/codex-usage-drain-model/usage_drain_spans.csv`

The report stays aggregate-only. It does not persist prompts, assistant text,
tool output, command text, patch text, or transcript snippets.
