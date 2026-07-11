# Dashboard Final Redesign Release-Candidate Guide

This guide defines the migration, default-launch, rollback, and maintainer
signoff contract for R11 of the dashboard redesign. It tracks issue #201 from
base commit `88ebcd80d08c1eb2229d9c7e929849e328af4097`.

## Status And Decision Boundary

The statements below use these labels:

- **Verified at the R11 base** means the behavior is present in current code,
  documentation, or focused compatibility tests.
- **Passed local R11 evidence** means the named check was run against this
  candidate on 2026-07-11 and is recorded below. It is not publishing approval.
- **Open decision** means maintainer approval is required; this guide does not
  guess or silently change the behavior.

This document records local accessibility, performance, package-install,
security, and broad release checks. GitHub CI and maintainer approval remain the
R12 merge boundary.

## Launch Paths

### Installed package

Install or upgrade the published distribution, refresh package-owned plugin
files, and start the live dashboard:

```bash
pipx install codex-usage-tracking
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

For an existing pipx installation, replace the first command with:

```bash
pipx upgrade codex-usage-tracking
```

**Verified at the R11 base:** `serve-dashboard --open` opens
`http://127.0.0.1:8765/react-dashboard.html` by default. The command refreshes
active-session usage before startup unless `--no-refresh` is supplied. Its JSON
output reports both `dashboard_url` and `legacy_dashboard_url`.

**Passed local R11 evidence:** the `0.17.2` wheel was built, installed into a
clean temporary environment, and exercised through CLI, plugin setup, doctor,
dashboard generation, React/legacy server routes, package resources, and strict
support-bundle smoke checks.

### Source checkout

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python
codex-usage-tracker serve-dashboard --open
```

This path is for branch development and release-candidate testing. The plugin
installer points the generated MCP configuration at the selected Python and
supports the checkout's `src` directory.

**Passed local R11 evidence:** the source checkout served the real local index
at `/react-dashboard.html`; the in-app browser verified All time loading, warm
cache restoration, data-window switching, parser status, and desktop layout.

### Static snapshot

```bash
codex-usage-tracker open-dashboard
```

**Verified at the R11 base:** `open-dashboard` generates and opens the static
legacy dashboard file. It is not an alias for the live React route. Use
`serve-dashboard` for the redesign's live query, refresh, and lazy-context
workflow.

## Default And Compatibility Policy

The release-candidate policy is to retain the current transition behavior:

| Entry point | Behavior at the R11 base | Release-candidate disposition |
| --- | --- | --- |
| `serve-dashboard --open` | Opens `/react-dashboard.html` | Keep as the preferred live launch |
| `/react-dashboard.html` | Serves the React redesign | Candidate default live UI |
| `/dashboard.html` | Serves the legacy dashboard shell | Keep as the rollback route |
| `/` | Serves the legacy dashboard shell | Keep unchanged as the transition rollback entry |
| `open-dashboard` | Opens a generated static legacy file | Keep unchanged for static snapshots |

Do not delete the legacy assets, redirect `/dashboard.html`, or redefine the
static command during R11. Those changes would remove the same-server rollback
surface and require a separate reviewed decision.

**Maintainer decision:** `/` remains the legacy entry point for the transition
release. The CLI continues to open the React route explicitly, while `/` and
`/dashboard.html` preserve a same-server recovery path. A later root-route
switch requires a separate reviewed change to code, tests, and this guide.

## Migration Expectations

- Existing `serve-dashboard` users move to the redesign automatically only
  when the CLI opens the browser. Manually saved `/dashboard.html` and `/`
  bookmarks continue to open the legacy shell.
- Existing `?view=` links remain valid on the React route. Maintained values are
  `overview`, `investigator`, `calls`, `call`, `threads`, `usage-drain`,
  `cache-context`, `diagnostics`, `reports`, and `settings`.
- The historical `view=insights` alias resolves to Overview, and unknown view
  values fall back to Overview. Relevant record, return-route, filter, search,
  paging, thread, and context-option parameters remain compatibility inputs.
- `usage-drain` remains the stable route identifier even though the visible
  destination is named Limits.
- Existing local database, pricing, allowance, thresholds, projects, privacy,
  and plugin paths remain authoritative. The redesign does not introduce a
  second settings store or authorize a storage/schema migration.
- Existing aggregate JSON, CSV, API, and MCP contracts remain the analytical
  source of truth. Explicit raw-context access remains localhost-only, gated,
  redacted, and absent from static HTML payloads.
- Users who require a static file continue to use `open-dashboard`; users who
  require the redesign use the localhost server.

## Exact Rollback

### Roll back the dashboard view without changing the installation

1. Leave the current `codex-usage-tracker serve-dashboard` process running.
2. Open `http://127.0.0.1:8765/dashboard.html` in the same browser.
3. When rolling back a bookmarked workflow, copy the query string from the
   React URL to the legacy URL. For example:

   ```text
   http://127.0.0.1:8765/dashboard.html?view=calls
   ```

4. Confirm the required workspace and aggregate data load before continuing.
5. Preserve the failed React URL and non-sensitive console/error details for
   the R11 evidence record. Do not include prompts, messages, tool output, raw
   logs, or other private content.

If a non-default `--host`, `--port`, or dashboard output name was used, take the
exact `legacy_dashboard_url` from `serve-dashboard --json` instead of assuming
the example URL.

### Roll back an installed release candidate

1. Stop the dashboard server.
2. Reinstall the maintainer-designated last-known-good version:

   ```bash
   pipx install --force "codex-usage-tracking==0.17.1"
   codex-usage-tracker setup
   codex-usage-tracker doctor
   codex-usage-tracker serve-dashboard --open
   ```

3. Open the printed `legacy_dashboard_url` if the last-known-good package still
   prefers the React route.
4. Record the exact package version and result without publishing local paths
   or private usage data.

`0.17.1` is the last tagged release before this redesign candidate and is the
designated installed-package rollback version. Rehearse the command in a clean
environment before publishing release notes.

### Roll back a source-checkout candidate

Use a separate clean checkout or worktree at the R11 base, then reinstall its
plugin wrapper:

```bash
git switch --detach 88ebcd80d08c1eb2229d9c7e929849e328af4097
. .venv/bin/activate
python -m pip install -e ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python --force
codex-usage-tracker serve-dashboard --open
```

Do not use this procedure in a worktree with uncommitted changes. The detached
checkout is a local verification surface, not a release or publishing action.

## Known Limits At Release Candidate

- The product is desktop-first. Compact desktop (1280x800) and standard desktop
  (1600x900) are the visual release targets. Narrow-window accessibility and
  containment remain tested, but tablet/mobile polish is not a release gate.
- The first all-history recommendation scan can remain noticeably slower than
  the bounded aggregate snapshot. Revision-matched browser caches make warm
  reloads and revisited data windows immediate.
- Static packaged workspaces retain fixture fallback; static mode does not
  provide the live refresh and lazy-context workflow.
- Settings reports authoritative local state but does not add writable pricing,
  allowance, privacy, or parser configuration controls.
- SVG and PNG output from MCP visualization tools remains deliberately deferred;
  semantic visualization specifications remain the supported contract.
- The final merge and release version require maintainer review. This candidate
  does not authorize publishing.

## R11 Evidence Record

Fill this table with links or artifact identifiers from synthetic-data checks.
Do not paste raw logs or real user data into this document.

| Evidence gate | Status | Artifact or result | Reviewer |
| --- | --- | --- | --- |
| Route and viewport matrix | Passed local R11 evidence | `dashboard-visual-hardening.spec.mjs`: 1 passed across 10 routes at 1280x800 and 1600x900 | Automated |
| Accessibility and keyboard matrix | Passed local R11 evidence | `dashboard-release-candidate.spec.mjs`: 5 passed, including Axe, focus, zoom, reduced motion, and chart/table parity | Automated |
| Performance and cache benchmarks | Passed local R11 evidence | `dashboard-performance.spec.mjs`: 5 passed; bounded All time, 100k virtualization, reload cache, append refresh | Automated |
| Production bundle and package assets | Passed local R11 evidence | `npm run dashboard:bundle-report`; initial JS 60.02 kB gzip and packaged React assets verified | Automated |
| Clean installed-wheel smoke | Passed local R11 evidence | `scripts/smoke_installed_package.py`; wheel `0.17.2`, 58 resources, React and rollback routes | Automated |
| Source-checkout launch smoke | Passed local R11 evidence | Real-data localhost run at port 4197 plus in-app browser interaction checks | Automated |
| Synthetic documentation screenshots | Passed local R11 evidence | `npm run dashboard:screenshots`; nine 1600x900 images mirrored into package docs | Automated |
| Dependency and security audit | Passed local R11 evidence | Agent Maintainer full run `20260711T162623133790Z-full-2a6457464d45` | Automated |
| Release-readiness and broad checks | Passed local R11 evidence | Agent Maintainer CI run `20260711T163951719550Z-ci-12c2c69f6cc1`; release and dist checks passed | Automated |
| Same-server legacy rollback rehearsal | Passed local R11 evidence | React and `/dashboard.html` returned HTTP 200; installed smoke compared React, root, and legacy assets | Automated |
| Installed-version rollback rehearsal | Passed local R11 evidence | Clean install of published `0.17.1`; version and `serve-dashboard` command verified | Automated |

## Maintainer Signoff Checklist

- [x] All R11 evidence rows are complete and link to synthetic, share-safe
  artifacts.
- [x] The parity ledger has no unexplained omission or unreviewed R11 gate.
- [x] Both source-checkout and installed-wheel launch paths were exercised.
- [x] `/react-dashboard.html`, `/dashboard.html`, and compatibility query links
  were exercised from the packaged candidate.
- [x] Same-server rollback was rehearsed without changing or losing local data.
- [x] The last-known-good package version was selected as `0.17.1`.
- [x] Package rollback was rehearsed in a clean environment.
- [x] The `/` route decision is recorded and matches code, tests, and docs.
- [x] Known limits are acceptable for the transition release and appear in the
  final release notes.
- [x] Accessibility, performance, security, and package results contain no
  invented or unrun outcomes.
- [x] Privacy review confirms that evidence and screenshots use synthetic data
  and expose no raw session content.
- [ ] R12 maintainer approval is recorded before merge or release work begins.
