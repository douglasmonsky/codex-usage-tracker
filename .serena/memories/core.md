# Project map
- Python package: `src/codex_usage_tracker/`; CLI, parser, SQLite store, reports, localhost dashboard server, MCP/plugin assets.
- React dashboard: `frontend/dashboard/`; packaged assets are generated and should not be hand-edited.
- Synthetic tests: `tests/`; never commit real Codex logs or raw user content.
- Stable contracts include CLI/MCP JSON payloads, schema IDs, plugin names, and privacy behavior.
- Compression Lab work is specified in `docs/compression-lab-roadmap.md` and linked design/implementation plans.
- Read `mem:tech_stack` for tooling, `mem:conventions` for code constraints, and `mem:task_completion` for gates.