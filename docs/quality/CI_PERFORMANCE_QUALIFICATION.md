# CI performance qualification

Absolute latency remains a product contract, but a GitHub-hosted runner is not
a pinned qualification host. Required pull-request CI therefore separates
deterministic correctness from host qualification instead of treating every
wall-clock pause as a product regression.

## Outcomes

The performance plugin emits one
`codex-usage-tracker.ci-performance-qualification.v1` JSON record:

- `pass`: the runner qualified and every recorded budget passed;
- `product_regression`: the runner qualified and at least one recorded budget
  failed;
- `runner_unqualified`: the runner did not qualify, so timing breaches remain
  telemetry and are not described as product regressions.

`runner_unqualified` never suppresses an ordinary pytest failure. Row counts,
planner choices, transaction counts and scope, percentile sample semantics,
query plans, response sizes, and all other deterministic assertions remain
blocking.

## Hosted-runner qualification

The plugin measures three independent calibration rounds both before and after
the performance suite. Each round contains:

- a fixed CPU probe comparing wall time with process CPU time; and
- 60 short SQLite WAL transactions measuring p95 and maximum duration.

At least two of three rounds must be healthy at both boundaries. A qualified
runner then enforces every recorded absolute budget, including the 2,000-call
append writer targets of 50 ms p95 and 150 ms maximum. A deterministic
regression still fails required pull-request CI.

The JSON record is printed as `CI_PERFORMANCE_QUALIFICATION=...`, added to the
GitHub step summary, and retained as a workflow artifact. A missing report is
called out explicitly.

## Strict absolute qualification

The authoritative absolute-budget command is explicit strict mode on a known
qualification host:

```bash
CODEX_USAGE_PERFORMANCE_LANE=strict \
CODEX_USAGE_PERFORMANCE_REPORT=/tmp/performance-qualification.json \
python -m pytest -p no:tach -p tests.kernel.performance_qualification \
  tests/kernel/test_ingest_performance.py \
  tests/kernel/allowance/test_performance.py \
  tests/kernel/evidence/test_performance.py \
  tests/kernel/interfaces/test_performance.py \
  tests/kernel/query/test_performance.py
```

Strict mode has no runner escape: any wall-clock breach fails. The scheduled
`Qualified hosted performance` workflow is deliberately labeled as hosted and
calibration-qualified; it is not represented as controlled hardware.

## Cost

Calibration adds six small cohorts, approximately 360 control transactions and
30,000 fixed hash operations per suite. Local evidence added about 0.1 seconds
to the existing synthetic performance run. Required CI adds the JSON summary
and one small artifact upload. The hosted qualification workflow runs once per
week and on explicit dispatch.
