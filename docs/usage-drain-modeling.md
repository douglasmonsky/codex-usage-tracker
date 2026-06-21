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
- [Codex Pricing](https://developers.openai.com/codex/pricing)
- [Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)
- [Codex app-server](https://developers.openai.com/codex/app-server)
- [Codex configuration reference](https://developers.openai.com/codex/config-reference)

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

Codex app-server documentation also points to live surfaces that are available
to an integration, but are not yet part of this historical local-log model:

- `account/read` can report auth mode and `planType`.
- `account/rateLimits/read` and `account/rateLimits/updated` can expose current
  ChatGPT rate-limit state.
- `account/usage/read` can fetch account token-activity summaries and daily
  buckets.
- streamed item schemas include command, file-change, MCP tool, dynamic tool,
  web-search, image-view, and compaction items; command and dynamic-tool items
  can include `durationMs`.

Those sources are useful candidates for a future live calibration layer. For the
current report, they should not be treated as historical evidence unless the
tracker explicitly captures aggregate snapshots from them.

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

The script also fits exploratory predictive control families on closed spans:

- `baseline_train_mean`: train-period mean only
- `credits_only`: standard Codex credit estimate and log credit estimate
- `token_shape`: credits plus row count, input/cache/output/reasoning token mix,
  cache ratio, and per-call credit density
- `fast_proxy`: token shape plus fast-proxy candidate credit share and documented
  fast-weighted credits
- `usage_state`: fast proxy plus baseline observed usage percent, limit-window
  length, reset timing, reset-window elapsed/fraction, plan type, and limit id
- `time_controls`: usage state plus day-of-week, weekend, hour sine/cosine, and
  days since first span
- `date_day_hour_controls`: time controls plus date/day/hour categorical controls
- `full_controls`: date/day/hour controls plus call duration and previous-call gap
- `lag_regime`: usage state plus prior-span and rolling causal history features
  such as previous delta, rolling 3/10/50-span deltas, rolling median/mode,
  rolling volatility, drain-per-credit rolling means, EWMA, low-delta share,
  same-limit-bucket history, and same-date/hour/day-of-week history
- `lag_time_controls`: lag regime plus day/hour controls
- `adaptive_full_controls`: lag time controls plus duration and previous-call gap

The script also reports simple causal baselines:

- `constant_one_percent`
- `persistence_previous_delta`
- `rolling3_delta`
- `rolling10_delta`
- `rolling50_delta`
- `rolling10_median_delta`
- `rolling10_mode_delta`
- `same_bucket_rolling10_delta`
- `same_bucket_rolling10_mode_delta`
- `same_date_rolling10_delta`
- `same_date_rolling10_mode_delta`
- `same_hour_rolling10_delta`
- `same_hour_rolling10_mode_delta`
- `same_day_of_week_rolling10_delta`
- `same_day_of_week_rolling10_mode_delta`
- `ewma_delta`

Two validation splits are reported:

- `time_ordered_80_20`: train on earlier spans, hold out the newest spans. This
  is the stricter future-prediction test.
- `interleaved_every_5th`: hold out every fifth span. This is a distributional
  explanation test that keeps dates and usage regimes mixed across train and
  holdout.

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

After adding richer control families and refreshing the local aggregate index,
the predictive model comparison produced:

| validation split | best model | holdout R2 | holdout MAE | interpretation |
| --- | --- | ---: | ---: | --- |
| interleaved every fifth | full controls | 0.50 | 2.74 pct points | date/day/hour/window controls explain some historical variation |
| interleaved every fifth | date/day/hour controls | 0.50 | 2.75 pct points | duration adds almost nothing beyond date/time/window controls |
| interleaved every fifth | usage state | 0.31 | 3.12 pct points | observed usage state and bucket controls help materially |
| interleaved every fifth | credits only | 0.07 | 3.65 pct points | token-derived credits alone explain little |
| time ordered 80/20 | usage state | very negative | 1.94 pct points | newest spans are a different lower-drain regime; MAE improves but R2 is unstable because holdout variance is tiny |
| time ordered 80/20 | full controls | very negative | 6.71 pct points | date/hour fixed effects overfit old regimes and predict the newest period badly |

Current read: better variables move the model from “barely explanatory” to
“partly explanatory” on a mixed historical holdout, but not near perfect. The
largest remaining issue is regime drift: the newest spans average roughly 1%
usage deltas, while earlier training spans average roughly 5%. More prediction
work should focus on regime/window detection before adding more raw features.

After adding causal rolling/regime features, the newest future holdout became
much more predictable:

| validation split | model | holdout R2 | holdout MAE | interpretation |
| --- | --- | ---: | ---: | --- |
| time ordered 80/20 | constant one percent | -0.00 | 0.003 pct points | newest positive deltas are almost always 1% |
| time ordered 80/20 | previous delta persistence | -1.01 | 0.007 pct points | previous-delta prediction is also nearly exact |
| time ordered 80/20 | lag regime ridge | very negative | 0.68 pct points | learned rolling features help, but direct causal baselines are better |
| interleaved every fifth | previous delta persistence | 0.85 | 0.85 pct points | short-term drain regime persistence explains most mixed-history variation |
| interleaved every fifth | adaptive full controls | 0.84 | 1.35 pct points | richer controls help less than direct persistence |

Current updated read: for the latest observed regime, the best predictor is not
model cost or calendar time. It is the counter behavior itself: once the visible
usage counter starts moving in 1% increments, the next closed positive span is
usually another 1% increment. That is close to perfect predictability for the
visible percentage deltas, but it is also a reminder that the target is a coarse
displayed allowance counter, not exact per-call billing.

After adding explicit date/hour/day-of-week history, rolling mode/median, and
reset-window phase features, the aggregate report became clearer but not
materially closer to exact billing:

| validation split | model | holdout R2 | holdout MAE | interpretation |
| --- | --- | ---: | ---: | --- |
| time ordered 80/20 | constant one percent | -0.00 | 0.003 pct points | newest holdout is almost entirely 1% deltas |
| time ordered 80/20 | rolling10 mode delta | -0.00 | 0.003 pct points | mode collapses to the same 1% rule |
| time ordered 80/20 | same-date rolling10 delta | very negative | 0.027 pct points | date-specific history is close, but worse than the simple 1% rule |
| interleaved every fifth | previous delta persistence | 0.85 | 0.85 pct points | still the best simple mixed-history MAE |
| interleaved every fifth | same-date rolling10 delta | 0.76 | 1.43 pct points | date context helps, but does not beat immediate persistence |
| interleaved every fifth | same-hour rolling10 delta | 0.70 | 1.71 pct points | hour-of-day context is weaker |
| interleaved every fifth | same-day-of-week rolling10 delta | 0.74 | 1.54 pct points | weekday context helps some, but is not dominant |
| interleaved every fifth | adaptive full controls | 0.85 | 1.36 pct points | richer controls slightly improve R2 but not MAE |

The new `delta_regimes` summary explains why. In the refreshed local aggregate
index, there are 1,452 closed positive spans. Across all spans, `1%` deltas are
725 spans, or 49.9%. In the newest time-ordered holdout, `1%` deltas are 290 of
291 spans, or 99.7%. The latest 100 closed spans are all `1%`. That makes the
visible counter highly predictable right now, but mostly because the displayed
counter is quantized and currently moving in a very stable regime.

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
