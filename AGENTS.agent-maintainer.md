# Generated Agent Maintainer Guidance

This file is generated from `[tool.agent_maintainer]` by
`python3 -m agent_maintainer guidance`. Do not edit it by hand; update
configuration first, then regenerate it.

## Operating Intent

- Prefer small, coherent commits that keep maintenance feedback easy to review.
- Keep source, tests, documentation, and configuration moving together.
- Treat failing checks as design feedback before reaching for suppressions.
- Preserve the configured architecture boundaries instead of adding imports around them.
- Add or update tests for behavior changes unless tests are explicitly disabled.

## File Inspection Safety

- Prefer `rg --files` or `git ls-files` when enumerating files to inspect.
- Restrict bulk reads to relevant text/source globs instead of every file under a tree.
- Do not read generated or binary artifacts unless the task explicitly targets them:
  `__pycache__`, `*.pyc`, `.venv`, `venv`, `.verify-logs`, `.coverage`,
  `coverage.xml`, `htmlcov`, `mutants`, `build`, and `dist`.
- Agent Maintainer and hook subprocesses set `PYTHONDONTWRITEBYTECODE=1` by
  default. Set `AGENT_MAINTAINER_WRITE_BYTECODE=true` only when explicitly
  debugging bytecode-cache behavior.
- Manual Mutmut runs remove `mutants` after success. Set
  `AGENT_MAINTAINER_KEEP_MUTANTS=true` only when explicitly debugging
  mutation artifacts.
- When a broad command is unavoidable, exclude generated, binary, cache, and
  virtualenv paths before printing file contents.

## Active Configuration

- Mode: `legacy-ratchet`
- Source roots: `src`
- Test roots: `tests`
- Package paths: `src`
- Coverage source: `src`
- Architecture backend: `tach`
- Tests required: `true`
- Diagnostic artifacts: `enabled` at `.verify-logs`
- Source-without-test-change errors in profiles: `<none>`
- Source-only changes without test-file changes: `blocked`

## Architecture Policy Changes

- `tach.toml`, `tach.domain.toml`, and architecture boundary
 configuration are policy files.
- If a policy file changes, add or update a decision note under
 `docs/architecture/decisions/`.
- The note must explain why the policy change is intentional and why
 it is not architecture drift.
- Prefer refactoring code to preserve an existing boundary before
 changing the boundary.

## Verification Flow

- Trusted agent hooks normally run fast checks after edits and the precommit profile
  before completion.
- Run the precommit profile manually when hooks are unavailable, after bypassing hooks,
  or when reproducing a hook failure:
  `python3 -m agent_maintainer verify --profile precommit`.
- Run the full profile before merging larger changes or changing shared verifier logic:
  `python3 -m agent_maintainer verify --profile full`.
- After changing `[tool.agent_maintainer]`, run
  `python3 -m agent_maintainer guidance` and `python3 -m agent_maintainer doctor`.

## Thresholds To Preserve

- Total coverage floor: `80%`
- Changed-code coverage floor: `90%`
- File length limits: `600` physical lines, `450` source lines
- File length baseline: `.agent-maintainer/file-length-baseline.json`
- Change budget warnings: `300` lines or `8` files
- Change budget blocks: `800` lines or `20` files
- Cohesive-change override: `disabled`; allowlist `<none>`; max `2000` lines / `40` files
- New suppression budget: `3`
- Ruff McCabe complexity: `10`
- Xenon complexity: absolute `B`, modules `A`, average `A`
- Pyright mode: `standard`
- Interrogate floor: `80%`
- Folder Python-file warning/block thresholds: `20` / `40` (block active in fresh-strict)
- Structure hint patterns are advisory refactor prompts; split by responsibility when a folder no longer has one clear boundary.

## Optional Gates

- pip-audit: `disabled`
- Mutmut: `disabled`
- Semgrep: `disabled`
- OSV Scanner: `disabled`
- Trivy: `disabled`
- Python SBOM: `disabled`
- License checking: `disabled`
- Secret scanning: `disabled`
- wemake-python-styleguide: `disabled`
- Interrogate: `disabled`
- Markdown linting: `disabled`
- YAML linting: `disabled`
- TOML formatting: `disabled`
- Schema validation: `disabled`

## Escape Hatches

- Prefer config changes over one-off command drift when repository layout changes.
- Keep temporary CLI or environment overrides out of committed config unless they are policy.
- Use `require_tests = false` only for repositories that intentionally have no tests.
- Use `allow_source_without_test_change = true` only when existing tests already cover the change.
- If a check is wrong, make the smallest correction to the check, config, or docs.
