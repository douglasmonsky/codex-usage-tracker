# Parallel Hardening CI Design

## Context

The `Hardening gates` GitHub Actions job currently installs Python, Node, Go, and
Rust tooling in one runner and then executes every hardening check serially. A
successful representative run took 6 minutes 56 seconds even though the other CI
jobs completed in less than 4 minutes.

The measured hardening critical path was:

| Work | Duration |
|---|---:|
| Combined tool installation | 3m 10s |
| Dashboard tests | 1m 23s |
| Dashboard route performance budget | 53s |
| Remaining dashboard, Python, security, and policy checks | 1m 30s |

The installation step is dominated by compiling Taplo from source, which took 1
minute 48 seconds. The application-owned Python route benchmark took 37.06
seconds without a profiler and 38.39 seconds under Scalene. Its largest reported
function accounted for only 2.32% of sampled CPU, so application-code
micro-optimization is not the primary CI opportunity.

## Goals

- Reduce pull-request wall-clock time by running independent hardening work in
  parallel.
- Preserve every existing hardening check and its current command semantics.
- Preserve `Hardening gates` as one stable aggregate status name.
- Avoid compiling pinned repository-policy binaries on every warm-cache run.
- Keep failure ownership clear so a failed check points to one logical job.

## Non-goals

- Removing, weakening, or conditionally skipping hardening checks.
- Changing dashboard or Python product behavior.
- Optimizing individual application functions based only on profile share.
- Introducing larger paid GitHub-hosted runners or third-party installer actions.
- Minimizing aggregate runner minutes at the expense of pull-request latency.

## Job Design

Replace the single serial implementation with four independent worker jobs and
one aggregate job.

### Dashboard quality

Use Node 22 and the repository lockfile. Run:

- dashboard lint;
- dashboard type checking;
- dashboard tests;
- dashboard build;
- dashboard governance; and
- dashboard bundle budget.

This job owns the JavaScript and TypeScript toolchain. It must not install Python,
Go, or Rust tooling except where an existing dashboard command directly requires
the system Python executable.

### Dashboard route budget

Use Python 3.14 with the minimum repository installation needed by
`scripts/benchmark_dashboard_routes.py`. Run the existing deterministic 100,000
row, three-iteration benchmark with compression disabled and thresholds enforced.
Keep its output under `/tmp` and do not upload synthetic benchmark state unless a
future debugging requirement explicitly adds an artifact.

### Python hardening

Use Python 3.14 and the repository development dependencies. Preserve the pinned
Agent Maintainer override. Run:

- Agent Maintainer guidance drift;
- whole-source Pyright;
- dependency hygiene;
- dead-code detection;
- dependency vulnerability auditing; and
- Python security checks.

### Repository policy

Own repository-format and supply-chain checks:

- workflow security;
- GitHub Actions lint;
- secret scanning;
- Markdown lint;
- YAML lint;
- TOML formatting; and
- workflow and Dependabot schema validation.

Use only the Python, Node, Go, and Rust packages required by these commands rather
than installing the repository's complete Python development environment.

### Aggregate hardening gate

Keep the `hardening` job identifier and the visible name `Hardening gates` for a
small final job that declares `needs` on all four worker jobs. It must use
`if: always()` and fail unless every required worker result is `success`.

This preserves one stable branch-protection target while retaining detailed
worker-job failures in the Actions UI. Cancellation and skipped dependencies must
not produce a false success.

## Caching

- Enable the supported npm cache through `actions/setup-node`, keyed from the
  existing lockfile.
- Enable the supported pip cache through `actions/setup-python`, keyed from the
  relevant Python dependency files.
- Cache the version-pinned Actionlint, Gitleaks, and Taplo executable directories
  with a key containing the runner OS and all three tool versions.
- On an exact binary-cache hit, skip the corresponding `go install` and
  `cargo install` commands. On a miss, build the pinned versions exactly as the
  current workflow does.

The binary cache improves repeated runs without replacing pinned upstream tools
or adding a third-party installer action. A cold cache is allowed to remain
slower; the four jobs still execute concurrently.

## Expected Outcome

The warm-cache critical path should move from 6 minutes 56 seconds to roughly 2
to 3 minutes. This is an estimate, not a performance guarantee. The first PR must
record actual per-job durations, and any speedup claim must compare completed
GitHub Actions runs with the same workflow scope.

## Validation

- Validate workflow YAML and GitHub Actions schemas locally.
- Run Actionlint and Zizmor against the edited workflow.
- Run the repository release-readiness and whitespace checks.
- Open a PR and confirm all four worker jobs execute independently.
- Confirm `Hardening gates` succeeds only after all four workers succeed.
- Compare the completed PR run against run `29387911750`, recording both the
  total workflow duration and the hardening critical path.

## Risks and Mitigations

- **Higher aggregate runner usage:** accepted because this public repository uses
  standard GitHub-hosted runners and pull-request latency is the priority.
- **Cache masking a missing installer:** cache keys include exact tool versions;
  every command still executes against the pinned binary name.
- **Changed required-check names:** the aggregate gate preserves the current
  visible `Hardening gates` status.
- **Duplicated setup:** each job installs only its own toolchain, and supported
  package caches offset repeated downloads.
- **False aggregate success:** the aggregate expression checks every `needs`
  result explicitly while running under `if: always()`.
