# Capacity-First Limits Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace usage-percentage history with a weekly credits-per-percentage capacity history, automatically detect zero or multiple defensible capacity changes, and present current limit facts in one compact row.

**Architecture:** Extract one shared aggregate capacity-cycle loader used by analysis and series services. Extend the conservative max-statistic detector into a hierarchical, alpha-spending multi-change detector that emits supported boundaries and regimes while preserving singular v2 compatibility fields. Keep React orchestration in `LimitsPage.tsx`, move compact readouts and change timelines into focused components, and make the existing visualization contract render capacity points, robust rolling summaries, and supported boundaries.

**Tech Stack:** Python 3.10+, SQLite, pytest, React 18, TypeScript, TanStack Query, Vitest/Testing Library, CSS modules, existing dashboard visualization contracts.

## Global Constraints

- The primary history is weekly `credits / 1%`; the rolling five-hour window remains current observed context until a separate decay-aware model is validated.
- Capacity points use completed high/medium-quality cycles with at least `0.95` price coverage, no unresolved conflict, and a positive finite capacity; each cycle contributes one vote.
- Rolling summaries use the trailing eight eligible cycles and appear after four eligible cycles.
- Default y-domain uses Tukey `1.5 × IQR` fences, discloses clipped points, and offers **Show full range**.
- Multi-change detection starts with family-wise alpha `0.05`, requires four cycles per regime, uses `1,999` deterministic Monte Carlo permutations when exact enumeration is unsafe, requires the upper 95% Monte Carlo uncertainty bound to clear the allocated alpha, requires absolute Cliff's delta `>= 0.474`, and splits child alpha equally.
- Across at least 1,000 deterministic no-change simulations, the upper 95% binomial confidence bound for family-wise false-positive rate must not exceed `0.05` before promotion.
- Rejected candidate boundaries and their selected before/after medians never appear in default UI/API/MCP payloads.
- Analysis runs automatically and idempotently per allowance source revision; no user-facing revision button remains.
- Normal payloads remain canonical and aggregate-first. Physical record provenance stays opt-in.
- Preserve existing v2 schema identifiers and deprecated singular analysis fields for one compatibility window.
- Preserve all unrelated and pre-existing uncommitted work in this feature worktree.

---

## File Structure

- Create `src/codex_usage_tracker/allowance_intelligence/capacity_history.py`: shared capacity-cycle SQL loading, robust rolling summaries, bucket aggregation, Tukey-domain metadata, and regime annotation.
- Modify `src/codex_usage_tracker/allowance_intelligence/change_detection.py`: hierarchical multi-change detector plus singular compatibility wrapper.
- Modify `src/codex_usage_tracker/allowance_intelligence/analysis.py`: persist boundaries/regimes and default conservative parameters using the shared cycle loader.
- Modify `src/codex_usage_tracker/allowance_intelligence/service.py`: add bounded capacity history to weekly series and support `all` range.
- Modify `src/codex_usage_tracker/server/allowance_v2.py` and `src/codex_usage_tracker/cli/mcp_allowance.py`: preserve revision-keyed job coalescing and expose canonical multi-change results.
- Modify `frontend/dashboard/src/api/allowanceIntelligenceTypes.ts`: capacity point, boundary, regime, and compatibility types.
- Modify `frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.ts`: capacity-first chart specification.
- Create `frontend/dashboard/src/features/limits/AllowanceCapacityStatusRow.tsx`: compact responsive current status.
- Create `frontend/dashboard/src/features/limits/AllowanceCapacityChangeTimeline.tsx`: supported-regime timeline and no-change/pending/error states.
- Modify `frontend/dashboard/src/features/limits/LimitsPage.tsx`: capacity-first orchestration and automatic revision analysis.
- Modify `frontend/dashboard/src/features/limits/LimitsIntelligence.module.css` and `LimitsPage.module.css`: compact layout and responsive/accessibility states.
- Modify focused Python, API/MCP, and React tests listed in each task.

---

### Task 1: Shared Capacity History Domain

**Files:**
- Create: `src/codex_usage_tracker/allowance_intelligence/capacity_history.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/analysis.py`
- Test: `tests/allowance_intelligence/test_capacity_history.py`
- Test: `tests/allowance_intelligence/test_analysis.py`

**Interfaces:**
- Produces: `load_capacity_cycles(connection, *, source_revision, archive_scope, window_kind, cohort_key, start_at=None, end_at=None) -> list[dict[str, Any]]`
- Produces: `build_capacity_history(cycles, *, granularity, trailing_window=8, regime_boundaries=()) -> dict[str, Any]`
- The history contains `points`, `buckets`, `robust_domain`, `clipped_point_count`, and `eligible_cycle_count`.
- Each point contains `cycle_id`, `completed_at`, `credits_per_percent`, `rolling_median`, `rolling_q1`, `rolling_q3`, `quality_grade`, `price_coverage`, and optional `regime_id`.

- [ ] **Step 1: Write failing capacity-domain tests**

```python
def test_capacity_history_gives_each_completed_cycle_one_vote() -> None:
    cycles = synthetic_capacity_cycles([100, 120, 900, 110], completed=True)
    history = build_capacity_history(cycles, granularity="cycle", trailing_window=8)
    assert [row["credits_per_percent"] for row in history["points"]] == [100, 120, 900, 110]
    assert history["points"][-1]["rolling_median"] == 115
    assert history["eligible_cycle_count"] == 4


def test_capacity_history_discloses_tukey_outliers_without_dropping_them() -> None:
    history = build_capacity_history(
        synthetic_capacity_cycles([90, 95, 100, 105, 1_000], completed=True),
        granularity="cycle",
    )
    assert len(history["points"]) == 5
    assert history["clipped_point_count"] == 1
    assert history["robust_domain"]["mode"] == "tukey_1_5_iqr"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_capacity_history.py -q`

Expected: FAIL because `capacity_history` does not exist.

- [ ] **Step 3: Implement the shared loader and history builder**

```python
def load_capacity_cycles(connection: sqlite3.Connection, *, source_revision: str,
                         archive_scope: str, window_kind: str, cohort_key: str,
                         start_at: str | None = None,
                         end_at: str | None = None) -> list[dict[str, Any]]:
    """Return one aggregate capacity row per allowance cycle."""
    # Query allowance_cycles and grouped eligible allowance_intervals with
    # bound parameters; apply archive/range clauses; attach credits_per_percent.


def build_capacity_history(cycles: list[dict[str, Any]], *, granularity: str,
                           trailing_window: int = 8,
                           regime_boundaries: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    eligible = [_normalized_cycle(row) for row in cycles if _eligible_cycle(row)]
    points = _rolling_points(eligible, trailing_window=trailing_window)
    return {
        "points": points,
        "buckets": _bucket_points(points, granularity),
        "robust_domain": _tukey_domain(points),
        "clipped_point_count": _clipped_count(points),
        "eligible_cycle_count": len(points),
    }
```

- [ ] **Step 4: Replace `analysis._analysis_cycles` with `load_capacity_cycles`**

Use the shared loader with the same source revision, archive scope, weekly window, and cohort. Remove the duplicated SQL helper only after analysis tests prove identical eligible-cycle behavior.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_capacity_history.py tests/allowance_intelligence/test_analysis.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -- src/codex_usage_tracker/allowance_intelligence/capacity_history.py src/codex_usage_tracker/allowance_intelligence/analysis.py tests/allowance_intelligence/test_capacity_history.py tests/allowance_intelligence/test_analysis.py
git commit -m "refactor: share allowance capacity history"
```

### Task 2: Conservative Multiple-Change Detection

**Files:**
- Modify: `src/codex_usage_tracker/allowance_intelligence/change_detection.py`
- Test: `tests/allowance_intelligence/test_change_detection.py`
- Create: `scripts/calibrate_allowance_change_detector.py`
- Create: `tests/allowance_intelligence/test_change_calibration.py`

**Interfaces:**
- Produces: `detect_cycle_changes(cycles, *, semantic_key, min_cycles_per_regime=4, permutation_count=1999, familywise_alpha=0.05) -> dict[str, Any]`
- Preserves: `detect_cycle_change(...)` as a compatibility wrapper returning deprecated singular fields only when exactly one boundary is supported.
- Result fields: `status`, `boundaries`, `regimes`, `eligible_cycle_count`, `familywise_alpha`, `detector_version`, `selection_correction`, `caveats`, plus deprecated singular fields.

- [ ] **Step 1: Write failing zero/one/multiple change tests**

```python
def test_detector_returns_multiple_supported_capacity_regimes() -> None:
    cycles = capacity_cycles([300] * 8 + [100] * 8 + [220] * 8)
    result = detect_cycle_changes(cycles, semantic_key="three-regimes", permutation_count=499)
    assert result["status"] == "supported_changes"
    assert len(result["boundaries"]) == 2
    assert [round(regime["median_credits_per_percent"]) for regime in result["regimes"]] == [300, 100, 220]
    assert result["selected_boundary"] is None


def test_detector_suppresses_rejected_best_split_effect() -> None:
    result = detect_cycle_changes(capacity_cycles([95, 110, 90, 105] * 4), semantic_key="null", permutation_count=499)
    assert result["boundaries"] == []
    assert len(result["regimes"]) == 1
    assert result["effect_size"] is None
    assert result["adjusted_p_value"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_change_detection.py -q`

Expected: FAIL because `detect_cycle_changes` and multi-regime fields do not exist.

- [ ] **Step 3: Implement hierarchical alpha-spending recursion**

```python
def detect_cycle_changes(cycles: list[dict[str, Any]], *, semantic_key: str,
                         min_cycles_per_regime: int = 4,
                         permutation_count: int = 1_999,
                         familywise_alpha: float = 0.05) -> dict[str, Any]:
    eligible, caveats = _eligible_cycles(_ordered(cycles))
    boundaries = _detect_segment(
        eligible, start=0, end=len(eligible), alpha=familywise_alpha,
        semantic_key=semantic_key, minimum=min_cycles_per_regime,
        permutation_count=permutation_count,
    )
    boundaries.sort(key=lambda row: row["split_index"])
    regimes = _regimes(eligible, boundaries)
    return _multi_result(eligible, boundaries, regimes, caveats, familywise_alpha)


def _detect_segment(..., alpha: float, ...) -> list[dict[str, Any]]:
    selected = _selection_adjusted_test(...)
    if not selected["p_value"] < alpha or abs(selected["cliffs_delta"]) < 0.474:
        return []
    child_alpha = alpha / 2
    return [*_detect_segment(left, alpha=child_alpha, ...),
            _accepted_boundary(selected, alpha),
            *_detect_segment(right, alpha=child_alpha, ...)]
```

Use a segment-specific deterministic seed derived from `semantic_key`, segment endpoints, and alpha. Do not recurse after a rejected parent.

- [ ] **Step 4: Add deterministic calibration harness and fast regression test**

`scripts/calibrate_allowance_change_detector.py` accepts `--simulations`, `--seed`, `--permutations`, and `--json`. It generates no-change histories with Gaussian, skewed, outlier-contaminated, and heteroskedastic families, runs the production detector, and reports false-positive count/rate plus a Wilson 95% upper bound. `tests/allowance_intelligence/test_change_calibration.py` runs a small deterministic smoke set; the 1,000-history acceptance run remains a named local/statistical gate so ordinary CI is not lengthened by minutes.

- [ ] **Step 5: Run focused tests and the 1,000-history gate**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_change_detection.py tests/allowance_intelligence/test_change_calibration.py -q`

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/calibrate_allowance_change_detector.py --simulations 1000 --seed 20260715 --permutations 1999 --json`

Expected: tests PASS; JSON reports `wilson_upper_95 <= 0.05`.

- [ ] **Step 6: Commit**

```bash
git add -- src/codex_usage_tracker/allowance_intelligence/change_detection.py tests/allowance_intelligence/test_change_detection.py tests/allowance_intelligence/test_change_calibration.py scripts/calibrate_allowance_change_detector.py
git commit -m "feat: detect multiple allowance capacity changes"
```

### Task 3: Persist Regimes And Preserve V2 Compatibility

**Files:**
- Modify: `src/codex_usage_tracker/allowance_intelligence/analysis.py`
- Modify: `src/codex_usage_tracker/allowance_intelligence/contracts.py`
- Test: `tests/allowance_intelligence/test_analysis.py`
- Test: `tests/server/test_server_allowance_v2.py`
- Test: `tests/cli/test_allowance_intelligence_cli_mcp.py`

**Interfaces:**
- Analysis defaults change to `min_cycles_per_regime=4`, `permutation_count=1999`, and `familywise_alpha=0.05`.
- The persisted payload exposes `boundaries[]` and `regimes[]` identically through Python service, HTTP, CLI/MCP, and cached reads.
- `selected_boundary`, `adjusted_p_value`, `effect_size`, and `confidence_interval` remain non-null only for exactly one supported boundary and carry a `compatibility_status: "deprecated_single_boundary"` marker.

- [ ] **Step 1: Write failing persisted-contract tests**

```python
def test_analysis_persists_multiple_boundaries_and_regimes(connection) -> None:
    seed_three_capacity_regimes(connection)
    result = build_allowance_analysis(connection, parameters={"min_cycles_per_regime": 4, "permutation_count": 499})
    assert len(result["boundaries"]) == 2
    assert len(result["regimes"]) == 3
    assert read_allowance_analysis(connection)["boundaries"] == result["boundaries"]
    assert result["selected_boundary"] is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_analysis.py tests/server/test_server_allowance_v2.py tests/cli/test_allowance_intelligence_cli_mcp.py -q`

Expected: FAIL on unknown parameter or missing multi-change fields.

- [ ] **Step 3: Update analysis request, snapshot identity, and payload builders**

Include the multi-change detector version and all three parameters in the semantic snapshot key. Continue using the existing `allowance_analysis_snapshots` table and revision-keyed job request key; no schema migration is required.

- [ ] **Step 4: Update HTTP and MCP compatibility assertions**

Assert API/MCP parity for `boundaries`, `regimes`, `familywise_alpha`, canonical copied-row diagnostics, and deprecated singular fields. Ensure default MCP output never returns rejected candidate medians.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the same pytest command from Step 2.

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -- src/codex_usage_tracker/allowance_intelligence/analysis.py src/codex_usage_tracker/allowance_intelligence/contracts.py tests/allowance_intelligence/test_analysis.py tests/server/test_server_allowance_v2.py tests/cli/test_allowance_intelligence_cli_mcp.py
git commit -m "feat: expose allowance capacity regimes"
```

### Task 4: Add Weekly Capacity History To Series

**Files:**
- Modify: `src/codex_usage_tracker/allowance_intelligence/service.py`
- Modify: `src/codex_usage_tracker/server/allowance_v2.py`
- Modify: `src/codex_usage_tracker/cli/mcp_allowance.py`
- Test: `tests/allowance_intelligence/test_service.py`
- Test: `tests/server/test_server_allowance_v2.py`
- Test: `tests/cli/test_allowance_intelligence_cli_mcp.py`

**Interfaces:**
- `build_allowance_series(..., range_preset="8w", granularity="cycle")` adds `capacity_history` for weekly requests.
- `range_preset="all"` resolves to the earliest eligible weekly cycle without creating an unbounded persistent dashboard query; the endpoint still returns bounded aggregate cycle rows.
- Five-hour series returns `capacity_history.status = "unsupported_window_model"` and no inferred capacity points.

- [ ] **Step 1: Write failing service tests**

```python
def test_weekly_series_returns_capacity_history_and_supported_boundaries(connection) -> None:
    seed_capacity_cycles(connection)
    payload = build_allowance_series(connection, now=NOW, range_preset="8w", granularity="cycle")
    assert payload["capacity_history"]["unit"] == "credits_per_percent"
    assert payload["capacity_history"]["points"] == sorted(
        payload["capacity_history"]["points"], key=lambda row: row["completed_at"]
    )
    assert payload["capacity_history"]["clipped_point_count"] >= 0


def test_five_hour_series_refuses_weekly_capacity_math(connection) -> None:
    payload = build_allowance_series(connection, now=NOW, window_kind="five_hour")
    assert payload["capacity_history"] == {"status": "unsupported_window_model", "points": []}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_service.py -q`

Expected: FAIL because `capacity_history` and `all` are absent.

- [ ] **Step 3: Implement bounded weekly history and all-range resolution**

Load capacity cycles through `load_capacity_cycles`, read the current persisted analysis without starting heavy work, annotate points only when its source revision matches, and call `build_capacity_history`. Keep the existing observed `points` and `cycles` fields for compatibility.

- [ ] **Step 4: Update HTTP/MCP option parsing and tests**

Accept `range=all`; keep the existing finite dashboard `limit=5000` server rule untouched. Verify canonical/archive scope and copied-row counts propagate.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest tests/allowance_intelligence/test_service.py tests/server/test_server_allowance_v2.py tests/cli/test_allowance_intelligence_cli_mcp.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -- src/codex_usage_tracker/allowance_intelligence/service.py src/codex_usage_tracker/server/allowance_v2.py src/codex_usage_tracker/cli/mcp_allowance.py tests/allowance_intelligence/test_service.py tests/server/test_server_allowance_v2.py tests/cli/test_allowance_intelligence_cli_mcp.py
git commit -m "feat: serve weekly allowance capacity history"
```

### Task 5: Capacity-First Frontend Contract And Chart

**Files:**
- Modify: `frontend/dashboard/src/api/allowanceIntelligenceTypes.ts`
- Modify: `frontend/dashboard/src/api/allowanceIntelligence.test.ts`
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.ts`
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.test.ts`

**Interfaces:**
- Adds `AllowanceCapacityPoint`, `AllowanceCapacityHistory`, `AllowanceCapacityBoundary`, and `AllowanceCapacityRegime` TypeScript types.
- `buildAllowanceIntelligenceVisualization(series, status, "weekly", { showFullRange })` renders cycle points, rolling median, quartile band, and supported-boundary annotations in credits per percentage point.

- [ ] **Step 1: Write failing visualization tests**

```typescript
it('renders weekly capacity instead of usage percentage history', () => {
  const spec = buildAllowanceIntelligenceVisualization(seriesWithCapacity(), statusPayload(), 'weekly', { showFullRange: false });
  expect(spec.title).toBe('Weekly limit capacity over time');
  expect(spec.axes.y.unit).toBe('credits / 1%');
  expect(spec.series.map(row => row.id)).toEqual(['cycle-capacity', 'rolling-median', 'interquartile-band']);
  expect(spec.annotations).toHaveLength(2);
});

it('discloses robust-domain clipping and supports full range', () => {
  const robust = buildAllowanceIntelligenceVisualization(seriesWithOutlier(), statusPayload(), 'weekly', { showFullRange: false });
  const full = buildAllowanceIntelligenceVisualization(seriesWithOutlier(), statusPayload(), 'weekly', { showFullRange: true });
  expect(robust.caveats.join(' ')).toContain('1 point outside the robust range');
  expect(full.axes.y.max).toBeUndefined();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend/dashboard && npm test -- --run src/features/limits/allowanceIntelligenceVisualization.test.ts`

Expected: FAIL on usage-percent title/unit/series.

- [ ] **Step 3: Extend API types and implement capacity visualization**

Map `capacity_history.points` into visualization records with `completedAt`, `creditsPerPercent`, `rollingMedian`, `rollingQ1`, `rollingQ3`, `regimeId`, and clipped-edge metadata. Use boundary timestamps for annotations and duplicate the exact values in the visualization table contract.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `cd frontend/dashboard && npm test -- --run src/api/allowanceIntelligence.test.ts src/features/limits/allowanceIntelligenceVisualization.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -- frontend/dashboard/src/api/allowanceIntelligenceTypes.ts frontend/dashboard/src/api/allowanceIntelligence.test.ts frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.ts frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.test.ts
git commit -m "feat: chart allowance capacity over time"
```

### Task 6: Compact Limits Workspace And Automatic Analysis

**Files:**
- Create: `frontend/dashboard/src/features/limits/AllowanceCapacityStatusRow.tsx`
- Create: `frontend/dashboard/src/features/limits/AllowanceCapacityChangeTimeline.tsx`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.tsx`
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceModel.ts`
- Modify: `frontend/dashboard/src/features/limits/LimitsIntelligence.module.css`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.module.css`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.test.tsx`
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceModel.test.ts`

**Interfaces:**
- `AllowanceCapacityStatusRow` receives status plus capacity readout and renders four labeled cells.
- `AllowanceCapacityChangeTimeline` receives analysis state/result and optional `onSelectBoundary`.
- `LiveLimitsPage` automatically starts one analysis job only when the current revision has no compatible persisted analysis and does not expose a run button.

- [ ] **Step 1: Write failing page tests for the user-visible contract**

```typescript
it('shows compact current facts and a capacity-first history', async () => {
  renderLimitsPage();
  expect(await screen.findByRole('heading', { name: 'Weekly limit capacity over time' })).toBeVisible();
  expect(screen.getByRole('list', { name: 'Current limit status' }).children).toHaveLength(4);
  expect(screen.queryByText('Usage percentage over time')).not.toBeInTheDocument();
  expect(screen.queryByText('Personal model')).not.toBeInTheDocument();
});

it('automatically starts analysis and never exposes revision language', async () => {
  renderLimitsPage({ analysis: { status: 'missing' } });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/allowance/analysis/jobs'), expect.objectContaining({ method: 'POST' })));
  expect(screen.queryByRole('button', { name: /revision|run analysis/i })).not.toBeInTheDocument();
});

it('suppresses rejected candidate medians and lists every supported change latest first', async () => {
  renderLimitsPage({ analysis: analysisWithTwoChanges() });
  const items = await screen.findAllByRole('listitem', { name: /capacity changed/i });
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent('Jul');
  expect(screen.queryByText('Adjusted p-value')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend/dashboard && npm test -- --run src/features/limits/LimitsPage.test.tsx src/features/limits/allowanceIntelligenceModel.test.ts`

Expected: FAIL because oversized cards, usage chart, and manual button remain.

- [ ] **Step 3: Implement the compact status row**

Render weekly observed, five-hour observed, weekly reset, and current calibration in a semantic `<dl>`/list structure with visible freshness/grade labels. Remove the large reconstructed-use answer band and `metricGrid` from the live v2 workspace; preserve static legacy rendering only for file-mode compatibility.

- [ ] **Step 4: Replace foregrounded forecast panels with capacity summary and change timeline**

The no-change state renders “No reliable capacity change detected,” eligible cycles, and generated time only. Supported changes render latest-first plain-language rows and expandable technical details. Do not render rejected split medians.

- [ ] **Step 5: Make analysis automatic and revision-keyed**

Add an effect guarded by `allowanceRevision`, `analysisQuery.data?.status === "missing"`, and absence of an active job. Start/reuse the existing idempotent job, poll it, refetch analysis on completion, and keep the chart usable during pending/failure states.

- [ ] **Step 6: Add robust/full-range and time controls**

Default to eight weeks and cycle granularity. Offer eight weeks, six months, all history, and custom dates; cycle/week/month granularity; and a checkbox/button labeled **Show full range** when clipped points exist. Five-hour remains in the status row and cannot switch the capacity chart into invalid weekly math.

- [ ] **Step 7: Implement responsive and accessibility behavior**

Use four columns at wide width, two below the existing tablet breakpoint, and one at narrow/mobile width. Preserve focus outlines, status text, exact chart-table values, non-color change direction, and a live region for background analysis completion.

- [ ] **Step 8: Run focused tests and verify GREEN**

Run: `cd frontend/dashboard && npm test -- --run src/features/limits/LimitsPage.test.tsx src/features/limits/allowanceIntelligenceModel.test.ts src/features/limits/allowanceIntelligenceVisualization.test.ts`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -- frontend/dashboard/src/features/limits/AllowanceCapacityStatusRow.tsx frontend/dashboard/src/features/limits/AllowanceCapacityChangeTimeline.tsx frontend/dashboard/src/features/limits/LimitsPage.tsx frontend/dashboard/src/features/limits/allowanceIntelligenceModel.ts frontend/dashboard/src/features/limits/LimitsIntelligence.module.css frontend/dashboard/src/features/limits/LimitsPage.module.css frontend/dashboard/src/features/limits/LimitsPage.test.tsx frontend/dashboard/src/features/limits/allowanceIntelligenceModel.test.ts
git commit -m "feat: make limits capacity first"
```

### Task 7: Contracts, Documentation, Generated Assets, And Statistical Gate

**Files:**
- Modify: `docs/allowance-intelligence.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/mcp.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `docs/usage-drain-modeling.md`
- Modify: `docs/architecture.md`
- Modify: `CHANGELOG.md`
- Modify: `.codex/tasks.toml`
- Create: `.github/workflows/allowance-statistical-calibration.yml`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.css`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.js`

**Interfaces:**
- Adds named `allowance-statistical-calibration` task running the 1,000-history gate.
- Documents capacity-first defaults, weekly-only inference, multiple supported regimes, automatic analysis, and deprecated singular fields.

- [ ] **Step 1: Add the named statistical gate and CI split**

Create `allowance-statistical-calibration.yml` with `workflow_dispatch` and a weekly schedule. Its one job installs the existing dev dependencies and runs `/Users`-independent `python scripts/calibrate_allowance_change_detector.py --simulations 1000 --seed 20260715 --permutations 1999 --json`. It fails when `wilson_upper_95 > 0.05` and uploads only the aggregate JSON result. It is intentionally not a dependency of ordinary pull-request CI.

- [ ] **Step 2: Update user and contract documentation**

Replace usage-percentage-history descriptions with weekly credits-per-percentage capacity history. Include zero/one/multiple boundary examples, no-change suppression, five-hour limitations, aggregate provenance, and MCP polling semantics.

- [ ] **Step 3: Rebuild packaged React assets**

Run: `cd frontend/dashboard && npm run dashboard:build`

Expected: Vite build succeeds and generated `UsageDrainPage.css/js` change only through the build.

- [ ] **Step 4: Run named dashboard/statistical gates**

Run:

```bash
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
/Users/Monsky/.codex/bin/codex-task dashboard-governance --json
/Users/Monsky/.codex/bin/codex-task dashboard-source-budget --json
/Users/Monsky/.codex/bin/codex-task dashboard-route-budget --json
/Users/Monsky/.codex/bin/codex-task allowance-statistical-calibration --json
```

Expected: every compact packet reports PASS.

- [ ] **Step 5: Commit**

```bash
git add -- docs/allowance-intelligence.md docs/dashboard-guide.md docs/mcp.md docs/cli-json-schemas.md docs/usage-drain-modeling.md docs/architecture.md CHANGELOG.md .codex/tasks.toml .github/workflows/allowance-statistical-calibration.yml src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.css src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.js
git commit -m "docs: document capacity-first limits intelligence"
```

### Task 8: Final Verification, Live Audit, And Dashboard Handoff

**Files:**
- Modify only files required by failures proven during verification.
- Review all branch changes and existing uncommitted work before final commits.

**Interfaces:**
- Produces a verified branch, a running bounded local dashboard, and aggregate-only audit evidence.

- [ ] **Step 1: Run Python and repository gates**

```bash
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m ruff check .
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m mypy
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m compileall src
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done
PYTHONPATH=src /Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/check_release.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 2: Run full frontend verification**

Run: `cd frontend/dashboard && npm test -- --run && npm run lint && npm run build`

Expected: tests, lint, typecheck/build all pass.

- [ ] **Step 3: Run aggregate-only live audit**

Against the user-owned local database, print only counts, medians, coverage, supported-boundary count, regime count, copied-row exclusion, endpoint latency, payload size, and physical-ID presence booleans. Do not print cycle IDs, record IDs, source files, timestamps tied to individual records, prompts, or transcript content.

- [ ] **Step 4: Inspect with Serena and review the complete diff**

Run JetBrains inspections on changed Python/TypeScript/TSX files. Review `git status --short --branch`, `git diff --stat`, `git diff`, staged paths, generated assets, and tracked-secret patterns. Confirm no raw local data or unrelated user changes entered commits.

- [ ] **Step 5: Launch and probe the bounded dashboard**

Launch with the repository default finite `--limit 5000`, retain the server session, and run:

```bash
/Users/Monsky/.codex/bin/codex-probe-local-url http://127.0.0.1:8766/react-dashboard.html --contains 'Codex Usage Tracker' --show 200
```

Expected: HTTP success and matching content. Open `http://127.0.0.1:8766/react-dashboard.html?view=usage-drain` for user testing.

- [ ] **Step 6: Commit any proven verification fixes separately**

Stage only exact files changed for a proven failure and use a focused Conventional Commit message. Do not amend or squash existing commits.
