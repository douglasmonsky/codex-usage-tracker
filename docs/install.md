# Install Guide

## Recommended Install

Use `pipx` so the tracker is installed from PyPI as a command-line app without mixing dependencies into another project.

```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install codex-usage-tracking
codex-usage-tracker setup
codex-usage-tracker serve-dashboard --open
```

Use the Python launcher that is normal for your platform:

- macOS/Linux: `python3` may be the right command instead of `python`.
- Windows: `py -m pip install --user pipx`, `py -m pipx ensurepath`, and `pipx install ...` after opening a fresh terminal.
- macOS with Homebrew: `brew install pipx` is a convenient alternative to `python -m pip install --user pipx`.

If `codex-usage-tracker` is not found immediately after `ensurepath`, open a new terminal or add the printed pipx binary directory to `PATH`.

Package naming: the public PyPI distribution is [`codex-usage-tracking`](https://pypi.org/project/codex-usage-tracking/); the installed command is `codex-usage-tracker`; the GitHub repository remains `douglasmonsky/codex-usage-tracker`. The `codex-usage-tracker` PyPI name is not this project, so avoid similarly named packages when following these docs.

`setup` installs or refreshes the package-owned plugin wrapper, including MCP tools and companion Codex skills, initializes local config templates when needed, refreshes the aggregate index, runs `doctor`, prints a success/failure summary, and tells you whether Codex needs a restart for plugin discovery.

Restart Codex after plugin registration if you want Codex to discover the MCP tools in a fresh session. The localhost dashboard can run immediately.

`serve-dashboard` and `open-dashboard` refresh active-session usage before opening by default. Add `--no-refresh` only when you intentionally want to inspect the cached local index without scanning logs first.

## Platform Support

The CLI, SQLite index, dashboard generator, and localhost server are Python-based and are not macOS-only. CI runs the package on Ubuntu with Python 3.10, 3.11, 3.12, 3.13, and 3.14.

The installed-package Docker smoke path uses `python:3.14-slim` by default, which exercises the built wheel, package data, CLI entry point, and plugin installer on the newest supported runtime.

By default the tracker looks for Codex JSONL logs under `~/.codex`, stores its own database/config under `~/.codex-usage-tracker`, and writes the local plugin wrapper under `~/plugins/codex-usage-tracker`. Override paths with `--codex-home`, `--db`, `--plugin-dir`, or `--marketplace` if your platform or Codex installation uses a different layout.

Windows support should work for the core dashboard/CLI when Codex writes readable JSONL logs, but plugin discovery is tied to Codex's local plugin directory behavior. Run `codex-usage-tracker doctor --suggest-repair` after setup if Codex does not show the plugin.

Plugin discovery limitations are separate from core Python CLI/dashboard support. If Codex cannot discover the local plugin wrapper, the installed command, SQLite index, generated dashboard, localhost server, and CLI JSON reports can still work.

## Upgrade

```bash
pipx upgrade codex-usage-tracking
codex-usage-tracker setup
```

For source installs used during development or branch testing, rerun the GitHub install with `--force`:

```bash
pipx install --force "git+https://github.com/douglasmonsky/codex-usage-tracker.git"
codex-usage-tracker setup
```

## Codex-Assisted Install

Open a Codex session on your machine and paste:

```text
Install and configure Codex Usage Tracker.
Install the PyPI distribution codex-usage-tracking with pipx. The installed command should be codex-usage-tracker. Use pipx install "git+https://github.com/douglasmonsky/codex-usage-tracker.git" only for branch testing or if PyPI is temporarily unavailable.
If pipx is missing, install it with the platform's Python launcher or use a local virtual environment.
After installation, run codex-usage-tracker setup and serve-dashboard --open.
Verify the dashboard opens locally and tell me the dashboard URL plus whether I need to restart Codex for plugin discovery.
```

Codex should run roughly the same shell commands as the recommended install. This path is useful if you want Codex to verify the dashboard URL and plugin discovery state for you.

After Codex discovers the plugin, you can ask usage questions directly in a Codex session. The `codex-usage-api` companion skill guides Codex to refresh the aggregate index, query stable local JSON/MCP outputs, and explain usage patterns without storing prompts or raw transcript text. See [MCP And Codex Skills](mcp.md) for example prompts.

## Source Checkout

```bash
git clone https://github.com/douglasmonsky/codex-usage-tracker.git
cd codex-usage-tracker
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install ".[dev]"
codex-usage-tracker install-plugin --python .venv/bin/python
```

Use the source checkout when developing the project or testing a branch locally.

## Plugin Registration

After installing the Python package, register the local Codex plugin:

```bash
codex-usage-tracker install-plugin
```

For a source checkout that should use the repo-local virtual environment:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python
```

When the selected Python is a repo-local virtual environment, the generated MCP config includes a `PYTHONPATH` pointing at that checkout's `src` directory. That keeps source-checkout plugin installs working even before an editable install. `doctor --suggest-repair` validates that the configured MCP Python can import the server.

If you previously installed the older source-checkout symlink, replace it once:

```bash
codex-usage-tracker install-plugin --python .venv/bin/python --force
```

`install-plugin` creates `~/plugins/codex-usage-tracker`, writes a package-owned `.mcp.json` that points at the installed Python executable, and updates `~/.agents/plugins/marketplace.json`.

## Local Dashboard

Generate a static dashboard:

```bash
codex-usage-tracker open-dashboard
codex-usage-tracker open-dashboard --no-refresh
```

Serve the dashboard with live aggregate refresh and lazy context loading:

```bash
codex-usage-tracker serve-dashboard --open
codex-usage-tracker serve-dashboard --no-context-api --open
```

The server binds to localhost, requires a per-server token for refresh/context endpoints, and rejects non-loopback `Host` or cross-origin `Origin` headers.
`--no-context-api` starts context loading off; the details panel can enable it later without restarting the server.

`open-dashboard` and `serve-dashboard` refresh active-session logs before opening by default. The lower-level `dashboard --open` command writes from the current SQLite index when you need a fully static file-generation step.

## Setup Checks

```bash
codex-usage-tracker doctor
codex-usage-tracker doctor --suggest-repair
codex-usage-tracker --version
python -m codex_usage_tracker --version
```

`doctor` is read-only. `doctor --suggest-repair` explains likely follow-up commands without making changes.

## Lifecycle Commands

```bash
codex-usage-tracker setup
codex-usage-tracker upgrade-plugin
codex-usage-tracker uninstall-plugin
codex-usage-tracker reset-db --yes
codex-usage-tracker --privacy-mode strict support-bundle --output ~/.codex-usage-tracker/support-bundle.json
```

`support-bundle` writes package, Python, OS/platform, doctor status, database schema, parser diagnostics, pricing status, allowance status, threshold status, project config status, and privacy metadata. It does not include raw logs, prompts, assistant messages, tool output, context text, or aggregate rows.

Default `support-bundle` mode keeps local diagnostic paths because they can help troubleshoot setup on your machine. Use `--privacy-mode strict` before sharing: strict mode redacts local diagnostic path strings in the bundle and doctor details while preserving existence flags, counts, parser diagnostics, and status fields.
