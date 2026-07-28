# Project map
- Authority starts at `docs/INDEX.md`; the only roadmap is `docs/roadmap/AGENT_FIRST_CLEAN_CUTOVER.md`.
- The replacement is built under `src/codex_usage_tracker/agent_kernel/`, one CK packet at a time.
- `src/codex_usage_tracker/kernel/` and the frontend are frozen 0.28 oracles until CK-14; do not extend or import them.
- Use deterministic synthetic fixtures only; never inspect or commit real Codex logs or raw user content.
- The replacement stores structural facts, not prompt, response, reasoning, command, patch, or tool-output bodies.
- Read `mem:tech_stack` for tooling, `mem:conventions` for code constraints, and `mem:task_completion` for gates.
