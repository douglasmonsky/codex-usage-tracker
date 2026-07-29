# CI performance qualification

Absolute latency remains a product contract, but a GitHub-hosted runner is not
a controlled qualification host. Required pull-request CI therefore separates
deterministic correctness from host qualification instead of treating every
wall-clock pause as a product regression.

## Required CI: invariants only

Required CI runs the full synthetic scale files once with
`CODEX_USAGE_PERFORMANCE_LANE=invariants`. Wall-clock observations remain in
the tests, but that lane never asserts them. Row counts, planner choices,
transaction counts and scope, percentile sample semantics, query plans,
response sizes, and all other deterministic assertions remain blocking.

The scale step has a five-minute host-side deadline. Exit 124 or 137 is reported
as bounded suite non-completion, not as proof of an absolute-latency product
regression. Ordinary assertion and process failures remain blocking.

## Outcomes

The performance plugin emits one
`codex-usage-tracker.ci-performance-qualification.v1` JSON record:

- `pass`: the runner qualified and every recorded budget passed;
- `product_regression`: the runner qualified and at least one recorded budget
  failed;
- `runner_unqualified`: the runner did not qualify, so timing breaches remain
  telemetry and are not described as product regressions.
- `invariants_only`: observations were retained while wall-clock enforcement
  was intentionally disabled.
- `suite_timeout`: the qualification process exceeded its five-minute host
  deadline before it could produce a complete report.

`runner_unqualified` never suppresses an ordinary pytest failure. Completed
plugin reports include `pytest_exit_status`, so an invariant failure remains
distinguishable from a qualified timing regression.

## Hosted-runner qualification

The plugin measures three independent calibration rounds both before and after
the performance suite. Each round contains:

- a fixed CPU probe comparing wall time with process CPU time; and
- 60 short SQLite WAL transactions measuring p95 and maximum duration.

At least two of three rounds must be healthy at both boundaries. A qualified
runner then enforces every recorded absolute budget, including the 2,000-call
append writer targets of 50 ms p95 and 150 ms maximum.

The scheduled/manual workflow runs five independent unprofiled repetitions on
one pinned `ubuntu-24.04` image. Each fresh process emits its own JSON record.
The aggregate records median, p95, maximum, and coefficient of variation for
every metric and retains all five inputs as one workflow artifact. The image is
pinned; shared runner hardware is not.

All five repetitions must pass calibration. A single qualified timing spike
remains visible in p95 and maximum telemetry but does not become a product
regression. `product_regression` requires the five-run median to exceed the
explicit metric budget. An unqualified repetition makes the aggregate
`runner_unqualified` and non-blocking; ordinary pytest failures remain
blocking. A host-side timeout writes a distinct `suite_timeout` record before
the aggregate fails.

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
30,000 fixed hash operations per repetition. Local evidence added about 0.1
seconds to one synthetic performance run. Required CI performs no calibration
or artifact upload. The hosted qualification workflow runs five repetitions
once per week and on explicit dispatch.
