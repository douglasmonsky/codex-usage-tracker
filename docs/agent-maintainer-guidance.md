# Agent Maintainer Guidance

`AGENTS.agent-maintainer.md` is generated from `[tool.agent_maintainer]` in
`pyproject.toml` by:

```bash
python3 -m agent_maintainer guidance
```

Do not edit the generated sidecar by hand. Update configuration or the upstream
renderer, regenerate it, and verify with:

```bash
python3 -m agent_maintainer guidance --check
```

This repo uses `legacy-ratchet` mode. Existing oversized files and structure
warnings are tracked in `.agent-maintainer/ratchet-baseline.json` so future work
can fail on regressions while refactor PRs reduce the baseline over time.

The first aggressive refactor targets should be the largest source files named
by:

```bash
python3 -m agent_maintainer ratchet next --limit 20
```

Use the `justfile` aliases in this repo for common verification commands:

```bash
just vp
just v
just vc
just doctor
```
