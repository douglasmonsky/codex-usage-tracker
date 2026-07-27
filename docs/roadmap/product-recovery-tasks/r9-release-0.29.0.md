# R9 — Qualify And Release 0.29.0

## Objective

Merge the release source through maintained CI, build one exact `0.29.0`
candidate from the resulting merged-main SHA, qualify those bytes through every
product surface, and publish only those verified artifacts.

## Depends On

R7 and R8.

## Owned Areas

- version and changelog;
- release qualification, stable contract, and artifact budgets;
- wheel and sdist;
- protected publication workflow evidence;
- final execution-ledger closure.

R9 contains no unrelated feature or refactor.

## Contract Added First

Add failing release contracts for:

- repository, package, plugin, MCP, skill, and docs version agreement;
- schema-v3 upgrade and rollback;
- exact six-tool catalog;
- required pre-merge R7 source scorecard and post-build exact-artifact
  scorecard;
- R6 browser qualification;
- R8 public docs;
- measured artifact budgets;
- build-once exact-byte promotion.

## Release Decision

- Do not publish stale `0.28.0` bytes to PyPI.
- Prepare `0.29.0` from the qualified recovery head.
- Preserve the historical `v0.28.0` source-release evidence.
- Only merged `main` or its exact tag may enter protected publication.
- Pre-merge local distributions are disposable previews and can never be
  promoted as release artifacts.
- Tags and production publishing require explicit maintainer approval.

## Required Sequence

1. Audit current `origin/main`.
2. Create `release/0.29.0`.
3. Apply only version, changelog, qualification, budget, and release wording.
4. Run the complete source, Console/browser, schema upgrade, rollback, privacy,
   release, and pre-merge R7 qualification gates. Any local distributions are
   non-promotable previews.
5. Complete one final stable-diff review.
6. Open the release PR, wait for maintained CI, and merge it.
7. Invoke the protected build-once workflow against the exact merged-main SHA.
   It creates wheel, sdist, release manifest, and durable workflow artifacts,
   then stops before registry or GitHub release upload.
8. Download those workflow artifacts, verify exact members, source bytes,
   hashes, sizes, manifest identity, and budgets, then install that exact wheel
   and its plugin locally.
9. Run the complete R7 fresh-task suite plus installed Console/browser,
   schema-upgrade, rollback, privacy, and package smokes against those exact
   bytes.
10. If any check fails, do not overwrite or rebuild the candidate. Fix through
    a new PR and merged-main SHA, then restart at the protected build step; the
    failed artifacts are never promoted.
11. After explicit approval, tag the exact qualified merged-main SHA and
    promote the stored artifacts by recorded hash through protected Trusted
    Publishing to TestPyPI, PyPI, and the GitHub release without rebuilding.
12. Verify TestPyPI, PyPI, GitHub, and a clean local download are byte-identical.
13. Run a clean public-installed fresh-task and Console smoke.
14. Close the ledger with public URLs, hashes, sizes, workflow, and scorecard.

## Parallel Execution

One release coordinator owns artifacts, Git state, versioning, PR, tags, and
publication.

After the exact candidate is immutable, explicitly authorized qualification
subagents may run isolated read-only lanes:

- Python and schema qualification;
- frontend and browser qualification;
- installed plugin/MCP/skill fresh-task qualification;
- artifact and public-document audit.

They may not rebuild artifacts, change the candidate, publish, tag, or modify
external state. Any accepted fix invalidates the candidate and restarts the
build-once sequence.

## Validation

- focused release contracts;
- complete `just vc`;
- deterministic assets;
- wheel and sdist exact checks;
- isolated upgrade from public `0.27.0`;
- schema-v3 rollback;
- R7 fixed prompt suite;
- installed browser smoke;
- privacy and secret scan;
- maintained CI;
- protected publication and public byte verification.

## Acceptance

- Exact qualified bytes are public.
- Public installation exposes the same plugin, MCP, and skill tested locally.
- Fresh-task outcomes meet release gates.
- PyPI, GitHub, and downloaded artifacts match.
- The roadmap and ledger close with no hidden remaining publication step.

## Handoff

The next roadmap begins from public `0.29.0` dogfood evidence. No post-release
feature is bundled into R9.
