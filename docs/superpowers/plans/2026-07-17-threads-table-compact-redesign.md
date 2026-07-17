# Threads Table Compact Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Threads leaderboard a polished scan-first table without changing its data, virtualization, expansion, or privacy contracts.

**Architecture:** Keep the existing `ThreadAccordionGrid` and TanStack table model. Define presentation defaults alongside Threads orchestration, give shared thread columns intentional sizes and human-readable cells, and fix alignment/styling inside the Threads CSS module. Version the local preference key so the compact defaults reach existing installations.

**Tech Stack:** React 19, TypeScript, TanStack React Table, TanStack React Virtual, CSS Modules, Vitest/Testing Library, Playwright, Vite.

## Global Constraints

- Keep every advanced column available from **Columns**.
- Preserve aggregate-only data, API schemas, URL state, pagination, exports, and inline call expansion.
- Preserve dense/roomy modes, keyboard interaction, accessible names, and narrow-screen behavior.
- Rebuild packaged dashboard assets instead of editing generated JavaScript.
- Use only synthetic test data and screenshots.

---

### Task 1: Pin The Scan-First Presentation Contract

**Files:**
- Modify: `frontend/dashboard/src/features/shared/tables.test.ts`
- Modify: `frontend/dashboard/src/features/threads/ThreadAccordionGrid.test.tsx`
- Modify: `frontend/dashboard/src/App.threads.test.tsx`

**Interfaces:**
- Consumes: `threadColumns`, `ThreadAccordionGrid`, and the Threads workspace.
- Produces: regression coverage for column widths, default visibility, humanized unloaded metadata, and full thread identity access.

- [ ] **Step 1: Write failing tests**

Add assertions equivalent to:

```ts
expect(threadColumns.find(column => column.id === 'name')?.size).toBe(280);
expect(screen.getByRole('columnheader', { name: /Thread/i })).toBeInTheDocument();
expect(screen.queryByRole('columnheader', { name: /Models/i })).not.toBeInTheDocument();
expect(screen.getByTitle(fixtureThread.name)).toBeInTheDocument();
expect(screen.getByText('Mostly user')).toBeInTheDocument();
```

- [ ] **Step 2: Verify RED**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/shared/tables.test.ts src/features/threads/ThreadAccordionGrid.test.tsx src/App.threads.test.tsx
```

Expected: FAIL because the columns have default widths, all columns are visible, identifiers lack a title, and initiator text is raw.

### Task 2: Implement The Compact Grid

**Files:**
- Modify: `frontend/dashboard/src/features/shared/tables.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadAccordionGrid.tsx`
- Modify: `frontend/dashboard/src/features/threads/ThreadsPage.module.css`
- Modify: `docs/dashboard-guide.md`
- Regenerate: `src/codex_usage_tracker/plugin_data/dashboard/react/assets/ThreadsPage.js`

**Interfaces:**
- Produces: `threadDefaultColumnVisibility: VisibilityState` in Threads orchestration.
- Preserves: `ThreadAccordionGridProps`, query paging, row virtualization, and explicit child-call actions.

- [ ] **Step 1: Add intentional column definitions and defaults**

Use explicit sizes and cells, for example:

```tsx
{
  accessorKey: 'name',
  header: 'Thread',
  size: 280,
  minSize: 220,
  cell: info => <span className="thread-name-cell" title={String(info.getValue())}>{String(info.getValue())}</span>,
}
```

Set nonessential column visibility to `false`, pass it to `useEvidenceGridPreferences`, and use a versioned Threads preference key.

- [ ] **Step 2: Align and style the custom grid**

Move the disclosure chevron into the first visible grid cell. Add CSS that resets header buttons, truncates cells, freezes the identity column, preserves hover/expanded backgrounds, and provides `:focus-visible` outlines.

- [ ] **Step 3: Verify GREEN and rebuild**

Run:

```bash
npm --workspace frontend/dashboard test -- src/features/shared/tables.test.ts src/features/threads/ThreadAccordionGrid.test.tsx src/App.threads.test.tsx
npm --workspace frontend/dashboard run typecheck
npm --workspace frontend/dashboard run build
```

Expected: all commands PASS and only Threads packaged assets change.

- [ ] **Step 4: Run browser and full gates**

Verify the branch dashboard at desktop and narrow widths, then run:

```bash
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
```

Expected: PASS with no browser console errors and explicit 100-call pagination retained.

- [ ] **Step 5: Publish and merge**

Stage only intended files, commit with Conventional Commit style, push the branch, open a ready PR, wait for required checks, and squash merge after they pass.
