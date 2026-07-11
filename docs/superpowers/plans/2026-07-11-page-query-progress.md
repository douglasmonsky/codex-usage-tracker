# Page Query Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add accurate, page-local progress indicators for full-scope dashboard endpoint loading and refreshes.

**Architecture:** Add one reusable presentation component that receives real query-module counts and errors from each page. Query ownership remains local; no global registry and no elapsed-time percentages are introduced.

**Tech Stack:** React 19, TypeScript, TanStack Query, Vitest, Testing Library, CSS modules and dashboard tokens.

## Global Constraints

- Render directly below each page header.
- Use completed query modules for determinate progress and indeterminate animation only for one indivisible request.
- Never estimate progress from elapsed time.
- Keep cached data visible during refresh and label it as updating.
- Show initial endpoint errors instead of implying fallback rows are full-scope evidence.
- Do not show live-endpoint progress in static file mode.
- Respect `prefers-reduced-motion`.

---

### Task 1: Shared Page Progress Primitive

**Files:**
- Create: `frontend/dashboard/src/design/PageLoadProgress.tsx`
- Create: `frontend/dashboard/src/design/PageLoadProgress.module.css`
- Create: `frontend/dashboard/src/design/PageLoadProgress.test.tsx`
- Modify: `frontend/dashboard/src/design/index.ts`

**Interfaces:**
- Produces `PageLoadProgress({ active, completed?, total?, label, error?, updating? })`.
- Returns `null` when inactive and error-free.

- [ ] **Step 1: Write failing tests**

```tsx
render(<PageLoadProgress active completed={1} total={2} label="Loading allowance evidence" />);
expect(screen.getByRole('progressbar', { name: 'Loading allowance evidence' })).toHaveAttribute('aria-valuenow', '1');
expect(screen.getByText('1 of 2 modules ready')).toBeInTheDocument();

render(<PageLoadProgress active label="Loading report pack" />);
expect(screen.getByRole('progressbar', { name: 'Loading report pack' })).not.toHaveAttribute('aria-valuenow');

render(<PageLoadProgress active={false} label="Loading" error="Report endpoint failed" />);
expect(screen.getByRole('alert')).toHaveTextContent('Report endpoint failed');
```

- [ ] **Step 2: Confirm the tests fail**

Run: `npm --workspace frontend/dashboard test -- src/design/PageLoadProgress.test.tsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the component**

```tsx
export type PageLoadProgressProps = {
  active: boolean;
  completed?: number;
  total?: number;
  label: string;
  error?: string | null;
  updating?: boolean;
};

export function PageLoadProgress(props: PageLoadProgressProps) {
  if (!props.active && !props.error) return null;
  if (props.error) return <div className={styles.error} role="alert">{props.error}</div>;
  const determinate = typeof props.total === 'number' && props.total > 0;
  const completed = determinate ? Math.min(Math.max(props.completed ?? 0, 0), props.total!) : 0;
  return (
    <section className={styles.root} aria-live="polite">
      <div className={styles.copy}>
        <strong>{props.updating ? 'Updating page evidence' : props.label}</strong>
        {determinate ? <span>{completed} of {props.total} modules ready</span> : null}
      </div>
      <div role="progressbar" aria-label={props.label} aria-valuenow={determinate ? completed : undefined} className={styles.track}>
        <span className={determinate ? styles.fill : styles.indeterminate} />
      </div>
    </section>
  );
}
```

Use existing spacing and color tokens. The determinate fill uses `completed / total`; the indeterminate fill animates across the fixed-height track. Under reduced motion, show a static 35% fill.

- [ ] **Step 4: Verify and commit**

Run: `npm --workspace frontend/dashboard test -- src/design/PageLoadProgress.test.tsx && npm --workspace frontend/dashboard run typecheck`

Expected: PASS.

Commit: `feat: add page query progress primitive`

### Task 2: Multi-Query Pages

**Files:**
- Modify: `frontend/dashboard/src/features/overview/OverviewPage.tsx`
- Modify: `frontend/dashboard/src/features/limits/LimitsPage.tsx`
- Modify: `frontend/dashboard/src/features/cache-context/cacheContextEvidence.ts`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Test: nearest existing tests for each page.

**Interfaces:**
- Consumes `PageLoadProgress` from Task 1.
- Extends `CacheContextEvidence` with `progress: { active: boolean; completed: number; total: number; error: string | null; updating: boolean }`.
- Investigator total equals the agentic report plus all diagnostic snapshot definitions.

- [ ] **Step 1: Add failing page assertions**

For Limits, hold both fetch promises and assert `0 of 2 modules ready`; resolve History and assert `1 of 2`; resolve Diagnostics and assert disappearance. For Cache, assert three modules and transition from fallback to full-scope evidence. For Overview, Threads, and Investigator, assert progress from their existing query states.

- [ ] **Step 2: Confirm focused failures**

```bash
npm --workspace frontend/dashboard test -- \
  src/features/limits/LimitsPage.test.tsx \
  src/features/cache-context/CacheContextPage.test.tsx \
  src/App.overview.test.tsx \
  src/App.threads.test.tsx \
  src/App.investigator.test.tsx
```

Expected: FAIL because page progress is absent.

- [ ] **Step 3: Integrate actual query state**

```tsx
const completed = Number(Boolean(historyQuery.data)) + Number(Boolean(diagnosticsQuery.data));
<PageLoadProgress
  active={canUseLive && loading}
  completed={completed}
  total={2}
  label="Loading allowance history and detector"
  error={error && !completed ? errorMessage(error) : null}
  updating={completed > 0}
/>
```

Place each component immediately after its page header. Cache exposes its query states through the evidence hook rather than duplicating queries.

- [ ] **Step 4: Verify and commit**

Run the focused tests above and `npm --workspace frontend/dashboard run typecheck`.

Expected: PASS.

Commit: `feat: show multi-query page loading progress`

### Task 3: Diagnostics, Reports, Assets, And Browser Verification

**Files:**
- Modify: `frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`
- Modify: nearest Diagnostics and Reports tests.
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/`

**Interfaces:**
- Reports uses indeterminate progress because its report pack is one request.
- Diagnostics treats the active structured-fact source as one module; its persisted notebook matrix keeps its existing module status.

- [ ] **Step 1: Add failing tests**

Hold endpoint promises, assert progress appears, resolve them, and assert it disappears. Reject the first Reports request and assert a visible incomplete-evidence alert remains.

- [ ] **Step 2: Confirm focused failures**

Run: `npm --workspace frontend/dashboard test -- src/features/diagnostics/DiagnosticsPage.test.tsx src/features/reports/ReportsPage.test.tsx`

Expected: FAIL because the component is not rendered.

- [ ] **Step 3: Integrate single-query states**

```tsx
<PageLoadProgress
  active={canUseLive && reportQuery.isFetching}
  label="Loading full-scope report pack"
  error={reportQuery.error && !reportQuery.data ? errorMessage(reportQuery.error) : null}
  updating={Boolean(reportQuery.data)}
/>
```

Diagnostics derives loading and errors from `factState`, never from the shell row loader.

- [ ] **Step 4: Run complete validation**

```bash
npm --workspace frontend/dashboard test -- src/design/PageLoadProgress.test.tsx src/features/diagnostics/DiagnosticsPage.test.tsx src/features/reports/ReportsPage.test.tsx
npm --workspace frontend/dashboard run typecheck
npm run dashboard:governance
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
npm --workspace frontend/dashboard run build
python3 scripts/check_release.py
git diff --check
```

Expected: every command passes.

- [ ] **Step 5: Verify in the in-app browser**

Restart the local server after the build so packaged assets are recopied. Visit Overview, Threads, Limits, Cache and Context, Diagnostics, Reports, and Investigator. Confirm each page shows its own progress while pending, no page-level overflow appears, and the bar disappears after success.

- [ ] **Step 6: Commit final integration**

Commit: `feat: complete dashboard page loading progress`
