# Dashboard Final Redesign Release-Candidate Guide

This guide defines the migration, default-launch, rollback, and maintainer
signoff contract for R11 of the dashboard redesign. It tracks issue #201 from
base commit `88ebcd80d08c1eb2229d9c7e929849e328af4097`.

## Status And Decision Boundary

The statements below use these labels:

- **Verified at the R11 base** means the behavior is present in current code,
  documentation, or focused compatibility tests.
- **Pending R11 evidence** means the behavior must not be treated as release
  proof until the named release-candidate check is run and recorded.
- **Open decision** means maintainer approval is required; this guide does not
  guess or silently change the behavior.

No accessibility, performance, package-install, or broad release check is
claimed by this document.

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

**Pending R11 evidence:** repeat these steps against the built wheel in a clean
environment and record the wheel version, Python version, operating system,
asset responses, and smoke-check result in the evidence table below.

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

**Pending R11 evidence:** record a clean source-checkout launch separately from
the installed-wheel launch. A passing source launch is not package evidence.

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
| `/` | Serves the legacy dashboard shell | Keep unchanged unless the open decision below is approved |
| `open-dashboard` | Opens a generated static legacy file | Keep unchanged for static snapshots |

Do not delete the legacy assets, redirect `/dashboard.html`, or redefine the
static command during R11. Those changes would remove the same-server rollback
surface and require a separate reviewed decision.

**Open decision:** should `/` remain a legacy entry point for the transition
release, or redirect to `/react-dashboard.html`? Current code serves the legacy
shell at `/`. R11 can ship without changing it because the CLI already opens
the React route explicitly. Record the maintainer decision before R12; do not
describe a root-route switch as complete unless code, tests, and this guide are
updated together.

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
   pipx install --force "codex-usage-tracking==<last-known-good-version>"
   codex-usage-tracker setup
   codex-usage-tracker doctor
   codex-usage-tracker serve-dashboard --open
   ```

3. Open the printed `legacy_dashboard_url` if the last-known-good package still
   prefers the React route.
4. Record the exact package version and result without publishing local paths
   or private usage data.

**Open decision:** replace `<last-known-good-version>` with an approved released
version before publishing release notes. The R11 base does not identify that
release, so this guide does not invent one.

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

## Known Limits At Release-Candidate Draft

- Full route/viewport automation, axe, keyboard, focus, 200% zoom, reduced
  motion, contrast, containment, and chart/table-equivalence evidence is
  pending R11.
- Startup, 5k-row, no-cap, 100k-synthetic-row, reload, cache-hit, and
  single-appended-record performance evidence is pending R11.
- Query-cache reuse exists, but benchmark and invalidation evidence is pending
  R11.
- Built-wheel assets and clean installed-package launch behavior remain pending
  R11 package verification.
- Static packaged workspaces retain fixture fallback; static mode does not
  provide the live refresh and lazy-context workflow.
- Settings reports authoritative local state but does not add writable pricing,
  allowance, privacy, or parser configuration controls.
- SVG and PNG output from MCP visualization tools remains deliberately deferred;
  semantic visualization specifications remain the supported contract.
- The final merge, root-route decision, release version, and package rollback
  version require maintainer review. This draft does not authorize publishing.

## R11 Evidence Record

Fill this table with links or artifact identifiers from synthetic-data checks.
Do not paste raw logs or real user data into this document.

| Evidence gate | Status | Artifact or result | Reviewer |
| --- | --- | --- | --- |
| Route and viewport matrix | Pending R11 evidence | `<artifact>` | `<name>` |
| Accessibility and keyboard matrix | Pending R11 evidence | `<artifact>` | `<name>` |
| Performance and cache benchmarks | Pending R11 evidence | `<artifact>` | `<name>` |
| Production bundle and package assets | Pending R11 evidence | `<artifact>` | `<name>` |
| Clean installed-wheel smoke | Pending R11 evidence | `<artifact>` | `<name>` |
| Source-checkout launch smoke | Pending R11 evidence | `<artifact>` | `<name>` |
| Synthetic documentation screenshots | Pending R11 evidence | `<artifact>` | `<name>` |
| Dependency and security audit | Pending R11 evidence | `<artifact>` | `<name>` |
| Release-readiness and broad checks | Pending R11 evidence | `<artifact>` | `<name>` |
| Same-server legacy rollback rehearsal | Pending R11 evidence | `<artifact>` | `<name>` |
| Installed-version rollback rehearsal | Pending R11 evidence | `<artifact>` | `<name>` |

## Maintainer Signoff Checklist

- [ ] All R11 evidence rows are complete and link to synthetic, share-safe
  artifacts.
- [ ] The parity ledger has no unexplained omission or unreviewed R11 gate.
- [ ] Both source-checkout and installed-wheel launch paths were exercised.
- [ ] `/react-dashboard.html`, `/dashboard.html`, and compatibility query links
  were exercised from the packaged candidate.
- [ ] Same-server rollback was rehearsed without changing or losing local data.
- [ ] The last-known-good package version was selected and package rollback was
  rehearsed in a clean environment.
- [ ] The `/` route decision is recorded and matches code, tests, and docs.
- [ ] Known limits are acceptable for the transition release and appear in the
  final release notes.
- [ ] Accessibility, performance, security, and package results contain no
  invented or unrun outcomes.
- [ ] Privacy review confirms that evidence and screenshots use synthetic data
  and expose no raw session content.
- [ ] R12 maintainer approval is recorded before merge or release work begins.
