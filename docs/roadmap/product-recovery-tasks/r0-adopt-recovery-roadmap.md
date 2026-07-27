# R0 — Adopt The Product Recovery Roadmap

## Objective

Replace the completed Product Kernel Reset as active authority with the
`0.29.0` Product Recovery Roadmap. Preserve the reset as historical evidence
and record the incomplete `0.28.0` publication truthfully.

## Depends On

None.

## Owned Files

- `AGENTS.md`
- `docs/roadmap/product-recovery.md`
- `docs/roadmap/product-recovery-execution.md`
- `docs/roadmap/product-recovery-tasks/**`
- status notices in:
  - `docs/roadmap/product-kernel-reset.md`
  - `docs/roadmap/product-kernel-reset-execution.md`
- `scripts/check_kernel_scope.py`
- `tests/kernel/test_kernel_scope.py`

## Contract Added First

Add a fail-closed scope contract listing every recovery roadmap file before
creating those files. The focused scope test must fail because the new
allowlist is absent, then pass after the exact inventory is added.

## Required Work

1. Verify `origin/main`, repository version, schema version, `v0.28.0`, GitHub
   release state, and public PyPI latest.
2. Record that K0–K15 completed.
3. Record K16 as superseded with a GitHub source release but no public PyPI
   `0.28.0` package.
4. Add the active roadmap, execution ledger, and R0–R9 packets.
5. Point `AGENTS.md` to the new authority.
6. Preserve the reset roadmap in place to avoid breaking historical links.
7. Preserve the paused public-doc and thread-label worktrees.
8. Run documentation, scope, release, and diff checks.
9. Complete one final read-only review after the diff is stable.

## Non-Goals

- No product code.
- No schema or contract change.
- No package version bump.
- No late `0.28.0` publication.
- No deletion of branches, worktrees, databases, or historical roadmaps.

## Parallel Execution

R0 is coordinator-owned and should not use parallel writing agents. A
read-only reviewer runs only after primary validation. Later task packets may
name parallel lanes once R0 merges.

## Acceptance

- One active roadmap authority is unambiguous.
- Every task has scope, ownership, dependencies, validation, and parallel
  boundaries.
- Existing reset links remain valid.
- Scope inventory fails closed for unlisted recovery files.
- Public release state is accurate.
- Documentation-only gates pass.

## Handoff

Record the R0 merge SHA in the execution ledger. R1 must base from that SHA.
