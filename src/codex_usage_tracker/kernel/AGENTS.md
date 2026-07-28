# Frozen 0.28 Spike Instructions

This directory is the frozen 0.28 implementation spike. Read the repository
root `AGENTS.md` and `docs/INDEX.md` before working under this path; their
agent-first clean-cutover direction controls.

- Do not add product features, refactor this implementation, or use it as the
  owner of replacement behavior.
- New product work belongs under `src/codex_usage_tracker/agent_kernel/` and
  must follow the active CK task packet.
- Consult this directory only for an oracle or behavioral lesson explicitly
  named by an active packet. Do not import, copy, wrap, or open its databases
  from the replacement.
- Modify this directory only when the current task explicitly authorizes
  narrowly scoped safety or critical public-release maintenance before
  cutover. Preserve the shipped surface and prove the correction with
  synthetic tests.
- Do not restore reset-era K-number gates, removed planning frameworks, or
  obsolete execution ledgers.
