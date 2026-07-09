# Agent Maintainer Hardening Branch Roadmap

Branch: `refactor/secret-scan-hardening`

## Goal

Adopt the latest Agent Maintainer ratchet and a small set of low-noise hardening
checks without mixing in broad Python refactors or large documentation cleanup.

## Completed Chunks

- Upgrade generated Agent Maintainer guidance and add local `just` wrappers.
- Add a latest-main ratchet baseline for existing file-length and structure debt.
- Enable configured `gitleaks` secret scanning with allowlists for ignored local
  artifacts and intentional fake-secret fixtures.
- Fix the publish workflow glob flagged by `actionlint`.
- Format TOML configuration with Taplo.
- Enable repo-configured `yamllint`.
- Add a repo-specific Markdown lint config and enable the gate with historical
  prose/layout rules disabled.
- Add CI hardening job for `actionlint`, `gitleaks`, `markdownlint`,
  `yamllint`, Taplo, and GitHub workflow schema validation.
- Fix pytest verifier imports by including the repository root in pytest's
  Python path.
- Run one mechanical `ruff format` PR to clear format gate without behavior
  changes.
- Enable Taplo as Agent Maintainer gate after formatting TOML configuration.
- Enable GitHub workflow schema validation with explicit `check-jsonschema`
  arguments.
- Re-run focused validation for the enabled optional gates.
- Add explicit root Tach module inventory and ADR so architecture checks report
  real dependency violations instead missing configuration.

## Branch Exit

This branch is ready for PR once the latest commit is pushed and CI confirms the
same hardening gates remotely.

## Follow-Up PRs

### 1. Stabilize The Existing Full Profile

First fix failures that prevent the full profile from being a useful signal.
These are not product refactors; verifier hygiene should be kept in small
mechanical PRs.

- Fix narrow Pyright errors already surfaced in `cli/main.py` and
  `context/reader.py`. These look like concrete typing issues, not broad strict
  mode migration.

### 2. Make Architecture And Dependency Checks Actionable

After tests and mechanical formatting are stable, make structural gates produce
useful review feedback.

- Fix actual `tach` boundary violations only after config is explicit.
- Triage `deptry` into three buckets: real unused dependencies, intentionally
  optional/runtime dependencies, packaging/test-only dependencies. Commit
  configuration only with a short explanation.
- Triage `vulture` similarly: delete true dead code, preserve public/CLI/MCP
  entry points with explicit allowlists, avoid broad suppressions.

### 3. Security Hardening Pass

Once the codebase imports and architecture checks are stable, move to security
findings.

- Triage `bandit` findings. Start with medium SQL-construction warnings and URL
  handling; classify string-literal test fixtures separately from real issues.
- Keep `gitleaks` enabled as the current-tree secret gate. Consider a separate
  history-scan PR only after confirming no real credentials are present and
  deciding how to handle historical false positives.
- Keep `pip-audit` disabled until the project has a pinned dependency input.
  Decide between a constraints file, lock export, or dedicated audit
  requirements file before enabling it.
- Triage `zizmor` with a repo-specific config/invocation. Do not enable as
  blocking until it audits local workflows without remote-fetch failures.

### 4. Ratchet Large Python Files Down

After gates are trustworthy, start the actual refactor sequence. Use one PR per
module boundary and keep behavior covered by focused tests.

- Start with `src/codex_usage_tracker/cli/mcp_server.py`, because it directly
  contributed to context/tool-output confusion and is far over the file-length
  threshold.
- Split `src/codex_usage_tracker/reports/api.py` by report family before editing
  behavior; it is the largest source file in the raw baseline.
- Split `src/codex_usage_tracker/store/content_index.py` by ingestion, FTS,
  provenance, and query responsibilities.
- Then address medium oversized modules surfaced by the latest file-length log:
  `allowance_intelligence/model.py`, `server/handler.py`, diagnostics modules,
  and CLI parser/main files.
- Keep each refactor PR below the normal change budget unless a cohesive change
  plan is created first.

### 5. Optional Strictness Later

These are useful but should wait until the above gates stop producing basic
noise.

- Tighten Markdown linting by re-enabling historical spacing/inline-HTML rules
  only in dedicated docs cleanup PRs.
- Consider `wemake` only after file-length and complexity ratchets have reduced
  the largest modules.
- Consider `interrogate` only if public API/docstring policy becomes a real
  product requirement.
- Consider mutation testing as a manual/release gate after core tests and
  complexity failures are under control.

## Validation

- `python3 scripts/check_release.py`
- `git diff --check`
- `python -m agent_maintainer guidance --check`
- Focused direct checks for each enabled optional gate.
