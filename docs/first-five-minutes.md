# First Five Minutes

This is the shortest path from a fresh machine to a working local dashboard.

## 1. Install

Use `pipx` so the tracker runs as its own command-line app:

```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install codex-usage-tracking
```

Use `python3` on macOS/Linux if that is your normal launcher. On Windows, `py -m pip install --user pipx` and `py -m pipx ensurepath` may be the right form. If `codex-usage-tracker` is not found after install, open a new terminal or add the path printed by `pipx ensurepath`.

## 2. Set Up

```bash
codex-usage-tracker setup
```

`setup` installs the local Codex plugin wrapper, initializes local config templates, refreshes the aggregate SQLite index from local Codex logs, and runs `doctor`. Restart Codex after setup if you want the companion MCP tools and skills to appear in new Codex sessions.

## 3. Launch

```bash
codex-usage-tracker serve-dashboard --open
```

This starts a localhost dashboard and refreshes active-session usage first. Keep the terminal running while using the live dashboard.

## 4. Verify

The first healthy state usually looks like this:

- Browser opens a `127.0.0.1` dashboard URL.
- The top badge says `Live`, not only `Static`.
- `Visible Calls` is greater than zero if local Codex logs exist.
- `doctor` does not report a `fail` status:

```bash
codex-usage-tracker doctor --suggest-repair
```

## If The Dashboard Is Empty

Run these checks in order:

```bash
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker refresh
codex-usage-tracker serve-dashboard --open --refresh
```

Common causes:

- No local Codex logs exist yet on that machine.
- Codex logs are somewhere other than `~/.codex`; use `--codex-home <path>` with `setup`, `refresh`, or `serve-dashboard`.
- You are looking only at active sessions while the data is archived; use the dashboard `History` selector or run with `--include-archived`.
- Browser cached an old static file; reload the `serve-dashboard` URL.
- On Windows, use a recent version if JavaScript files fail to load. Older releases could inherit a `.js` MIME type from the Windows registry.

## If The Plugin Does Not Show In Codex

The dashboard can work even when plugin discovery is not active. For plugin discovery:

```bash
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker install-plugin
```

Then restart Codex and start a fresh Codex session.

A healthy local installation or dashboard service does not prove that the current
Codex task loaded MCP tools. Check the tools exposed to the current task. When an MCP
result includes a dashboard evidence target, open its absolute localhost URL when
present; otherwise use the relative target only after following its launch guidance
(`codex-usage-tracker serve-dashboard --open`).

## What To Attach To Issues

For public GitHub issues, prefer a strict support bundle:

```bash
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

Review the JSON before posting it. The bundle's `issue_report.safe_fields` lists the safest fields to paste. Do not add raw Codex JSONL logs, prompts, assistant messages, tool output, command text, patch text, full local paths, secrets, credentials, or private config values.

## Next Useful Commands

```bash
codex-usage-tracker summary --preset last-7-days
codex-usage-tracker query --min-tokens 100000
codex-usage-tracker diagnostics overview --refresh
```

For deeper details, see the [Install Guide](install.md), [Dashboard Guide](dashboard-guide.md), and [CLI Reference](cli-reference.md).
