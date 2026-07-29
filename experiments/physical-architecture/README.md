# Physical architecture bake-off

This tree is the CK-04 experiment boundary. It cannot be imported by the production
package. Candidate A, C, and D may choose different tables, indexes, SQL, projection
maintenance, and publication internals, but they consume the same frozen shared contract.

The shared contract version is `ck04-candidate-adapter-v1`. Candidate processes add this
directory to `PYTHONPATH` and import `shared`; the directory name containing the experiment
has a hyphen intentionally and is not a production Python package.

## Candidate seam

Each candidate implements `shared.CandidateAdapter`:

```python
class Adapter:
    candidate_id = "A"
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

    def execute(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        ...
```

`execute()` is the only candidate-specific callable in the bake-off runner. The immutable
request carries a verified CK-03 fixture/oracle bundle, one workload case, a disposable run
root, a repetition number, and the early-stop controller. Unsupported optional experiments
return `RunOutcome.UNSUPPORTED`; a candidate may not omit a mandatory case. A stopped run
must first trip the shared controller and remains a recorded partial failure.
Every non-unsupported result includes `MeasurementValues`; `execute_measured_candidate()`
binds those values to the host clocks, pinned environment, fixture and workload digests.

`load_fixture_bundle()` verifies canonical manifest bytes, manifest and oracle SHA-256
digests, every persisted source's exact bytes/records/digest, the five vertical slices, and
the required question cases. It rejects absolute, escaping, missing, or non-CK-03 inputs.

## Frozen workload and measurements

`build_workload_matrix(physical_cores=...)` returns stable case IDs for:

- every required history build, monotonic expansion, scale, parser-worker count, writer and
  index mode, and unpublished schema upgrade;
- all nine ordinary changes and seven isolated-artifact unsafe changes;
- every P1 named preset and required vertical-slice question in cold, warm, and repeated
  modes, plus deep pages, exact count, valuation replacement, selected timeline,
  deterministic ties, and bounded full sorting;
- all nine publication termination boundaries and the injected-fault union required by the
  bake-off and qualification plan;
- four DBHub generic/named by default/less-capable trials and the file-based agent-perf
  attribution workload.

The matrix digest includes the qualification host's physical-core input. Candidate result
files use `codex-usage-tracker.physical-bakeoff-measurement.v1`. The collector owns wall and
process clocks; the candidate supplies the remaining explicit resource, storage, ingestion,
projection, plan, MCP, call, token, correctness, selector, and publication measurements.
JSON Lines records are canonical and append-only.

Speed claims require at least five unprofiled samples. `distribution_summary()` fixes median,
nearest-rank p95, maximum, and population coefficient of variation. `rank_candidates()` uses
the seven documented weights and deterministic lower-cost normalization over identical
fixture digests and scale. Profile output is attribution evidence only.

The qualification runner retains canonical invocation, measurement, and summary files but
discards each completed candidate run root by default. This keeps repeated production-scale
measurements from filling the qualification filesystem and distorting later write timings.
Pass `--retain-run-artifacts` only for a bounded diagnostic that genuinely needs the
generated candidate database; the retention choice is recorded in both invocation and
summary artifacts.

Raw qualification output belongs under
`experiments/physical-architecture/.measurements/`, which is ignored by Git. The accepted
decision commits only bounded canonical manifests containing the exact input and output
hashes, environment identity, score calculation, sensitivity results, approved query-plan
exceptions, crash observations, and research-lane metrics needed to audit the selection.

## Publication failures

`PublicationCrashDriver` is the process-control seam. The driver launches and terminates its
own candidate, while the shared harness selects `CrashCase` and compares `CrashObservation`
with the CK-03 oracle. The prior publication, rollback, sidecar terminal state, abandoned
artifact disposition, and subsequent recovery are all observed facts; exceptions or a
candidate's assertion are not substitutes.

## DBHub research

`build_dbhub_run()` creates a disposable copy of a synthetic SQLite snapshot, removes all
write bits, records its digest, writes one TOML configuration, and returns shell-free stdio
argv pinned to `@bytebase/dbhub@0.24.0` and its npm integrity. The live 0.24.0 connector opens
SQLite read-write before its tools apply `PRAGMA query_only`, so this lane cannot truthfully
claim an engine-level read-only connection. `DbhubRun.runtime_access()` grants owner-write
permission only for the MCP process, then restores mode `0444` and fails if the digest
changed. The row cap is at most 100. Only schema search, generic read SQL, and one to four
single-statement parameterized read tools are admitted. `verify_unchanged()` is mandatory
after the MCP process exits.

DBHub is dev-only comparison infrastructure, never a candidate, runtime dependency, plugin,
or user workflow.

## Agent Perf

Each candidate provides a JSON file conforming to
`shared/agent-perf-workload-v1.schema.json`. The file names exactly one synthetic standard
`build.scale.standard` command with `{python}`, `{fixture_root}`, and `{output_root}`
placeholders and pins the CK-03 fixture revision, manifest/oracle digests, and workload
matrix digest. Shells, absolute/private paths, secret-like environment variables, alternate
profiled commands, and fewer than five unprofiled runs are rejected. Agent Perf wraps this
same command; it does not define a second workload.

Fixture generation time is excluded from candidate timing. Do not run production or growth
workloads in routine checks; those are explicit qualification-host operations.
