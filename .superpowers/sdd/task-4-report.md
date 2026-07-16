# Task 4 Report: Browser QA, Documentation, Generated Assets, And Release Gates

## Status

DONE. Task 4 implementation, generated assets, synthetic screenshot proof, source-budget corrections, release readiness, and targeted Playwright smoke are complete. The earlier gate failures below are retained as resolved historical RED evidence; the appended final-fix section records the green branch state.

Commits: `ae21c6f docs: update threads expansion workflow`; `1d324fb fix: resolve threads final review gates`

## RED / GREEN Evidence

- RED: `npm run dashboard:smoke -- --grep "threads expand inline"` initially failed 4/4 because the new flow used the legacy full call-thread key `thread-9f3a1c`, while the fixture's aggregate parent row is canonically labeled `thread-9f3a`.
- Intermediate browser run: the 390px case passed, while the desktop round-trip exposed an overly broad parent-row locator after expansion.
- GREEN: after targeting the canonical aggregate parent with an anchored accessible row name, the focused browser run passed 4/4 across `chromium-desktop` and `chromium-mobile`.
- Post-build GREEN: the same targeted Playwright command passed 4/4 again.

The desktop flow proves that a parent click stays in Threads, the labeled inline expansion appears, an explicit child Open reaches Call Investigator, Back returns to Threads, and the same thread remains expanded. The 390px flow measures vertically stacked identity/signal evidence, a visible Open action at least 44px high, and no page-level horizontal overflow.

## Files And Generated Assets

- Added browser behavior and responsive assertions in `tests/playwright/dashboard-react.spec.mjs`.
- Updated the visible Threads workflow in `docs/dashboard-guide.md`.
- Updated `scripts/capture_dashboard_screenshots.mjs` to expand the canonical synthetic parent deterministically, wait for its labeled Calls region, and fail closed unless the page has no API token or embedded payload and contains the known static synthetic markers.
- Regenerated the matching 1600x900 synthetic Threads screenshot pair:
  - `docs/assets/dashboard-threads.png`
  - `src/codex_usage_tracker/plugin_data/docs/assets/dashboard-threads.png`
- Rebuilt `src/codex_usage_tracker/plugin_data/dashboard/react/` through `npm run dashboard:build`, including the extracted Evidence Grid controls chunks.
- Restored the eight other screenshot pairs that the all-routes capture command regenerated incidentally; they are outside Task 4 scope.

The two Threads PNGs are byte-identical (SHA-256 `4cf6f369795c1a3fd66c7800ccacd8e4441ba3c6916fc7134394128d1bb7344a`) and were visually reviewed. They show one inline aggregate expansion with explicit Open and Copy actions.

## Validation Results

- Focused Vitest selection: PASS, 5 files / 51 tests.
- `npm run dashboard:typecheck`: PASS.
- `npm run dashboard:lint`: PASS.
- `npm run dashboard:stylelint`: PASS.
- `npm run dashboard:build`: PASS (TypeScript and Vite production build).
- `npm run dashboard:screenshots`: PASS, all nine routes captured from the synthetic Vite fixture; only the scoped Threads pair retained.
- `npm run dashboard:smoke -- --grep "threads expand inline"`: PASS, 4/4 post-build.
- `python3 scripts/check_dashboard_source_budgets.py`: FAIL with the exact packet:
  - `new oversized tests file: frontend/dashboard/src/App.threads.test.tsx`
  - `new oversized source file: frontend/dashboard/src/features/threads/ThreadsPage.tsx`
- `/Users/Monsky/.codex/bin/codex-task dashboard-verify --json`: FAIL after 96/97 files and 462/463 tests passed. `src/App.calls-detail.test.tsx:218` queries a Threads table by `getByRole('table', { name: 'Thread leaderboard' })`, but Tasks 1-3 changed that surface to a `treegrid`. Full private log: `/var/folders/8b/wt4vy9ld3_v82nb4hsqpvw880000gp/T/codex-task-logs/965fc4bf9644/20260716T010926.039184Z-dashboard-verify.log`.
- `python3 scripts/check_release.py`: PASS (`python` and `.venv/bin/python` were unavailable in this worktree, so the available Python 3 interpreter was used).
- `git diff --check`: PASS.

## Synthetic / Privacy Confirmation

The capture ran only against the repository Vite fixture on localhost. The capture script rejects an API token, rejects an embedded usage payload, and requires `Stored snapshot`, `8 calls analyzed`, and `Local data only` markers before writing an image. No real Codex session data, prompts, context snippets, databases, local HTML dashboards, secrets, credentials, or `.env` files are in the Task 4 change set.

## Final Diff Review

The final review covered status, diff stat, the complete human-authored Task 4 diff, generated asset names, screenshot dimensions/hashes, and the packaged React output. Exact staging excludes the pre-existing `.superpowers/sdd/task-3-report.md` modification plus untracked `.idea/` and `.serena/logs/` artifacts.

## Concerns

1. The source-budget failure belongs to the Tasks 1-3 implementation and is intentionally not refactored in Task 4.
2. The full dashboard gate has one stale pre-existing table-role assertion in `App.calls-detail.test.tsx`; Task 4's browser and focused suites pass.
3. The preserved documentation query uses the full call thread key `thread-9f3a1c`, while the aggregate fixture canonicalizes it to parent `thread-9f3a`. The capture therefore clicks the canonical parent and waits for the actual accessible `Calls for thread-9f3a` region before capture.

## Final Fix RED Evidence

Before the review fixes, `python3 scripts/check_dashboard_source_budgets.py` failed with:

- `new oversized tests file: frontend/dashboard/src/App.threads.test.tsx` (667 physical lines; limit 600).
- `new oversized source file: frontend/dashboard/src/features/threads/ThreadsPage.tsx` (458 physical lines and over the 400-nonblank-line source limit).

The existing focused Threads tests are the characterization gate for the behavior-preserving split and orchestration extraction below.

## Final Fix Results

Status: PASS. The complete Task 4 review list is fixed without changing server schemas, privacy behavior, or unrelated product behavior.

Files:

- Split focused endpoint and progressive-loading characterizations into `frontend/dashboard/src/App.threads-live.test.tsx`; `App.threads.test.tsx` is now 447 physical lines.
- Extracted typed URL/control-state orchestration into `features/threads/useThreadsPageControls.ts`; `ThreadsPage.tsx` is now 384 physical / 366 nonblank lines.
- Updated the calls-detail Threads assertion to the `treegrid` contract and removed stale legacy column-copy assertions.
- Added exact Call Investigator URL-state assertions to the desktop/mobile Playwright flow.

Exact validation:

- `npm run dashboard:test -- --run src/App.threads.test.tsx src/App.threads-live.test.tsx src/App.calls-detail.test.tsx`: PASS, 3 files / 31 tests.
- `npm run dashboard:typecheck`: PASS.
- `npm run dashboard:lint`: PASS.
- `npm run dashboard:stylelint`: PASS.
- `python3 scripts/check_dashboard_source_budgets.py`: PASS (`13 ratcheted exceptions`).
- `/Users/Monsky/.codex/bin/codex-task dashboard-verify --json`: PASS (exit 0).
- `python3 scripts/check_release.py`: PASS.
- `npm run dashboard:smoke -- --grep "threads expand inline"`: PASS, 4/4 across `chromium-desktop` and `chromium-mobile`.
- `git diff --check`: PASS.

Self-review: verified status, diff stat, the complete scoped human-authored diff, source line counts, and exact staging. The extracted hook preserves initial URL hydration, page resets, clear-filter URL replacement, selected-thread toggling, and thread-call sort defaults. The moved live-query tests retain their original assertions without duplication or weakening.

Privacy check: tests and browser smoke use only repository synthetic fixtures. No real Codex session content, prompts, private records, secrets, credentials, `.env` files, databases, screenshots, or production data are included.
