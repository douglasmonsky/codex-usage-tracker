# MCP-First Pivot Execution Ledger

This ledger is the durable handoff for the
[MCP-first pivot](mcp-first-pivot.md). Update the applicable entry in the same
commit as each roadmap task.

## Entry Format

```markdown
## Task N - Name
- Status: planned | active | blocked | complete
- Branch:
- Commits:
- Focused verification:
- Full verification:
- Deviations from plan:
- Follow-up risks:
```

## Task 1 - Record the pivot baseline and freeze dashboard surface growth

- Status: complete
- Branch: `pivot/1-establish-program`
- Commits: `3488d7a` (`docs: add MCP-first pivot design and roadmap`);
  `9a0d6ce` (`docs: establish MCP-first pivot program`)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md" ".agent-maintainer/change-plans/*.md"`; `git diff --check`
- Deviations from plan: Approved design and implementation roadmap were adopted
  in a preliminary documentation commit to isolate their 4,209-line reviewed
  content from the Task 1 baseline changes.
- Follow-up risks: The release sequence assumes the published baseline remains
  `0.21.0`; shift all planned minors together if that changes before execution.

## Task 2 - Make public product and storage statements internally consistent

- Status: complete
- Branch: `pivot/2-position-product`
- Commits: `docs: position MCP as the primary product` (this commit)
- Focused verification: `python -m pytest tests/packaging/test_public_docs.py tests/cli/test_cli_release.py -q`; `python scripts/check_release.py`
- Full verification: `npx markdownlint-cli2 README.md "docs/**/*.md"`; `git diff --check`
- Deviations from plan: The local Task 2 branch is intentionally stacked on the
  reviewed Task 1 commits because pushing and merging are outside this task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after Task 1
  merges; do not drop the Task 1 baseline and review-fix commits.

## Task 3 - Introduce a declarative MCP tool catalog and profiles

- Status: complete
- Branch: `pivot/3-mcp-tool-catalog`
- Commits: `refactor: catalog MCP tools by profile` (this commit)
- Focused verification: `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/interfaces/mcp src/codex_usage_tracker/cli/mcp_runtime.py`; `python -m ruff check src/codex_usage_tracker/interfaces/mcp tests/mcp`; `git diff --check`
- Deviations from plan: The local Task 3 branch is intentionally stacked on the
  reviewed Task 1 and Task 2 commits because pushing and merging are outside
  this task. The installed compatibility server remains the active legacy
  runtime; profile-selected server activation is deferred to its roadmap task.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Core tools intentionally raise
  `CoreToolNotImplemented` until their service tasks land.

## Task 4 - Define shared MCP evidence contracts

- Status: complete
- Branch: `pivot/4-mcp-evidence-contracts`
- Commits: `feat: define MCP evidence contracts` (this commit)
- Focused verification: `python -m pytest tests/core/contracts tests/core/test_json_contracts.py -q`; `python -m pytest tests/mcp/test_tool_registry.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/core/contracts`; `python -m ruff check src/codex_usage_tracker/core/contracts tests/core/contracts`; `git diff --check`
- Deviations from plan: The local Task 4 branch is intentionally stacked on the
  reviewed Tasks 1-3 commits because pushing and merging are outside this task.
  `ToolDataClass` moved to the core contract layer and is re-exported downward
  by the MCP interface model so core never imports `interfaces` and the alias
  cannot drift.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later core tools must use the registered envelope and
  evidence schemas without weakening finite-number or payload-budget checks.

## Task 5 - Add request models and shared source/accounting context builders

- Status: complete
- Branch: `pivot/5-request-context`
- Commits: `feat: build shared analysis request context`;
  `fix: harden analysis request context validation`;
  `fix: normalize invalid database context errors` (this commit)
- Focused verification: `python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q`
- Full verification: `python scripts/benchmark_dashboard_routes.py --sizes 100000 --iterations 3 --skip-compression --enforce-thresholds --output-dir /private/tmp/pivot-context-after-final`; `python -m pyright src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py`; `python -m ruff check src/codex_usage_tracker/application src/codex_usage_tracker/store/api.py tests/application tests/store/test_store_dashboard_queries.py`; `git diff --check`
- Deviations from plan: The local Task 5 branch is intentionally stacked on
  the reviewed Tasks 1-4 commits because pushing and merging are outside this
  task. The shared context query opens the existing database in read-only mode
  and computes all scoped physical, canonical, coverage, revision, and freshness
  facts in one explicit transaction and one aggregate SQL statement. The route
  benchmark was not repeated for the review fix because its SQL body and every
  valid-file execution path remained byte-for-byte unchanged.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Later interface adapters may accept `record` as a
  compatibility alias, but application `EvidenceRequest` remains canonical on
  `record_id`.

## Task 6 - Implement stable status and capabilities use case

- Status: complete
- Branch: `pivot/6-stable-status`
- Commits: `f39e152` (`feat: add stable MCP usage status`);
  `fix: report exact status freshness thresholds` (this commit)
- Focused verification: `python -m pytest tests/application/test_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/core/test_conversational_readiness.py -q`; `python -m pytest tests/application/test_requests.py tests/application/test_context.py tests/store/test_store_dashboard_queries.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/application/status.py src/codex_usage_tracker/interfaces/mcp/core_tools.py`; `python -m ruff check src/codex_usage_tracker/application/status.py src/codex_usage_tracker/application/requests.py src/codex_usage_tracker/interfaces/mcp/core_tools.py src/codex_usage_tracker/interfaces/mcp/registry.py tests/application/test_status.py tests/mcp/test_tool_profiles.py`; `git diff --check`
- Deviations from plan: The historical full/developer `usage_status` already
  delegated to dashboard status behavior through the profile registry, so no
  compatibility-module change was needed. `StatusRequest` gained additive
  local path and profile fields to keep the application and adapter seams
  deterministic and testable. Review follow-up restricted freshness thresholds
  to whole seconds and made the returned context use the exact adjusted
  freshness contract emitted in the result.
- Follow-up risks: Rebase or recreate the branch from updated `main` after the
  preceding tasks merge. Status reports existing readiness and persistent
  service probes but deliberately does not claim current-task MCP exposure.

## Task 7 - Introduce the generic job facade over existing registries

- Status: complete
- Branch: `pivot/7-job-facade`
- Commits: `refactor: unify usage job status` (this commit)
- Focused verification: `python -m pytest tests/jobs tests/server/test_analysis_jobs.py tests/server/test_diagnostic_jobs.py tests/server/test_refresh_jobs.py tests/server/test_server_usage_refresh.py tests/server/test_server_allowance_v2.py tests/server/test_compression_routes.py tests/compression/test_jobs.py tests/cli/test_mcp_integration.py -q`; existing-only baseline comparison: `python -m pytest tests/server/test_analysis_jobs.py tests/server/test_refresh_jobs.py tests/server/test_server_usage_refresh.py tests/server/test_diagnostic_jobs.py tests/server/test_compression_routes.py tests/compression/test_jobs.py tests/cli/test_mcp_integration.py -q`
- Full verification: `python -m pyright --pythonpath "$(command -v python)" src/codex_usage_tracker/jobs src/codex_usage_tracker/server/usage_refresh.py src/codex_usage_tracker/server/analysis_jobs.py src/codex_usage_tracker/server/compression_routes.py src/codex_usage_tracker/cli/mcp_dogfood.py src/codex_usage_tracker/cli/mcp_server.py`; `python -m ruff check --no-cache` and `python -m ruff format --check --no-cache` over all touched Python source and tests; `git diff --check`
- Deviations from plan: Dogfood job records are created in
  `cli/mcp_server.py`, not `cli/mcp_dogfood.py`, so the creation point received
  one additive registration call while lifecycle and historical payloads stayed
  in the existing helper module. Compression registration remains route-local
  because its registry lives in the pre-existing compression package, which
  was outside this task's declared mutation list.
- Follow-up risks: The facade is intentionally observational and process-local;
  later roadmap tasks own launch policy, unified persistence, recovery, TTL,
  cleanup, and the public core job-status adapter.

## Task 8 - Implement core refresh and generic job-status tools

- Status: complete
- Branch: `pivot/8-core-refresh-jobs`
- Commits: `feat: add core refresh and job tools` (this commit)
- Focused verification: `python -m pytest tests/application/test_refresh.py tests/application/test_job_status.py tests/mcp/test_tool_profiles.py tests/cli/test_mcp_integration.py tests/store/test_store_large_batches.py -q`
- Full verification: Task 7 facade regression plus
  `tests/store/test_store_sources.py tests/store/test_store_dashboard_mcp.py`;
  Pyright on the new application services and core adapter; Ruff check/format
  on all touched Python files; `git diff --check`.
- Deviations from plan: The application owns a small process-local async
  coordinator rather than importing the legacy server registry. Coordinators
  are weakly shared per injected `JobService`, so active equivalent requests
  deduplicate without retaining test services or contaminating later tests.
- Follow-up risks: Refresh jobs remain intentionally process-local. Later
  roadmap tasks own durable recovery/retention; this task adds no persistence,
  schema, dependency, or legacy payload change.

## Task 9 - Implement the canonical query request and application service

- Status: complete
- Branch: `pivot/9-canonical-query`
- Commits: `7449ec2` (`feat: add canonical usage query service`);
  `fix: harden canonical query semantics` (this commit)
- Focused verification: `python -m pytest -p no:cacheprovider -p no:tach tests/application/test_query.py tests/application/test_query_validation.py tests/core/test_json_contracts.py tests/store/test_store_dashboard_queries.py -q` (63 passed)
- Full verification: focused verification plus
  `tests/application/test_requests.py tests/reports/test_query_exports.py tests/cli/test_mcp_integration.py`
  (88 passed); shared subagent-predicate regression
  `tests/store/test_subagent_usage_queries.py` (10 passed); Pyright on the three
  canonical query application modules (0
  errors); Ruff check and format check on all touched Python files;
  `git diff --check`.
- Deviations from plan: The authoritative typed `QueryRequest` lives in
  `application.query_models` and is re-exported from `application.requests`.
  Estimate-only queries use truthful entity-identity ordering because cost and
  credit estimates are attached through established pricing helpers after the
  bounded canonical SQL query; explicit sorting by those derived estimates is
  rejected. `reports/api.py` required no change because legacy
  `build_query_report()` behavior remains intact.
- Follow-up risks: Aggregates containing multiple pricing models or service
  tiers report cost and credit as unknown with zero coverage rather than
  presenting a misleading blended estimate. A later task may add per-model
  pre-aggregation when partial mixed-group coverage is needed.

## Task 10 - Define the analysis-goal catalog and strategy protocol

- Status: complete
- Branch: `pivot/10-analysis-catalog`
- Commits: `refactor: catalog usage analysis strategies` (this commit)
- Focused verification: analytics catalog/protocol tests plus existing agentic,
  evidence, recommendation, and subagent report regressions.
- Full verification: Pyright on `analytics/`; Ruff check and format on touched
  files; diff/privacy review.
- Deviations from plan: Compatibility strategies retain existing algorithms at
  existing boundaries, use default paths only in `analyze()`, and preserve legacy
  summary/schema provenance without reinterpreting incompatible evidence.
- Follow-up risks: Task 11 owns canonical execution/job orchestration and fuller
  conversion of compatibility evidence into the analysis-v2 result contract.
  Comparison goals fail closed with `comparison_algorithm` unavailable until a
  Task 11 strategy explicitly consumes both canonical timestamp windows.

## Task 11 - Implement the canonical analysis application service

- Status: complete
- Branch: `pivot/11-analysis-service`
- Commits: `feat: orchestrate evidence-backed usage analysis` (this commit)
- Focused verification: analysis, analytics, JSON contracts, jobs, server jobs, and report regressions.
- Full verification: Pyright; Ruff check/format; release checker; diff/privacy review.
- Deviations from plan: Jobs use a bounded process-local semantic index; comparison goals remain fail-closed.
- Follow-up risks: Task 12 owns transport serialization; job persistence remains out of scope.

## Task 12 - Add the core query and analysis MCP tools

- Status: complete
- Branch: `pivot/12-core-query-analysis`
- Commits: `4dcbeb7`, `2f11833`
- Focused verification: core query/analysis transports, default profile identity,
  CLI compatibility, and application regressions; 69 tests passed.
- Full verification: targeted Pyright and Ruff; format check; release checker;
  skill-mirror byte comparison; diff/privacy review.
- Deviations from plan: transport implementation lives in a focused private module
  and is re-exported from `core_tools.py` so both files remain within source limits.
- Follow-up risks: analysis jobs remain process-local; durable persistence is deferred.

## Task 13 - Implement canonical evidence retrieval and `usage_evidence`

- Status: complete
- Branch: `pivot/13-canonical-evidence`
- Commits: `319230e`, `bf8a5b5`, `981d8b6`, `ae58abc`
- Focused verification: evidence contracts, all selector types, pagination,
  dashboard targets, default profile registration, and Task 9/11/12 regressions;
  353 primary tests, 74 application/job regressions, and 24 Task 12 regressions passed.
- Full verification: targeted Pyright and Ruff; format check; release checker;
  diff/privacy review; independent re-review after the ambiguity fix.
- Deviations from plan: finding selectors accept an optional `analysis_id` so
  report-local finding IDs cannot resolve ambiguously across compatible analyses.
- Follow-up risks: analysis and finding evidence remains process-local until
  durable analysis persistence is implemented.

## Task 14 - Consolidate allowance operations behind `usage_allowance`

- Status: complete
- Branch: `pivot/14-allowance`
- Commits: `d58242f`, `33dda26`, `58a44c6`, `2ebfe46`, plus this documentation commit.
- Focused verification: every application operation, legacy payload equivalence,
  MCP envelope/target/budget behavior, tool registration, allowance intelligence,
  and server regressions; 441 tests passed. A combined Task 12/13 regression
  superset passed 369 tests.
- Full verification: targeted source Pyright; Ruff check and format check on all
  touched Python files; release checker; skill-mirror retrieval tests; diff/privacy review.
- Deviations from plan: result targets use the richer Limits v2 descriptor and
  generic job polling. The public roadmap field remains `range`; the internal
  builder uses `range_preset` to avoid shadowing the built-in.
- Follow-up risks: analysis jobs remain process-local, five-hour analysis is not
  supported, and individual allowance tools remain compatibility surfaces through 0.24.

## Task 15 - Move legacy MCP tools into explicit compatibility and developer profiles

- Status: complete
- Branch: `pivot/15-mcp-profiles`
- Commits: `b2a3b58`, plus this checklist/ledger commit.
- Focused verification: complete MCP/profile/CLI-release suite; 74 tests passed.
  The Task 14 allowance regression gate passed 442 tests after registration changed.
- Full verification: targeted source Pyright; Ruff check and format check; release
  checker; staged diff, source-size, and privacy review; independent review clean.
- Deviations from plan: PR290 already exposed the five dogfood/visualization names.
  The explicit developer-only invariant takes precedence: all 59 baseline names remain
  in `developer`, while `full` preserves the 54 non-developer baseline names. The
  legacy CLI module retains import-compatible implementations, but its decorators are
  inert and its process entrypoint delegates to the selected-profile server.
- Follow-up risks: Task 16 still owns installed-launcher selection of `core`. The
  temporary empty `compatibility_mcp` import sentinel remains for compatibility but
  cannot register or run hidden tools.

## Task 16 - Make the installed plugin launch the core MCP profile by default

- Status: complete
- Branch: `pivot/16-core-launcher`
- Commits: `feat: default the plugin to core MCP tools` (this commit)
- Focused verification: launcher, generated-installer, readiness, doctor, and
  selected-profile server tests passed; the full MCP profile suite also passed.
- Full verification: release checker before and after build; wheel and sdist
  build; distribution release check; clean installed-wheel smoke with an isolated
  FastMCP registry probe proving the seven ordered core tools; touched-file Ruff
  check/format; source/package launcher byte comparison; independent review clean.
- Deviations from plan: The public installer module is an import alias, so the
  generated-config change lives in `cli/plugin_installer.py`. MCP diagnostics also
  learned the new internal module path, and explicit package data includes the
  packaged launcher. Static smoke catalogs moved to a small helper so the main
  smoke gate stays below the repository source-size limit. Its synthetic dashboard
  check now uses the bounded 5,000-row limit instead of the legacy unbounded value.
- Follow-up risks: Task 17 must bump both byte-identical launcher copies' pinned
  runtime version and package spec together with the 0.22.0 release metadata.

## Task 17 - Gate Release 0.22.0

- Status: release candidate complete; publication and public qualification are
  deferred pending explicit authorization.
- Branch: `pivot/17-release-022`
- Commits: `7f4e50b` (`test: add core MCP golden questions`), `ba6fd3d`
  (`fix: harden release gate compatibility`), plus
  `chore: prepare 0.22.0 MCP core release` (this commit).
- Focused verification: ten synthetic golden-question fixtures and their
  deterministic routing evaluator passed 11 tests; release, plugin-installer,
  launcher, public-doc, canonical-query, SQL-filter, and JSON-contract
  regressions passed. The installed-wheel smoke reported version `0.22.0`, 59
  packaged resources, and the exact ordered seven-tool core profile.
- Full verification: 1,820 Python tests passed in 101.74 seconds; the coverage
  pass also ran 1,820 tests in 102.01 seconds and reported
  88.31270245256826% combined coverage, 90.99716960592205% statement
  coverage, and 77.77144485608436% branch
  coverage. Pyright reported 0 errors and 7 existing lazy-export warnings;
  Ruff and mypy passed. Dashboard verification passed 109 files / 571 tests,
  lint, type checking, governance, source budgets, and bundle budgets. The
  100,000-row route benchmark reported no budget violations (46.478998-second
  population and 10.183382-second recommendation materialization). Release
  checks, build, Twine, distribution inspection, installed-package smoke, and
  diff checks passed.
- Release inventory: `core` exposes 7 tools, `full` exposes 59, and `developer`
  exposes 64. The tracked JSON schema inventory contains 90 identifiers,
  including 14 additive MCP-core/application schemas listed in the release
  note. The local wheel is 5,320,724 bytes with SHA-256
  `bd828aaad0fe0af7ad93c423f265a0b6dc5412c562341254c43ce922de699318`;
  the local sdist is 28,493,191 bytes with SHA-256
  `fae196b193c79a4b7e969a53a32beb56c58dd903518c152f36637aa350015027`.
- Deviations from plan: public historical 0.21 readiness evidence is no longer
  treated as a current-version claim by the release checker. The full-suite
  command now uses pytest importlib collection so duplicate test filenames in
  separate directories collect deterministically. The full gate also exposed
  and fixed a prior regression that replaced raw session-ID filtering with the
  canonical `session:` form; both forms are now additive and covered. TestPyPI,
  public PyPI, tags, pushes, and public-package smoke tests were not run because
  they require explicit publication authorization. The Task 15 developer-only
  invariant remains authoritative: `developer` preserves all 59 baseline
  0.21/PR290 names, while `full` preserves the 54 non-developer baseline names.
- Follow-up risks: the recorded hashes identify the local Step 3 artifacts;
  evidence text was appended to tracked docs afterward as required by the
  plan, so an authorized rebuild would need fresh hashes and qualification.
  The coverage run emitted 71 non-failing pre-existing resource warnings.

## Task 18 - Introduce the Evidence Console Route Model

- Status: complete; legacy direct workbenches remain renderable for the 0.23
  compatibility window but are absent from persistent navigation.
- Branch: `pivot/18-evidence-console-routes`
- Commits: `d30dd48` (`refactor: define Evidence Console routes`) plus
  `fix: preserve canonical Evidence Console links` (this commit).
- Focused verification: the six-file route, alias, shell, and target acceptance
  suite passed 70 tests. Canonical calls, threads, and investigator URL-builder
  regressions passed another 20 tests. The Python v2 dashboard-target suite
  passed all 307 tests, including call `record` selectors and both contextual
  and Explore thread targets.
- Full verification: dashboard type checking and lint passed; touched Python
  files passed Ruff; `git diff --check` passed. One diagnostic full-dashboard
  run passed 505 of 576 tests. Its 71 remaining failures are legacy assertions
  that navigate with workbench buttons intentionally removed by this task or
  assert pre-pivot output IDs; Tasks 19 through 23 own those parity migrations.
- Review: an independent read-only review reported no critical or important
  findings in canonical routes, compatibility normalization, contextual
  Evidence behavior, navigation exactness, or Python v2 targets.
- Deviations from plan: `App.tsx` and the page-level calls, threads, Explore,
  and investigator URL emitters also changed because they are the direct shell
  consumers that otherwise rewrote canonical links back to legacy IDs. Call
  URLs use the roadmap's `record` query key while preserving the design
  contract's `record_id` selector field. No publication action was taken.
- Follow-up risks: legacy navigation-heavy dashboard tests remain intentionally
  red until their owning Home, Explore, Evidence, Limits, and parity tasks land.
  Target Evidence kinds other than call still render through compatibility
  pages until Task 21 supplies the unified contextual renderer.

## Task 19 - Build the Focused Evidence Console Home

- Status: complete; the canonical Home route and its legacy Overview alias now
  render the same focused operational summary instead of the broad legacy
  dashboard.
- Branch: `pivot/19-home-status`
- Commits: `ff5dc7b` (`fix: restore Evidence Console route boundaries`),
  `5847bc3` (`feat: add bounded Home status payload`), `879faae`
  (`feat: load focused Home status`), `c90daac` (`feat: add focused Evidence
  Console home`), plus this documentation commit.
- Focused verification: 51 frontend tests passed across the Home view/model,
  readiness refresh lifecycle, shell, canonical-link, and route contracts. The
  Home store/status/shell and CLI integration targets passed 17 Python tests.
- Full verification: dashboard type checking, lint, stylelint, the named
  dashboard-governance gate, targeted Pyright, touched-file Ruff, and
  `git diff --check` passed. A diagnostic full-dashboard run passed 499 of 588
  tests; its 89 legacy Overview/workbench assertions are owned by Tasks 20
  through 24 and no Task 19 named acceptance check remains failing.
- Review: an independent review initially found four boundedness/scope issues:
  an unbounded recommendation count, missing pricing and allowance data in the
  fast payload, archived rows affecting active Home freshness, and overly wide
  recent-evidence materialization. All four were fixed, and the narrow
  independent re-review passed.
- Deviations from plan: a narrow store-query module owns the hard three-finding
  and five-evidence caps. The fast status payload carries pricing and allowance
  coverage so Home does not need a report scan. The route contract moved to its
  governance-approved feature boundary, and the three existing oversized
  source files touched by this task were ratcheted downward. No publication
  action was taken.
- Follow-up risks: legacy Overview and workbench tests remain intentionally red
  until Tasks 20 through 24 complete their parity migration. The static legacy
  shell receives an embedded Home summary, while the React path intentionally
  marks that summary deferred and loads the live bounded status endpoint.

## Task 20 - Consolidate Calls and Threads into Explore

- Status: complete; Explore now owns one accessible Calls/Threads mode switch,
  mounts only the active evidence surface, and canonicalizes legacy Calls and
  Threads URLs without losing mode-specific state.
- Branch: `pivot/20-explore-workspace`
- Commits: `cabaa0b` (`feat: unify calls and threads in Explore`), `15d6f5c`
  (`refactor: remove obsolete Explore diagnostics`), and `3175e82` (`test:
  migrate Explore browser journeys`), plus this documentation commit.
- Focused verification: the roadmap-named Explore, Calls, Threads, and URL-state
  command passed 23 tests. The expanded eight-file integration suite passed 56
  tests, including legacy route normalization, inactive-mode non-mounting,
  filter preservation, Evidence return state, and Calls/Threads regressions.
  The isolated browser smoke suite passed all 22 desktop and mobile journeys.
- Full verification: dashboard type checking, lint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, and
  `git diff --check` passed. A diagnostic full-dashboard run passed 528 of 596
  tests; its 68 remaining failures assert retired top-level navigation and
  pre-pivot route IDs that Tasks 21 through 24 continue to migrate.
- Review: an independent read-only review reported no critical or important
  findings in active-mode mounting, URL-state preservation, legacy route
  normalization, Evidence returns, query scoping, accessibility, privacy, or
  security.
- Deviations from plan: the obsolete Tools and Files sub-modes and their orphaned
  diagnostic adapters were removed rather than allowlisted after the two-mode
  contract made them dead code. The Playwright web server now derives its URL
  from a configurable strict port and never reuses an unrelated listener; the
  verified run used port 5187 because another local application owned 5173. No
  publication action was taken.
- Follow-up risks: compatibility workbenches remain directly routable while the
  remaining contextual Evidence and legacy-parity migrations land. The full
  dashboard inventory remains diagnostic until those owning tasks complete.

## Task 21 - Build One Contextual Evidence Route

- Status: complete; one contextual route now resolves exact call, thread,
  finding, and allowance-transition selectors without label fallback. Calls
  retain the gated Call Investigator, while the other kinds render bounded
  aggregate records from the shared evidence contract.
- Branch: `pivot/21-contextual-evidence`
- Commits: `44f6308` (`feat: expose bounded contextual evidence`), `c489482`
  (`feat: define canonical Evidence links`), `b9da403` (`feat: render contextual
  Evidence views`), `20cecf6` (`test: cover contextual Evidence views`), and
  `dccea7c` (`test: align release gate with pivot routes`), plus this
  documentation commit.
- Focused verification: 39 Python tests passed across the roadmap-named server,
  application, service, compatibility, and route-inventory suites. Twenty-nine
  frontend tests passed across the Evidence API, URL contract, all four
  renderers, route catalog, and Call Investigator compatibility.
- Full verification: dashboard type checking, lint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, touched-file Ruff,
  Ruff formatting, privacy-pattern scanning, and `git diff --check` passed. The
  port-isolated release-candidate passed all 11 Chromium checks covering
  accessibility, responsive layout, reduced motion, chart/table parity,
  simplified navigation, direct-route compatibility, return state, readiness,
  and localization. A diagnostic full-dashboard run passed 551 of 619 tests;
  its 68 failures are the unchanged legacy navigation and pre-pivot route-ID
  assertions already deferred from Task 20.
- Review: the final local review found no critical or important correctness,
  privacy, security, pagination, selector, or compatibility issue. The three
  task-level child-agent slots had already supplied the Task 20 review and the
  bounded Task 21 backend/frontend reconnaissance, so no fourth child was
  created.
- Deviations from plan: `CallEvidence` delegates to the existing Call
  Investigator instead of moving its 807-line implementation during the 0.23
  compatibility window. The early HTTP adapter accepts validated query fields
  on POST; Task 25 still owns the unified JSON-body v2 facade. The
  release-candidate command now derives its base URL from the configurable
  strict Playwright port, preserving the 5173 CI default while allowing safe
  isolated local runs. No publication action was taken.
- Follow-up risks: the full JSON HTTP facade, payload-budget conformance matrix,
  and compatibility-removal decision remain owned by Tasks 25, 27, and 45.
  Legacy unit assertions that still demand retired top-level route IDs remain
  diagnostic until their owning parity tasks land.

## Task 22 - Refocus Limits and Settings for the Evidence Console

- Status: complete; Limits now leads with observed reset state, marks observed
  facts, descriptive estimates, and supported changes explicitly, and opens
  matching persisted allowance evidence through the contextual Evidence route.
  Settings now presents local runtime readiness and keeps direct compatibility
  Labs behind an off-by-default Advanced preference.
- Branch: `pivot/22-focus-limits-settings`
- Commits: `45fa34c` (`refactor: focus Limits and Settings`) and `aef37bf`
  (`fix: localize compatibility Labs controls`), plus this documentation
  commit.
- Focused verification: 32 frontend tests passed across Limits, Settings, the
  browser-local preference hook, conversational readiness, and the route
  catalog. All 148 locale-catalog tests passed, including equal key sets,
  placeholder parity, and non-English Task 22 copy.
- Full verification: dashboard type checking, ESLint, stylelint, dependency
  boundaries, dead-code detection, source-budget enforcement, bundle budgets,
  privacy-pattern scanning, and `git diff --check` passed. The isolated
  port-5195 release candidate passed all 11 Chromium checks, including visible
  chart/table parity, immediate and restored Labs preference state, simplified
  navigation, and Spanish copy. A diagnostic full-dashboard run passed 554 of
  622 tests; its 68 failures are the same legacy navigation and pre-pivot route
  assertions deferred from Tasks 20 and 21.
- Review: the final local review found no critical or important correctness,
  privacy, evidence-link, storage-migration, localization, or compatibility
  issue. The task-level child-agent allowance had already been used for the
  pivot review and bounded backend/frontend reconnaissance, so no additional
  review child was created.
- Deviations from plan: the roadmap's former `usage-drain` page already lived
  at `features/limits/LimitsPage.tsx`. History controls were extracted to keep
  the source ratchet green, and App injects the route-catalog Labs inventory to
  preserve dependency direction. The browser gate and all twelve locale
  catalogs landed in a second focused commit to keep each commit within the
  20-file limit. No allowance calculation, detector, API, or publication
  behavior changed.
- Follow-up risks: five compatibility workbenches remain directly routable
  until Tasks 23 and 24 prove job parity and retire their duplicate navigation
  paths. Their legacy unit assertions remain diagnostic until those owning
  tasks land.

## Task 23 - Prove Job Parity and Hide Legacy Workbenches

- Status: complete; all eight sunset jobs have an executable signed parity
  record covering canonical evidence IDs, history scope, accounting context,
  caveats, replacement requests, destinations, ownership, and removal timing.
  The five legacy workbenches stay directly routable but are absent from the
  default Home, Explore, and Limits navigation and now name a core replacement.
- Branch: `pivot/23-dashboard-sunset-parity`
- Commits: `78934d3` (`feat: simplify the default dashboard surface`), plus this
  documentation commit.
- Focused verification: 69 Python tests passed across the analysis catalog,
  signed sunset parity, analyze, query, and evidence contracts. The roadmap's
  four-file frontend command passed 31 tests across the shell, route catalog,
  transition banner, and Diagnostics lifecycle; the final affected-component
  recheck passed 12 tests.
- Full verification: dashboard type checking, ESLint, dependency boundaries,
  dead-code detection, stylelint, source-budget enforcement, touched-file Ruff,
  bundle budgets, privacy-pattern scanning, and `git diff --check` passed. The
  port-isolated release candidate passed all 11 Chromium checks, including the
  five direct legacy routes and Spanish transition copy. A diagnostic named
  full-dashboard run passed 556 of 624 tests; its 68 failures are the unchanged
  retired-navigation and pre-pivot route-ID assertions already deferred from
  Tasks 20 through 22.
- Review: the final local diff review found no critical or important
  correctness, privacy, selector, accounting, accessibility, localization, or
  compatibility issue. The task-level child-agent allowance had already been
  used by prior pivot slices, so no additional review child was created.
- Deviations from plan: `analysis_catalog.py` changed because it is the source
  that overwrites strategy destinations in public analysis results; leaving it
  untouched would preserve links to retired workbenches. `navigation.ts`
  required no edit because Task 18 already enforced exactly Home, Explore, and
  Limits plus the Settings utility. The release-candidate used port 5197 because
  an unrelated listener owned 5173. Verification-only generated dashboard
  assets were restored to their clean pre-build state; Task 29 owns artifact
  synchronization. No publication action was taken.
- Follow-up risks: the 68 legacy unit assertions remain diagnostic until Task
  24 removes their obsolete workbench assumptions. Full-profile compression
  ranking and direct route bookmarks remain supported only through `0.24.x`,
  with the signed record blocking removal if parity later regresses.

## Task 24 - Remove the Usage Constellation and Frontend Dependencies

- Status: complete; the experimental Usage Constellation, its Three.js renderer
  and models, its browser and unit coverage, and all packaged constellation
  assets are removed. `three` and `@types/three` are absent from both manifests
  and the lockfile, and release validation now rejects their reintroduction.
- Branch: `pivot/24-remove-usage-constellation`
- Commits: `b34066e` (`refactor: remove non-core dashboard visualization`),
  `064f83b` (`test: enforce dashboard visualization sunset`), `7c279b1`,
  `e9f7ea7`, `a3a4dd2`, and `726e1f8` (bounded packaged-asset refreshes),
  `c1761f7` (`test: align dashboard coverage with core routes`), plus this
  documentation commit.
- Focused verification: the release suite passed 26 tests; the migrated route,
  Evidence, diagnostics, live-refresh, export, filter, source-identity, and
  compatibility subset passed 85 tests. `npm ls three --all` returned empty,
  asset synchronization was byte-for-byte clean, the initial bundle measured
  60.02 KiB under its 67 KiB ceiling, and the largest visualization route
  measured 112 KiB under its 113 KiB ceiling with no Three.js inputs.
- Full verification: the repository-defined `dashboard-verify` gate passed all
  607 frontend tests, TypeScript, ESLint, dependency boundaries, dead-code
  detection, stylelint, the refreshed source ratchet, production build, asset
  parity, bundle budgets, and `scripts/check_release.py`. The port-isolated
  release candidate passed all 11 Chromium checks. `npm ci`, governance,
  `git diff --check`, and the final staged-file review also passed.
- Review: the final diff contains 193 additions and 628 deletions across the
  compatibility-test cleanup, with no secret-bearing paths or unexpected
  worktree changes. The task-level child-agent allowance had already been used
  by prior pivot slices, so no additional review child was created.
- Deviations from plan: three obsolete top-level shell suites and two retired
  Overview-only load-more cases were deleted instead of being rewritten to
  assert navigation that no longer exists. Direct-route compatibility remains
  covered through canonical Home, Explore, Evidence, diagnostics, reports,
  investigator, and cache tests. The generated asset refresh was split into
  four commits to respect the 20-file commit cap. The release documentation's
  Tools catalog boundary was corrected so its parser does not consume the
  following workbench-replacement section. No publication action was taken.
- Follow-up risks: `npm ci` reports four existing audit findings (two moderate
  and two high); no automatic dependency rewrite was attempted. The remaining
  compatibility workbenches and static dashboard are still governed by their
  documented two-release sunset and later roadmap tasks.

## Task 25 - Add the Versioned HTTP API v2 Application Facade

- Status: complete; eight stable `/api/v2/` endpoints now decode bounded strict
  requests, invoke the same application services as the core MCP tools, and
  serialize their shared result contracts without calling MCP handlers. The
  Evidence Console's contextual Evidence client now posts a typed JSON body and
  consumes `evidence-result.v1` directly.
- Branch: `pivot/25-http-api-v2`
- Commits: `8f54acb` (`feat: add HTTP API v2 facade`), `d4a9d86`
  (`feat: serve stable HTTP API v2 routes`), `6e32622` (`feat: migrate Evidence
  Console to HTTP v2`), `ab2d307` (`fix: guard expensive allowance requests`),
  `bcafa59` (`fix: enforce strict JSON request bodies`), `9cdc103` (`chore:
  satisfy HTTP v2 quality gates`), and `c0f643f` (`docs: update tracked schema
  count`), plus this documentation commit.
- Focused verification: 60 Python tests passed across the pure decoder/facade,
  body and output limits, live localhost server, route inventory, shared JSON
  contracts, and the full dashboard-server suite. The roadmap's four-file
  frontend command passed 23 tests across the client and Home, Explore, and
  Evidence pages. The public documentation/contract check passed 21 tests.
- Performance and quality verification: the repository-defined 100,000-row
  dashboard route budget passed in 65.984 seconds with enforced thresholds.
  TypeScript type checking and ESLint passed; targeted Ruff lint and formatting,
  isolated mypy, project-interpreter Pyright, `git diff --check`, and the
  Task 25 route-handler dead-code recheck passed.
- Broad verifier: the repository-wide `full` profile ran for 4 minutes 13
  seconds and exposed existing pivot-branch debt in legacy file lengths,
  allowance exports/types, Tach boundaries, optional frontend tool discovery,
  and dependency audit. Its only Task 25-local findings were formatting,
  test-only type narrowing, dynamic route-handler discovery, and the public
  schema count; all four were repaired and rechecked. The raw repository-wide
  profile remains red on the unrelated inherited findings and is not represented
  as a passing gate.
- Review: POST bodies require `Content-Length`, enforce per-route byte budgets,
  reject wrong media types, malformed/non-object JSON, duplicate keys,
  non-finite numbers, and unknown top-level/nested fields. Responses enforce
  route budgets, async starts return `202`, all v2 errors are JSON, and Host,
  Origin, refresh/analyze/allowance token guards remain active. HTTP status and
  MCP status results have equal schema identifiers and field sets.
- Deviations from plan: the stable server integration lives in a small
  `HttpV2RouteMixin` so the legacy request handler becomes smaller rather than
  growing further. `request_guards.py` required no behavior change; live-server
  coverage proves the existing Origin and token guards remain in force. No v1
  route or publication state changed.
- Follow-up risks: compatibility routes remain intentionally available through
  their documented window. The repository-wide inherited verifier debt remains
  owned by later architecture, CI, and release-hardening roadmap tasks.

## Task 26 - Introduce the Simplified CLI Hierarchy

- Status: complete; primary help now exposes exactly `setup`, `status`,
  `doctor`, `refresh`, `analyze`, `query`, `open`, `export`, `config`,
  `service`, and `admin`. All historical top-level spellings remain parseable
  through `0.24.x` but are hidden from primary help, and interactive alias
  notices are isolated to stderr.
- Branch: `pivot/26-simplified-cli`
- Commits: `10314a9` (`feat: add simplified CLI hierarchy`), `7d71cf1`
  (`feat: route stable CLI application commands`), `9a73642` (`docs: publish
  simplified CLI migration`), plus this documentation commit.
- Behavior: `status`, bounded `query`, and `analyze` serialize the shared v2
  application contracts. Old-only query filters and `--limit 0` retain the v1
  compatibility path. `open` resolves Home, call, thread, target ID, or strict
  dashboard-target-v2 JSON and opens only matching loopback URLs. Configuration,
  service, operational, dogfood, and manual MCP commands are routed through the
  documented namespaces without duplicating their existing option builders.
- Verification: 191 tests passed across the new parser and command adapters,
  CLI release contracts, legacy CLI lifecycle, and i18n. Focused Ruff lint and
  formatting, project-interpreter Pyright, Python compileall, release readiness,
  `git diff --check`, primary/nested help smoke tests, and a real empty-state
  `status.v2` invocation passed. The architecture checker reported only the
  same inherited core/store dependency violations present before this task; it
  reported no CLI-interface violation.
- Review: strict target JSON rejects mismatched loopback absolute and relative
  URLs, machine-readable output never receives deprecation text, translated
  help keeps the same short inventory, and every legacy parser remains covered.
  No secrets or private records were added. The task-level child-agent allowance
  had already been used by prior pivot slices, so no additional review child was
  created.
- Deviations from plan: the work was split into three focused implementation
  commits to remain below the repository's 800-added-line commit cap. The
  installed-package smoke and release catalogs changed because they previously
  defined every historical command as stable. No compatibility command was
  deleted and no publication action was taken.
- Follow-up risks: the CLI default service object currently shares the proven
  HTTP v2 application-service adapter; a later boundary cleanup may move that
  adapter into the application package without changing contracts. Historical
  aliases and legacy query mode remain removal-blocked until `0.25.0`.

## Task 27 - Gate and Prepare Release 0.23.0

- Status: release-ready; the complete local release candidate and required
  100,000-row route budget pass. Publication proceeds through the reviewed PR,
  updated `main`, GitHub release, and Trusted Publishing workflow.
- Branch: `pivot/27-release-0.23.0`
- Commits: `6441076` (`chore: prepare 0.23 release contracts`), `f67a647`
  (`docs: explain the 0.23 Evidence Console`), `a84b10e` (`docs: add core
  Evidence Console screenshots`), `b775d3c` (`test: capture responsive
  Evidence Console release evidence`), `460d1e5` (`fix: localize the service
  namespace`), `893d2f9` (`perf: index all-history allowance observations`),
  and `1813169` (`chore: refresh Evidence Console assets`), plus this
  documentation commit.
- Product inventory: 15 browser routes comprise five Evidence Console routes
  and ten direct-only legacy routes. Default analytical navigation is Home,
  Explore, and Limits; Settings is a utility action and Evidence is contextual.
  Home begins with the bounded Usage Pulse calls, tokens, cache-reuse, and cost
  summary before its readiness and evidence sections. Explore provides Calls
  and Threads modes. All four Evidence selector kinds render, stable old URLs
  normalize, and Home performs no hidden heavy scan.
  MCP profiles expose 7 core, 59 full, and 64 developer tools. Primary CLI help
  exposes 11 commands and retains 34 hidden compatibility aliases. The shared
  JSON inventory contains 95 schemas.
- Focused verification: 381 Python acceptance tests passed. The frontend suite
  passed 609 tests across 115 files. The port-isolated Playwright release
  candidate passed 14 scenarios, including Explore Calls and Threads parity,
  stable URL normalization, all Evidence selectors, and the Home scan guard.
  The restored Usage Pulse recheck passed 31 focused frontend tests and the
  complete dashboard and browser release-candidate gates again.
  Twelve synthetic screenshots cover Home, Explore Calls, Explore Threads,
  Limits, Evidence, Settings, a legacy route, tablet, mobile, 200% zoom,
  reduced motion, and keyboard use without private user data.
- Full verification: all 1,905 Python tests passed and coverage measured 88%.
  Ruff, mypy, Pyright (zero errors and seven inherited lazy-export warnings),
  TypeScript, ESLint, dependency boundaries, dead-code detection, stylelint,
  source budgets, dashboard asset parity, release checks, installed-package
  smoke, and `git diff --check` passed. Initial dashboard payloads measure
  60.02 KiB JavaScript and 9.66 KiB CSS. The largest visualization chunk is the
  documented 112.00 KiB gzip exception under its 113.00 KiB ADR limit. The
  recorded candidate wheel and sdist measure 6,956,865 and 31,909,932 bytes,
  respectively, and both pass Twine and distribution release checks.
- Performance evidence: migrations 32–34 add the global newest-first allowance,
  focused recommendation/call sorting, source, and parent-thread lookup indexes.
  The stable enforced 100,000-row run passed every route budget: Calls measured
  0.074 seconds p95, Threads 0.007 seconds p95, thread calls 0.014 seconds p95,
  and allowance diagnostics 0.584 seconds p95. Population completed in 44.8
  seconds.
- Post-candidate polish and freshness correction: Home once again exposes
  refresh/loading progress, removes annotation footnotes from Usage Pulse, and
  replaces the three generic actions with an MCP/plugin setup guide and six
  visible copyable investigation prompts. Explore now points first-time visitors
  to the Calls/Threads switch. Live preview diagnosis found macOS volume-device
  drift was misclassifying 1,217 tracked logs as replacements; preserving
  path/inode/prefix-tail safety while tolerating `st_dev` drift reduced the same
  catch-up to 11 append-safe logs and 14 new logs. The preview advanced from
  `2026-07-22T19:59:50.013Z` to `2026-07-23T17:21:33.634Z`; the focused Calls
  route returned that newest row with populated cost and credit fields in 0.006
  seconds. A profiled synthetic refresh identified per-row canonical
  fingerprint lookups as the Python hotspot. Batched lookups reduced the
  identical unprofiled 10,000-row refresh from 7.55 to 3.52 seconds. Startup
  refresh is now asynchronous: the real 224,244-call preview served its stored
  dashboard in about four seconds while refresh continued in the background,
  instead of withholding the server behind the roughly 10.5-minute full scan.
- Roadmap protection: Tasks 25, 27, 34, and 41 now explicitly preserve bounded
  Home/Limits hydration and the focused Calls, Threads, and Thread Calls query
  plans. A v2 facade may not replace or deprecate those routes until functional
  parity, exact filtering/sorting/counts, cost/credit parity,
  incremental-freshness coverage, and the named 100,000-row route budget all
  pass.
- Deviations from plan: additive migrations 33 and 34 and focused endpoint
  changes were necessary to correct real filter/count/query-plan defects found
  during release qualification. No route threshold was loosened and no failing
  route result was hidden.
- Follow-up risks: the broader 100,000-row full-content ingestion benchmark
  retained exact table parity and measured a 23.5% parallel speedup, but its
  26.9-second median and 578 MiB sampled process-tree peak remain above the
  historical 20-second/544 MiB sentinels. The excess is in the optional
  content/fact indexing pipeline rather than dashboard availability or focused
  endpoint hydration; it is recorded for 0.24 performance hardening.

## Task 27.5 - Foundation Audit and 0.24 Plan Confirmation

- Stable task ID: `ARCH-AUDIT-00`
- Status: complete; Task 27 and the `0.23.0` release gate completed before
  evidence collection, and this checkpoint recorded `PROCEED`.
- Branch: `pivot/27.5-foundation-audit`
- Commits: `docs: add 0.24 foundation audit checkpoint` (this checkpoint;
  exact SHA is recorded in Git/PR history).
- Audit report: `docs/superpowers/reports/0.24-foundation-audit.md`.
- Audited commit SHA: `589e10a1afeca72e47d6b2d5777cd8189d292996`.
- Decision: `PROCEED`.
- Changed files:
  `docs/superpowers/reports/0.24-foundation-audit.md`,
  `docs/roadmap/mcp-first-pivot-execution.md`, `.gitignore`, and `AGENTS.md`.
  The latter two add the user-approved ignored GitNexus index and
  context-efficient GitNexus/Serena/source/test workflow; the 548 MiB local
  `.gitnexus/` index and IntelliJ `.idea/` directory remain untracked.
- Focused verification:
  - migration, canonical accounting, refresh, content, OTel, allowance,
    contract, core MCP, profile, and HTTP-v2 suite: `126 passed in 11.35s`;
  - fresh temporary SQLite database: schema/user version 34, 34 migration
    records, 38 physical tables, `integrity_check=ok`,
    `foreign_key_check=[]`, and normal `foreign_keys=0`;
  - `ruff check .`: passed;
  - `.venv/bin/python -m pyright --pythonpath .venv/bin/python src`: 0 errors,
    7 existing lazy-export warnings;
  - `python scripts/check_release.py`: passed;
  - `npx markdownlint-cli2`: passed;
  - synthetic isolated doctor: completed with the expected warning-only
    missing-local-setup result.
- Full verification: `.venv/bin/python -m pytest -q`:
  `1907 passed in 116.87s`.
- Architecture graph and inventory evidence:
  - Tach map: 381 modules, 1,327 edges, 3 non-trivial SCCs;
  - `tach check`: the 8 pre-existing direction violations recorded in the
    report, assigned to Tasks 28-30;
  - GitNexus at the audited SHA: 1,348 files, 25,190 symbols, 54,349
    relationships, 1,311 clusters, and 300 processes;
  - `gitnexus check --cycles --json`: 7 file-level cycles, including
    analytics/application, store/schema, store/refresh, frontend, and one
    generated-bundle cycle.
- Migration fixtures tested: unversioned legacy aggregate through v34; fresh
  v34; representative v23, v24, v25, v27, v28, v31, and v33 states; canonical
  rebuild; OTel v30/v31; malformed legacy failure/partial-commit evidence;
  refresh idempotency and CSV compatibility. Every retained SQLite fixture
  returned `integrity_check=ok` and zero `foreign_key_check` rows.
- Findings assigned to Tasks 28-33:
  - Task 28: composition, status, repository, evidence, focused-route, and
    refresh workflow ownership;
  - Task 29: MCP extraction and registration cycles;
  - Task 30: dependency direction, explicit adapters, contract isolation, and
    remaining cycles;
  - Task 31: foreign-key enforcement, atomic migration failure,
    transaction/rebuild/cache-write safety, cascade and retained migration
    fixtures;
  - Task 32: indexed byte-offset context retrieval and inspected-byte budgets;
  - Task 33: persistent generic jobs/results and recovery.
- Maintainer approval reference: not required for `PROCEED`.
- Deviations from plan: no production behavior or schema changed. GitNexus
  added independent graph evidence and user-approved repository guidance; no
  roadmap task was broadened.
- Follow-up risks: the report contains 14 assigned findings and no blocker or
  unassigned high-severity finding. Task 28 may start only after this audit
  checkpoint lands. Focused Home, Limits, Calls, Threads, and Thread Calls
  routes remain protected until exact parity and performance gates pass.

## Task 28 - Application Composition Root and Dependency Protocols

- Stable task ID: `ARCH-COMPOSE-01`.
- Status: complete on `pivot/28-composition-root`; Task 27.5 recorded
  `PROCEED` before implementation began.
- Branch: `pivot/28-composition-root`.
- Commits: `refactor: compose tracker application services` (this task; exact
  SHA is recorded in Git/PR history).
- Composition contract:
  - frozen `ApplicationPaths` owns the Codex home, database, pricing,
    allowance, rate-card, threshold, and project paths;
  - frozen `ApplicationContainer` owns those paths, one clock, narrow
    repositories/providers, one shared `JobService`, the analysis catalog, and
    dashboard-target resolution;
  - CLI, HTTP v2, and the selected-profile MCP server compose the container at
    their interface boundary and pass it inward;
  - application and analytics modules no longer import `core.paths`, and
    status requests no longer consult `Path.home()` implicitly;
  - compatibility analysis delegates receive the exact container paths through
    immutable request context instead of reopening module-global defaults.
- Changed files: new `application/container.py`, `application/paths.py`,
  `application/protocols.py`, and their tests; path/context injection across
  status, query, evidence, allowance, refresh, analytics compatibility, CLI,
  HTTP v2, the live server, and core MCP registration; architecture
  documentation and the user-approved GitNexus resource navigation table.
- Focused verification:
  - required container/protocol, MCP, and interface suite:
    `92 passed in 10.67s`;
  - expanded application/analytics/HTTP/CLI slice:
    `110 passed in 3.26s`;
  - `ruff check` over the changed application, analytics, interface, and test
    surfaces: passed;
  - Pyright over `src/codex_usage_tracker/application`: 0 errors;
  - custom temporary-container tests reject default-home access, preserve exact
    paths, bind all seven core MCP tools, and prove the job/result repository is
    shared.
- Independent review:
  - one final reviewer reported two actionable findings; both were accepted as
    `R1` and `R2`;
  - `R1` moved live HTTP v2 composition to server startup so async jobs remain
    visible across separate request-handler connections;
  - `R2` preserves the configured projects path through both CLI and live HTTP
    composition;
  - the focused post-review regression slice passed `34 tests in 3.40s`, and
    the bounded application, analytics, MCP, interface, and server recheck
    passed `456 tests in 31.18s`;
  - reviewer-efficiency attribution timed out once and was recorded with token
    status `pending`, as required; it did not block the task.
- Full verification:
  - `.venv/bin/python -m pytest -q`: `1912 passed in 118.84s`;
  - `.venv/bin/python -m ruff check .`: passed;
  - `.venv/bin/python -m mypy`: passed;
  - `.venv/bin/python -m pyright --pythonpath .venv/bin/python src`: 0 errors
    and the seven inherited lazy-export warnings;
  - compileall, release-readiness checks, and `git diff --check`: passed.
- Architecture evidence:
  - the final GitNexus `detect-changes --scope all` mapped 96 changed symbols
    to 15 affected execution flows and classified the cross-cutting composition
    change as high risk, which triggered the full verification gate;
  - Tach still reports the eight dependency-direction violations recorded by
    Task 27.5. This task introduced no new violation; Task 30 remains their
    assigned owner.
- Deviations from plan: `RequestContext` gained a non-serialized
  `application_paths` field so compatibility strategies can use the composed
  path set without creating an analytics-to-default-path dependency. Core MCP
  registration gained explicit container-bound handler adapters while retaining
  the unbound compatibility functions for direct callers. No DI framework,
  route, schema, table, or public payload changed.
- Follow-up risks: full/developer MCP compatibility registration remains the
  Task 29 extraction target. The known Tach direction violations and remaining
  explicit adapter work remain Task 30 scope. Focused Home, Limits, Calls,
  Threads, and Thread Calls route protections are unchanged.

## Task 29 - MCP Package Extraction and Explicit Registration

- Status: complete; squash-merged through PR 296.
- Branch: `pivot/29-mcp-extraction`.
- Commits: `6cde2bac` (`refactor: extract MCP interface package`).
- Registration contract:
  - `interfaces/mcp/server.py:create_mcp_server` is the only FastMCP
    construction boundary and registers immutable profile catalogs explicitly;
  - every server instance owns an isolated registry and receives its
    `ApplicationContainer` through the factory;
  - importing every `interfaces.mcp` implementation and historical
    `cli.mcp_*` compatibility module creates no global server and registers no
    tools;
  - historical CLI module paths remain import-compatible aliases, while
    implementation, local-operation, dogfood, routing, transport, and
    serialization concerns live under `interfaces/mcp/`.
- Preserved contracts: exact ordered inventories remain 7 core, 59 full, and
  64 developer tools. Tool names, signatures, descriptions, lifecycle
  metadata, JSON schemas, default profile selection, and
  `python -m codex_usage_tracker.mcp_server` remain unchanged.
- Changed files: extracted MCP implementations and compression-routing helpers
  from `cli/` into `interfaces/mcp/`; completed `server.py`; added
  `transports.py`, `serialization.py`, isolated local-operation and dogfood
  modules; reduced old paths to shims; added factory/import-side-effect tests;
  updated architecture documentation and compatibility/profile tests.
- Focused verification:
  - roadmap-named factory/import/profile/CLI suite: `30 passed in 10.39s`;
  - expanded MCP, CLI compatibility, golden-question, and store adapter suite:
    `139 passed in 14.11s`;
  - complete Python suite: `1,919 passed in 121.56s`;
  - package-scoped Pyright: 0 errors and 0 warnings;
  - repository Ruff, mypy, source-tree Pyright, compileall, Vulture, release
    readiness, and `git diff --check`: passed;
  - Tach reported only inherited boundary violations in untouched core, store,
    and related modules; Task 29 added no interface-to-CLI violation.
- Final review:
  - one read-only reviewer reported two medium findings and both were accepted;
  - restored the exact pre-0.24 fallback and deprecated-tool description text,
    then strengthened import purity with a fresh-process FastMCP
    construction/registration probe;
  - post-review MCP, profile, CLI, and release recheck: `65 passed in 14.22s`;
    focused Ruff and Pyright passed with zero errors and warnings;
  - reviewer token status is pending in the aggregate-only review metrics
    index, so tokens per accepted finding are not yet available.
- Architecture evidence:
  - refreshed GitNexus index at Task 28 merge commit before branch creation:
    25,354 symbols, 54,588 relationships, 1,315 clusters, 300 processes;
  - GitNexus exact context found one production caller of the previous server
    builder and six upstream dependents through CLI/module entrypoints, so the
    compatibility factory name remains as a thin alias;
  - staged change analysis classified 40 files and 25 changed symbols as low
    risk with no affected indexed process, and the post-extraction full index
    completed with 25,314 nodes, 54,496 edges, 1,303 clusters, and 300 flows;
  - implementation-package scans prove zero CLI imports, global FastMCP
    instances, and decorator registrations.
- Deviations from plan: Compression Lab router and payload helper modules moved
  with their declared wrapper because leaving them under `cli/` would preserve
  an interface-to-CLI reverse dependency. This added no tool, route, schema,
  table, runtime dependency, or user-visible behavior.
- Follow-up risks: Task 30 still owns the repository-wide Tach boundary and
  remaining non-MCP import cycles. No Task 29 compatibility surface is removed.

## Task 30 - Enforce Python Architecture with Tach Domain Boundaries

- Status: complete; squash-merged as PR
  [#297](https://github.com/douglasmonsky/codex-usage-tracker/pull/297)
  at `80e0c38`.
- Branch: `pivot/30-tach-boundaries`.
- Commits: `ebafb71` (`chore: close completed change plans`), `f6865ae`
  (`chore: add repository GitNexus agent workflow`), and `264df75`
  (`fix: normalize GitNexus refactoring examples`), and `0a21a71`
  (`fix: keep GitNexus refreshes index-only`), and `d3151b0`
  (`refactor: enforce tracker architecture boundaries`), `65c2502`
  (`docs: record Task 30 architecture commit`), and `f40d1d6`
  (`fix: satisfy architecture CI compatibility`).
- Boundary contract:
  - root ownership, explicit dependencies, and circular-domain enforcement are
    enabled with no ignore baseline;
  - every Python source module has a Tach owner;
  - core request/error/version contracts are dependency-light and preserve old
    application import identities;
  - analytics consumes a read-only context protocol instead of application
    types;
  - CLI, HTTP, and MCP are independently owned interfaces and do not import one
    another;
  - runtime readiness is injected from interfaces, and allowance calculation is
    invoked above store through the refresh derived-fact callback;
  - exact historical helper/materialization paths remain tested compatibility
    leaves.
- Focused verification:
  - `python -m tach check`: passed with zero violations and zero declared
    cycles;
  - architecture regression suite: `13 passed`;
  - architecture, analytics, application status/request/query, HTTP/CLI,
    allowance, deduplication, refresh-callback, and migration slice:
    `145 passed in 5.73s`;
  - the final dashboard-contract and source-record-schema ownership cleanup
    passed `337` focused core, store, migration, and architecture tests;
  - the accepted-review refresh, MCP readiness, compatibility-edge, and
    architecture fixes passed `49` focused tests;
  - the CI compatibility follow-up passed all seven architecture boundary tests
    under Python 3.10, the reviewed Bandit baseline gate, the static-analysis
    policy tests, and the repository TOML formatting check;
  - Ruff passed over source and the changed tests;
  - source Pyright reported 0 errors and the seven inherited lazy-export
    warnings.
- Full verification:
  - pre-review complete Python suite: `1933 passed in 115.95s`;
  - final post-review complete Python suite: `1936 passed in 116.05s`;
  - pre-review coverage suite: `1933 passed`, 88% aggregate coverage;
  - mypy, compileall, Vulture, dependency hygiene, Bandit baseline, Agent
    Maintainer guidance drift, Ruff, Tach, source Pyright, release readiness,
    JavaScript syntax, and `git diff --check` passed;
  - workflow security, Actions lint, secret scan, Markdown/YAML/TOML checks,
    and workflow schema validation passed;
  - wheel and sdist build, Twine metadata, distribution release verification,
    and packaged dashboard asset parity passed.
- Architecture evidence: the initial baseline contained eight Tach violations
  grouped as two core-to-diagnostics imports and six store-to-allowance/pricing
  imports. The initial GitNexus snapshot identified four Python file cycles;
  repeated fresh indexes exposed masked schema/write cycles as the graph was
  simplified. Shared contracts, callback inversion, observation
  synchronization, refresh metadata, and lower write/rebuild primitives were
  split at their actual ownership boundaries rather than allowlisted. The final
  GitNexus graph contains zero Python file cycles; its remaining three cycles
  are two pre-existing frontend-source cycles and one generated-dashboard cycle.
  The final staged impact scan reported high breadth across 111 files and eight
  execution flows, matching the declared cohesive migration without touching
  frontend sources.
- Deviations from plan: nested `interfaces.cli`, `interfaces.http`, and
  `interfaces.mcp` domains are required to represent independent adapters.
  Exact compatibility leaf modules are declared separately from stable parent
  domains so old imports remain available without weakening stable direction.
  Agent Maintainer's full and precommit aggregate profiles remain red on
  inherited repository-wide file-length, Markdown-code Ruff, test-suite
  Pyright, and Xenon ratchets; its change-plan check passes, the Task 30
  dashboard target is now below the file-length threshold, and the touched
  legacy store schema improved from 665 to 647 source lines and from 766 to 741
  physical lines. All named CI-equivalent gates listed above pass directly.
- Final review:
  - one read-only reviewer reported five actionable findings: two high, two
    medium, and one low; all five were accepted;
  - the public store facade now preserves allowance materialization for refresh
    and rebuild, MCP status injects the real readiness probe, dynamic root
    aliases and the `store.api` compatibility leaf have explicit Tach edges,
    and GitNexus stale-index guidance is index-only with corrected fences;
  - reviewer token status and tokens per accepted finding are `pending` because
    aggregate usage attribution was unavailable without retrying the completed
    review.
- Follow-up risks: the three visible non-Python GitNexus cycles remain future
  frontend ownership work. No route, SQLite schema, or frontend behavior
  changed; the existing conversational-readiness schema is now registered and
  documented.

## Task 31 - Enforce SQLite Foreign Keys and Integrity Checks

- Status: complete; `pivot/31-sqlite-integrity` landed through PR #298 as
  squash commit `920d2dbbefacb31820877a2e04c601a6baafda83`.
- Connection and migration contract:
  - every runtime SQLite connection is centralized through the verified shared
    policy or explicitly configures that policy for the in-memory allowance
    fallback;
  - writable and read-only connections enable and verify
    `PRAGMA foreign_keys=ON`; read-only connections also enforce
    `query_only=ON`;
  - schema scripts execute statement-by-statement inside one migration
    savepoint, so a failed migration restores its original user version,
    migration ledger, and rows;
  - source replacement uses declared cascades and clears optional OTel matches
    before deleting their referenced usage rows.
- Diagnostic contract:
  - `codex-usage-tracker.database-integrity.v1` reports bounded pass, fail, or
    unknown state without row identifiers or source content;
  - doctor and `admin integrity` run read-only `integrity_check(100)` and
    `foreign_key_check`; the command exits `0` for pass, `1` for findings, and
    `2` for missing, invalid, or unreadable databases;
  - normal status remains non-blocking and reports `unknown`/`not_checked` with
    the explicit `admin integrity` next action.
- Migration and cleanup verification:
  - historical fixtures for v13, v15-v17, v20-v21, v24, v26-v27, v30, and
    current-minus-one migrate in place and finish with clean integrity checks;
  - the reviewed 18-key inventory covers usage, content, compression,
    recommendation, allowance, and analysis-run cascades;
  - invalid pre-enforcement fixtures and synthetic Compression Lab benchmark
    rows now provide valid parent records rather than bypassing constraints.
- Refresh and cache recovery:
  - one transaction-bound cache repository owns all runtime `refresh_meta`
    writes while refresh metadata, Home metrics, and recommendation invalidation
    keep their existing caller-owned transactions;
  - refresh persists bounded primary, OTel, and finalization phase state;
    interrupted phases retry idempotently and complete the marker;
  - rebuild clears aggregate state and writes its resumable marker in one
    transaction, so pre-clear failure rolls back and post-clear interruption is
    explicit and recoverable on the next refresh.
- Focused verification:
  - the final connection, cache ownership, interrupted workflow, retained
    migration/refresh/rebuild, Home cache, and release-doc slice passed `48`
    tests;
  - the earlier connection, cascade, migration, integrity-report, status, CLI,
    and historical-fixture slice passed `52` tests;
  - the broader store, application, diagnostics, CLI, and evidence slice passed
    `626` tests;
  - Ruff and Tach pass with zero violations; source Pyright reports zero errors
    and the seven inherited lazy-export warnings.
- Full verification:
  - final complete Python suite: `1977 passed in 107.37s`;
  - final coverage suite: `1977 passed`, 88% aggregate coverage;
  - MyPy, Deptry, Vulture, reviewed Bandit baseline, compileall, JavaScript
    syntax, Markdown, TOML, YAML, and `git diff --check` gates passed;
  - source and distribution release-readiness checks, sdist/wheel build, Twine,
    and installed-package smoke checks passed.
- Architecture evidence:
  - after repairing a corrupted derived FTS index, a forced GitNexus rebuild
    completed; the final incremental refresh contains 25,529 nodes, 54,900
    edges, 1,321 clusters, and 300 flows;
  - final change detection mapped 45 indexed files and 92 symbols to 146
    execution flows, classifying the broad connection/migration blast radius as
    critical;
  - exact upstream analysis found three direct callers and 13 affected
    processes for the shared connection policy, while the new integrity checker
    has two direct callers and low standalone blast radius. The complete suite
    and coverage gate exercise the identified store, compression, allowance,
    diagnostics, reporting, server, CLI, context, and MCP paths.
- Final review:
  - one read-only reviewer reported six findings: five medium and one low; all
    six were accepted;
  - rechecks preserve short read-only busy timeouts, historical 0.22 schema
    documentation, retained fixture coverage, one cache write owner, and
    resumable refresh/rebuild phases;
  - reviewer token status is `pending`; aggregate usage attribution timed out
    and was not retried.
- Deviations from plan: Task 31 adds no schema migration or forced database rebuild.
  Atomic script execution replaces `sqlite3.executescript` only to preserve the
  existing schema changes inside the migration transaction. Status deliberately
  avoids a full integrity scan to preserve the bounded endpoint gains from the
  0.23 blocker work.
- Follow-up risks: no automatic repair surface is introduced. Any future schema
  relationship must update the exact foreign-key inventory test and cleanup
  coverage.

## Task 32 - Add Indexed Byte Offsets for Bounded Context Retrieval

- Status: complete and squash-merged to `main` as `4523c39` through PR #299.
- Schema and ingestion contract:
  - schema v35 adds one nullable `usage_events.source_byte_offset`; existing
    rows migrate in place with null offsets and retain sequential fallback;
  - binary JSONL parsing records the exact token-event byte position for ASCII
    and multibyte UTF-8 under LF and CRLF newlines;
  - append-only refresh preserves existing offsets and records new offsets,
    while rewritten and cloned files cannot reuse stale provenance.
- Read contract:
  - the selected-call loader validates path, size, modification time, inode,
    device/prefix provenance, offset bounds, and the already-open descriptor
    identity before seeking;
  - a configurable 128 KiB pre-target window must contain the selected turn
    plus source start or a preceding semantic turn anchor, otherwise the
    existing sequential reader runs;
  - the target token line must match the requested timestamp plus cumulative
    and last-call token values, preventing another call in the same turn from
    satisfying a corrupted offset;
  - offset and fallback modes share parsing, redaction, limits, tool-output
    controls, compaction handling, malformed-line behavior, and quick/full
    serialized estimates, and neither reads beyond the target token event;
  - opt-in diagnostics report `offset_seek` or `sequential_fallback`, a bounded
    reason, and actual inspected source bytes.
- Focused verification:
  - Task 32 offset, provenance, migration, and context suites: `60 passed`;
  - broader parser, store, context, schema, and privacy slice: `331 passed`;
  - targeted Ruff and Pyright report zero findings.
- Performance evidence:
  - the prescribed synthetic source-log benchmark pads the final target source
    to exactly 100,000 lines and compares five-run medians;
  - latest unprofiled result: 131,478 of 9,071,823 bytes inspected (`1.4493%`),
    `0.005884s` offset median versus `0.183515s` sequential median (`31.189x`),
    with byte-for-byte equivalent normalized payloads and all thresholds green;
  - Agent Perf run `20260724T043235Z-63247a16` attributes only `0.08%` of
    application work to `_read_context_from_offset`; the deliberately forced
    fallback remains concentrated in JSON envelope scanning. The earlier
    baseline profile produced no attributable samples, so the identical
    unprofiled ratchet—not profiler comparison—is the speed claim.
- Full verification:
  - complete Python suite: `1998 passed in 115.81s`;
  - coverage suite: `1998 passed`, 88% aggregate coverage;
  - source and built-distribution release checks, wheel/sdist builds, Twine
    validation, and an installed-package smoke test all pass;
  - Ruff, Pyright, MyPy, Tach, Deptry, Vulture, Bandit, compileall, packaged
    dashboard JavaScript syntax, Markdown, YAML, TOML, and diff checks pass
    with only the repository's reviewed existing Bandit/YAML warnings;
  - the full Agent Maintainer gate still reports inherited repository-wide
    file-length, historical-document formatting, Pyright-test, and Xenon
    findings. The roadmap-required legacy migration inventory test remains over
    the generic file limit, while changed production files stay within their
    ratchets and the task-specific and named direct gates above pass without
    suppressing or relaxing findings;
  - the single final read-only review reported four findings (one high, two
    medium, one low); all four were accepted and fixed with same-turn target
    identity, descriptor TOCTOU, pre-turn carry-anchor, and parse-error scoping
    regressions. Reviewer token attribution and tokens per accepted finding are
    `pending` because the one permitted usage-index refresh timed out.
- Deviations from plan:
  - the repository's current provenance owner is `store/sources.py`, not the
    historical `source_records.py` path named by the roadmap;
  - context entry formatting and benchmark ratchet logic moved into focused
    helper modules, and the additive migration uses the existing query-index
    schema owner, keeping changed production files under their active
    file-length ratchets.
- Follow-up risks:
  - pre-v35 rows use sequential fallback until their source is reindexed;
  - a selected turn whose pre-token context exceeds 128 KiB deliberately falls
    back rather than risking an incomplete offset result.

## Remaining Planned Tasks

Tasks 27.5 through 34 are merged. Task 35 is active on
`pivot/35-immutable-action-pins`; Tasks 36 through 45 remain planned in the
approved implementation roadmap. Add a full
entry using the format above when each task becomes active; do not mark a task
complete without its named focused and full verification evidence.

## Task 33 - Persist Generic Analysis Jobs and Reusable Results

- Status: complete locally on `pivot/33-persisted-analysis-jobs`; reviewed PR
  and squash merge remain.
- Storage contract:
  - schema v36 adds compact `analysis_jobs` lifecycle storage and a partial
    unique index that atomically deduplicates active semantic jobs; schema v37
    safely adds expired owner/lease defaults for early pre-release v36 stores;
  - normalized requests, progress, results, and errors are JSON-safe,
    byte-bounded, schema-allowlisted where a stable schema exists, and deeply
    reject raw-context-shaped fields;
  - compatible completed results require the same job kind, semantic key,
    source revision, and result schema.
- Runtime contract:
  - `JobService` uses the repository as the source of truth when configured and
    retains only active worker adapters in process;
  - analysis and allowance workers checkpoint queued, running, completed, and
    failed states while a background heartbeat renews their process lease;
    refresh keeps its transient generic status path;
  - startup and semantic reuse interrupt only expired foreign leases without
    resuming unknown worker code or disturbing a live second process;
  - persisted state changes are owner-scoped and monotonic, so late checkpoints
    cannot regress a terminal state or reduce progress.
- Retention and diagnostics:
  - terminal rows are pruned by age and count in the terminal update transaction
    as well as during explicit maintenance;
  - doctor reports active, queued, running, completed, failed, interrupted, and
    cumulatively pruned counts without creating a missing database.
- Focused verification:
  - repository and restart coverage: `16 passed`;
  - application, HTTP, container, migration, and doctor integration:
    `100 passed`;
  - pre-release v36 lease migration and original startup regressions:
    `52 passed`;
  - the final codec boundary slice: `12 passed`.
- Full verification:
  - complete Python suite: `2016 passed in 126.30s`;
  - coverage suite: 88% aggregate and 90% changed-line coverage;
  - Ruff format/check, MyPy, targeted Pyright, Tach, Deptry, Vulture, configured
    Xenon complexity, Bandit, compileall, file-length ratchets, cohesive
    change-plan validation, and `git diff --check` pass;
  - source and distribution release checks, wheel/sdist build, Twine metadata,
    and a clean installed-package smoke pass;
  - one broad Agent Maintainer run
    `20260724T063559290936Z-full-1ff4b37aa9ba` exposed inherited
    repository-wide formatting/type/boundary noise plus task-local source
    length, privacy, and change-budget findings. The task-local findings were
    fixed and rechecked directly without rerunning the broad profile or
    relaxing a threshold.
- Final review:
  - the single read-only reviewer reported five findings and all five were
    accepted: live-process lease ownership, owner-scoped monotonic transitions,
    deep privacy validation for every JSON column, transactional terminal
    pruning, and a cold-import cycle;
  - post-review regressions cover two live owners, heartbeat expiry, stale
    updates, every persisted JSON column, pruning during terminal updates,
    early v36 stores, and a cold Python import;
  - reviewer token status and tokens per accepted finding are `pending`; the
    one permitted local aggregate attribution call was rejected by the
    installed plugin's privacy-mode contract and was not retried.
- Code-intelligence verification:
  - GitNexus's derived FTS cache was corrupt; its normal repair path also
    failed, so an index-only forced rebuild restored a clean disposable index;
  - the refreshed index contains 25,716 nodes, 55,445 edges, 1,299 clusters,
    and 300 flows. It maps this 20-file change to 147 symbols and 18 affected
    execution flows with critical expected schema/application reach; the
    focused integration, full-suite, release, and installed-package gates above
    validate that reach.
- Follow-up risks:
  - a crashed worker can remain active for at most the 30-second lease window;
    startup or the next semantic lookup then marks it interrupted;
  - generic persistence deliberately stores no raw context and cannot resume
    unknown worker code after a process exit.

## Task 34 - Make Quality and Work-Proof Gates Directly Blocking

- Status: merged through PR #301 as `0a4818e`.
- Blocking coverage:
  - aggregate branch coverage now fails below 85% in both Coverage.py and Agent
    Maintainer configuration;
  - pull-request CI writes `coverage.xml` and directly fails below 90%
    changed-line coverage with `diff-cover`;
  - Python 3.14 uses the coverage run as its matrix test run instead of running
    the full suite twice.
- Work-proof contract:
  - every MCP tool declares explicit constant, row, source, evidence, or job
    work proof in the validated declarative catalog;
  - unknown tools cannot silently fall back to constant work;
  - synthetic known-row query and changed-source refresh tests mutate successful
    payloads to zero units and prove those false-green responses fail, while
    constant-size status remains valid.
- Schema and compatibility inventories:
  - a static release inventory is checked against the runtime schema registry,
    public schema documentation, and schema IDs emitted by Python and React
    runtime sources;
  - the first blocking run found and registered 14 existing Python schema IDs
    plus the selected-report React export schema that were previously orphaned;
  - all 45 deprecated MCP aliases are named in the normative deprecation ledger
    and checked against exact runtime lifecycle and migration metadata.
- Verification:
  - focused schema, compatibility, work-proof, release, and registry slices:
    `43 passed` and `16 passed`;
  - complete Python suite: `2029 passed in 138.08s`;
  - complete coverage suite: `2029 passed in 147.42s`, 88.05% aggregate branch
    coverage;
  - changed-line coverage initially failed at 89%, prompting four negative-path
    registry tests; the final staged result is 93%;
  - Ruff on changed files, MyPy, Pyright, Tach, Deptry, Vulture, Bandit,
    compileall, release checks, wheel/sdist build, Twine validation, and the
    clean installed-package smoke pass;
  - the single broad Agent Maintainer `ci` profile
    `20260724T075319219554Z-ci-5ae198abc763` reported inherited repository-wide
    formatting, test-type, dependency-boundary, complexity, file-length, and
    missing frontend-helper findings. Its task-local workflow injection,
    registry-complexity, and changed-file-length findings were fixed and
    rechecked directly without rerunning the broad profile or weakening a
    threshold.
- Final review:
  - the single read-only reviewer reported two actionable findings, one high
    and one medium; both were accepted;
  - R1 replaced family-shaped proof guesses with per-tool paths matching core
    envelopes, compatibility JSON payloads, persisted jobs, and concrete local
    file results, then added representative positive and false-green tests;
  - R2 made the release checker identify the named changed-line coverage step,
    require its pull-request condition and command, reject
    `continue-on-error`, and cover both disabled forms with negative tests;
  - the bounded post-review recheck passed `54 tests`, retained 88.05%
    aggregate coverage and 93% changed-line coverage, and passed the source
    release checker.
- PR verification:
  - the first PR run exposed an obsolete Vulture protocol stub and an unquoted
    `BASE_REF` in the new shell command;
  - the stub was removed, the branch reference and release invariant now
    require shell-safe quoting, and the exact Vulture, Zizmor, focused pytest,
    Ruff, and release-readiness commands pass locally.
- Follow-up risks:
  - auxiliary schemas with intentionally flexible payloads are inventoried with
    empty required-field maps; future stabilization may tighten those shapes
    without changing their IDs when the change is additive.

## Task 35 - Pin Workflow and Release Dependencies Immutably

- Status: complete locally on `pivot/35-immutable-action-pins`; final review
  complete and reviewed PR remains.
- Immutable workflow contract:
  - every third-party workflow action uses an official 40-character commit
    SHA and a trailing reviewed release-tag comment;
  - `REVIEWED_ACTION_PINS` validates the action, tag, and SHA as one offline
    tuple, so mutable, abbreviated, missing-comment, and mismatched-comment
    references fail release readiness;
  - local actions remain relative, while Docker action references require a
    `sha256` digest.
- Reviewed dependency sources:
  - action tags and commits were resolved from the official GitHub release and
    commit APIs;
  - the installed-package `python:3.14-slim` smoke image is pinned to the
    reviewed multi-platform manifest digest.
- Dependabot and operator policy:
  - Dependabot action PRs carry CI/dependency metadata and require a human to
    update the release comment and reviewed-pin catalog together;
  - development and release-checklist docs record the review and verification
    sequence for action updates.
- Focused verification:
  - CI policy, immutable-pin, release-quality, release CLI, and packaging slice:
    `74 passed`;
  - `actionlint`, offline `zizmor`, Ruff, source release readiness, and
    `git diff --check` pass.
- Broad verification:
  - CI-equivalent Agent Maintainer run
    `20260724T090631521509Z-ci-313859a133e4` completed the full suite and
    surfaced inherited repository-wide file-length, formatting, type,
    complexity, and boundary debt;
  - its only task-local failure was the cohesive change-plan template, which
    was repaired and passes the direct staged plan check.
- Final review:
  - the single read-only reviewer reported two medium false-green findings and
    both were accepted;
  - noncanonical-but-valid YAML `uses` keys are now rejected and covered;
  - Docker smoke validation parses the actual `DEFAULT_DOCKER_IMAGE`
    assignment, so a decoy digest cannot satisfy the gate;
  - reviewer token attribution remains `pending` after the permitted aggregate
    metrics helper timed out; no retry was attempted.
- Follow-up:
  - Task 36 owns build-once artifact promotion and will reuse these immutable
    workflow boundaries.

## Task 36 - Promote One Verified Release Artifact

- Status: merged by PR #304 as `a52338d510b731288819c169dbbd2ba412fa56ad`;
  the complete hosted CI matrix passed.
- Build-once contract:
  - one wheel/sdist pair and one canonical manifest are uploaded as the sole
    `python-dist` build artifact;
  - the manifest binds exact hashes to the Git SHA, package version, database
    schema, JSON schemas, MCP tool profiles, and Evidence Console bundles;
  - missing, altered, multi-version, stale-asset, wrong-source, and
    non-canonical inputs fail closed.
- Promotion graph:
  - TestPyPI receives the build bytes, then qualification downloads and smokes
    those published bytes;
  - protected PyPI publication consumes a fresh verified download from
    TestPyPI and never rebuilds;
  - GitHub Release attachment consumes verified PyPI bytes, and the last job
    rechecks hashes at all three public locations.
- Manual safety:
  - workflow dispatch is TestPyPI-only; production publication requires an
    exact `v<package-version>` release tag and the protected `pypi`
    environment;
  - manual TestPyPI dry runs use distinct prerelease versions, while a
    production release performs TestPyPI qualification and PyPI promotion in
    one release-event run.
- Primary verification:
  - the release, packaging, workflow-policy, and immutable-pin slice passes
    `122` tests; the complete new release package passes `71` focused tests;
  - changed-line coverage is `92%`, including `92.7%` for artifact manifests,
    `85.7%` for artifact normalization, and `94.8%` for promotion evidence;
  - Ruff, mypy, focused Pyright, Tach, Deptry, Bandit, actionlint, offline
    Zizmor, schema inventory, suppression budget, change-plan budget, source
    release readiness, and whitespace checks pass;
  - a canonical wheel/sdist pair passed Twine, manifest create/verify, and an
    isolated installed-wheel smoke covering the CLI, package data, MCP core
    inventory, plugin installation, setup/doctor, dashboard generation, and a
    strict-privacy support bundle;
  - two independent final-source builds used the same commit-derived
    `SOURCE_DATE_EPOCH`; the wheels and normalized sdists were byte-identical.
- Broad verification:
  - the full suite initially passed `2072` tests and exposed two Task 36
    failures: missing Tach ownership and release schemas incorrectly listed in
    the MCP-only contract document; both were fixed and their exact regressions
    pass directly;
  - the one broad Agent Maintainer run exposed those same Task 36 issues plus
    file length, dependency, security, complexity, and coverage findings. All
    Task 36 findings were repaired and bounded checks pass. Remaining
    file-length and repository-format failures are inherited outside this
    change.
- Tooling note:
  - GitNexus successfully supplied the base architecture/process orientation.
    Its post-diff incremental refresh failed with an inconsistent `file_fts`
    index, so final conclusions use the source, Tach, tests, and release
    artifacts as authority rather than rebuilding the index and risking
    generated guidance churn.
- Final review:
  - one read-only reviewer reported three findings and all three were accepted:
    reproducible rerun/manual-candidate handling, release-tag/package-version
    binding, and exact package-index artifact-set validation;
  - all three fixes pass the bounded recheck above. Reviewer token attribution
    is `pending` because the aggregate metrics helper timed out.

## Task 37 - Budget Product and Package Complexity

- Status: complete; PR #305 merged to `main` at
  `f5cb45ac64653f29c8712a0a1ea09ddfd0674ac9`.
- Graph-guided scope:
  - a fresh GitNexus index at `a52338d` routed measurement to the MCP
    `tool_specs` catalog, CLI `build_parser` inventory, Evidence Console route
    catalog, stable JSON schema registry, SQLite schema constant, and release
    artifact boundary;
  - Serena verified the exact symbols before implementation. Source and focused
    tests remain authoritative.
- Budget decisions:
  - default/full MCP ceilings are 7/59, stable CLI families are 11, and
    Evidence Console placements remain 3 primary, 1 contextual, and 1 utility;
  - immutable PyPI 0.23.0 artifacts establish 7,017,243-byte wheel and
    32,021,790-byte sdist baselines with exactly 5% rounded-up headroom;
  - post-constellation initial React JavaScript is 61,457 deterministic gzip
    bytes with exactly 10% rounded-up headroom;
  - existing oversized authored files are explicitly frozen while new or
    growing violations remain zero;
  - 0.23 schema 34 to pre-adoption schema 37 is recorded as architecture
    history, and the one-increment blocking ratchet starts prospectively at 37.
- Focused verification so far:
  - all 31 budget tests plus the focused CLI bundle-contract test pass,
    including a reduced ceiling for every metric, strict literal route-catalog
    parsing, recursive source exclusions, line-debt growth, and duplicate
    distributions;
  - source measurement, release readiness, MyPy, Ruff, format, and the
    config-backed dashboard bundle gate pass.
- Broad verification:
  - one Agent Maintainer `ci` run
    `20260724T111442082155Z-ci-c9b951763d69` passed all 2,146 tests and
    reported only inherited repository-wide file-length, formatting, Pyright
    test, Xenon, Pylint, Tach/config, optional TypeScript-tooling, and
    Zizmor findings; its launch-snapshot change-plan failure was corrected and
    the direct plan check passes;
  - final wheel/sdist measurements are 7,077,471 and 32,160,218 bytes, both
    under their immutable-0.23-derived ceilings.
- Final review:
  - the single read-only reviewer reported four findings (two medium, two
    low); all four were accepted;
  - the route catalog now rejects comments, nested decoys, spreads, computed
    keys, calls, and non-object entries; critical policy values are pinned;
    recursive exclusions are normalized; and the checker itself now satisfies
    the Task 37 Xenon A/B complexity gate;
  - reviewer token attribution is `pending` in the aggregate-only metrics
    ledger.

## 0.24 Release Blocker - Read-only Compression Status Polling

- Status: fixed locally on `fix/compression-status-read-only`; release gate
  remains in progress.
- Root cause:
  - `get_compression_run(..., touch=False)` still opened the writable
    connection and initialized the schema while the dashboard polled job status;
  - `read_compression_source_generation()` also performed schema setup during
    the background evidence fold;
  - those redundant writes could overlap and fail the compression job with
    `sqlite3.OperationalError`.
- Fix:
  - non-touching status reads now use `connect_read_only`;
  - source-generation reads require the caller's already initialized schema and
    perform only the query.
- Verification:
  - deterministic regressions prove both paths work without initialization or
    writes;
  - two accepted reviewer findings restore missing-database status semantics
    and fresh-database query initialization without reintroducing writes on the
    normal initialized read path;
  - the focused application/compression/store/dashboard slice passes 56 tests;
  - the previously flaky end-to-end dashboard compression test passes 100
    consecutive runs;
  - the full Python suite passes 2,158 tests with 88.1% coverage; its broad gate
    also exposed and hardened one frontend retry assertion whose default
    one-second wait was unreliable under full-suite contention; ESLint,
    TypeScript, and all 621 frontend tests then pass;
  - Ruff lint, configured MyPy, focused Pyright, release readiness,
    product-complexity budget, and whitespace checks pass.
- Final review:
  - the single read-only reviewer reported two medium findings; both were
    accepted and pass bounded regression checks;
  - review metrics: 2 findings, 2 accepted; reviewer tokens `pending`; tokens
    per accepted finding `pending`.

## Task 38 - Convert Legacy Dashboard Workbenches to Notice-only Routes

- Status: merged by PR #307 as `cacd3fff73acc5b4cbaa7ecb442dc993038fa25f`;
  the complete hosted CI matrix passed.
- Graph-guided scope:
  - a fresh GitNexus index at `b4dc219` identified
    `App -> DashboardRouteView` as the production rendering boundary;
  - source inspection then found a second production reachability path through
    `currentViewExport`, whose compatibility exports dynamically imported the
    retired page modules.
- Notice-only behavior:
  - Investigate, Compression Lab, Cache and Context, Diagnostics Notebook, and
    Reports now render one shared compatibility notice;
  - each notice names the previous feature, core MCP replacement, `0.24.x`
    compatibility window, `0.25.0` removal release, copyable prompt, and
    Evidence/Explore/Limits destinations;
  - direct-route component and Playwright tests prove the five routes make no
    historical workbench API requests, and automatic refresh is disabled.
- Compatibility preservation:
  - HTTP, CLI, full-profile MCP, and CSV export compatibility remain supported
    through `0.24.x`;
  - legacy CSV selection moved into a 1.71 kB gzip compatibility chunk with
    four parity tests, so exports no longer import retired UI modules;
  - route inventory explicitly classifies all retained investigations,
    reports, diagnostics, compression, context, and investigator endpoints as
    compatibility-only.
- Production bundle:
  - all five retired page chunks are absent from the emitted asset directory
    and from the `App.js` dependency map;
  - the bundle gate and release tests now fail closed if any retired chunk is
    emitted or referenced;
  - the ratcheted Diagnostics page debt decreased from 510/480 to 504/475
    physical/nonblank lines.
- Verification:
  - TypeScript, ESLint, dependency boundaries, dead-code, Stylelint, source
    budgets, production build, bundle budgets, and release readiness pass;
  - full frontend suite passes `609` tests in `117` files;
  - focused route-inventory and release assertions pass `6` tests;
  - Chromium release-candidate matrix passes `14` tests, including all five
    direct notice-only routes with zero historical requests;
  - `dashboard-verify` completed successfully as
    `20260724T131359.371748Z`.
- Localization:
  - all notice copy, including the status badge and destination-group
    accessibility label, is routed through the shell i18n layer;
  - all 12 supported locale catalogs include the 16 compatibility keys with
    placeholder parity;
  - 148 i18n contract tests, 11 notice-component tests, and the Spanish
    Chromium release-candidate assertion pass.
- Broad verification:
  - one Agent Maintainer `ci` run
    `20260724T131547933321Z-ci-12d86b4eae31` passed all `2,162` Python tests
    at 88.12% coverage and all `609` frontend tests;
  - it reported inherited repository-wide file-length, documentation-format,
    Pyright, Xenon, and optional TypeScript-helper findings; task-local
    TypeScript, ESLint, dependency-boundary, source-budget, bundle, release,
    privacy, dependency, and secret checks pass directly.
- Roadmap deviation:
  - `api/client.ts` and `CompressionLabPage.tsx` needed no behavioral change:
    production routing no longer reaches their old query/job code, while the
    source remains intentionally available for Tasks 40 and 41.
- Final review:
  - the single read-only reviewer reported one low-severity localization
    finding; it was accepted and fixed across every supported locale;
  - review metrics: 1 finding, 1 accepted (`R1`); reviewer tokens `pending`;
    tokens per accepted finding `pending`.

## Task 39 - Gate and Publish Release 0.24.0

- Status: release candidate preparation and local qualification complete;
  TestPyPI rehearsal, hosted review, merge, and public promotion remain.
- Foundation entry gate:
  - `docs/superpowers/reports/0.24-foundation-audit.md` audits
    `589e10a` and records `PROCEED`;
  - the audit has no blockers, and every high finding was assigned to Tasks
    28-33, all of which are complete before this gate;
  - the release keeps the five legacy workbenches notice-only through
    `0.24.x`; their implementation and compatibility removal remain assigned
    to Tasks 40 and 41 for `0.25.0`.
- Architecture and contract inventory:
  - Tach reports no dependency violations and keeps
    `root_module = "forbid"`;
  - the release carries SQLite schema version `37`, `114` stable JSON schemas,
    and MCP profiles of `7` core, `59` full, and `64` developer tools;
  - the refreshed GitNexus graph at the Task 38 merge contains `25,400` nodes,
    `54,647` edges, `1,291` clusters, and `300` execution flows.
- Focused integrity verification:
  - all `36` architecture, connection-integrity, foreign-key cascade,
    persisted-job, and byte-offset tests pass;
  - the dedicated release, public-documentation, and CLI slice passes `48`
    tests, and source release readiness passes.
- Complete product verification:
  - all `2,164` Python tests pass at `88.12%` coverage against the enforced
    `85%` floor;
  - Ruff, configured MyPy, Pyright with zero errors, the product-complexity
    budget, and whitespace checks pass;
  - the frontend gate passes all `609` tests plus ESLint, TypeScript,
    dependency boundaries, dead-code, Stylelint, source budgets, production
    bundle budgets, release readiness, and deterministic asset verification;
  - the Chromium release-candidate matrix passes all `14` tests.
- Performance evidence:
  - the 100,000-row focused route benchmark has no budget violations;
  - the synthetic-history gate passes every threshold and proves equivalent
    offset-seek payloads while measuring a `27.939x` median speedup over
    sequential fallback for the late-source ratchet.
- Local artifact qualification:
  - Twine and distribution release readiness pass for the wheel and sdist;
  - the isolated installed-package smoke verifies version `0.24.0`, all `7`
    core MCP tools, all `59` bundled resources, plugin installation,
    setup/doctor, dashboard generation, and strict support-bundle export;
  - local wheel:
    `aa493c338e52c700695e9c9f888c41f2089c8ac21edbd8441a6c144f449103ff`
    (`7,022,392` bytes);
  - local sdist:
    `3d13428f005d0ac95a0ff2cae353ed4e792aca93e9d29738e272a2118cd758e0`
    (`32,121,969` bytes);
  - these hashes are local qualification evidence only; the release-event
    manifest remains authoritative for public TestPyPI, PyPI, and GitHub
    artifact identity.
- Gate-discovered correction:
  - the first distribution check proved the new JSON manifest example was
    absent from the sdist; `MANIFEST.in` now packages documentation JSON and
    the rebuilt distribution passes the exact-member gate.
- Roadmap deviations:
  - the package version also required synchronized updates to the runtime
    constant, plugin manifest, source and packaged MCP launchers, and
    development smoke commands;
  - release checks and public-document tests now fail closed if the new
    release note, upgrade guide, or manifest example is absent.
