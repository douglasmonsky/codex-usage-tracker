# Adoption Hardening Roadmap

This roadmap covers the next phase after the `0.12.x` architecture repair. The project is now getting enough outside attention that the priority shifts from fast feature expansion to making first-run setup, support, diagnostics, and large-history behavior boring for new users.

## Current Signals

- GitHub interest has moved beyond personal-use scale: stars, forks, clones, and traffic are all growing.
- The project has already handled outside bug reports around Windows dashboard serving and large-history SQLite limits.
- The release cadence has been fast, so the next minor releases should tighten trust and support surfaces before adding more complex diagnostics.
- Current local gates are healthy: Ruff, MyPy, Tach, release checks, Agent Maintainer fast profile, and pytest pass.
- Main technical debt is no longer giant files, but there are still dense domains: `usage_drain`, `server`, dashboard APIs, and large integration tests.

## Operating Rules

- Keep `main` always releasable.
- Use one short-lived branch per reviewable capability.
- Prefer PRs even for solo-maintainer work so each change has a review artifact.
- Avoid stacking branches unless a later branch truly depends on an earlier one.
- Do not release every small branch. Release after a coherent group of user-facing improvements lands.
- Preserve privacy guarantees: no raw prompts, assistant messages, tool outputs, patch text, secrets, or private config values in stored snapshots, support bundles, screenshots, generated dashboards, or test fixtures.

## 0.13: Adoption Hardening

Goal: make first-time installs and bug reports easier for users who did not build the tool.

Branches:

- `feature/doctor-first-run-report`
  - Make `doctor` clearly report Python version, package version, Codex log discovery, tracker DB path, dashboard asset health, plugin registration state, and common Windows/browser pitfalls.
  - Add `--json` parity for any new fields shown in text output.
  - Acceptance: focused doctor tests plus installed-package smoke coverage.

- `feature/support-bundle-issue-flow`
  - Improve strict support bundle output for issue reports.
  - Add a short CLI hint showing which safe fields users can paste into GitHub issues.
  - Acceptance: privacy tests prove strict bundles do not leak raw prompts, outputs, full paths, tokens, or private config values.

- `test/installed-wheel-platform-smokes`
  - Strengthen wheel-level smoke tests for setup, dashboard generation, `serve-dashboard --help`, `doctor`, support bundle, and bundled dashboard assets.
  - Keep CI runtime reasonable by using synthetic logs and selected commands.
  - Acceptance: wheel smoke catches entrypoint and package-data regressions before release.

- `docs/first-five-minutes-onboarding`
  - Add a concise first-run walkthrough: install, setup, launch, verify, troubleshoot.
  - Include "what to do if the dashboard is empty" and "what to attach to an issue" sections.
  - Acceptance: README stays scannable; deeper details live in docs.

Release target:

- Ship `0.13.0` once the user-facing flow feels reliable.

## 0.14: Guided Diagnostics

Goal: turn powerful diagnostics into plain answers before exposing more raw charts.

Branches:

- `feature/guided-usage-summary`
  - Add a "What is driving my usage?" report across dashboard and CLI.
  - Prioritize threads, models, effort, cache misses, subagents, command/tool activity, and usage-drain signals.

- `feature/weekly-allowance-change-report`
  - Add a guided report explaining projected weekly credits, confidence bands, observed usage coverage, and caveats.
  - Avoid overclaiming; frame changes as local evidence, not universal allowance proof.

- `feature/thread-efficiency-report`
  - Add thread-level efficiency indicators: cost per visible call, cache behavior, cold resume signs, context pressure, and long-thread tradeoffs.

- `feature/diagnostics-refresh-diff`
  - Show what changed since the previous diagnostics refresh.
  - Keep this snapshot-based and on demand.

Release target:

- Ship `0.14.0` when at least two guided reports are useful end to end.

## 0.15: Reliability And Scale

Goal: make large histories and long diagnostics predictable.

Branches:

- `perf/large-history-refresh-benchmarks`
  - Add synthetic benchmark thresholds for setup, refresh, diagnostics refresh, and dashboard API payloads.

- `feature/diagnostics-refresh-progress`
  - Add progress/status for expensive diagnostics refreshes so users know whether work is running, stale, failed, or complete.

- `fix/resumable-diagnostic-snapshots`
  - Make failed diagnostic snapshot refreshes isolated and resumable by section.

- `test/parser-compat-fixtures`
  - Add focused parser fixtures for new Codex log shapes as users report them.

Release target:

- Fold remaining refresh-behavior hardening into the next adoption patch/minor after `0.15.0`.

## 0.16: Maintainability Ratchet

Goal: keep the project easy to change while adoption grows.

Branches:

- `refactor/usage-drain-subpackages`
  - Split usage-drain internals by spans, features, models, reports, charts, and allowance helpers.

- `refactor/server-api-boundaries`
  - Split server routing, static assets, diagnostics APIs, usage APIs, and response helpers.

- `refactor/xenon-b-ranked-modules`
  - Reduce the current B-ranked Xenon modules until `xenon --max-absolute B --max-modules A --max-average A src` can pass.

- `chore/expand-mypy-coverage`
  - Expand MyPy coverage in small safe slices.

Release target:

- These can land behind compatibility facades and may ship as `0.16.0` or be spread across smaller minors if that materially reduces release risk.

## 1.0 Readiness Bar

Do not call the project `1.0` until:

- First-run setup is boring on macOS, Windows, and Linux.
- The support-bundle issue flow is privacy-safe and easy to use.
- Dashboard and CLI JSON contracts are documented and stable.
- Diagnostics are useful but clearly caveated where inference is uncertain.
- Large-history refresh behavior is predictable.
- Several outside issue reports have been handled without emergency patch churn.
