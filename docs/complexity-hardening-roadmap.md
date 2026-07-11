# Complexity Hardening Roadmap

Status: in progress

## Goal

Clear the current Xenon C/E function backlog without lowering the configured
B/A/A thresholds, then enable Xenon as a maintained CI gate. Triage Pylint into
low-noise correctness/maintainability checks instead of attempting a cosmetic
full-tree cleanup.

## Baseline

- Xenon: 21 C/E-ranked functions, including one E-ranked function in
  `reports/agentic_evidence.py`.
- Pylint: 9.12/10 across `src`, with broad historical convention and design
  findings.
- Existing required gates remain unchanged: Ruff, Mypy, whole-source Pyright,
  Tach, Deptry, Vulture, Bandit, pip-audit, workflow/security checks, package
  build, and the full test suite.

## PR Sequence

### 1. Agentic Evidence

- [x] Lock compact evidence row and summary behavior with direct tests.
- [x] Split `_compact_agentic_evidence_row` into field-family helpers.
- [x] Replace `_agentic_evidence_summary` branch accumulation with declarative
  metric specifications and bounded reducers.
- Exit: both functions rank B or better and report/MCP contracts are unchanged.

### 2. Agentic Report Assembly

- [x] Reduce `build_agentic_investigation_report` and
  `build_action_brief_report` through focused finding/section builders.
- [x] Reduce investigation export, shell-churn hypothesis, and dogfood payload
  compaction through typed/declarative helpers.
- Exit: all report-family functions rank B or better with report and MCP tests
  green.

### 3. Content Indexing

- [x] Reduce content snippets and source-file extraction with explicit parsing
  and clipping helpers.
- [x] Split serial source indexing into read, accumulate, flush, and FTS phases.
- [x] Simplify shell/path token classification without changing privacy-safe
  path identities.
- Exit: content query/extract/index/event functions rank B or better with
  incremental, parallel, FTS, and MCP content tests green.

### 4. Waste Candidate Diagnostics

- [x] Reduce repeated-file, shell-churn, and large-low-output candidate builders
  through shared metric and explanation helpers.
- Exit: all candidate functions rank B or better and diagnostic payload schemas
  remain unchanged.

### 5. Allowance And Isolated Utilities

- [x] Reduce allowance analysis/readiness and nonparametric statistical branch
  complexity while preserving evidence grades and exact test results.
- [x] Reduce doctor formatting and command-wrapper classification.
- Exit: every remaining C/E function ranks B or better.

### 6. Maintained Gates

- [x] Add Xenon B/A/A to hardening CI only after the full source tree passes.
- [x] Audit Pylint messages into correctness, maintainability, and convention
  groups.
- [x] Enable a reviewed low-noise Pylint selection or changed-code ratchet; do
  not add broad suppressions to manufacture a green full-tree score.
- [ ] Run the full CI, security, package, and release validation matrix.

The 2026-07-11 Pylint audit counted 1,448 default findings. Most were legacy
convention or broad design signals already owned by Ruff, file-length, Xenon,
Tach, or focused refactors: 342 missing function docstrings, 270 duplicate-code
reports, 229 too-many-argument reports, 184 line-length reports, and 120
useless-import-alias reports. The maintained Pylint gate now selects fatal and
error messages plus a reviewed set of high-signal control-flow, exception,
subprocess, finite-number, and comparison checks. The eight findings exposed by
that selection were fixed in code. This is repository-level configuration, not
inline suppression, and the historical audit remains available for future
advisory cleanup.

The complete source tree also passes the configured Xenon B/A/A gate. That
result closes the original 21-function C/E backlog and makes complexity drift a
maintained hardening failure instead of a periodic advisory scan.

## Validation Pattern

Each refactor PR must:

1. Add or identify direct behavior-lock tests before changing a hotspot.
2. Run Xenon against the touched module and the complete source tree.
3. Run focused tests plus whole-source Pyright, Ruff, file-length, release, and
   whitespace checks.
4. Merge only after the remote CI matrix is green.

## Non-Goals

- Lowering Xenon thresholds or baseline-suppressing current C/E functions.
- Mass docstring, naming, or formatting churn for Pylint score improvement.
- Combining feature work with complexity refactors.
- Changing MCP, API, CLI, dashboard, or persisted payload contracts.
