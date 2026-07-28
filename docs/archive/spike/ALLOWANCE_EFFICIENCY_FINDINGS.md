# Kernel Allowance Efficiency Findings

> Historical, non-authoritative spike evidence. The logical interval lessons
> remain useful, but this file does not define the replacement schema, APIs, or
> paths.

The 0.26 kernel treats allowance percentages as upstream observations. It
calculates local efficiency only between adjacent observations with the same
window kind, limit identity, plan identity, and reset timestamp.

## Measurement contract

- `used_percent` and `observed_at` are exact upstream-observed facts.
  `remaining_percent` is their exact deterministic complement.
- Percentage points per hour and local tokens, calls, or turns per percentage
  point are deterministic calculations over one compatible adjacent interval.
- Local usage covers canonical calls in the half-open interval after the prior
  observation through the current observation. The turn count records turns
  whose first canonical model call falls in that interval.
- The reasoning counter remains separately visible and is not added again to
  `total_tokens`.
- A positive local ratio always carries `outside_usage_possible`. It is not
  causal billing attribution.
- Missing previous observations or intervals, reset boundaries, unchanged
  percentages, non-monotonic percentages, and incompatible windows produce no
  ratio. A ratio without an observed reset timestamp is explicitly marked
  `reset_timestamp_unobserved`.
- Cost and credit values are estimates. Missing model rates remain null or
  partially covered rather than falling back to an invented price.

The `usage_allowance` MCP tool, `GET /api/kernel/v1/allowance`, bounded
`usage_query` allowance measures, exact allowance evidence selector, and Limits
Console all read the same committed generation. None starts a refresh.

## Optional local rate card

Place an owner-controlled JSON file at
`$CODEX_USAGE_TRACKER_CACHE_ROOT/rate-card.json`. With the default cache root,
the path is `~/.codex/codex-usage-tracker/kernel-v1/rate-card.json`.

```json
{
  "schema": "codex-usage-tracker.kernel-rate-card.v1",
  "source": {
    "name": "Local documented rates",
    "url": "https://example.invalid/documented-source",
    "effective_at": "2026-01-01",
    "fetched_at": "2026-01-02"
  },
  "models": {
    "gpt-example": {
      "input_per_million": 10,
      "cached_input_per_million": 1,
      "output_per_million": 20,
      "credits_input_per_million": 5,
      "credits_cached_input_per_million": 0.5,
      "credits_output_per_million": 10,
      "confidence": "user_override"
    }
  }
}
```

Every configured model must provide all six non-negative rates and a confidence
of `exact`, `estimated`, or `user_override`. The card must include source name,
URL, effective date, and fetched date. Invalid cards fail closed.
