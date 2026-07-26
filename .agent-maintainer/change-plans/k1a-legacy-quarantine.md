# Change Plan: K1A Legacy Quarantine

## Goal

Create the deliberately incomplete, non-publishable 0.26 integration skeleton
and remove every K1 path classified as `retire`, `transplant`, or unarchived
`historical` from normal agent search.

## Contract

- Preserve every K1 `keep` path.
- Remove exactly the 1,473 manifest-named non-keep paths after proving the
  worktree is clean.
- Retain source provenance only in the K1 manifest and immutable `v0.25.1` tag.
- Reject publication from integration and every K1A-K9 task ref.
- Permit only the K1A additions named by the scope checker.
- Keep the kernel skeleton importable without importing legacy code.
- Use synthetic fixtures only.

## Owned Paths

- `.github/workflows/ci.yml`
- `.github/workflows/publish.yml`
- `.codex-plugin/plugin.json`
- `.mcp.json`
- `AGENTS.md`
- `MANIFEST.in`
- `config/kernel-code-disposition-v1.json`
- `config/kernel-development-efficiency-v1.json`
- `docs/kernel-development-scope.md`
- `docs/roadmap/product-kernel-reset-execution.md`
- `justfile`
- `pyproject.toml`
- `scripts/check_kernel_scope.py`
- `scripts/check_release.py`
- `src/codex_usage_tracker/kernel/**`
- `tests/kernel/test_code_disposition_manifest.py`
- `tests/kernel/test_kernel_scope.py`
- every exact non-keep path in `config/kernel-code-disposition-v1.json`

## Validation

- contract-red K1A scope tests;
- exact keep/removal/addition inventory;
- kernel import and publication-ref rejection;
- K1A phase CI;
- retained release artifact tests and applicable release checks;
- build isolation and package-content inspection;
- clean detached reference status;
- secret, private-fixture, diff-target, and whitespace checks.

## Budget

- Maximum changed files: 1,600
- Maximum changed lines: 280,000

This budget authorizes the manifest-driven quarantine only. It does not
authorize K2 schema or product behavior.
