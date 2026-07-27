# R3 — Accelerate Cold Build And Incremental Refresh

## Objective

Reduce the production-shaped cold build from about 18 minutes to at most four
minutes while making ordinary append-only refresh sub-second and keeping reads
available.

## Depends On

R2.

## Owned Areas

- source discovery and cursor planning;
- parser and normalizer hot paths;
- ingestion orchestration;
- writer and index-build strategy;
- refresh lease, progress, recovery, and moving-tail tests;
- R3 benchmarks.

R3 does not edit schema contracts, query plans, MCP schemas, or Console files.

## Contract Added First

Add failing unprofiled benchmarks and lifecycle tests for:

- complete production-shaped build ≤240 seconds;
- ordinary append-safe tail ≤500 ms;
- bounded larger tail ≤2 seconds;
- no-change refresh performs no fact or rollup writes;
- browser or query cannot trigger refresh;
- `recent_30d`, `recent_90d`, and `complete` first-build source selection is
  deterministic against one captured UTC cutoff;
- every discovered source is cataloged and uncertain timestamps fail open into
  hydration rather than silently deferring data;
- coverage expansion hydrates whole sources monotonically without rebuilding
  already hydrated history;
- one active compatible worker is joined;
- lines appended during build are included before promotion;
- readers stay available on the committed generation.

## Implementation Order

1. Remove repeated cumulative counts from every parser batch.
2. Stop opening thousands of short writer transactions for an unpublished
   database.
3. Batch inserts and metadata updates.
4. Defer secondary index construction until bulk fact load completes.
5. Avoid repeated thread, turn, source, and stable-ID work within one stream.
6. Skip full JSON materialization where bounded structural extraction proves
   equivalent.
7. Make progress reflect parse, normalize, write, index, validate, and promote
   work truthfully.
8. Add bounded process parallelism only after global repeated work is removed.
9. Evaluate content-addressed per-source fact shards only if the required cold
   build still misses its gate.
10. Catalog deferred sources and apply a bounded whole-source hydration policy
    before parsing; never make row-prefix hydration part of the fact contract.

Every optimization changes one suspected cause, reruns the identical
unprofiled workload, and records before/after evidence. Profiler shares do not
count as speedup proof.

## Refresh Invariants

- Complete-line parsing only.
- Source replacement and truncation reconcile bounded rows.
- One durable owner and recoverable lease.
- No long `BEGIN IMMEDIATE` across parsing or derived-state work.
- After the R4 rollup-interface checkpoint, the fact-writing transaction
  invokes that frozen updater contract so appended facts and rollups publish
  atomically.
- A failed refresh never invalidates the active generation.
- No duplicate refresh is started by MCP, Console, or agent orchestration.
- A deferred source with a recent append is hydrated in full.
- Query, Console, and evidence reads cannot implicitly expand coverage.

## Parallel Execution

R3 may run in parallel with R4 and the R7 harness after R2.

R3 owns:

- `discovery`, `parser`, `normalize`, `ingest`, `writer`, `lease`, and watcher
  implementation and tests.

R4 owns query, rollup read plans, application, and MCP files. R7 owns runners
and installed qualification. If a required change crosses ownership, pause and
integrate through the coordinator rather than editing the other lane.

R3 may use the frozen R4 interface fixture before the implementation checkpoint.
R3 owns the ingestion call site; it must not edit the R4 updater module. The
coordinator verifies the integrated transaction after R4 publishes that module.

Within R3, multiple writing subagents are not recommended because parser,
normalizer, writer, and ingestion share the same transaction contract.
Read-only profiling or SQLite-plan audits may run in parallel.

## Validation

- focused parser/writer/ingest tests;
- accounting oracle;
- fault and recovery suite;
- synthetic scale matrix;
- production-shaped unprofiled cold run;
- production-shaped `recent_30d` first-use run and explicit expansion to
  `recent_90d` and `complete`;
- warm no-change and tail distributions;
- concurrent read test;
- database and lock-duration measurements;
- privacy checks;
- broader repository gate.

## Acceptance

- Required cold and warm targets pass.
- Progress never appears stuck while work advances.
- Refresh does not block committed reads.
- Reopen and query never rebuild.
- Moving-tail correctness remains exact.
- The recent-history first useful generation is at most 20 seconds and never
  claims complete history.
- R1 agent scenarios no longer spend minutes in refresh orchestration.

## Handoff

R5 receives stable refreshed facts. R7 records installed cold, warm, tail, and
concurrent-write outcomes.
