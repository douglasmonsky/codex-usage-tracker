# Agent Maintainer Hardening Branch Roadmap

Current chunk: `refactor/content-index-persistence`

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
- Replace the placeholder leaf-level Tach inventory with enforceable package
  domain contracts, record the reviewed reports-to-allowance edge, and move
  shared command parsing into `core` to remove a store-to-diagnostics cycle.
- Configure Deptry with the package's first-party and development dependency
  model, remove five verified dead private helpers, and keep Vulture at 60%
  confidence with a reviewed whitelist for dynamic and public surfaces.
- Fix Zizmor's upstream workflow input, apply least-privilege workflow defaults,
  retain reviewed action tag pins with Dependabot updates, and enable pip-audit
  against a universal pinned runtime requirements file.
- Fix actionable Bandit URL, assertion, fallback, and subprocess findings; keep
  reviewed B105/B608 heuristics in a compact baseline so new findings still
  fail in hardening CI.
- Clear the remaining whole-source Pyright backlog and replace the narrow CI
  type-check surface with all of `src`.

## Branch Exit

The branch is ready for PR once the latest commit is pushed and CI confirms the
same hardening gates remotely.

## Follow-Up PRs

### 1. Stabilize Existing Full Profile

The pytest collection/import blocker, mechanical formatting blocker, and
whole-source Pyright backlog are cleared. All of `src` is now protected by the
CI Pyright command. Complexity and broad style debt remain separate refactor
work so the type gate stays fast and actionable.

### 2. Make Architecture And Dependency Checks Actionable

After tests and mechanical formatting are stable, make structural gates produce
useful review feedback.

- [x] Keep the now-green Tach domain contract in maintained validation and audit
  circular dependencies separately before enabling cycle blocking.
- [x] Triage `deptry` into three buckets: real unused dependencies, intentionally
  optional/runtime dependencies, and packaging/test-only dependencies. Commit
  configuration only with a short explanation.
- [x] Triage `vulture` similarly: delete true dead code, preserve public/CLI/MCP
  entry points with explicit allowlists, and avoid broad suppressions.

### 3. Security Hardening Pass

Once codebase imports and architecture checks are stable, move to security
findings.

- [x] Triage `bandit` findings. Start with medium SQL-construction warnings and URL
  handling; classify string-literal test fixtures separately from real issues.
- [x] Keep `gitleaks` enabled for the current tree and security-profile history
  scan, with the deleted synthetic Slack-token fixture path explicitly
  allowlisted after confirming the finding was not a real credential.
- [x] Enable `pip-audit` against the dedicated universal pinned runtime input
  in `requirements/audit.txt`.
- [x] Triage `zizmor` repo-specific config/invocation and enable the clean
  offline workflow audit in hardening CI.

### 4. Ratchet Large Python Files Down

After gates are trustworthy, start the actual refactor sequence. Use one PR per
module boundary and keep behavior covered by focused tests.

- Start with `src/codex_usage_tracker/cli/mcp_server.py`, because it directly
  contributed to context/tool-output confusion and is far over the file-length
  threshold.
  - [x] Extract asynchronous dogfood job state, cache fingerprints, and worker
    execution into a focused module without changing MCP tool contracts.
  - [x] Introduce a shared registration runtime and move allowance intelligence
    tools into their own module while preserving compatibility exports.
  - [x] Move filtered usage discovery, coverage, indexed-content search, and
    token-waste candidate tools into a focused registration module.
  - [x] Move goal-led investigation, hypothesis testing, action briefs, and
    strict evidence export into a focused orchestration module.
  - [x] Move dashboard/API, export, and local config tools into a focused module;
    the registration module is now
    below the configured file-length threshold.
- Split `src/codex_usage_tracker/reports/api.py` by report family before editing
  behavior; it is the largest source file in the raw baseline.
  - [x] Extract coverage, indexed-content discovery, pattern scans, and focused
    token-waste candidate reports behind compatibility re-exports.
  - [x] Extract hypothesis input normalization and family classification before
    splitting the larger evaluator engine.
  - [x] Extract filtered query and recommendation reports so hypothesis
    evaluators can depend on a concrete module instead of the facade.
  - [x] Extract hypothesis evaluators, result metrics, and shared agentic
    evidence compaction into independently sized modules.
  - [x] Extract investigation suggestions and goal-led agentic findings into a
    dedicated report family below both line thresholds.
  - [x] Extract action-brief construction and split goal/finding strategy from
    agentic report assembly so both modules remain under threshold.
  - [x] Extract investigation walk and strict evidence export; the remaining
    report facade is now below both configured line thresholds.
- Split `src/codex_usage_tracker/store/content_index.py` by ingestion, FTS,
  provenance, and query responsibilities.
  - [x] Extract content search, thread trace, and shared paging/snippet helpers
    while preserving the original facade exports.
  - [x] Extract parser/provenance row construction from refresh orchestration.
  - [x] Extract persistence and FTS synchronization behind focused helpers;
    the content-index facade is now below both configured line thresholds.
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
