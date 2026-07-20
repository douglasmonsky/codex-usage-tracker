# MCP-First Dashboard Transition Implementation Plan

> **For Codex:** Execute this plan task by task with `superpowers:executing-plans` or `superpowers:subagent-driven-development`. Release N and Release N+1 are separate releases.

**Goal:** Make MCP the primary analysis surface and the live React dashboard its focused evidence companion, without regressing Calls, Threads, Limits, Call Investigator, Diagnostics, or Settings.

**Architecture:** Introduce one exhaustive route catalog, one shell-owned per-origin experimental preference, a locally provable conversational-readiness model, and a renderer-independent dashboard-target contract. Release N lands the bridge with navigation unchanged. Release N+1 derives a six-tab default navigation only after replacement, privacy, package, and browser gates pass.

**Tech Stack:** Python 3.10+, FastMCP, stdlib HTTP server, React 19, TypeScript, TanStack Router/Query/Table, Vitest, Testing Library, Playwright/Axe, pytest, Vite, setuptools.

**Approved design:** [`docs/superpowers/specs/2026-07-19-mcp-first-dashboard-transition-design.md`](../specs/2026-07-19-mcp-first-dashboard-transition-design.md)

---

## Non-Negotiable Contracts

- Release N preserves the current React navigation and every existing route ID.
- Release N+1 defaults to exactly Overview, Calls, Threads, Limits, Diagnostics Notebook, and Settings.
- Call Investigator remains contextual and functionally unchanged.
- Limits keeps status, history, and statistical analysis.
- Diagnostics remains visible and receives a **Highly experimental** banner.
- Investigate and Compression Lab become opt-in experimental navigation entries; direct URLs always work.
- Cache And Context and Reports become direct-only transitioning routes only after job parity is signed off.
- Files, Commands, and Models aliases disappear only in Release N+1.
- No React route is deleted and no legacy static entry point changes in these releases.
- The experimental preference is shell-owned, browser-local, per origin, and off by default.
- Targets and copied prompts exclude API tokens, raw/indexed text, local paths, raw context, and privacy-disallowed labels.
- Reuse existing components, CSS tokens, Lucide icons, fixtures, and localization. Add no UI framework.
- Use synthetic data in tests, captures, docs, and release evidence.

## Delivery Map

| PR | Release | Outcome | Merge gate |
| --- | --- | --- | --- |
| 1 | N | Route catalog, preference, banners; navigation unchanged | Frontend coherence, unit, lint, typecheck |
| 2 | N | Readiness and MCP-to-dashboard evidence bridge | Python/TS schema, privacy, MCP, server tests |
| 3 | N | Fresh packaged assets, installed-wheel smoke, required browser gate | Clean asset diff, build, Playwright/Axe |
| 4 | N+1 | Six-tab default, experimental group, direct transitioning routes | Job parity, unit, browser, localization |
| 5 | N+1 | Focused Overview and MCP-first docs | Task walkthrough and full release gate |

Record the Release N tag and commit after PR 3. Release N+1 must be revertible to it without a data migration.

---

## Release N: Foundation Without Navigation Changes

### Task 1: Centralize route metadata and lock the baseline

**Files:**

- Create: `frontend/dashboard/src/app/routeCatalog.ts`
- Create: `frontend/dashboard/src/app/routeCatalog.test.ts`
- Modify: `frontend/dashboard/src/app/navigation.ts`
- Modify: `frontend/dashboard/src/routes/dashboardSearch.ts`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/app/shellUrl.ts`
- Modify: `frontend/dashboard/src/app/shellUrl.test.ts`
- Modify: `frontend/dashboard/src/app/currentViewExport.ts`

**Step 1: Write failing coherence tests.** Assert every `DashboardViewId` is cataloged and rendered once, IDs and labels are unique, `call` is contextual, foundation navigation matches the current ten primary entries, and return labels resolve from the full catalog rather than visible navigation.

```ts
expect(new Set(routeCatalog.map(route => route.id))).toEqual(new Set(dashboardViewIds));
expect(navigationForPhase('foundation').map(route => route.id)).toEqual([
  'overview', 'investigator', 'compression-lab', 'calls', 'threads',
  'usage-drain', 'cache-context', 'diagnostics', 'reports', 'settings',
]);
expect(routeDefinition('diagnostics')).toMatchObject({
  maturity: 'experimental', placement: 'primary', lifecycle: 'active',
});
expect(routeDefinition('cache-context')).toMatchObject({
  maturity: 'experimental', placement: 'hidden', lifecycle: 'transitioning',
});
```

Run `npm --workspace frontend/dashboard test -- routeCatalog.test.ts shellUrl.test.ts`. Expected: FAIL because the catalog does not exist.

**Step 2: Implement the exhaustive catalog.** Export `dashboardViewIds` from `dashboardSearch.ts` and define:

```ts
type RouteMaturity = 'stable' | 'experimental';
type RoutePlacement = 'primary' | 'contextual' | 'hidden';
type RouteLifecycle = 'active' | 'transitioning' | 'deprecated';
type DashboardExposurePhase = 'foundation' | 'simplified';

type DashboardRouteDefinition = {
  id: DashboardViewId;
  label: string;
  description: string;
  icon: LucideIcon;
  maturity: RouteMaturity;
  placement: RoutePlacement;
  lifecycle: RouteLifecycle;
  navigationGroup: 'primary' | 'experimental' | null;
  experimentalNavigationEligible: boolean;
  capabilities: { refresh: boolean; export: boolean; copyLink: boolean };
  safeParams: readonly string[];
};
```

Classify stable/primary/active: Overview, Calls, Threads, Limits, Settings; experimental/primary/active: Diagnostics; experimental/hidden/active: Investigate and Compression Lab; experimental/hidden/transitioning: Cache And Context and Reports; stable/contextual/active: Call Investigator. Keep placement independent from discoverability: only Investigate and Compression Lab set `experimentalNavigationEligible: true`. Files, Commands, and Models remain separate navigation aliases classified stable/hidden/deprecated until Task 12 removes them.

**Step 3: Move all route consumers.** Derive Release N `navItems` from `navigationForPhase('foundation')`; retain `secondaryNavItems`. Make return labels, keyboard labels, export labels, and refresh/export checks use the full catalog. Keep rendering exhaustive. Add `thread_key` to Threads URL cleanup.

**Step 4: Verify.** Run:

```bash
npm --workspace frontend/dashboard test -- routeCatalog.test.ts shellUrl.test.ts dashboardRouter.test.tsx App.shell.test.tsx
npm run dashboard:typecheck
npm run dashboard:lint
```

Expected: PASS with unchanged visible navigation.

**Step 5: Commit.**

```bash
git add -- frontend/dashboard/src/app/routeCatalog.ts frontend/dashboard/src/app/routeCatalog.test.ts frontend/dashboard/src/app/navigation.ts frontend/dashboard/src/routes/dashboardSearch.ts frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/app/shellUrl.ts frontend/dashboard/src/app/shellUrl.test.ts frontend/dashboard/src/app/currentViewExport.ts
git commit -m "refactor: centralize dashboard route metadata"
```

### Task 2: Add the shell-owned experimental preference

**Files:**

- Create: `frontend/dashboard/src/app/useExperimentalDashboardFeatures.ts`
- Create: `frontend/dashboard/src/app/useExperimentalDashboardFeatures.test.tsx`
- Modify: `frontend/dashboard/src/App.tsx`
- Modify: `frontend/dashboard/src/routes/DashboardRouteView.tsx`
- Modify: `frontend/dashboard/src/features/settings/useSettingsSection.ts`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.module.css`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.test.tsx`

**Step 1: Write failing tests.** Cover default-off, immediate update, remount, malformed values, restricted storage, and the per-origin explanation. Use key `codex-usage-dashboard-show-experimental-v1` with JSON booleans.

**Step 2: Implement one owner in `App.tsx`.** The hook catches read/write failures but preserves current-session state:

```ts
export function useExperimentalDashboardFeatures() {
  const [showExperimental, setShowExperimental] = useState(readPreference);
  useEffect(() => safelyWrite(showExperimental), [showExperimental]);
  return { showExperimental, setShowExperimental };
}
```

Pass value and setter through `DashboardRouteView` to Settings. Do not duplicate state in Settings and do not change navigation in Release N.

**Step 3: Add Settings > Advanced.** Append `advanced` to `settingsSections`; add the native checkbox **Show experimental dashboard features**; explain browser-origin scope, direct-link availability, and that Diagnostics stays visible.

**Step 4: Verify.** Run `npm --workspace frontend/dashboard test -- useExperimentalDashboardFeatures.test.tsx SettingsPage.test.tsx App.shell.test.tsx` and `npm run dashboard:typecheck`. Expected: PASS; navigation remains unchanged.

**Step 5: Commit.**

```bash
git add -- frontend/dashboard/src/app/useExperimentalDashboardFeatures.ts frontend/dashboard/src/app/useExperimentalDashboardFeatures.test.tsx frontend/dashboard/src/App.tsx frontend/dashboard/src/routes/DashboardRouteView.tsx frontend/dashboard/src/features/settings/useSettingsSection.ts frontend/dashboard/src/features/settings/SettingsPage.tsx frontend/dashboard/src/features/settings/SettingsPage.module.css frontend/dashboard/src/features/settings/SettingsPage.test.tsx
git commit -m "feat: add experimental dashboard preference"
```

### Task 3: Add shared maturity and transition banners

**Files:**

- Create: `frontend/dashboard/src/components/FeatureMaturityBanner.tsx`
- Create: `frontend/dashboard/src/components/FeatureMaturityBanner.module.css`
- Create: `frontend/dashboard/src/components/FeatureMaturityBanner.test.tsx`
- Modify: `frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx`
- Modify: `frontend/dashboard/src/features/diagnostics/DiagnosticsPage.query.test.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Modify: `frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`

**Step 1: Write failing semantic tests.** Require `role="note"`, an accessible label, title, description, and optional replacement action. Assert Diagnostics says **Highly experimental** independently of the preference.

**Step 2: Implement one component.** Reuse product tokens and render:

```tsx
<FeatureMaturityBanner
  kind="experimental"
  title="Highly experimental"
  description="Useful for technical exploration; methods and presentation may change."
/>
```

Add experimental banners to Investigate and Compression Lab. Add transition-capable banners to Cache And Context and Reports, but keep neutral copy while they remain visible in Release N.

**Step 3: Verify.** Run `npm --workspace frontend/dashboard test -- FeatureMaturityBanner.test.tsx DiagnosticsPage.query.test.tsx dashboardRouter.test.tsx`, `npm run dashboard:stylelint`, and `npm run dashboard:typecheck`. Expected: PASS and all direct routes render.

**Step 4: Commit.**

```bash
git add -- frontend/dashboard/src/components/FeatureMaturityBanner.tsx frontend/dashboard/src/components/FeatureMaturityBanner.module.css frontend/dashboard/src/components/FeatureMaturityBanner.test.tsx frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx frontend/dashboard/src/features/diagnostics/DiagnosticsPage.query.test.tsx frontend/dashboard/src/features/investigator/InvestigatorPage.tsx frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx frontend/dashboard/src/features/cache-context/CacheContextPage.tsx frontend/dashboard/src/features/reports/ReportsPage.tsx
git commit -m "feat: label dashboard feature maturity"
```

### Task 4: Report locally provable conversational readiness

**Files:**

- Create: `src/codex_usage_tracker/core/conversational_readiness.py`
- Create: `tests/core/test_conversational_readiness.py`
- Modify: `src/codex_usage_tracker/server/status.py`
- Modify: `src/codex_usage_tracker/server/dashboard_shell.py`
- Modify: `src/codex_usage_tracker/server/handler.py`
- Modify: `src/codex_usage_tracker/server/dashboard_pages.py`
- Modify: `src/codex_usage_tracker/cli/mcp_dashboard.py`
- Modify: `tests/server/test_server_status.py`
- Modify: `tests/server/test_server_dashboard_shell.py`
- Modify: `tests/dashboard/test_dashboard_server.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `frontend/dashboard/src/api/types.ts`
- Create: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx`
- Create: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.module.css`
- Create: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.test.tsx`
- Modify: `frontend/dashboard/src/features/overview/OverviewPage.tsx`
- Modify: `frontend/dashboard/src/features/overview/OverviewPage.test.tsx`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.test.tsx`

**Step 1: Write failing backend contract tests.** Cover fresh install before restart, valid generated wrapper, missing/malformed config, failed launcher import, and uninspectable/static state. Define:

```python
class ConversationalReadiness(TypedDict):
    schema: Literal["codex-usage-tracker-conversational-readiness-v1"]
    state: Literal["ready", "restart-required", "unavailable", "unknown"]
    summary: str
    next_action: str | None
    evidence: list[str]
```

`ready` means only that local installation and launcher checks pass. Never claim the current Codex task loaded MCP tools. Reuse bounded pure doctor checks; do not run the full doctor on every status request.

**Step 2: Add optional `conversational_analysis` to live status and shell boot payloads.** Thread `codex_home` explicitly through `handler._handle_status` → `handle_status_request` → `status_payload`, and through `dashboard_pages._dashboard_shell_payload` → `dashboard_shell_payload`. MCP `usage_status` passes `mcp_dashboard.DEFAULT_CODEX_HOME`. Static exports omit the field and normalize to `unknown`; no helper silently falls back to the process home.

Add server and MCP integration tests using a temporary custom Codex home. Prove the status endpoint and React shell report that fixture's readiness rather than the developer machine's default home.

**Step 3: Render the same recovery card in Overview and Settings.** Ready shows local checks passed; restart-required gives restart/fresh-task action; unavailable gives the exact setup/doctor action; unknown explains the limitation. Always expose Calls, Threads, Limits, Diagnostics, and Advanced experimental controls as manual fallback.

**Step 4: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_conversational_readiness.py tests/server/test_server_status.py tests/server/test_server_dashboard_shell.py tests/dashboard/test_dashboard_server.py tests/cli/test_mcp_integration.py -q
npm --workspace frontend/dashboard test -- ConversationalAnalysisStatus.test.tsx OverviewPage.test.tsx SettingsPage.test.tsx
npm run dashboard:typecheck
```

Expected: PASS across all four states and static fallback.

**Step 5: Commit.**

```bash
git add -- src/codex_usage_tracker/core/conversational_readiness.py tests/core/test_conversational_readiness.py src/codex_usage_tracker/server/status.py src/codex_usage_tracker/server/dashboard_shell.py src/codex_usage_tracker/server/handler.py src/codex_usage_tracker/server/dashboard_pages.py src/codex_usage_tracker/cli/mcp_dashboard.py tests/server/test_server_status.py tests/server/test_server_dashboard_shell.py tests/dashboard/test_dashboard_server.py tests/cli/test_mcp_integration.py frontend/dashboard/src/api/types.ts frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.module.css frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.test.tsx frontend/dashboard/src/features/overview/OverviewPage.tsx frontend/dashboard/src/features/overview/OverviewPage.test.tsx frontend/dashboard/src/features/settings/SettingsPage.tsx frontend/dashboard/src/features/settings/SettingsPage.test.tsx
git commit -m "feat: report conversational analysis readiness"
```

### Task 5: Implement the privacy-safe dashboard-target contract

**Files:**

- Create: `src/codex_usage_tracker/core/dashboard_targets.py`
- Create: `tests/core/test_dashboard_targets.py`
- Modify: `src/codex_usage_tracker/core/json_contract_server.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `src/codex_usage_tracker/dashboard_service.py`
- Modify: `tests/cli/test_dashboard_service.py`
- Create: `frontend/dashboard/src/app/dashboardTargets.ts`
- Create: `frontend/dashboard/src/app/dashboardTargets.test.ts`
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `docs/cli-json-schemas.md`

**Step 1: Write failing contract tests.** Require schema `codex-usage-tracker-dashboard-target-v1`, stable IDs, normalized history/filters, privacy mode, relative URL, optional absolute URL, and fallback instruction. Test normal, redacted, and strict modes. Reject API tokens, raw/indexed text, paths, raw-context fields, and unreviewed search text.

```python
target = build_dashboard_target(
    view="call",
    record_id="record-123",
    privacy_mode="strict",
    service_origin="http://127.0.0.1:47821",
)
assert target["relative_url"] == "/react-dashboard.html?view=call&record=record-123"
```

**Step 2: Implement pure builders and register the stable schema.** Accept only cataloged destinations and canonical selectors: `record_id`, `thread_key`, `diagnostic_fact`, `limit_evidence`, `history`, and per-view allowlisted filters. Sort parameters. Return an absolute URL only for an explicitly active loopback origin or healthy persistent service. Add `DashboardServiceStatus.react_url` without changing existing `url` root semantics.

Register `codex-usage-tracker-dashboard-target-v1` in `SERVER_JSON_PAYLOAD_CONTRACTS`. Validate common required keys (`view`, normalized `filters`, `history`, `privacy_mode`, and `relative_url`) plus nullable `absolute_url` and `fallback_instruction`. Route-specific canonical identifiers remain optional by destination and receive explicit builder tests because the current registry validates required fields only. Add `core/dashboard_targets.py` to `RUNTIME_SCHEMA_SOURCE_PATHS` so emitted-schema coverage and the documented-schema equality test remain authoritative.

Resolution order: reachable persistent service, known active `serve-dashboard` origin, then relative URL plus `codex-usage-tracker serve-dashboard --open`.

**Step 3: Mirror the contract in TypeScript.** Build links and copied prompts from reviewed fields only; drop unknown fields. Keep catalog `safeParams` authoritative.

**Step 4: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_dashboard_targets.py tests/core/test_json_contracts.py tests/cli/test_dashboard_service.py -q
npm --workspace frontend/dashboard test -- dashboardTargets.test.ts routeCatalog.test.ts
```

Expected: PASS with deterministic URLs and no forbidden fixture value.

**Step 5: Commit.**

```bash
git add -- src/codex_usage_tracker/core/dashboard_targets.py tests/core/test_dashboard_targets.py src/codex_usage_tracker/core/json_contract_server.py tests/core/test_json_contracts.py src/codex_usage_tracker/dashboard_service.py tests/cli/test_dashboard_service.py frontend/dashboard/src/app/dashboardTargets.ts frontend/dashboard/src/app/dashboardTargets.test.ts frontend/dashboard/src/app/routeCatalog.ts docs/cli-json-schemas.md
git commit -m "feat: define privacy-safe dashboard targets"
```

### Task 6: Attach evidence targets to MCP results

**Files:**

- Modify: `src/codex_usage_tracker/cli/mcp_dashboard.py`
- Modify: `src/codex_usage_tracker/cli/mcp_investigations.py`
- Modify: `tests/cli/test_mcp_integration.py`
- Modify: `tests/cli/test_cli_release.py`
- Modify: `tests/core/test_json_contracts.py`
- Modify: `docs/mcp.md`

**Step 1: Write failing integrations.** Assert Overview targets on `usage_status`; Call Investigator targets on call rows/detail; Threads targets by `thread_key`; matching targets on evidence findings; and relative fallback when service is unreachable. Assert public MCP tool names stay unchanged.

**Step 2: Add one annotation helper.** Wrap existing payload builders after return. Preserve query semantics, order, schemas, and fields. Resolve service status once per tool call. Emit targets only with canonical IDs; never substitute a display name for missing `thread_key`.

```python
payload = calls_payload(...)
return attach_call_targets(payload, privacy_mode=privacy_mode, origin=resolved_origin)
```

**Step 3: Document additive fields and readiness limits.**

**Step 4: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/cli/test_mcp_integration.py tests/cli/test_cli_release.py tests/core/test_json_contracts.py tests/core/test_dashboard_targets.py -q
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py
```

Expected: PASS; tool names unchanged.

**Step 5: Commit.**

```bash
git add -- src/codex_usage_tracker/cli/mcp_dashboard.py src/codex_usage_tracker/cli/mcp_investigations.py tests/cli/test_mcp_integration.py tests/cli/test_cli_release.py tests/core/test_json_contracts.py docs/mcp.md
git commit -m "feat: link MCP findings to dashboard evidence"
```

### Task 7: Make thread targets canonical and add evidence actions

**Files:**

- Modify: `frontend/dashboard/src/api/types.ts`
- Modify: `frontend/dashboard/src/api/client.ts`
- Modify: `frontend/dashboard/src/features/threads/threadsUrlState.ts`
- Modify: `frontend/dashboard/src/features/threads/threadsUrlState.test.ts`
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.tsx`
- Create: `frontend/dashboard/src/features/threads/ThreadsPage.test.tsx`
- Create: `frontend/dashboard/src/components/DashboardEvidenceActions.tsx`
- Create: `frontend/dashboard/src/components/DashboardEvidenceActions.test.tsx`
- Modify: `frontend/dashboard/src/features/investigator/InvestigatorPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`

**Step 1: Write failing tests.** `?view=threads&thread_key=thread-abc` selects by key when its display label changes. Existing `?thread=Display%20Name` remains compatible. New links emit `thread_key`. Add `threadKey?: string` to `ThreadRow` and map API `thread_key`.

**Step 2: Implement key-first selection.** Match by key before name, clear both selectors when leaving Threads, and never expose raw names in strict mode.

**Step 3: Add shared actions.**

```ts
type DashboardEvidenceActionsProps = {
  target: DashboardTarget;
  question: string;
  onStatus: (message: string) => void;
};
```

**Open evidence** uses a safe same-origin/loopback link with `rel="noopener noreferrer"`. **Copy investigation prompt** includes only a concise question, aggregate IDs, scope, and target. With no origin, show/copy launch guidance. Add actions to Investigate and Reports; leave Call Investigator unchanged.

**Step 4: Verify.**

```bash
npm --workspace frontend/dashboard test -- threadsUrlState.test.ts ThreadsPage.test.tsx DashboardEvidenceActions.test.tsx dashboardTargets.test.ts
npm run dashboard:typecheck
```

Expected: PASS; clipboard fixtures contain no tokens, paths, raw text, or redacted labels.

**Step 5: Commit.**

```bash
git add -- frontend/dashboard/src/api/types.ts frontend/dashboard/src/api/client.ts frontend/dashboard/src/features/threads/threadsUrlState.ts frontend/dashboard/src/features/threads/threadsUrlState.test.ts frontend/dashboard/src/features/threads/ThreadsPage.tsx frontend/dashboard/src/features/threads/ThreadsPage.test.tsx frontend/dashboard/src/components/DashboardEvidenceActions.tsx frontend/dashboard/src/components/DashboardEvidenceActions.test.tsx frontend/dashboard/src/features/investigator/InvestigatorPage.tsx frontend/dashboard/src/features/reports/ReportsPage.tsx
git commit -m "feat: open canonical dashboard evidence"
```

### Task 8: Localize Release N copy and synchronize bundled skills

**Files:**

- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: `skills/codex-usage-api/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md`
- Modify: `frontend/dashboard/src/app/i18n.ts`
- Modify: `frontend/dashboard/src/features/settings/SettingsPage.tsx`
- Modify: `frontend/dashboard/src/components/FeatureMaturityBanner.tsx`
- Modify: `frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx`
- Modify: `frontend/dashboard/src/components/DashboardEvidenceActions.tsx`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/locales/*.json`
- Modify: `tests/core/test_i18n.py`
- Modify: `tests/playwright/dashboard-release-candidate.spec.mjs`
- Modify: `tests/cli/test_cli_release.py`
- Modify: `docs/mcp.md`
- Modify: `docs/first-five-minutes.md`

**Step 1: Add failing Release N localization coverage.** Require supported-locale keys for the experimental toggle and origin scope, Diagnostics and workbench maturity wording, all readiness/recovery states, Open evidence, Copy investigation prompt, and fallback launch guidance. Add a browser locale case proving the new shell copy renders without falling back to English.

**Step 2: Route all new Release N copy through the existing i18n layer.** Update every supported packaged locale in the same release as the components. Do not ship literal-only English for the toggle, banners, readiness card, or evidence actions.

**Step 3: Update source skills, then package copies byte-for-byte.** Surface **Open evidence** with an absolute target; otherwise show the relative target and launch instruction. Never infer task-level MCP availability.

**Step 4: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_i18n.py tests/cli/test_cli_release.py -q
npm --workspace frontend/dashboard test -- SettingsPage.test.tsx FeatureMaturityBanner.test.tsx ConversationalAnalysisStatus.test.tsx DashboardEvidenceActions.test.tsx
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py
```

Expected: PASS across every supported locale with byte-identical source/package skill copies.

**Step 5: Commit.**

```bash
git add -- skills/codex-usage-tracker/SKILL.md skills/codex-usage-api/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-api/SKILL.md frontend/dashboard/src/app/i18n.ts frontend/dashboard/src/features/settings/SettingsPage.tsx frontend/dashboard/src/components/FeatureMaturityBanner.tsx frontend/dashboard/src/features/shared/ConversationalAnalysisStatus.tsx frontend/dashboard/src/components/DashboardEvidenceActions.tsx src/codex_usage_tracker/plugin_data/dashboard/locales tests/core/test_i18n.py tests/playwright/dashboard-release-candidate.spec.mjs tests/cli/test_cli_release.py docs/mcp.md docs/first-five-minutes.md
git commit -m "feat: localize MCP evidence bridge"
```

### Task 9: Make packaged React assets deterministic

**Files:**

- Modify: `package.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/check_release.py`
- Modify: `scripts/smoke_installed_package.py`
- Modify: `tests/cli/test_cli_release.py`

**Step 1: Add a failing asset-sync check.**

```json
"dashboard:assets:check": "npm run dashboard:build && git diff --exit-code -- src/codex_usage_tracker/plugin_data/dashboard/react"
```

Require it and require the package job to build React before `python -m build`.

**Step 2: Harden packaging.** Set up Node 22, run `npm ci`, build React, then build wheel/sdist. After `python scripts/check_release.py --dist`, the package CI job must run `python scripts/smoke_installed_package.py`. Extend that smoke so the isolated installation serves `/react-dashboard.html`, `/dashboard.html`, and referenced React assets.

**Step 3: Verify.**

```bash
npm run dashboard:assets:check
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m build
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py --dist
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/smoke_installed_package.py
```

Expected: PASS and no generated diff; the smoke installs a built wheel into an isolated environment and serves both React and legacy entry points.

**Step 4: Commit.**

```bash
git add -- package.json .github/workflows/ci.yml scripts/check_release.py scripts/smoke_installed_package.py tests/cli/test_cli_release.py src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "build: verify packaged dashboard assets"
```

### Task 10: Require the release-candidate browser matrix

**Files:**

- Modify: `package.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/playwright/dashboard-release-candidate.spec.mjs`
- Modify: `tests/playwright/dashboard-react.spec.mjs`
- Modify: `scripts/capture_dashboard_screenshots.mjs`
- Modify: `docs/dashboard-guide.md`

**Step 1: Add command and required Chromium CI gate.**

```json
"dashboard:release-candidate": "REACT_DASHBOARD_WEB_SERVER=1 DASHBOARD_BASE_URL=http://127.0.0.1:5173 playwright test tests/playwright/dashboard-release-candidate.spec.mjs --project=chromium-desktop"
```

The same CI job that runs this command must first run `npx playwright install --with-deps chromium`; installation in the separate visualization job does not carry across GitHub runners.

**Step 2: Expand Release N coverage.** Test preference persistence, direct experimental/transitioning routes, Diagnostics banner, Call Investigator returns, all readiness states, manual fallback, desktop/tablet/mobile, 200% zoom, keyboard/focus, reduced motion, Axe serious/critical findings, and console errors. Assert baseline navigation remains unchanged.

**Step 3: Capture synthetic evidence** for every route category and readiness state.

**Step 4: Verify.**

```bash
npm run dashboard:release-candidate
npm run dashboard:verify
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_i18n.py -q
git diff --check
```

Expected: PASS; clean assets; no serious/critical accessibility issue.

**Step 5: Commit and ship Release N.**

```bash
git add -- package.json .github/workflows/ci.yml tests/playwright/dashboard-release-candidate.spec.mjs tests/playwright/dashboard-react.spec.mjs scripts/capture_dashboard_screenshots.mjs docs/dashboard-guide.md src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "test: gate dashboard release candidates"
```

Create the Release N PR and record its merge commit/package version. Do not start Task 11 until Release N is shipped and installed-wheel smoke is green.

---

## Release N+1: Change Default Discoverability

### Task 11: Prove Cache/Reports replacement parity before hiding them

**Files:**

- Create: `docs/dashboard-sunset-job-parity.md`
- Create: `tests/cli/test_dashboard_sunset_parity.py`
- Modify: `src/codex_usage_tracker/cli/mcp_investigations.py`
- Modify: `src/codex_usage_tracker/cli/mcp_dashboard.py`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.tsx`
- Modify: `frontend/dashboard/src/features/cache-context/CacheContextPage.test.tsx`
- Modify: `frontend/dashboard/src/features/reports/ReportsPage.test.tsx`
- Modify: `docs/mcp.md`
- Modify: `docs/dashboard-guide.md`

**Step 1: Turn the approved parity matrix into failing acceptance tests.** For synthetic fixtures, prove:

- cache trend/context-pressure scope, caveats, and aggregate supporting Calls are available through Overview plus MCP;
- cross-thread cache/cold-resume ranking and selected evidence are available through MCP plus Threads/Calls;
- each cache heatmap job is either represented by a tested experimental viewer or explicitly recorded as intentionally removed;
- report intent selection, methodology, confidence, caveats, evidence targets, and export are reachable without undocumented CLI knowledge;
- every replacement target resolves to the same canonical call/thread used by the legacy page fixture.

**Step 2: Fill only parity gaps.** Add missing aggregate fields, target annotations, or copy to existing MCP/report builders. Do not redesign the stable dashboard. Keep payload changes additive.

**Step 3: Add transition notices while routes remain visible.** Cache And Context points to Overview, Threads, Calls, and the named MCP investigation. Reports points to the report/action brief, evidence targets, and existing export. Notices must include direct recovery when MCP is unavailable.

**Step 4: Sign the decision record.** For each job record replacement, acceptance test, owner, result, intentional removals, and Release N baseline. Any row not PASS blocks Task 12.

**Step 5: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/cli/test_dashboard_sunset_parity.py tests/cli/test_mcp_integration.py -q
npm --workspace frontend/dashboard test -- CacheContextPage.test.tsx ReportsPage.test.tsx DashboardEvidenceActions.test.tsx
```

Expected: PASS for every matrix row. Stop if any replacement is missing or points at different evidence.

**Step 6: Commit.**

```bash
git add -- docs/dashboard-sunset-job-parity.md tests/cli/test_dashboard_sunset_parity.py src/codex_usage_tracker/cli/mcp_investigations.py src/codex_usage_tracker/cli/mcp_dashboard.py frontend/dashboard/src/features/cache-context/CacheContextPage.tsx frontend/dashboard/src/features/reports/ReportsPage.tsx frontend/dashboard/src/features/cache-context/CacheContextPage.test.tsx frontend/dashboard/src/features/reports/ReportsPage.test.tsx docs/mcp.md docs/dashboard-guide.md
git commit -m "test: prove dashboard sunset job parity"
```

### Task 12: Switch to the six-tab default navigation

**Files:**

- Modify: `frontend/dashboard/src/app/navigation.ts`
- Modify: `frontend/dashboard/src/app/routeCatalog.ts`
- Modify: `frontend/dashboard/src/app/routeCatalog.test.ts`
- Modify: `frontend/dashboard/src/App.tsx`
- Modify: `frontend/dashboard/src/App.shell.test.tsx`
- Modify: `frontend/dashboard/src/app/shellUrl.test.ts`
- Modify: `frontend/dashboard/src/styles/shell.css`
- Modify: `frontend/dashboard/src/app/RowLimitControl.tsx`
- Create: `frontend/dashboard/src/components/AdvancedShellControls.tsx`
- Create: `frontend/dashboard/src/components/AdvancedShellControls.test.tsx`

**Step 1: Change the tests first.** Preference off must show exactly:

```ts
['Overview', 'Calls', 'Threads', 'Limits', 'Diagnostics Notebook', 'Settings']
```

Preference on adds a visually separate **Experimental** group with Investigate and Compression Lab. Cache And Context and Reports are absent from navigation but direct links render transition notices. Files, Commands, and Models do not render. Toggling updates immediately without reload and visiting a direct route does not persist the preference.

Also test Call Investigator returns to Reports/Cache correctly even though those labels are not visible.

**Step 2: Activate simplified exposure.** In `App.tsx`, use `navigationForPhase('simplified', showExperimental)`. Remove `secondaryNavItems` rendering and imports. Keep all route IDs, lazy components, URL cleanup, and direct-route rendering.

**Step 3: Reduce shell density.** Keep global search, history/time scope, refresh, and copy-link visible. Move `RowLimitControl` and other technical loading controls into an accessible topbar `AdvancedShellControls` disclosure. This is separate from Settings > Advanced because it controls the current data load. Persist no new state.

**Step 4: Verify focused shell behavior.**

```bash
npm --workspace frontend/dashboard test -- routeCatalog.test.ts App.shell.test.tsx shellUrl.test.ts AdvancedShellControls.test.tsx
npm run dashboard:typecheck
npm run dashboard:lint
npm run dashboard:stylelint
```

Expected: PASS with six default tabs, two optional Labs, and every direct route intact.

**Step 5: Commit.**

```bash
git add -- frontend/dashboard/src/app/navigation.ts frontend/dashboard/src/app/routeCatalog.ts frontend/dashboard/src/app/routeCatalog.test.ts frontend/dashboard/src/App.tsx frontend/dashboard/src/App.shell.test.tsx frontend/dashboard/src/app/shellUrl.test.ts frontend/dashboard/src/styles/shell.css frontend/dashboard/src/app/RowLimitControl.tsx frontend/dashboard/src/components/AdvancedShellControls.tsx frontend/dashboard/src/components/AdvancedShellControls.test.tsx
git commit -m "feat: simplify dashboard navigation"
```

### Task 13: Refine the stable first-run experience

**Files:**

- Modify: `frontend/dashboard/src/features/overview/OverviewPage.tsx`
- Modify: `frontend/dashboard/src/features/overview/OverviewPage.module.css`
- Modify: `frontend/dashboard/src/features/overview/OverviewPage.test.tsx`
- Modify: `frontend/dashboard/src/features/overview/overviewModel.ts`
- Modify: `frontend/dashboard/src/features/overview/overviewModel.test.ts`
- Modify: `frontend/dashboard/src/App.shell.test.tsx`

**Step 1: Lock stable-flow tests before visual changes.** Assert one bounded summary group, one primary usage trend, bounded findings, conversational readiness/recovery, recent calls, and direct actions to Calls/Threads/Limits/Diagnostics. Assert Call Investigator and Limits tests/snapshots remain unchanged.

**Step 2: Remove Overview duplication.** Keep only metrics that answer current usage, trend, what needs attention, and where evidence lives. Do not move Cache/Reports complexity into Overview. Put Usage Constellation behind the experimental preference or omit it from default Overview based on the approved design's “evaluate” clause.

**Step 3: Keep manual recovery obvious.** Non-ready/unknown states expose the stable manual workflow and one action to enable experimental workbenches for this origin. Ready states lead with an MCP investigation prompt and evidence links.

**Step 4: Verify.**

```bash
npm --workspace frontend/dashboard test -- OverviewPage.test.tsx overviewModel.test.ts App.shell.test.tsx LimitsPage.test.tsx callInvestigatorState.test.ts callInvestigatorReadout.test.ts
npm run dashboard:typecheck
```

Expected: PASS; Limits and Call Investigator behavior equal the Release N baseline.

**Step 5: Commit.**

```bash
git add -- frontend/dashboard/src/features/overview/OverviewPage.tsx frontend/dashboard/src/features/overview/OverviewPage.module.css frontend/dashboard/src/features/overview/OverviewPage.test.tsx frontend/dashboard/src/features/overview/overviewModel.ts frontend/dashboard/src/features/overview/overviewModel.test.ts frontend/dashboard/src/App.shell.test.tsx
git commit -m "refactor: focus the dashboard overview"
```

### Task 14: Localize Release N+1 changes and document the MCP-first product contract

**Files:**

- Modify: `README.md`
- Modify: `docs/first-five-minutes.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/mcp.md`
- Modify: `docs/privacy.md`
- Modify: `docs/cli-json-schemas.md`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/locales/*.json`
- Modify: `tests/core/test_i18n.py`
- Modify: `tests/playwright/dashboard-release-candidate.spec.mjs`
- Modify: `scripts/capture_dashboard_screenshots.mjs`
- Modify: `docs/assets/*`

**Step 1: Extend localization coverage for Release N+1 only.** Release N already covers the toggle, banners, readiness, and evidence actions in Task 8. Here require keys for the six-tab default navigation, Experimental group, Advanced shell disclosure, Overview refinements, and Cache/Reports transition notices across every supported locale.

**Step 2: Rewrite the journey.** README and first five minutes lead with MCP conversational analysis; live React is the evidence companion. Clearly distinguish `serve-dashboard --open` live React behavior, generated/open static legacy behavior, MCP-unavailable fallback, experimental access, and transitioning direct routes.

**Step 3: Document privacy.** List target allowlists and exclusions, explain local clipboard behavior, and state that no browser-to-task invocation occurs.

**Step 4: Regenerate only synthetic screenshots.** Capture the six-tab default at desktop/mobile, experimental group enabled, Diagnostics banner, readiness recovery, and one canonical evidence target. Scan images/copy for paths, names, tokens, and real records.

**Step 5: Verify.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_i18n.py tests/cli/test_cli_release.py -q
npm run dashboard:release-candidate
npx markdownlint-cli2 README.md "docs/**/*.md"
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py
```

Expected: PASS in every supported locale with synthetic-only evidence.

**Step 6: Commit.**

```bash
git add -- README.md docs/first-five-minutes.md docs/dashboard-guide.md docs/mcp.md docs/privacy.md docs/cli-json-schemas.md src/codex_usage_tracker/plugin_data/dashboard/locales tests/core/test_i18n.py tests/playwright/dashboard-release-candidate.spec.mjs scripts/capture_dashboard_screenshots.mjs docs/assets
git commit -m "docs: position MCP as the primary analysis surface"
```

### Task 15: Run the task evaluation and Release N+1 gate

**Files:**

- Create: `docs/mcp-first-dashboard-release-evaluation.md`
- Modify: `docs/dashboard-sunset-job-parity.md`
- Modify: `CHANGELOG.md`
- Modify: `src/codex_usage_tracker/plugin_data/dashboard/react/*`

**Step 1: Run six synthetic walkthroughs.** Record happy and recovery paths for:

1. determine recent usage drivers and open exact evidence;
2. find the heaviest thread and inspect one contributing call;
3. inspect Limits and understand statistical evidence;
4. complete a token-waste investigation with MCP ready;
5. complete useful manual analysis with MCP unavailable/unknown;
6. open Diagnostics and correctly identify it as highly experimental.

For each, record start state, steps, wrong turns, target expected/actual IDs, recovery, and PASS/FAIL. Any dead end, mismatched target, privacy issue, or more than one wrong turn blocks release.

**Step 2: Run focused regression gates.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest tests/core/test_dashboard_targets.py tests/cli/test_mcp_integration.py tests/cli/test_dashboard_sunset_parity.py tests/server/test_server_open_investigator.py -q
npm --workspace frontend/dashboard test -- routeCatalog.test.ts App.shell.test.tsx dashboardTargets.test.ts DashboardEvidenceActions.test.tsx threadsUrlState.test.ts OverviewPage.test.tsx
npm run dashboard:release-candidate
```

**Step 3: Run the complete repository gates.**

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/ruff check .
PATH="$PWD/.venv/bin:$PATH" .venv/bin/mypy
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest
npm run dashboard:verify
npm run dashboard:assets:check
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m build
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/check_release.py --dist
PATH="$PWD/.venv/bin:$PATH" .venv/bin/python scripts/smoke_installed_package.py
git diff --check
```

Expected: all PASS; committed React assets match source; installed React and legacy entry points both smoke successfully.

**Step 4: Perform the final review.** Inspect `git status --short --branch`, `git diff --stat`, the full diff, and staged files for real/private data. Confirm no route deletion, no legacy behavior change, and no unintended Call Investigator or Limits diff. Update the evaluation and changelog with exact check results and the Release N rollback version/commit.

**Step 5: Commit and open the Release N+1 PR.**

```bash
git add -- docs/mcp-first-dashboard-release-evaluation.md docs/dashboard-sunset-job-parity.md CHANGELOG.md src/codex_usage_tracker/plugin_data/dashboard/react
git commit -m "docs: record MCP-first dashboard release evidence"
```

The PR description must list: Release N dependency, parity sign-off, exact checks, task-evaluation results, screenshots, rollback commit/version, and the explicit statement that route deletion and legacy removal remain deferred.

---

## Deferred Follow-Up: Release N+2 or 1.0

Do not include these actions in this plan's implementation PRs:

- deleting Cache And Context or Reports routes;
- removing or redirecting legacy static entry points;
- graduating or deleting Investigate, Compression Lab, or Diagnostics;
- redesigning Call Investigator or removing Limits statistical analysis.

After at least two compatible minor releases, use support evidence plus the Task 15 evaluation to write a separate decision/design document for each graduation, removal, or legacy-entry-point change.
