# Agent Maintainer Hardening Branch Roadmap

Current chunk: `chore/refresh-file-length-baseline`

## Goal

Adopt latest Agent Maintainer ratchets as low-noise maintained gates, without
mixing in broad Python refactors or unrelated documentation cleanup.

## Completed Chunks

- Upgrade generated Agent Maintainer guidance and local `just` wrappers.
- Add latest-main ratchet baseline for existing file-length structure debt.
- Enable configured `gitleaks` secret scanning with allowlists for ignored local
  artifacts and intentional fake-secret fixtures.
- Fix the publish workflow glob flagged by `actionlint`.
- Format TOML configuration with Taplo.
- Enable repo-configured `yamllint`.
- Add repo-specific Markdown lint config and enable the gate with historical
  prose/layout rules disabled.
- Add CI hardening job for `actionlint`, `gitleaks`, `markdownlint`,
  `yamllint`, Taplo, and GitHub workflow schema validation.
- Fix pytest verifier imports by including the repository root in pytest's
  Python path.
- Run one mechanical `ruff format` PR to clear the format gate without behavior
  changes.
- Enable Taplo Agent Maintainer gate for TOML configuration formatting.
- Enable GitHub workflow schema validation through explicit `check-jsonschema`
  arguments.
- Re-run focused validation for enabled optional gates.
- Add explicit root Tach module inventory ADR so architecture checks report real
  dependency violations instead of missing configuration.
- Add CI-maintained Agent Maintainer guidance drift and narrow Pyright gates for
  the source surface already cleaned on this branch.
- Refresh the file-length baseline against post-`0.17.2` `main` so existing
  oversized modules are tracked at their actual paths and counts. Keep the
  thresholds unchanged at 600 physical and 450 source lines.

## Branch Exit

The branch is ready for PR once the latest commit is pushed and CI confirms the
same hardening gates remotely.

## Follow-Up PRs

### 1. Stabilize Existing Full Profile

The pytest collection/import blocker, mechanical formatting blocker, and first
narrow source Pyright errors are cleared. The cleaned Pyright surface is now
protected in CI. Remaining type backlog is broader and should be handled in
focused typing PRs, not as a blanket strictness migration. Once the profile is
fast and consistently green, replace the narrow CI Pyright command with the
maintained Agent Maintainer profile.

### 2. Make Architecture And Dependency Checks Actionable

After tests and mechanical formatting are stable, make structural gates produce
useful review feedback.

- Fix actual `tach` boundary violations only after config is explicit.
- Triage `deptry` into three buckets: real unused dependencies, intentionally
  optional/runtime dependencies, and packaging/test-only dependencies. Commit
  configuration only with a short explanation.
- Triage `vulture` similarly: delete true dead code, preserve public/CLI/MCP
  entry points with explicit allowlists, and avoid broad suppressions.

### 3. Security Hardening Pass

Once codebase imports and architecture checks are stable, move to security
findings.

- Triage `bandit` findings. Start with medium SQL-construction warnings and URL
  handling; classify string-literal test fixtures separately from real issues.
- Keep `gitleaks` enabled as the current-tree secret gate. Consider a separate
  history-scan PR only after confirming no real credentials are present and
  deciding how to handle historical false positives.
- Keep `pip-audit` disabled until the project has pinned dependency input.
  Decide between a constraints file, lock export, or dedicated audit
  requirements file before enabling it.
- Triage `zizmor` repo-specific config/invocation. Do not enable it as blocking
  until it audits local workflows without remote-fetch failures.

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

These checks are useful, but should wait until the gates above stop producing
basic noise.

- Tighten Markdown linting by re-enabling historical spacing/inline-HTML rules
  only in dedicated docs cleanup PRs.
- Consider `wemake` only after file-length and complexity debt drops enough to
  make failures actionable.
- Consider `interrogate` only after deciding the project's public-docstring
  policy.
- Consider mutation testing only for narrow stable modules, not the full repo.

## Validation Pattern

For each PR:

1. Run the focused tool or test that proves the chunk.
2. Run the relevant Agent Maintainer profile when it is stable for that chunk.
3. Run `python scripts/check_release.py`.
4. Run `git diff --check`.
5. Push only the focused branch and let CI confirm the remote gate.
