# CK-03 — Build shared synthetic fixtures and truth oracles

**Status:** Completed
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Produce one deterministic source generator and correctness oracle for
all candidates and final qualification.

**Why:** Candidate-specific fixtures would make performance and correctness
comparisons meaningless.

**Controls:** CK-01/CK-02, `QUALIFICATION_PLAN.md`,
`PHYSICAL_ARCHITECTURE_BAKEOFF.md`.
**Dependencies:** CK-02.

**Scope and expected files:**

- `tests/agent_kernel/fixtures/generator/**`;
- tiny hand-auditable fixtures;
- small/standard/production/growth manifests generated on demand;
- accounting, lifecycle, evidence, source-lifecycle, question-answer, and
  crash-state oracle modules;
- aggregate production-shape profile schema;
- deterministic fixture CLI.

**Schema/API changes:** Fixture/oracle formats only.
**Non-goals:** Reading real logs, storing raw content, candidate schema.

**Invariants:** Same seed/config produces identical source bytes/manifests;
scale uses same semantic cases; expected results derive independently from
candidate SQL; no private values/paths.

**Tests/benchmarks:** Digest reproducibility on two processes/Python versions,
tiny hand audit, generator time/bytes, manifest completeness, all question
oracle references.

**Acceptance:** All five bake-off slices and every Foundation/Cutover question
have truth cases; 100k and 1.316M fixtures reproduce exact declared
distributions; fixture generation is excluded from product timing.

**Failure/rollback:** Delete generated artifacts, keep generator source. Do not
patch candidates around an oracle error; fix and rerun all candidates.

**Cleanup/docs:** Record fixture revision/digest policy in qualification docs.

## Implementation evidence

- Fixture revision `agent-kernel-structural-v1` generates deterministic
  structural-only JSONL for tiny, small, standard, production, and growth
  profiles. The checked-in tiny corpus contains 100 canonical calls, 339 source
  records, and 244,657 exact source bytes.
- The tiny manifest, oracle, and complete-tree SHA-256 digests are
  `78003a7cfdee8beb1a263b3027fec162a612352be6fbefd13a65e821640bc7ae`,
  `9f78b8f87c17ef5e98810be6a4a01f4a13bfc055ac8eb74c9f147a7087d8e41b`,
  and `e6caa8bc1ff642018f21f6638dd69c6c704bdecdda362adc41daff021618799a`.
  Independent Python 3.14 processes with distinct hash seeds reproduce those
  exact bytes; the supported Python matrix repeats the digest ratchet in CI.
- The oracle bundle covers all five bake-off slices, all 80 CK-01 oracle IDs,
  four-class token accounting and missingness, lifecycle ordering, evidence
  pagination/selectors, source replacement/truncation/copy behavior, and nine
  publication crash boundaries.
- Every question variant is an emitted source record with distinct inputs,
  explicit expected rows, plan/compiler/projection metadata, caveats, and
  selectors. Independent reconciliation re-derives its formulas and verifies
  every selector against an exact manifestation, revision, record ordinal,
  adapter version, and byte range.
- Emitted control records cover the CK-02 allowance compatibility tuple,
  rate-card/publication facts, late-parent hierarchy, real tool identity, and
  every vertical slice. Archive-copy, replacement, truncation, and moving-tail
  transitions are materialized as before/after byte streams with occurrence
  mappings, while named history selections are counted from emitted integer
  timestamps.
- The production-shaped profile validates its schema, capability counts,
  cardinality histograms, storage/WAL attribution, phase timings, and declared
  stream aggregates. Atomic publication uses same-filesystem sibling staging
  with macOS `renamex_np(RENAME_EXCL)`, Linux
  `renameat2(RENAME_NOREPLACE)`, and Windows no-replace `os.rename`; unsupported
  platforms fail closed. Adversarial tests prove lock ownership, late
  destination preservation, exactly one winning writer, and leak-free failure.
- A persisted 100,000-call standard fixture generated 232,201 records and
  105,606,168 source bytes in 8.493 seconds. The exact manifest-only
  production profile streamed 1,316,864 calls, 3,056,541 records, and
  1,392,996,507 source bytes in 97.798 seconds without persisting the
  approximately 1.4 GB corpus.
- Agent Perf run `20260728T233155Z-630dbb79` identified source-handle churn as
  the largest application hotspot in one profiled standard workload. This is
  diagnostic attribution only; CK-03 makes no comparative speedup claim because
  the change was not measured with the required repeated median, p95, maximum,
  and coefficient-of-variation protocol.
- Post-R7 adversarial qualification passed 14 reconciliation tests in 0.30
  seconds; the combined generator and reconciliation qualification passed 19
  tests in 0.69 seconds.
- Qualification on `origin/main` `c90da147b7779590a8885e33d561957aba38c6c9`
  passed 82 focused tests in 1.70 seconds and the broad `just v` gate with
  528 tests in 64.93 seconds, plus Ruff, MyPy, Pyright, scope, deterministic
  assets, frontend, maintainability, and release-safety checks.

## Deviations and residual risks

- The 2.5-million-call growth profile remains generated on demand. Its exact
  distribution is validated algebraically, but it was not materialized after
  the standard-profile slope showed it would exceed the bounded interactive
  wait.
- Production qualification used exact streaming serialization and hashing in
  manifest-only mode; it did not persist the approximately 1.4 GB source tree.
  The standard profile proves persisted and manifest-only generation share the
  same serialization path.
- CK-03 freezes candidate-independent expected rows and formula metadata.
  CK-04 must additionally prove each physical candidate reconciles every
  formula and selector against the generated source records; these fixtures do
  not admit candidate SQL or a physical schema.
- Final review produced **9 findings; 9 accepted and resolved**.
  Reviewer-token attribution is **pending** because the required `strict` usage
  command was unavailable; tokens per accepted finding remain pending. The
  measurement was not retried.

**Suggested commits:**

1. `test: add agent-kernel source fixture generator`
2. `test: add accounting lifecycle and evidence oracles`
