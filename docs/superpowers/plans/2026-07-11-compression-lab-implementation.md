# Compression Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ship the five-PR Compression Lab roadmap: bounded attribution, six versioned detectors, persistent async analysis, compact MCP query tools, overlap-aware intervention simulation, and skill/plugin routing.

**Architecture:** Add a `codex_usage_tracker.compression` domain above the existing store APIs. The store owns evidence queries and persisted run/candidate rows; compression owns candidate contracts, attribution, estimation, orchestration, jobs, payloads, and simulation; MCP wrappers remain thin. Every PR starts from the newly merged `main`, updates the roadmap ledger, and preserves existing MCP contracts.

**Tech Stack:** Python 3.10+, standard-library SQLite/threading/statistics, FastMCP, pytest, Tach, Agent Maintainer, Markdown.

## Global Constraints

- Research-grade measurement is the primary product goal, but all savings remain explicitly heuristic.
- Every candidate returns nonnegative ordered `low`, `likely`, and `high` estimates.
- Automatic local-content analysis is allowed; default payloads omit raw excerpts.
- Whole-call tokens must never be multiplied across repeated events.
- Portfolio estimates must not exceed unique eligible record/component capacity.
- Persist analysis runs, not intervention experiments.
- Cold full-history analysis is asynchronous; warm profile/list queries target 500 ms.
- Status/profile/list/detail target payloads are 4/8/16/24 KB by default.
- Existing MCP tool names and stable payload contracts remain compatible.
- Python 3.10 remains the minimum version; use no new runtime dependency.
- Source files remain under 600 physical and 450 source lines.
- Each PR remains under the configured 800-line/20-file change budget or includes a reviewed cohesive-change plan.
- Use synthetic fixtures only; never commit real local content, paths, commands, or logs.

---

## PR 1: Attribution Kernel And Persistent Run Cache

### Task 1: Compression Domain Contracts And Stable IDs

**Files:**
- Create: `src/codex_usage_tracker/compression/__init__.py`
- Create: `src/codex_usage_tracker/compression/models.py`
- Create: `src/codex_usage_tracker/compression/identifiers.py`
- Create: `src/codex_usage_tracker/compression/tach.domain.toml`
- Test: `tests/compression/test_models.py`

**Interfaces:**
- Produces: `EstimateRange`, `ComponentExposure`, `CandidateDraft`, `CompressionCandidate`, `CompressionScope`, `stable_scope_hash(scope)`, and `stable_candidate_id(...)`.
- `EstimateRange` validates `0 <= low <= likely <= high` and serializes with `as_dict()`.
- `ComponentExposure` supports the components `cached_input`, `uncached_input`, `output`, `reasoning_output`, `content_fragment`, and `tool_output`.

- [ ] **Step 1: Write failing contract and deterministic-ID tests**

```python
def test_estimate_range_requires_ordered_nonnegative_values() -> None:
    with pytest.raises(ValueError, match="low <= likely <= high"):
        EstimateRange(low=20, likely=10, high=30)


def test_candidate_id_is_deterministic_for_revision_scope_and_policy() -> None:
    first = stable_candidate_id(
        source_revision="rev-1",
        scope_hash="scope-1",
        family="file_rediscovery",
        pattern_key="path:abc",
        detector_version="file-v1",
        estimator_version="compression-estimator-v1",
    )
    assert first == stable_candidate_id(
        source_revision="rev-1",
        scope_hash="scope-1",
        family="file_rediscovery",
        pattern_key="path:abc",
        detector_version="file-v1",
        estimator_version="compression-estimator-v1",
    )
```

- [ ] **Step 2: Run the tests and confirm imports fail**

Run: `.venv/bin/python -m pytest tests/compression/test_models.py -q`

Expected: FAIL because `codex_usage_tracker.compression` does not exist.

- [ ] **Step 3: Implement frozen dataclasses and SHA-256 identifiers**

Use canonical JSON with sorted keys and compact separators for hashes. Reject unknown component names and invalid estimate ranges in `__post_init__`.

- [ ] **Step 4: Add the Tach domain contract**

```toml
[root]
depends_on = [
  "//codex_usage_tracker.core",
  "//codex_usage_tracker.pricing",
  "//codex_usage_tracker.store",
]
```

- [ ] **Step 5: Run focused tests and architecture checks**

Run: `.venv/bin/python -m pytest tests/compression/test_models.py -q`

Expected: PASS.

Run: `.venv/bin/python -m tach check`

Expected: PASS.

- [ ] **Step 6: Commit the contracts**

```bash
git add -- src/codex_usage_tracker/compression tests/compression/test_models.py
git commit -m "feat: add compression lab contracts"
```

### Task 2: Record-Component Attribution And Overlap Allocation

**Files:**
- Create: `src/codex_usage_tracker/compression/attribution.py`
- Test: `tests/compression/test_attribution.py`

**Interfaces:**
- Consumes: `EstimateRange`, `CandidateDraft`, and component capacities from Task 1.
- Produces: `build_capacity_ledger(rows)`, `validate_candidate_claims(drafts, ledger)`, and `allocate_overlaps(drafts, ledger)`.
- Allocation is proportional per record/component/bound and uses candidate ID as the deterministic tie key.

- [ ] **Step 1: Write duplicate-event and overlap invariant tests**

```python
def test_repeated_events_do_not_duplicate_whole_call_capacity() -> None:
    ledger = build_capacity_ledger([
        {"record_id": "call-1", "uncached_input_tokens": 1000},
        {"record_id": "call-1", "uncached_input_tokens": 1000},
    ])
    assert ledger.capacity("call-1", "uncached_input") == 1000


def test_overlap_allocation_caps_portfolio_at_unique_capacity() -> None:
    adjusted = allocate_overlaps(two_candidates_claiming_same_1000_tokens(), one_call_ledger(1000))
    assert sum(row.adjusted_estimate.likely for row in adjusted) == 1000
    assert all(row.adjusted_estimate.likely <= row.gross_estimate.likely for row in adjusted)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/compression/test_attribution.py -q`

Expected: FAIL because attribution functions are missing.

- [ ] **Step 3: Implement capacity deduplication and proportional allocation**

Use integer arithmetic with deterministic remainder distribution ordered by `candidate_id`. Validate candidate claims before allocation and raise `AttributionError` for unknown records, unknown components, negative claims, or gross estimates above eligible exposure.

- [ ] **Step 4: Run focused and property-style parameterized tests**

Run: `.venv/bin/python -m pytest tests/compression/test_attribution.py -q`

Expected: PASS for low/likely/high bounds, duplicate events, three-way overlap, disjoint records, and zero capacity.

- [ ] **Step 5: Commit attribution**

```bash
git add -- src/codex_usage_tracker/compression/attribution.py tests/compression/test_attribution.py
git commit -m "feat: add bounded compression attribution"
```

### Task 3: Schema V15 And Compression Run Repository

**Files:**
- Modify: `src/codex_usage_tracker/store/schema.py`
- Create: `src/codex_usage_tracker/store/compression_runs.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Modify: `tests/store/test_store_migrations.py`
- Test: `tests/store/test_compression_runs.py`

**Interfaces:**
- Produces store APIs: `create_compression_run`, `update_compression_run`, `replace_compression_candidates`, `find_compression_run`, `get_compression_run`, `list_compression_candidates`, `get_compression_candidate`, and `delete_stale_compression_runs`.
- Run cache lookup keys: source revision, scope hash, detector-set version, estimator version, and schema version.

- [ ] **Step 1: Write migration and repository tests**

```python
def test_v15_creates_compression_run_tables(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.db") as conn:
        init_db(conn)
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"compression_runs", "compression_candidates", "compression_candidate_records"} <= names


def test_exact_cache_key_reuses_only_completed_run(tmp_path: Path) -> None:
    run_id = create_completed_run(tmp_path / "usage.db", source_revision="rev-1")
    assert find_compression_run(tmp_path / "usage.db", exact_cache_key("rev-1"))["run_id"] == run_id
    assert find_compression_run(tmp_path / "usage.db", exact_cache_key("rev-2")) is None
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/store/test_store_migrations.py tests/store/test_compression_runs.py -q`

Expected: FAIL because schema version 15 and repository APIs do not exist.

- [ ] **Step 3: Add migration 15 and indexed tables**

Add `compression_runs`, `compression_candidates`, and `compression_candidate_records` exactly as specified in the design. Use foreign keys with cascade deletion, indexes for cache lookup/ranking, JSON text columns for structured fields, and UTC ISO timestamps.

- [ ] **Step 4: Implement transactional persistence and compact JSON decoding**

Use one transaction to replace a run's candidates and claims. Candidate list queries must filter/sort/page in SQL and avoid loading nested claim rows.

- [ ] **Step 5: Run store, migration, and attribution tests**

Run: `.venv/bin/python -m pytest tests/store/test_store_migrations.py tests/store/test_compression_runs.py tests/compression -q`

Expected: PASS.

- [ ] **Step 6: Update roadmap PR 1 status and commit**

Set PR 1 to `implemented; awaiting PR validation` and append a dated progress entry.

```bash
git add -- src/codex_usage_tracker/store tests/store docs/compression-lab-roadmap.md
git commit -m "feat: persist compression analysis runs"
```

### Task 4: Validate, PR, And Merge PR 1

- [ ] Run `.venv/bin/python -m pytest tests/compression tests/store/test_compression_runs.py tests/store/test_store_migrations.py -q`.
- [ ] Run `just v` once for the coherent PR state.
- [ ] Run `.venv/bin/python scripts/check_release.py` and `git diff --check`.
- [ ] Review status, diff stat, actual diff, and staged/private-data exposure.
- [ ] Push `feature/compression-lab-foundation`, open PR titled `feat: add compression attribution foundation`, wait with `just wait-pr <number>`, fix all failures, and squash merge.
- [ ] Record the PR number and merge SHA in `docs/compression-lab-roadmap.md` on the next branch.

---

## PR 2: Six Detectors And Versioned Estimators

### Task 5: Shared Evidence Snapshot And Estimator Registry

**Files:**
- Create: `src/codex_usage_tracker/store/compression_evidence.py`
- Modify: `src/codex_usage_tracker/store/api.py`
- Create: `src/codex_usage_tracker/compression/evidence.py`
- Create: `src/codex_usage_tracker/compression/estimators.py`
- Test: `tests/compression/test_estimators.py`
- Test: `tests/store/test_compression_evidence.py`

**Interfaces:**
- Produces `CompressionEvidenceSnapshot`, loaded once per run, with calls, turns, tool calls, command runs, file events, content fragments, compactions, and coverage.
- Produces `estimate_candidate(draft, snapshot, policy=ESTIMATOR_POLICY_V1)` using direct, matched, then fallback tiers.

- [ ] Write failing evidence deduplication, percentile-baseline, fallback-range, and confidence tests.
- [ ] Run focused tests and confirm missing interfaces.
- [ ] Implement one read-only scoped evidence query with normalized unique keys and coverage counts.
- [ ] Implement `compression-estimator-v1` in one policy constant and standard-library quantile matching.
- [ ] Verify `.venv/bin/python -m pytest tests/compression/test_estimators.py tests/store/test_compression_evidence.py -q` passes.
- [ ] Commit with `feat: add compression evidence and estimators`.

### Task 6: Context, Repetition, And Output Detector Modules

**Files:**
- Create: `src/codex_usage_tracker/compression/detector_protocol.py`
- Create: `src/codex_usage_tracker/compression/context_detectors.py`
- Create: `src/codex_usage_tracker/compression/repetition_detectors.py`
- Create: `src/codex_usage_tracker/compression/output_detectors.py`
- Create: `src/codex_usage_tracker/compression/detector_registry.py`
- Test: `tests/compression/test_context_detectors.py`
- Test: `tests/compression/test_repetition_detectors.py`
- Test: `tests/compression/test_output_detectors.py`

**Interfaces:**
- `CompressionDetector.detect(snapshot, scope) -> list[CandidateDraft]`.
- Registry order: stale context, cache break/resume, file rediscovery, shell retry, validation repetition, tool-output bloat.
- Every draft declares detector version, eligible components, trace handles, intervention, and verification.

- [ ] Write one manually calculated fixture per detector plus duplicate-event and missing-coverage cases.
- [ ] Run tests and confirm missing detector implementations.
- [ ] Implement context detectors without claiming output/reasoning savings.
- [ ] Implement repetition detectors using fragment/output estimates rather than whole-call totals.
- [ ] Implement output detector with bounded retained-output target and confidence downgrade for weak downstream evidence.
- [ ] Verify all detector and attribution tests pass.
- [ ] Commit with `feat: add compression opportunity detectors`.

### Task 7: Compression Run Builder And Local Dogfood

**Files:**
- Create: `src/codex_usage_tracker/compression/run_builder.py`
- Create: `src/codex_usage_tracker/compression/profile.py`
- Test: `tests/compression/test_run_builder.py`
- Modify: `docs/compression-lab-roadmap.md`

**Interfaces:**
- `build_compression_run(db_path, scope, progress_callback=None, detector_families=None, force=False) -> dict[str, Any]`.
- Runs detectors over one snapshot, estimates drafts, allocates overlaps, persists candidates, and returns a compact profile.

- [ ] Write failing tests for successful, partial-warning, zero-evidence, and exact-cache-hit runs.
- [ ] Add a failing incremental test proving one appended record recomputes only its record/thread candidates before global overlap allocation.
- [ ] Implement staged progress at evidence load, each detector, attribution, persistence, and profile completion.
- [ ] Implement source-revision change detection and affected-record/thread incremental recomputation when detector and estimator versions are unchanged.
- [ ] Add local benchmark assertions for warm cache and a non-blocking benchmark script only if existing test timing helpers are insufficient.
- [ ] Run the new report on synthetic data and then dogfood against the maintainer DB without committing raw evidence.
- [ ] Update PR 2 roadmap status and commit with `feat: build compression analysis profiles`.
- [ ] Run `just v`, open/merge PR 2, and record its PR/merge SHA on the next branch.

---

## PR 3: Async MCP Lifecycle And Compact Query Surface

### Task 8: Persistent Job Registry And Monotonic Progress

**Files:**
- Create: `src/codex_usage_tracker/compression/jobs.py`
- Test: `tests/compression/test_jobs.py`

**Interfaces:**
- `CompressionJobRegistry.start(scope, refresh=False, detector_families=None) -> dict`.
- `status(run_id, include_result=False) -> dict`.
- Identical active requests return the same run ID; valid completed cache returns immediately.

- [ ] Write failing tests for job deduplication, cache hit, monotonic progress, partial completion, failure, and process restart status from SQLite.
- [ ] Implement daemon workers backed by persisted run state; keep only thread handles in memory.
- [ ] Ensure errors are structured and never include content excerpts.
- [ ] Verify `tests/compression/test_jobs.py` and run-builder tests pass.
- [ ] Commit with `feat: add async compression analysis jobs`.

### Task 9: MCP Start, Status, Profile, Candidate, And Detail Tools

**Files:**
- Create: `src/codex_usage_tracker/compression/payloads.py`
- Create: `src/codex_usage_tracker/compression/api.py`
- Create: `src/codex_usage_tracker/cli/mcp_compression.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `src/codex_usage_tracker/cli/tach.domain.toml`
- Test: `tests/cli/test_mcp_compression.py`
- Modify: `tests/cli/test_cli_release.py`

**Interfaces:**
- Public tools: `usage_compression_start`, `usage_compression_status`, `usage_compression_profile`, `usage_compression_candidates`, `usage_compression_candidate_detail`.
- Detail evidence modes: `handles`, `summaries`, `excerpts` with explicit bounds.

- [ ] Write failing direct MCP contract tests for tool names, envelope fields, cache metadata, `limit=0`/`None`, pagination, stale IDs, and excerpt disclosure.
- [ ] Implement compact payload builders with target-size measurements and truncation metadata.
- [ ] Implement thin FastMCP wrappers that delegate to `compression.api`.
- [ ] Import/re-export tools from `mcp_server.py` without adding business logic there.
- [ ] Verify focused MCP tests, Tach, Ruff, and mypy pass.
- [ ] Commit with `feat: expose compression lab MCP tools`.

### Task 10: Contract Documentation And PR 3 Integration

**Files:**
- Modify: `docs/mcp.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/compression-lab-roadmap.md`
- Test: `tests/cli/test_mcp_integration.py`

- [ ] Add one end-to-end synthetic MCP lifecycle test: start, poll, profile, page candidates, inspect one detail.
- [ ] Document exact arguments, schemas, disclosure fields, polling flow, and examples.
- [ ] Validate response-size targets in tests for default synthetic payloads.
- [ ] Run `just v`, release readiness, Markdown lint, and diff checks.
- [ ] Open/merge PR 3 and record its PR/merge SHA on the next branch.

---

## PR 4: Overlap-Aware Intervention Simulator

### Task 11: Intervention Catalog And Portfolio Simulation

**Files:**
- Create: `src/codex_usage_tracker/compression/interventions.py`
- Create: `src/codex_usage_tracker/compression/simulation.py`
- Test: `tests/compression/test_simulation.py`

**Interfaces:**
- `simulate_compression_portfolio(db_path, run_id, candidate_ids=None, intervention_families=None) -> SimulationResult`.
- Unknown candidate IDs are returned under `excluded_candidates`; stale run IDs return a structured stale result.

- [ ] Write failing tests for disjoint, overlapping, mixed-family, unknown-ID, stale-run, and deterministic-order simulations.
- [ ] Implement a versioned intervention catalog mapping each detector family to workflow change, existing tool, custom solution, and verification query.
- [ ] Reuse stored adjusted claims; never sum candidate gross estimates directly.
- [ ] Verify simulator and attribution invariant tests pass.
- [ ] Commit with `feat: simulate compression interventions`.

### Task 12: Simulator MCP Tool And Documentation

**Files:**
- Modify: `src/codex_usage_tracker/compression/api.py`
- Modify: `src/codex_usage_tracker/cli/mcp_compression.py`
- Modify: `src/codex_usage_tracker/cli/mcp_server.py`
- Modify: `tests/cli/test_mcp_compression.py`
- Modify: `docs/mcp.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/compression-lab-roadmap.md`

- [ ] Add failing `usage_compression_simulate` MCP tests with calculation trace and verification plan assertions.
- [ ] Implement the thin tool wrapper and compact simulation payload.
- [ ] Verify unknown/stale candidates return actionable next-tool arguments.
- [ ] Run `just v`, open/merge PR 4, and record its PR/merge SHA on the next branch.

---

## PR 5: Skill, Plugin, Documentation, And Dogfood Rollout

### Task 13: Compact Legacy Routers And Skill Guidance

**Files:**
- Modify: `src/codex_usage_tracker/reports/agentic.py`
- Modify: `src/codex_usage_tracker/reports/action_brief.py`
- Modify: `src/codex_usage_tracker/cli/mcp_investigations.py`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md`
- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`
- Test: `tests/reports/test_agentic_exports.py`
- Test: `tests/reports/test_action_brief.py`
- Test: `tests/cli/test_mcp_integration.py`

**Interfaces:**
- Broad `token_waste` requests return a compact compression-profile pointer and top candidate handles.
- Specialized legacy goals and tools remain compatible.

- [ ] Write failing compatibility tests proving old schemas remain and large nested evidence is removed only from broad token-waste routing.
- [ ] Update routers to reuse the newest valid compression run or return exact start/status arguments.
- [ ] Teach both source and packaged skills the start/status/profile/detail/simulate flow and stopping rules.
- [ ] Verify source and packaged skill copies are byte-identical.
- [ ] Commit with `feat: route usage guidance through compression lab`.

### Task 14: Examples, Shadow Comparison, Full Validation, And Final PR

**Files:**
- Create: `docs/examples/compression-lab-conversation.md`
- Create: `src/codex_usage_tracker/plugin_data/docs/examples/compression-lab-conversation.md`
- Modify: `docs/mcp.md`
- Modify: `README.md`
- Modify: `docs/compression-lab-roadmap.md`
- Modify: `tests/reports/test_agentic_dogfood.py`

- [ ] Add a synthetic conversation showing compact profile, selected detail, simulation, and verification.
- [ ] Extend dogfood checks to compare old and new top families without asserting equality of invalid old token totals.
- [ ] Run a fresh local full-history analysis, record only aggregate timings/counts, then confirm a warm rerun meets cache targets.
- [ ] Mark all roadmap PRs complete and append final measured results and residual limitations.
- [ ] Run `just v` and `just vc` because this final PR changes bundled skills/contracts and validates the full sequence.
- [ ] Run package build/install smoke and `python scripts/check_release.py --dist`.
- [ ] Review for private data, open PR 5, wait for all GitHub gates, squash merge, and confirm `origin/main` contains the merge SHA.

## Final Completion Evidence

- Five merged PR links and merge SHAs recorded in `docs/compression-lab-roadmap.md`.
- All six detectors produce bounded heuristic ranges.
- Synthetic overlap tests prove no duplicate portfolio attribution.
- Full-history cold and warm timings recorded without private evidence.
- MCP tool inventory includes all six Compression Lab tools.
- Source and packaged skills are synchronized.
- Existing MCP integration tests remain green.
- The branch/worktree retains only pre-existing `.idea/` and `.serena/` metadata after completion.
