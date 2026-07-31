# Agent-kernel synthetic fixtures

CK-03 fixtures are structural metadata only. They never read local Codex data
and never contain prompts, responses, reasoning, command or patch bodies, tool
output bodies, credentials, or absolute paths.

## Versioned formats

- Fixture profile: `codex-usage-tracker.synthetic-fixture-profile.v1`
- Source record revision: `agent-kernel-structural-v1`
- Manifest: `codex-usage-tracker.synthetic-fixture-manifest.v1`
- Oracle bundle: `codex-usage-tracker.synthetic-oracle-bundle.v1`
- Aggregate production shape:
  `codex-usage-tracker.production-shape-profile.v1`

CK-07A adds the corrected `tiny-v2` qualification fixture:

- source revision: `agent-kernel-structural-v2`;
- scenario sidecar:
  `codex-usage-tracker.synthetic-question-scenarios.v1`;
- oracle bundle: `codex-usage-tracker.synthetic-oracle-bundle.v2`; and
- manifest: `codex-usage-tracker.synthetic-fixture-manifest.v2`.

Its four compact base JSONL streams plus one 80-record semantic-mutation stream
contain adapter-ingestible structural events only. The manifest declares all
80 base-plus-mutation constructions, composed hashes, and asserted source and
published predicates. Question intent, normalized requests, independently
frozen canonical structural declarations, and required evidence live in
`question-scenarios.json`; independently derived rows and grades live in
`oracle-bundle.json`. No source JSONL record contains
`oracle_case`, expected rows, grades, grading/comparison output, answer caches,
body content, secrets, or absolute paths.

`scripts/generate_ck07a_fixture.py` deterministically rebuilds all 80 variants.
`tests.agent_kernel.fixtures.oracles.reference.evaluate_question_case` derives
answers without SQLite or Candidate A.
`tests.agent_kernel.fixtures.oracles.database_replay.evaluate_published_question_case`
uses one query-only database-v1 snapshot and does not import the reference
evaluator or expected output.

Each source is compact canonical JSON Lines: lexicographically sorted object
keys, UTF-8, no insignificant whitespace, and one LF terminator per record.
The deliberately malformed source contains one synthetic invalid line so every
candidate must report the same parse failure.

Normal active streams use contiguous chronological call clusters. Every
manifest source entry carries a conservative half-open structural-event time
hint plus `trusted`, `uncertain`, or `unavailable` confidence. Only
non-overlapping `trusted` hints support whole-source exclusion; uncertain,
window-independent control, malformed, deferred, empty, and no-timestamp
sources stay explicit. Named history windows are closed, so they overlap a
half-open hint when `hint.end_us > window.start_us` and
`hint.start_us <= window.end_us`. This additive inventory correction retains
the v1 manifest schema and structural revision while its canonical manifest
digest distinguishes corrected assets.

The generator writes into a private sibling staging directory and atomically
renames it only after all source, manifest, and oracle bytes succeed. It refuses
an existing destination. It keeps no candidate database schema, SQL, runtime,
MCP, or presentation dependency.

## Source-to-oracle reconciliation

The generator records each canonical serialized source record in a streaming
source ledger. Oracles are built from that ledger, not from profile
configuration in isolation:

- all 80 question variants are emitted records with distinct inputs, expected
  rows, formulas, plans, compiler/projection metadata, caveats, and selectors;
- each selector resolves to an emitted manifestation, revision, adapter
  version, record ordinal, and exact byte range;
- vertical-slice controls include the CK-02 allowance compatibility tuple,
  rate-card/publication records, late-parent hierarchy, and real tool identity;
- archive copy, replacement, truncation, and moving-tail phases are concrete
  before/after byte streams with occurrence mappings;
- named history counts are re-derived from emitted integer timestamps; and
- the production profile drives generation and validates declared stream
  aggregates, capability counts, cardinality histograms, storage/WAL
  attribution, and phase timings.

Publication uses same-filesystem sibling staging with exclusive no-replace
admission: macOS `renamex_np(RENAME_EXCL)`, Linux
`renameat2(RENAME_NOREPLACE)`, and Windows no-replace `os.rename`. Unsupported
platforms and filesystems fail closed. The race test proves that two concurrent
publishers yield exactly one complete winner and one non-destructive failure.

## Digest policy

All digests use SHA-256:

- source digest: exact source file bytes;
- oracle digest: complete canonical oracle-bundle bytes;
- manifest digest: canonical manifest bytes with `manifest_digest` omitted;
- tree digest: relative POSIX path, NUL, file bytes, NUL, in path order.

The checked-in tiny fixture is the only materialized corpus:

| Artifact | SHA-256 |
| --- | --- |
| Manifest | `91e0658f913c917bd8ce69fac9a1d75e881f41630eccc0f30f68bd9b6a972a35` |
| Oracle | `38787c3806be52a69ec03e7e8dcb0044b87dac4be826d620abf4cf34656da412` |
| Complete tree | `2321918c18652fc617882aef5f9c8584d3d6d73576037b516a2c9f9dcbc0f656` |

Independent processes with distinct hash seeds reproduced those exact bytes.
CI runs the same digest ratchet across its supported Python matrix.

The CK-07A structural-v2 identities are:

| Artifact | SHA-256 |
| --- | --- |
| Manifest bytes | `2098bfe5c920df4f8d4216baeecbde2ab572687f8da0f3e52a6db0e01ceb029a` |
| Manifest digest | `b6e8e5886482f59d36554db52dd30a834e7e1ca057b7fb54d04c9a558ffc354e` |
| Question scenarios | `6f26bd08536909a49740787e54b37974874cb7913463cc5c7801b06a9c841d63` |
| Oracle bundle | `cc7b5b6880f4085f32a5a55226854c3dd6108b6cbbb8110142511c52a2f1279f` |
| Complete tree | `cb19cfd5375366354da8ef9a6ef5eb957b5d7633b9d0e77c3192c97896781a4a` |

The v2 tree is 1,348,201 bytes because it adds the required 970,420-byte
question-scenario declaration sidecar. That new schema artifact is not a shared
response-byte ratchet. Comparable byte gates pass: source JSONL shrank from the
v1 corpus, the v2 oracle is within 25% of v1, and Candidate A's maximum encoded
response remains below the 20,480-byte 25%-headroom ceiling. Exact measurements
are in the CK-07A durable evidence.

## On-demand scales

```bash
.venv/bin/python -m tests.agent_kernel.fixtures.generator.cli \
  --profile tiny --check-committed

.venv/bin/python -m tests.agent_kernel.fixtures.generator.cli \
  --profile standard --output /path/to/new/fixture

.venv/bin/python -m tests.agent_kernel.fixtures.generator.cli \
  --profile production --output /path/to/new/manifest --manifest-only
```

`--manifest-only` still serializes and hashes every exact source record. It
does not estimate bytes; it differs only by not persisting the source files.
Fixture generation is excluded from product build timing.

Single unprofiled local qualification runs produced:

| Scale/mode | Calls | Elapsed | Exact source bytes | Records | Manifest SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| Tiny persisted | 100 | 26 ms | 244,757 | 339 | `91e0658f913c917bd8ce69fac9a1d75e881f41630eccc0f30f68bd9b6a972a35` |
| Small persisted | 10,000 | 688 ms | 10,658,480 | 23,311 | `cc3dba2b0109604b006ace5f97721d7d5ad4be400788422248e48411b5dd29fe` |
| Standard persisted | 100,000 | 6.819 s | 105,606,168 | 232,201 | `b5b938232e199793f49d7ab0bf67d360ea658f332f15e5d53449d4327c821f26` |
| Production manifest-only | 1,316,864 | 90.745 s | 1,392,996,507 | 3,056,541 | `a781398b8f7a471f1cb727ce6bda23a9e2d41046c26f3fc74354a99aec9869a9` |

The production oracle digest is
`b72a4febcf4150e450476a37f6ae1e282e96e84c837d5aec0b01aa76b15c4217`.
The 2.5-million-call growth profile remains on demand; its distribution is
validated algebraically and was not materialized after the standard slope
showed it would exceed the bounded interactive wait.

Agent Perf run `20260728T233155Z-630dbb79` attributed the largest application
share in one profiled standard workload to source-handle churn. That result is
diagnostic attribution only: CK-03 makes no comparative speedup claim because
the change was not measured with the repeated median, p95, maximum, and
coefficient-of-variation protocol required for performance evidence.
