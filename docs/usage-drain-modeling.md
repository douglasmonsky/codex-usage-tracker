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

The model explicitly prefers the 5-hour usage window (`300` minutes) when a
usage snapshot exposes more than one rate-limit window. In the current refreshed
local aggregate index, `primary` is the 5-hour window for all rows with usage
snapshots and `secondary` is weekly, but the analyzer no longer depends on that
ordering. Weekly usage is intentionally not the target because 5-hour drain is
the more reliable local signal for these spans.

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

1. Establish a baseline from the first visible 5-hour usage percentage, preferring
   any `300` minute rate-limit window over weekly windows.
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
- `effort_controls`: fast proxy plus effort mix and dominant-effort controls
- `online_capacity_controls`: effort controls plus prior-only capacity and
  remainder estimates, using earlier closed spans to estimate credits per
  visible percentage point
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
- `hybrid_streak_regime`

Two validation splits are reported:

- `time_ordered_80_20`: train on earlier spans, hold out the newest spans. This
  is the stricter future-prediction test.
- `interleaved_every_5th`: hold out every fifth span. This is a distributional
  explanation test that keeps dates and usage regimes mixed across train and
  holdout.

The report also includes `walk_forward_prediction`, which is stricter than the
interleaved split for simple rules. Each span is predicted using only earlier
closed spans. This avoids mistaking mixed-history explanatory power for true
future predictability.

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

The strict walk-forward check reinforces that split:

| scope | best MAE model | MAE | best RMSE model | RMSE | interpretation |
| --- | --- | ---: | --- | ---: | --- |
| all spans after first | one-percent grace | 0.936 pct points | hybrid streak regime | 2.574 pct points | grace slightly improves typical deltas; hybrid reduces large misses |
| all spans after 50 | one-percent grace | 0.933 pct points | hybrid streak regime | 2.606 pct points | same pattern after warmup |
| newest 20% holdout | constant / grace / rolling10 mode | 0.003 pct points | constant / grace / rolling10 mode | 0.059 pct points | the future holdout is almost all 1% |
| latest 500 spans | constant / grace / rolling10 mode | 0.002 pct points | constant / grace / rolling10 mode | 0.045 pct points | recent visible deltas are nearly flat |
| latest 100 spans | all simple rules | 0.000 pct points | all simple rules | 0.000 pct points | every observed delta is exactly 1% |

The new `hybrid_streak_regime` rule predicts `1%` after at least three prior
`1%` spans, falls back to previous delta after a repeated same-delta streak, and
otherwise uses a rolling-three mean. It does not beat previous-delta persistence
on full-history MAE (`0.972` vs `0.936` pct points), but it does produce the
best full-history RMSE (`2.574` pct points). That means it is useful as a
large-miss reducer and regime signal, not as the best simple point predictor.

The report now includes `regime_streaks`, which makes the current shape explicit:

| streak diagnostic | value | interpretation |
| --- | ---: | --- |
| one-percent runs | 70 | separate stretches where every closed positive span moved by exactly `1%` |
| long one-percent runs | 28 | runs with at least three consecutive `1%` spans |
| longest run | 271 spans | June 9-12, 2026 |
| current streak | 243 spans | started June 12, 2026 and continued through the latest local data |
| largest break after a long run | `2%` after 271 spans | the notable June 12 blip |

That is useful for operating against the visible counter, but it is not evidence
that tokens, fast mode, date, or wall time perfectly explain underlying cost.
The practical next step is probably to model regime changes explicitly: detect
when the visible allowance counter leaves the current 1% mode, then use token
and timing controls only inside comparable regimes.

The `walk_forward_prediction.error_diagnostics` section now shows where the
remaining misses live:

| scope/model | exact match | within 1 pct point | large error share | strongest miss pattern |
| --- | ---: | ---: | ---: | --- |
| all spans, previous delta | 76.9% | 84.7% | 7.6% | large misses cluster in older high-variance periods |
| all spans, rolling3 mean | 63.1% | 78.1% | 6.7% | smoothing reduces RMSE but creates more small misses |
| all spans, constant 1% | 50.0% | 64.6% | 24.1% | fails badly before the current 1% regime |
| newest 20%, previous delta | 99.3% | 100.0% | 0.0% | only a single 1% -> 2% -> 1% blip matters |
| latest 500, constant 1% | 99.8% | 100.0% | 0.0% | one 2% span accounts for the miss |

For the full-history previous-delta rule, the largest misses are transition
errors such as `33% -> 5%`, `37% -> 11%`, and `26% -> 5%`. The highest-error
dates are June 4-5, 2026, and reset-window phase also matters: first-quarter
spans have a higher mean absolute error than later phases. For the newest
holdout, the only meaningful error is a `2%` span on June 12, 2026 around hour
`21`, followed by the expected return to `1%`.

## Span Correlation Caveat

A span is defined as the calls between two visible usage-counter observations
where the selected 5-hour counter increases. That makes `delta_usage_percent` a
coarse displayed-counter target, not a direct measure of hidden per-call cost.
When the counter is in the current 1% regime, asking what predicts the next span
delta mostly asks what predicts another quantized `1%` tick.

The report now includes `span_correlations` to separate two questions:

| question | current read |
| --- | --- |
| What correlates with bigger visible deltas? | Weakly: `baseline_used_percent` is the largest full-history raw-feature Pearson correlation with `delta_usage_percent` at `0.254`; token and call totals are weak and negative. In the latest 500 spans, the target mean is `1.002%`, stddev is `0.045`, and all raw-feature correlations are near zero. |
| What correlates with work packed into one 1% tick? | Strongly: among exact `1%` spans, standard credits correlate with total tokens (`0.958` Pearson), input tokens (`0.957`), cached input tokens (`0.945`), row count (`0.928`), and call duration (`0.819`). |

So the next modeling target should probably be two-part:

1. Predict the counter regime: stable `1%`, transition/blip, or older
   high-variance behavior.
2. Inside stable `1%` regimes, model capacity per tick: calls, tokens, credits,
   duration, and wall-clock span time per visible percentage point.

The new `one_percent_regime_grace` walk-forward rule is a small step in that
direction. It keeps predicting `1%` for one small break after a long `1%` run.
On the current data, the calibrated default (`10` prior `1%` spans, one-span
grace, max `2%` break) slightly improves full-history MAE over plain previous
delta (`0.936251` -> `0.935562`) and matches the
best newest-holdout MAE (`0.003436`). The gain is small, but it captures the
right operational idea: a single `2%` tick after a long stable regime should be
treated as a possible blip, not automatic proof that the regime changed.

The report also includes empirical state-bucket walk-forward predictors. These
learn the modal prior actual delta for matching state buckets, then fall back to
simpler signatures when support is thin:

- `empirical_history_state_mode`: previous delta plus streak buckets
- `empirical_calendar_state_mode`: previous delta plus day-of-week and hour
- `empirical_reset_state_mode`: previous delta plus baseline/reset-window buckets
- `empirical_previous_work_state_mode`: previous delta plus the previous span's
  wall-time and call-duration buckets

Current full-history result:

| model | MAE | exact match | matched-state share | mean support |
| --- | ---: | ---: | ---: | ---: |
| previous delta | 0.936 pct points | 76.9% | | |
| one-percent grace | 0.936 pct points | 77.0% | | |
| empirical reset state | 1.155 pct points | 72.1% | 99.0% | 23.0 |
| empirical previous-work state | 1.344 pct points | 64.6% | 99.0% | 32.0 |
| empirical history state | 1.346 pct points | 66.6% | 99.0% | 59.1 |
| empirical calendar state | 1.358 pct points | 70.2% | 99.6% | 22.4 |

For the newest 20% holdout, the reset-state bucket predictor ties the simple
`1%`/grace rule at `0.003` MAE, but it does not beat it. The latest 500 spans
make the limitation clearer: constant `1%` is `0.002` MAE, while the empirical
calendar bucket degrades to `0.246` MAE because older calendar states sometimes
vote for stale high-delta behavior. So these bucket predictors are useful as a
diagnostic ceiling test, but they are not the path to perfect prediction on the
current data. The best visible-counter predictor remains the simpler current
regime rule: if the counter is in a long `1%` run, keep predicting `1%`.

The report now also tests a more explicit two-stage gate:

1. Use transition risk to decide whether the next span is likely to break away
   from `1%` continuation.
2. If it looks like a break, use matched history-state magnitude; otherwise keep
   the `one_percent_regime_grace` continuation prediction.

Real-data result:

| model | all-history MAE | newest 20% MAE | read |
| --- | ---: | ---: | --- |
| one-percent grace | 0.936 | 0.003 | best simple continuation rule |
| transition-gated history-state mode | 1.344 | 0.007 | fixed 50% gate switches too often in old regimes |
| transition-weighted history-state mode | 1.307 | 0.006 | soft blend is still worse than continuation |
| adaptive MAE transition gate | 1.226 | 0.003 | learns to back off in the newest regime but still trails continuation overall |

The adaptive gate raises its all-history mean threshold to about `0.915`,
overrides `29.1%` of opportunities, and matches the `1%` continuation rule in
the newest holdout by making no overrides. This is useful negative evidence:
binary transition risk is real, but converting it into exact visible-delta
magnitude is still the hard part.

The new `walk_forward_prediction.transition_risk` section turns the same problem
into a binary question: "will the next positive visible delta be something other
than `1%`?" It reports Brier score, AUC, average precision, and top-10% risk
precision/recall for causal risk scores.

| scope | positive rate | best Brier model | Brier | AUC | average precision | read |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| all spans after first | 50.0% | history-state risk | 0.080 | 0.953 | 0.932 | older high-variance regimes are rankable from streak/history buckets |
| newest 20% holdout | 0.3% | history-state risk | 0.008 | 0.340 | 0.007 | only one positive; low Brier mostly means "predict near zero" |
| newest 20% holdout | 0.3% | reset-state risk | 0.009 | 0.976 | 0.125 | ranks the single blip higher, but precision is still one event in a tiny sample |
| latest 500 | 0.2% | history-state risk | 0.006 | 0.368 | 0.003 | almost no positives, so ranking is unstable |
| after long 1% runs | 1.0% | stable one-percent rule | 0.010 | 0.500 | 0.215 | "long 1% run means near-zero break risk" is hard to beat on calibration |

Current read: binary risk framing is useful for proving that date/hour/reset and
streak variables can rank old regime transitions, but it does not reveal a
reliable early warning signal for the current regime. In the newest data, the
best-calibrated behavior is still to assign almost zero break risk after a long
`1%` streak. Reset state may occasionally rank the one visible blip higher, but
with one positive event this is not enough evidence to trust as a general
predictor.

The report now adds `piecewise_regime_segments`, which groups contiguous spans
by actual visible-delta regime:

- `stable_one_percent`: exactly `1%`
- `small_blip`: `>1%` through `2%`
- `moderate_delta`: `>2%` through `5%`
- `high_delta`: `>5%` through `10%`
- `very_high_delta`: above `10%`

Current segment shape:

| diagnostic | value |
| --- | ---: |
| contiguous segments | 290 |
| stable `1%` segments | 70 |
| small-blip segments | 89 |
| moderate-delta segments | 56 |
| high-delta segments | 48 |
| very-high-delta segments | 27 |
| latest segment | `stable_one_percent`, 243 spans, June 12-21 |
| longest segment | `stable_one_percent`, 271 spans, June 9-12 |

Inside segment labels, the best simple predictors are much closer:

| segment label | prediction rows | mean delta | best model | MAE |
| --- | ---: | ---: | --- | ---: |
| stable `1%` | 725 | 1.000 | constant `1%` | 0.000 |
| small blip | 213 | 2.000 | constant `1%` | 1.000 |
| moderate delta | 164 | 3.970 | previous delta | 1.256 |
| high delta | 168 | 8.149 | previous delta | 1.607 |
| very high delta | 181 | 17.564 | previous delta | 1.674 |

The longest old high-delta segments are also highly predictable once the segment
is known: a 53-span `very_high_delta` run on June 5 averages `21.17%` and has
previous-delta MAE `1.04`; another 45-span run that day averages `19.47%` and
has previous-delta MAE `0.69`. This is the clearest evidence so far that the
remaining problem is not "which raw variables explain every span?" It is
"where are the regime boundaries?" Once a segment has started, a simple local
rule is already close to perfect for that segment.

The `adaptation_by_position` view makes that boundary cost explicit:

| position inside segment | prediction rows | mean delta | best model | MAE |
| --- | ---: | ---: | --- | ---: |
| first span | 289 | 4.107 | constant `1%` | 3.107 |
| second span | 122 | 4.156 | previous delta | 0.279 |
| third span | 82 | 4.512 | previous delta | 0.134 |
| fourth/fifth span | 120 | 4.975 | previous delta | 0.067 |
| sixth-plus span | 838 | 4.402 | previous delta | 0.110 |

For `very_high_delta` segments specifically, the first-span previous-delta MAE
is still `7.44`, but it drops to `1.00` on the second span, `0.27` on the third,
and `0.74` after the sixth. Stable `1%` segments are exact from the first span
when using the constant `1%` rule. So the practical model is: first span after a
boundary is the expensive uncertainty; after one or two confirming spans, local
persistence is already extremely strong.

The new `boundary_diagnostics` view reframes this as a transition-risk problem.
Across 1,451 possible next-span transitions, 289 change visible-delta regime
label, for an overall boundary rate of `19.9%`. After a configured long `1%`
run, however, only 5 of 509 next-span opportunities change label, a `0.98%`
boundary rate.

| previous label | opportunities | boundaries | boundary rate |
| --- | ---: | ---: | ---: |
| small blip | 214 | 89 | 41.6% |
| stable `1%` | 724 | 69 | 9.5% |
| moderate delta | 164 | 56 | 34.1% |
| high delta | 168 | 48 | 28.6% |
| very high delta | 181 | 27 | 14.9% |

The top observed boundary transitions are mostly adjacent regime flips:
`small_blip->stable_one_percent` (36), `stable_one_percent->small_blip` (35),
`moderate_delta->stable_one_percent` (25), `small_blip->high_delta` (24), and
`stable_one_percent->moderate_delta` (24). Reset phase and clock hour still add
context: first-quarter reset-window spans have a `23.4%` boundary rate versus
`9.3%` in the third quarter, and hour `17` has a `36.3%` boundary rate in this
history. The practical read is still conservative: these buckets describe where
past boundaries clustered, but the current long `1%` regime has a much lower
observed break rate than the all-history average.

Segment age is the strongest boundary context added so far:

| previous segment position | opportunities | boundaries | boundary rate |
| --- | ---: | ---: | ---: |
| first span | 290 | 168 | 57.9% |
| second span | 122 | 40 | 32.8% |
| third span | 82 | 17 | 20.7% |
| fourth/fifth span | 120 | 21 | 17.5% |
| sixth-plus span | 837 | 43 | 5.1% |

Wall-clock segment age points the same way: transitions immediately after a new
segment starts (`0_sec`) have a `57.9%` boundary rate, while segments older than
30 minutes (`1800_plus_sec`) have a `2.1%` boundary rate. That makes the best
current boundary model look like a survival problem: new segments are
untrustworthy until they survive one or two confirming spans; old segments,
especially long `1%` segments, are much less likely to break.

The `walk_forward_risk` subsection tests this causally by predicting each
boundary opportunity from only earlier opportunities. After the first 10
opportunities, segment age is the best calibrated boundary-risk model by Brier
score:

| model | Brier | AUC | average precision | top-10% precision |
| --- | ---: | ---: | ---: | ---: |
| overall prior rate | 0.160 | 0.671 | 0.303 | 33.1% |
| segment age | 0.119 | 0.830 | 0.492 | 55.9% |
| previous label + segment age | 0.125 | 0.804 | 0.508 | 58.6% |
| reset + segment age | 0.133 | 0.771 | 0.473 | 54.5% |
| calendar + segment age | 0.135 | 0.781 | 0.487 | 56.6% |

In the newest time-ordered holdout there are only 2 boundaries in 292
opportunities, so ranking metrics are fragile. Still, segment-age variants beat
the prior-rate baseline on Brier (`0.009` for segment age and `0.006` for the
previous-label plus segment-age model, versus `0.053` for the prior). The read
is: segment age is now a real causal predictor of boundary risk, while
date/hour/reset buckets are useful secondary context but not the dominant signal.

The companion `walk_forward_delta_prediction` subsection asks the stricter
question: given the same boundary-opportunity context, what visible percent jump
comes next? This is intentionally different from boundary risk. Segment age can
tell us that a transition is more likely without beating the simple magnitude
rule that says "repeat the previous delta."

After the first 10 opportunities, the all-history next-delta results are:

| model | MAE | RMSE | R2 | Pearson |
| --- | ---: | ---: | ---: | ---: |
| previous delta | 0.936 | 2.786 | 0.781 | 0.891 |
| adaptive MAE risk gate | 0.959 | 2.845 | 0.772 | 0.886 |
| adaptive RMSE risk gate | 0.995 | 2.888 | 0.765 | 0.883 |
| risk-gated label + segment age | 1.016 | 2.907 | 0.762 | 0.881 |
| risk-weighted label + segment age | 1.028 | 2.728 | 0.790 | 0.893 |
| risk-weighted prior-boundary label + segment age | 1.244 | 2.742 | 0.788 | 0.890 |
| previous label + segment age | 1.580 | 3.542 | 0.646 | 0.811 |
| reset + segment age | 1.836 | 3.979 | 0.553 | 0.756 |
| calendar + segment age | 1.990 | 4.332 | 0.471 | 0.710 |
| segment age only | 3.141 | 6.391 | -0.152 | 0.203 |
| prior mode | 3.179 | 6.546 | -0.209 | 0.268 |
| prior-boundary label + segment age | 3.465 | 6.340 | -0.134 | 0.132 |

So the newest boundary feature is useful, but not in the way a perfect
next-delta predictor would need. It improves causal boundary-risk ranking, while
the exact magnitude is still best predicted by the immediately previous visible
delta. A risk-gated variant only overrides previous-delta prediction when
label+segment-age boundary risk is at least `50%`; it overrides `16.7%` of
all-history opportunities and improves sharply over always using the stale
label+segment-age mode, but it still loses to previous-delta MAE. A
risk-weighted blend is slightly worse on MAE but slightly better on RMSE and R2,
which says it reduces some larger misses while adding small errors elsewhere.
The adaptive gate learns its threshold from prior rows only. On all history, the
MAE-tuned gate raises the average threshold to `0.915`, overrides only `2.36%`
of opportunities, and lands between previous-delta persistence and the fixed
gate. The learned threshold mostly says the same thing the current data says:
exact next-delta prediction should almost always stay with persistence unless
boundary risk is extremely high.
The prior-boundary variant is a useful negative control: using only matched
historical boundary rows does not solve magnitude prediction. It matches prior
boundary state often, but loses because many current opportunities are
continuations where persistence is still the right answer.

The residual diagnostics make the remaining miss pattern much sharper. For the
all-history `previous_delta` model, boundaries are only `19.8%` of next-delta
opportunities but account for `89.4%` of absolute error. The biggest transition
error bucket is `very_high_delta->small_blip`: only `1.3%` of rows, but `16.7%`
of absolute error. Segment-position age points in the same direction:
first-span opportunities account for `51.9%` of absolute error, while
sixth-plus opportunities account for `25.9%`. Time buckets are also
concentrated, but they mostly look like where the hard regime changes happened:
day-of-week `4` accounts for `54.1%` of absolute error, hour `17` for `43.5%`,
the first reset-window quarter for `63.2%`, and previous call duration
`0_30_sec` for `63.0%`. Those are useful targeting variables, but the stronger
structural takeaway is that exact-delta predictability is now a boundary/first-
span problem, not a broad calendar regression problem.
In the newest time-ordered holdout, almost every opportunity is a `1%`
continuation: prior mode and segment age both reach `0.003` MAE, and the latest
100 opportunities are all exactly predicted by every simple model. That confirms
the current regime is easy because it is stable, not because calendar/reset
controls have uncovered a hidden pricing formula.

## Token Component Regression

The report now includes `token_component_regression`, which directly tests the
billing-shaped hypothesis across all positive spans with four token components:

- uncached input tokens
- cached input tokens
- reasoning output tokens
- non-reasoning output tokens

It runs two variants:

- `unweighted`: raw token components.
- `high_medium_fast_weighted`: the same components, but rows with medium/high
  fast-mode proxy confidence are multiplied by the documented model fast
  multiplier. In the current all-history run, this affects 42 rows across 31
  spans.

Current result:

| target | token variant | all-spans R2 | newest 20% holdout R2 | read |
| --- | --- | ---: | ---: | --- |
| visible 5-hour drain | unweighted | 0.029 | very negative | token components do not explain the coarse visible counter |
| visible 5-hour drain | medium/high fast weighted | 0.030 | very negative | fast weighting barely moves the visible-drain fit |
| tracker credit estimate | unweighted | 1.000 | 1.000 | token components exactly reconstruct rate-card credits |
| fast-weighted credit estimate | medium/high fast weighted | 1.000 | 1.000 | multiplying candidate fast spans preserves exact token accounting |

The no-intercept credit regression recovers the expected coefficients per
million tokens:

| component | coefficient |
| --- | ---: |
| uncached input | 125 |
| cached input | 12.5 |
| reasoning output | 750 |
| non-reasoning output | 750 |

Current read: token accounting is internally linear and consistent with the
local Codex rate card. The visible allowance percentage is the noisy part: it is
quantized, regime-dependent, and not a smooth per-call billing meter.

The practical interpretation is: token usage plus model controls should predict
the hidden credit/cost accounting, while spans are the normalization layer that
aligns that accounting to the coarse visible drain meter. A `1%` span is not one
fixed amount of tokens; it is the work that accumulated before the next visible
`1%` tick appeared.

The public Codex pricing docs currently publish five-hour message-limit ranges
and token credit rates, not exact included credit bucket sizes by plan. This
report should therefore continue treating allowance deltas as observed counter
data instead of assuming a documented hidden denominator.

## Feature Family Attribution

The report now includes `feature_family_attribution` for the main visible-delta
models and the one-percent capacity models. It compares named model families in
fixed sequences and reports `mae_improvement_vs_previous`; positive means the
later family reduced holdout MAE. This is a diagnostic comparison, not causal
proof that a specific field caused the gain.

On the current interleaved holdout for visible drain, the main cost/time
sequence looks like this:

| family | holdout MAE | MAE improvement vs previous |
| --- | ---: | ---: |
| train mean | 4.146 pct points | |
| credits | 3.650 pct points | 0.496 |
| token shape | 3.592 pct points | 0.058 |
| fast proxy | 3.610 pct points | -0.019 |
| usage state | 3.122 pct points | 0.488 |
| cyclic time | 3.151 pct points | -0.028 |
| date/day/hour categories | 2.786 pct points | 0.365 |
| duration and wall time | 2.852 pct points | -0.067 |

That says token-derived credits and observed usage/window state help some, and
categorical date/day/hour context helps mixed-history explanation. The current
fast proxy, cyclic time, and duration/wall-time controls do not improve MAE in
that sequence.

The history/regime sequence is much stronger:

| family | holdout MAE | MAE improvement vs previous |
| --- | ---: | ---: |
| usage state | 3.122 pct points | |
| history/regime | 1.314 pct points | 1.808 |
| history plus cyclic time | 1.332 pct points | -0.018 |
| history plus date and wall time | 1.443 pct points | -0.112 |

This reinforces the main modeling lesson so far: recent counter behavior is the
strongest visible-drain predictor. Date and wall-time controls are useful as
descriptive context, but once the model has recent regime/history state, they do
not move it closer to perfect predictability on this holdout.

## One-Percent Tick Capacity

The report now includes `one_percent_capacity_modeling`, which only uses exact
`1%` spans and switches the target from visible delta to `standard_usage_credits`
inside that tick. This is the better question when the visible counter is stuck
in a `1%` regime: not "will the next span be 1%?" but "how much work fits before
the next 1% tick?"

Current capacity distribution across 725 exact `1%` spans:

| metric | value |
| --- | ---: |
| mean standard credits per 1% tick | 42.245 |
| stddev | 37.268 |
| min | 0.709 |
| max | 146.557 |

The direct four-component accounting regression for exact `1%` spans is now
reported at
`one_percent_capacity_modeling.token_component_regression`. This is the specific
near-perfect case: once the span is closed, the four token buckets reconstruct
the estimated credit capacity inside that `1%` tick.

| target | token variant | all-spans R2 | newest 20% holdout R2 | MAE | affected fast-proxy rows |
| --- | --- | ---: | ---: | ---: | ---: |
| credits inside exact 1% ticks | unweighted | 1.000 | 1.000 | 0.000 | 0 |
| credits inside exact 1% ticks | medium/high fast weighted | 1.000 | 1.000 | 0.000 | 41 |

The no-intercept coefficients are unchanged in the one-percent subset:

| component | coefficient |
| --- | ---: |
| uncached input | 125 |
| cached input | 12.5 |
| reasoning output | 750 |
| non-reasoning output | 750 |

That result should be read narrowly. It says the local credit estimate is a
linear function of the four token buckets, including the documented fast-mode
multiplier where the proxy is medium/high confidence. It does not prove that the
visible allowance counter is an exact realtime billing meter, because the
counter itself is rounded, sampled, and regime-dependent.

The capacity models intentionally separate advance-prediction features from
same-span explanatory features:

| split | model family | holdout MAE | holdout R2 | read |
| --- | --- | ---: | ---: | --- |
| time-ordered 80/20 | rolling3 capacity baseline | 17.459 credits | 0.359 | best simple causal predictor of the newest capacity |
| time-ordered 80/20 | history + start context | 19.478 credits | 0.373 | richer date/hour/window controls do not beat rolling3 MAE |
| time-ordered 80/20 | history + bucketed state | 19.853 credits | 0.365 | nonlinear usage/window/hour buckets add noise in the newest holdout |
| time-ordered 80/20 | history + state interactions | 55.844 credits | -2.745 | day/hour/window interactions badly overfit older history |
| time-ordered 80/20 | history + state interactions, ridge100 | 19.756 credits | 0.389 | stronger shrinkage fixes the blow-up but still trails rolling3 MAE |
| time-ordered 80/20 | same-span shape | 14.628 credits | 0.702 | row count, duration, and wall time explain more after the span is known |
| time-ordered 80/20 | same-span shape + buckets | 11.722 credits | 0.800 | bucketed row count and wall-time controls improve explanatory fit |
| time-ordered 80/20 | same-span shape + interactions | 12.290 credits | 0.791 | more interactions do not beat simpler buckets |
| time-ordered 80/20 | same-span shape + interactions, ridge30 | 10.321 credits | 0.839 | regularized interactions beat simple shape buckets |
| time-ordered 80/20 | same-span tokens | 0.082 credits | 0.99999 | near-perfect but mostly accounting identity, because credits are token-derived |
| interleaved every fifth | rolling3 capacity baseline | 15.297 credits | 0.605 | mixed-history causal capacity is moderately predictable |
| interleaved every fifth | history + bucketed state | 16.434 credits | 0.557 | bucketed state still trails rolling3 on MAE |
| interleaved every fifth | history + state interactions | 14.632 credits | 0.627 | interactions help when train/holdout are mixed across history |
| interleaved every fifth | history + state interactions, ridge100 | 16.270 credits | 0.601 | shrinkage improves stability but loses mixed-history accuracy |
| interleaved every fifth | same-span shape | 8.967 credits | 0.892 | work-shape features explain capacity strongly |
| interleaved every fifth | same-span shape + buckets | 6.714 credits | 0.935 | bucketed row count/duration/wall time close much of the remaining shape gap |
| interleaved every fifth | same-span shape + interactions | 7.383 credits | 0.921 | extra shape interactions overfit compared with simpler buckets |
| interleaved every fifth | same-span shape + interactions, ridge30 | 6.428 credits | 0.940 | best non-token explanatory shape model so far |
| interleaved every fifth | same-span tokens | 0.049 credits | 0.999996 | again near-perfect but explanatory, not advance prediction |

The one-percent capacity attribution separates advance-prediction gains from
same-span explanatory gains:

| sequence/family | holdout MAE | MAE improvement vs previous |
| --- | ---: | ---: |
| causal start context | 25.754 credits | 6.018 |
| causal date/hour context | 22.702 credits | 3.052 |
| causal history | 16.120 credits | 7.316 |
| causal history plus interactions | 14.632 credits | 1.802 |
| same-span shape | 8.967 credits | 22.804 |
| same-span shape buckets | 6.714 credits | 2.253 |
| same-span regularized shape interactions | 6.428 credits | 0.956 |
| same-span tokens | 0.049 credits | 6.378 |

Current read: history matters for capacity, especially the previous few `1%`
ticks. Date, day-of-week, hour, reset-window, and used-percent buckets alone help
less than recent capacity history for advance prediction. Day/hour/window
interactions can improve mixed-history validation, but the time-ordered split
shows they are brittle against regime drift. Stronger ridge shrinkage repairs
the worst interaction overfit, but does not beat the simple rolling3 causal
baseline on the newest holdout. Once the span is closed, bucketed row count,
duration, and wall time make the non-token shape model much stronger, and
regularized shape interactions improve it further. Same-span tokens make the fit
look perfect, but that is not a forecasting win because the token totals are
observed inside the span and the credit estimate is derived from them.

Residual diagnostics are now included on each capacity model under
`holdout_error_diagnostics`. The current interleaved holdout shows the remaining
non-token error is concentrated in large spans:

| model | within 10 credits | large error share | largest error drivers |
| --- | ---: | ---: | --- |
| causal history + state interactions | 55.9% | 18.6% | `50_plus_calls` spans average `50.0` credits of absolute error; `900_1800_sec` call-duration spans average `38.9` |
| same-span shape + interactions, ridge30 | 76.6% | 1.4% | `50_plus_calls` spans average `19.5` credits of absolute error; `900_1800_sec` call-duration spans average `20.7` |
| same-span tokens | 100.0% | 0.0% | largest residual is `0.33` credits, consistent with numerical/accounting noise |

This points toward two different next steps. For advance prediction, high-work
`1%` ticks remain the hard cases because their size is not knowable from
pre-span history alone. For explanatory analysis after the span closes,
large-span shape still has some structure left, but token accounting absorbs
almost all of it.

## Allowance Breakpoint Analysis

The report now includes `allowance_breakpoint_analysis` to test the hypothesis
that token/credit usage may correlate much better after accounting for
allowance-denominator changes. It builds a chronological
`standard_usage_credits_per_visible_percent` series for every closed positive
usage-delta span, then greedily splits that series where piecewise segment means
reduce variance.

On the current refreshed local aggregate index:

| metric | value |
| --- | ---: |
| closed positive spans | 1,452 |
| global credit-to-visible-delta R2 | -0.479 |
| global mean credits per visible percent | 23.571 |
| global stddev credits per visible percent | 34.088 |
| piecewise SSE reduction | 60.9% |
| strongest single split | June 7, 2026 18:33 UTC |
| pre-split mean credits per visible percent | 6.670 |
| post-split mean credits per visible percent | 50.727 |

The detected segments are:

| segment | date range | spans | mean credits per visible % | exact 1% spans | plan/window read |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | May 17-June 7 | 895 | 6.670 | 184 | mixed `prolite`/`pro`, 300-minute Codex window |
| 2 | June 7-June 11 | 154 | 78.383 | 139 | all `pro`, 300-minute Codex window |
| 3 | June 11-June 12 | 159 | 38.376 | 159 | all `pro`, 300-minute Codex window |
| 4 | June 12-June 13 | 80 | 7.335 | 79 | all `pro`, 300-minute Codex window |
| 5 | June 13-June 18 | 50 | 86.838 | 50 | all `pro`, 300-minute Codex window |
| 6 | June 18-June 21 | 114 | 45.208 | 114 | all `pro`, 300-minute Codex window |

This supports the concern that a single global token-to-drain regression can
hide strong local structure. The later segments all have the same observed plan
type, limit id, and 5-hour window, so the shifts are not explained by the
tracker accidentally mixing weekly and 5-hour counters. They still should not be
described as proven official allowance changes: the same pattern could come
from counter rounding, hidden account-side state, usage from other surfaces,
sampling cadence, or imperfect span assignment.

The follow-up piecewise credit-to-delta fit is the more important negative
control. It asks whether a capacity-adjusted metric can predict visible drain:
`predicted_visible_delta = credits / detected_segment_capacity`. A second
variant rounds positive predictions up to the next visible `1%` tick.

| model | R2 | MAE | read |
| --- | ---: | ---: | --- |
| global credit slope | -0.479 | 4.093 | plain tokens/credits do not explain visible drain |
| global credit slope, ceiling to 1% tick | -0.312 | 3.597 | visible rounding helps, but the fit is still poor |
| piecewise mean capacity | -0.657 | 4.298 | denominator segments alone make the fit worse |
| piecewise mean capacity, ceiling to 1% tick | -0.580 | 4.108 | rounding helps but still misses badly |
| piecewise no-intercept slope | -0.442 | 3.958 | fitting a slope per segment helps only slightly |
| piecewise no-intercept slope, ceiling to 1% tick | -0.299 | 3.550 | best credit-derived variant here, still poor |

Current read: breakpoint detection shows real capacity clustering, but it does
not by itself produce a near-perfect visible-drain metric. Denominator shifts
plus display rounding are not enough. The stronger route is probably a two-stage
model: first predict counter regime/boundary state, then model credits or
capacity inside that regime.

The report now also includes
`allowance_breakpoint_analysis.online_capacity_credit_to_delta_fit`. This is a
causal denominator test: for each closed span, it predicts visible delta from
current same-span credits divided by a capacity estimate learned only from prior
spans. On a synthetic fixture with a clean `10 -> 40` capacity change, the
previous-capacity denominator is exact except for the first row after the
breakpoint. On the current local data, it fails badly:

| online denominator | R2 | MAE | known-breakpoint abs-error share | read |
| --- | ---: | ---: | ---: | --- |
| EWMA capacity | -42.014 | 5.601 | 10.1% | best online denominator, still much worse than counter persistence |
| rolling-3 mean capacity | -48.463 | 6.313 | 9.1% | reacts faster but still overpredicts large spans |
| rolling-10 mean capacity | -86.511 | 6.418 | 12.0% | stale denominator after shifts creates large misses |
| previous capacity | -36.644 | 7.071 | 3.5% | volatile one-span capacity causes extreme overprediction |
| rolling-10 median capacity | -284.385 | 12.140 | 11.7% | robust median is too sticky around regime changes |

That is useful negative evidence. If allowance changes were the only missing
piece, the online denominator models would be close after the first row of each
new segment and detected breakpoint rows would dominate the residuals. Instead,
most error happens away from detected breakpoint rows. The available aggregate
data still needs counter-state persistence, boundary/segment state, and probably
hidden account-side state; same-span credits plus an online denominator is not a
near-perfect visible-drain metric.

## GPT-5.5 Pro-Only Isolation

The report script now supports `--plan-type`, so the same analysis can be rerun
against a narrower slice:

```bash
PYTHONPATH=src python scripts/model_usage_drain.py \
  --include-archived \
  --model gpt-5.5 \
  --plan-type pro \
  --fast-proxy-csv /tmp/codex-fast-mode-inference-all-calls-v1/all_call_fast_mode_features.csv \
  --output-dir /tmp/codex-usage-drain-model-gpt55-pro
```

This is a row-level filter. It removes `prolite`, missing-plan, and other-model
rows before building spans, which is useful for isolating the dominant observed
plan/model regime. It is still not perfect causal attribution if excluded work
happened between two included rows.

Current comparison:

| metric | all rows | `gpt-5.5` + `pro` only | read |
| --- | ---: | ---: | --- |
| source rows | 26,952 | 19,760 | pro-only removes `prolite`, missing-plan, and one auto-review row |
| positive spans | 1,452 | 957 | fewer closed visible-delta spans |
| exact `1%` spans | 49.9% | 69.2% | pro-only is more dominated by the stable `1%` regime |
| mean visible delta | 4.374% | 2.178% | high-delta older behavior is reduced |
| token-component visible-drain R2 | 0.029 | 0.047 | tokens explain slightly more, but still very little |
| credits-only interleaved R2 | 0.075 | 0.163 | cost signal improves after isolating pro, still weak |
| best history/regime interleaved R2 | 0.852 | 0.476 | mixed-history predictability drops because there is less high-variance regime structure to learn |
| best walk-forward MAE | 0.936 | 0.733 | pro-only improves all-history causal next-delta error |
| latest 100 MAE | 0.000 | 0.000 | both scopes are currently stable at visible-counter granularity |
| breakpoint SSE reduction | 60.9% | 57.5% | capacity clustering remains after removing non-pro rows |
| best online denominator MAE | 5.570 | 2.510 | pro-only helps denominator tracking, but it is still not close to perfect |

The pro-only slice is cleaner and more recent-regime-heavy, but it does not
turn token usage into a near-perfect visible-drain predictor. The best read is
that plan isolation removes some noise and lowers errors, while the target is
still mainly governed by coarse counter regime, boundary state, and hidden
account-side context.

Adding effort and prior-capacity controls to the same `gpt-5.5` + `pro` run
clarified what helps:

| model family | interleaved R2 | interleaved MAE | read |
| --- | ---: | ---: | --- |
| credits only | 0.163 | 1.305 | first useful signal, but weak alone |
| token shape | 0.157 | 1.326 | token mix does not improve over credits |
| fast proxy | 0.182 | 1.303 | small improvement |
| effort controls | 0.183 | 1.291 | tiny MAE gain; effort has little variance here |
| online capacity controls | 0.254 | 1.342 | raises R2 but worsens MAE, so not a clean metric |
| usage state | 0.269 | 1.362 | counter/window state helps R2, but still not enough |
| lag regime | 0.418 | 1.059 | prior counter behavior remains much stronger |
| lag + cyclic time | 0.467 | 1.038 | best mixed-history learned control in this run |

In the 957 closed positive pro-only spans, the calls assigned to those spans are
heavily concentrated in one effort level: `xhigh` is 12,241 of 12,721 calls
inside closed spans, `high` is 398, `medium` is 77, and `low` is 5. Only 41
spans have mixed effort. That makes effort a useful control column but not a
major explanatory variable for this local dataset.

The prior-capacity result is more interesting. If hidden allowance denominator
were the main missing factor, then current credits divided by a denominator
learned from recent prior spans should get close. It does not. It improves R2
relative to effort-only controls, but the higher MAE means it is mostly helping
rank some large spans while making typical span prediction worse. That points
back to a stateful model: predict the visible-counter regime and boundary risk
first, then use credits/cost/time as within-regime explanatory components.

The research implication is that the right metric is probably piecewise and
stateful:

1. Detect stable allowance-capacity eras from
   `standard_usage_credits / visible_delta_percent`.
2. Detect whether the next span is a continuation or boundary using recent
   counter state.
3. Within stable regimes, model exact `1%` tick capacity.
4. Report boundary dates and segment fit separately from the global fit.

## State Ambiguity Lower Bound

The report now includes `walk_forward_prediction.state_ambiguity` to test
whether aggregate state is specific enough to make exact next-delta prediction
possible. It groups walk-forward rows by state signatures, then asks whether
identical-looking prior states produced different next visible deltas. This is
an oracle diagnostic, not a causal predictor, because the mode for each group is
computed with all rows in the scope.

Current result:

| scope | signature | repeated row share | ambiguous row share | oracle MAE on repeated states | read |
| --- | --- | ---: | ---: | ---: | --- |
| all history after first | previous delta | 99.9% | 99.9% | 1.283 | previous delta alone is heavily ambiguous |
| all history after first | reset state | 91.0% | 51.9% | 0.889 | reset/window buckets reduce ambiguity but do not remove it |
| all history after first | full bucket state | 59.5% | 26.9% | 0.811 | richer state helps, but repeated states still conflict |
| newest 20% holdout | full bucket state | 47.8% | 0.0% | 0.000 | the newest regime is unambiguous because it is nearly all `1%` |
| latest 100 spans | full bucket state | 49.0% | 0.0% | 0.000 | current local data is fully stable at visible-counter granularity |

The all-history result is the important caution. Even with previous delta,
streaks, reset-window buckets, day/hour, prior work buckets, plan type, and
limit id, about `26.9%` of rows live in repeated states that produced more than
one next delta. That means a perfect global predictor probably needs either
more historical account-side state, a better boundary detector, or an explicit
piecewise regime model. The recent zero-ambiguity result is still useful, but it
mostly says the current counter regime is stable, not that the hidden allowance
formula has been solved.

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
