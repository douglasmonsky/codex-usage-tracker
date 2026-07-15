# Capacity Chart Series Encoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make subscription tier and statistical role immediately distinguishable in the Limits capacity chart.

**Architecture:** Keep tier colors in the Limits presentation layer, add explicit observed/median mark styling to the Cartesian spec, and suppress only this chart's generated ECharts legend. Render a purpose-built two-part legend immediately above the chart so tier and mark meanings are explained independently.

**Tech Stack:** React 19, TypeScript, CSS Modules, ECharts, Vitest, Testing Library, Vite.

## Global Constraints

- Color encodes subscription tier; line shade, marker presence, and line weight encode statistical role.
- Observed capacity uses a lighter tier shade, a thin line, and hollow circular markers.
- Trailing median uses a darker tier shade, a thick solid line, and no markers.
- The replacement legend contains separate accessible plan and chart-mark keys.
- Other dashboard charts retain their existing legend behavior.
- Subscription provenance, capacity calculations, and change detection remain unchanged.
- Packaged dashboard assets are rebuilt from `frontend/dashboard` and never edited directly.
- No subagents are used; execute this plan inline.

---

### Task 1: Encode observed and median series distinctly

**Files:**
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.test.ts`
- Modify: `frontend/dashboard/src/visualization/renderer/optionBuilder.test.ts`
- Modify: `frontend/dashboard/src/features/limits/allowancePlanPresentation.ts`
- Modify: `frontend/dashboard/src/features/limits/allowanceIntelligenceVisualization.ts`
- Modify: `frontend/dashboard/src/visualization/spec/types.ts`
- Modify: `frontend/dashboard/src/visualization/renderer/cartesianModel.ts`

**Interfaces:**
- Produces: `allowancePlanMedianColor(value: string): string`.
- Produces: `CartesianSeriesSpec.pointStyle?: 'filled' | 'hollow' | 'none'`.
- Produces: `CartesianVisualizationSpecV1.showLegend?: boolean`.
- Preserves: `allowancePlanColor(value)` as the observed/key tier color.

- [ ] **Step 1: Write failing chart-spec assertions**

Update the weekly-capacity test to require the new encoding:

```ts
expect(spec.showLegend).toBe(false);
expect(spec.series[0]).toMatchObject({
  color: '#3b82f6',
  lineWidth: 1.5,
  pointStyle: 'hollow',
  showPoints: true,
});
expect(spec.series[1]).toMatchObject({
  color: '#1d4ed8',
  lineWidth: 3,
  pointStyle: 'none',
  showPoints: false,
});
expect(spec.series[0].color).not.toBe(spec.series[1].color);
expect(spec.series[2].color).not.toBe(spec.series[3].color);
```

Assert the rendered observed series uses `symbol: 'emptyCircle'`, the median uses
`symbol: 'none'`, and this chart has no ECharts `legend` option.

- [ ] **Step 2: Write a failing renderer-scope assertion**

In `optionBuilder.test.ts`, prove legend suppression is opt-in:

```ts
const defaultOption = buildEChartsVisualizationModel(allowanceChangePointSpec).option as Record<string, unknown>;
const hiddenOption = buildEChartsVisualizationModel({
  ...allowanceChangePointSpec,
  showLegend: false,
}).option as Record<string, unknown>;

expect(defaultOption.legend).toBeTruthy();
expect(hiddenOption.legend).toBeUndefined();
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
cd frontend/dashboard
npm test -- --run src/features/limits/allowanceIntelligenceVisualization.test.ts src/visualization/renderer/optionBuilder.test.ts
```

Expected: FAIL because `showLegend`, `pointStyle`, median shades, and renderer symbol handling do not exist.

- [ ] **Step 4: Add stable tier-role colors**

Change the tier presentation module to retain observed/key colors and add darker
median colors:

```ts
const PLAN_MEDIAN_COLORS: Record<string, string> = {
  pro: '#1d4ed8',
  prolite: '#9a4d00',
  plus: '#0f5f4c',
  team: '#513879',
  business: '#086467',
  enterprise: '#8c2f68',
  mixed: '#623e2f',
  unknown: '#454b55',
};

export function allowancePlanMedianColor(value: string): string {
  const planType = normalizeAllowancePlanType(value);
  return PLAN_MEDIAN_COLORS[planType] ?? darkenHex(allowancePlanColor(planType), 0.28);
}
```

Set Pro's observed/key color to `#3b82f6` and Pro Lite's to `#d97706`. Implement
`darkenHex` as a private deterministic RGB-channel transform for fallback tiers.

- [ ] **Step 5: Extend the Cartesian contract and renderer minimally**

Add `pointStyle` and `showLegend` to the types. In the renderer:

```ts
const pointStyle = seriesSpec.pointStyle ?? 'filled';
// series option
symbol: pointStyle === 'none' ? 'none' : pointStyle === 'hollow' ? 'emptyCircle' : undefined,
showSymbol: pointStyle === 'none'
  ? false
  : seriesSpec.showPoints ?? (seriesSpec.mark !== 'line' || spec.data.rows.length <= 24),
```

Build the legend only when `spec.showLegend !== false`:

```ts
const legend = spec.showLegend !== false && spec.series.length > 1
  ? { top: 4, left: 8 }
  : null;
```

- [ ] **Step 6: Apply the encoding to the capacity spec**

Set `showLegend: false`. Use `allowancePlanColor(planType)` plus
`pointStyle: 'hollow'` for capacity and `allowancePlanMedianColor(planType)` plus
`pointStyle: 'none'` for the median. Use the median shade for the one-plan IQR
band so the band remains associated with the median statistic.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run the same focused Vitest command. Expected: 2 test files pass.

- [ ] **Step 8: Commit Task 1**

Stage only the six Task 1 files and commit:

```bash
git commit -m "fix: distinguish capacity observations from medians"
```

---

### Task 2: Replace the repeated series legend with two explanatory keys

**Files:**
- Create: `frontend/dashboard/src/features/limits/AllowanceCapacityLegend.tsx`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.tsx`
- Modify: `frontend/dashboard/src/features/limits/AllowanceCapacityMethodology.tsx`
- Modify: `frontend/dashboard/src/features/limits/LimitsIntelligence.module.css`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.test.tsx`
- Modify: `docs/dashboard-guide.md`

**Interfaces:**
- Produces: `AllowanceCapacityLegend({ series }: { series: AllowanceSeriesPayload })`.
- Consumes: `allowancePlanColor`, `allowancePlanLabel`, and `normalizeAllowancePlanType`.

- [ ] **Step 1: Write the failing Limits-page assertions**

Replace the old `Subscription plan color key` assertion with:

```ts
expect(screen.getByRole('group', { name: 'Capacity chart legend' })).toBeVisible();
expect(screen.getByRole('list', { name: 'Subscription plan key' })).toHaveTextContent('Pro');
expect(screen.getByRole('list', { name: 'Chart mark key' })).toHaveTextContent('Observed reset window');
expect(screen.getByRole('list', { name: 'Chart mark key' })).toHaveTextContent('Trailing 8-window median');
```

- [ ] **Step 2: Run the Limits test and verify RED**

Run:

```bash
cd frontend/dashboard
npm test -- --run src/features/limits/LimitsPage.test.tsx
```

Expected: FAIL because the grouped legend and chart-mark key are absent.

- [ ] **Step 3: Create the focused legend component**

Render one group immediately before `Visualization`:

```tsx
<div className={styles.capacityLegend} role="group" aria-label="Capacity chart legend">
  <ul className={styles.legendKey} aria-label="Subscription plan key">...</ul>
  <ul className={styles.legendKey} aria-label="Chart mark key">
    <li><span className={styles.observedMark} aria-hidden="true" />Observed reset window</li>
    <li><span className={styles.medianMark} aria-hidden="true" />Trailing 8-window median</li>
  </ul>
</div>
```

Normalize and de-duplicate plan types from `series.capacity_history.points` in
first-appearance order. Render each plan once with the existing stable plan hue.

- [ ] **Step 4: Integrate and remove the duplicate methodology key**

Render `<AllowanceCapacityLegend series={seriesQuery.data} />` directly before the
chart when series data exists. Remove the old plan-key list and now-unused plan
presentation imports from `AllowanceCapacityMethodology`.

- [ ] **Step 5: Add responsive, non-color mark samples**

Reuse the existing surface tokens. Make the key container flex-wrap and the two
lists wrap independently. Draw observed and median samples with CSS pseudo-elements:

- observed: 24px thin line with a hollow centered circle;
- median: 24px thick solid line without a circle.

At narrow widths, stack the two keys while preserving full labels.

- [ ] **Step 6: Update the dashboard guide**

Document that the chart uses a two-part legend: tier hue and statistical mark.
State explicitly that observed capacity has hollow dots and the median has no dots.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run:

```bash
cd frontend/dashboard
npm test -- --run src/features/limits/LimitsPage.test.tsx src/features/limits/allowanceIntelligenceVisualization.test.ts src/visualization/renderer/optionBuilder.test.ts
```

Expected: 3 test files pass.

- [ ] **Step 8: Commit Task 2**

Stage only the six Task 2 files and commit:

```bash
git commit -m "fix: clarify capacity chart legend"
```

---

### Task 3: Rebuild and verify the live dashboard

**Files:**
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.js`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/UsageDrainPage.css`
- Regenerate: any other deterministic Vite chunks changed by the build.

**Interfaces:**
- Consumes: the completed frontend source from Tasks 1 and 2.
- Produces: packaged dashboard assets matching that source.

- [ ] **Step 1: Run the complete frontend validation**

```bash
cd frontend/dashboard
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all 95 frontend test files pass; typecheck, lint, and build exit 0.

- [ ] **Step 2: Run repository release checks**

From the repository root with the established virtualenv on `PATH`:

```bash
python scripts/check_release.py
git diff --check
```

Expected: release-readiness passes and diff check is empty.

- [ ] **Step 3: Restart the bounded local dashboard**

Stop the task-owned server on port 8770, then run:

```bash
PYTHONPATH=src python -m codex_usage_tracker.cli serve-dashboard --context-api explicit --limit 5000 --port 8770
```

Expected: the server announces the React dashboard URL after the bounded refresh.

- [ ] **Step 4: Inspect a local screenshot**

Capture `http://127.0.0.1:8770/react-dashboard.html?view=usage-drain` at 1440px wide.
Verify:

- the repeated four-item ECharts legend is absent;
- plan and mark keys appear immediately above the chart;
- Pro and Pro Lite retain distinct hues;
- observed series use hollow dots and thin lighter lines;
- median series use dark thick lines without dots;
- keys wrap cleanly and the plan-transition annotation does not overlap them.

- [ ] **Step 5: Final review**

Review `git status --short --branch`, `git diff --stat`, the actual source diff,
and generated-asset diff. Confirm no local databases, screenshots, raw usage data,
or secrets are staged.
