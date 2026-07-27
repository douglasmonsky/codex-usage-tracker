# Codex Usage Tracker

Codex Usage Tracker is a fast, local-first data kernel for exact Codex usage
facts and evidence. Version 0.26 replaces the experimental analysis product
with incremental ingestion, bounded queries, exact evidence timelines, a
six-tool MCP surface, and a focused Evidence Console.

- Product roadmap: `docs/roadmap/product-kernel-reset.md`
- Execution ledger: `docs/roadmap/product-kernel-reset-execution.md`
- Active search policy: `docs/kernel-development-scope.md`
- Frozen code disposition: `config/kernel-code-disposition-v1.json`
- Frozen retired surfaces: `config/kernel-retired-surfaces-v1.json`

Run the repository verification gate with:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
just v
```

The previous 0.25.1 implementation remains available at the immutable
`v0.25.1` tag. Do not restore retired analysis, telemetry, compatibility, or
static-dashboard runtime modules into the active tree.

## Install

Install the Python runtime into an isolated executable environment, then add
the same tagged repository as a Codex plugin marketplace:

```bash
pipx install "codex-usage-tracking==0.26.0"
codex plugin marketplace add douglasmonsky/codex-usage-tracker --ref v0.26.0
codex plugin add codex-usage-tracker@codex-usage-tracker
```

The plugin launches the `codex-usage-tracker` executable, so the MCP process
uses the exact interpreter owned by the pipx installation. After install,
start a fresh Codex task so its tool catalog is discovered from the new
plugin bundle.
