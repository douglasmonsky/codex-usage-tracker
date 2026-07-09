# Generated Agent Maintainer Guidance

Generated from `[tool.agent_maintainer]` by
`python3 -m agent_maintainer guidance`. Do not edit by hand.
Human reference: `docs/agent-maintainer-guidance.md`.
Do not read it during normal coding unless changing guidance.

## Hard Rules

- Keep commits small, tested, and aligned with configured boundaries.
- Treat failing checks as design feedback before adding suppressions.
- Update source, tests, docs, and config together when behavior changes.
- Do not relax thresholds or architecture rules to make checks pass.

## Context Hygiene

- Check branch/worktree once at turn start and before staging.
- Read long guidance files only when starting fresh, after compaction,
 or when guidance/config changed.
- If already read in current unchanged context, use targeted `rg`
 for specific rules instead of re-reading whole guidance.
- Prefer `rg --files` or `git ls-files` for file discovery.
- Do not bulk-read generated/cache/binary paths:
  `__pycache__`, `*.pyc`, `.venv`, `venv`, `.verify-logs`, `.coverage`,
  `coverage.xml`, `htmlcov`, `mutants`, `build`, `dist`.
- Use `AGENT_MAINTAINER_WRITE_BYTECODE=true` or
  `AGENT_MAINTAINER_KEEP_MUTANTS=true` only when explicitly debugging
  those artifacts.

## Repo Contract

- Mode: `legacy-ratchet`
- Source roots: `src`
- Tests: `tests`
- Architecture: `tach` with Tach domain contracts
- If Tach policy changes, add or update an ADR under
  `docs/architecture/decisions/`.

## Blocking Limits

- Coverage floors: total `80%`, changed `90%`
- File length: `600` physical / `450` source lines
- Change budget blocks: `800` lines or `20` files
- New suppression budget: `3`
- Complexity: Ruff `10`, Xenon `B`
- Source-only changes without test-file changes: `blocked`

## Active Gates

- Secret scanning: gitleaks

## Failure Loop

- Keep chat updates summary-first: completed check, actionable failure,
 or plan change.
- Do not emit routine `still running` updates for expected long checks.
- Use `apply_patch` for manual edits; avoid heredoc rewrite commands.
- After a failed verifier or hook result, read the repair capsule or
 `.verify-logs/LAST_FAILURE.md` before changing code or config.
- Prefer run-scoped `context --log-dir ...` commands for failures.
- Expand only if needed:
 `python3 -m agent_maintainer context failures --limit 20`.
- Fix the root cause; do not lower thresholds or add broad suppressions.

## Required Commands

- Prefer shortest repo wrappers when present: `just vp` (precommit),
 `just v` (full), `just vc` (CI-equivalent),
 `just wg <run-id>`, `just wp <pr-number>`, `just wv <run-id>`.
- Readable forms remain valid: `just verify-precommit`,
 `just verify`, `just verify-ci`, `just wait-github <run-id>`,
 `just wait-pr <pr-number>`, `just wait-verifier <run-id>`.
- Normal finish fallback: `just vp` only when trusted
 hooks are unavailable, bypassed, or failure reproduction is needed.
- Trusted hooks already run `fast` after edits and `precommit`
 at stop; do not duplicate a same-state hook pass manually.
- Larger/shared changes: after coherent final state, run one broad
 local profile, usually `full`.
- Use `ci` locally instead of `full` when diff/base-ref,
 CI profile, or workflow behavior changed.
- Run both `full` and `ci` only when verifier/profile/CI-diff
 behavior is under test.
- Run `security` or `manual` when touching those gates, before release,
 or when explicitly requested.
- For GitHub Actions or long verifier jobs, use
 `just wait-github <run-id>`, `just wait-pr <pr-number>`,
 or `just wait-verifier <run-id>`
 so tools own polling.
- Run `just doctor` after setup, config, toolchain, hook,
 or initializer changes.

## Escape Hatches

- Prefer config or code fixes over one-off environment overrides.
- Use cohesive change plans for intentional large diffs; include a reason
  and verification plan.
- If a check is wrong, make the smallest fix to the check, config, or docs.
