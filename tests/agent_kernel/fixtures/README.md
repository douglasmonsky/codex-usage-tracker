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

Each source is compact canonical JSON Lines: lexicographically sorted object
keys, UTF-8, no insignificant whitespace, and one LF terminator per record.
The deliberately malformed source contains one synthetic invalid line so every
candidate must report the same parse failure.

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
| Manifest | `a599cf149783af04d861699b0ff587a169f20dec4d372e4ffbe3f21c51995817` |
| Oracle | `9f78b8f87c17ef5e98810be6a4a01f4a13bfc055ac8eb74c9f147a7087d8e41b` |
| Complete tree | `a5bd281d7553836d952b1930196a3ddfadceae00b8ff0425695bb26c433b20cd` |

Python 3.13 and 3.14 independently reproduced those exact bytes. CI runs the
same digest ratchet across its supported Python matrix.

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
| Tiny persisted | 100 | 30 ms | 244,657 | 339 | `a599cf149783af04d861699b0ff587a169f20dec4d372e4ffbe3f21c51995817` |
| Small persisted | 10,000 | 1.055 s | 10,658,480 | 23,311 | `114f382cfc31c56908a0f97ac1ff37533185874262cefb00dfed9ccb05cff27d` |
| Standard persisted | 100,000 | 8.493 s | 105,606,168 | 232,201 | `c72618751298697f0178633c256cb20bbd9f53917db494a20b712856cacf8e1f` |
| Production manifest-only | 1,316,864 | 97.798 s | 1,392,996,507 | 3,056,541 | `d1a1b043afb8eda64c35db402470fe46be35accd2e63f85454bb942dd6a72223` |

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
