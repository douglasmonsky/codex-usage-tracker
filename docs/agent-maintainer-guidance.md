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

## Dashboard Governance

The dashboard uses Agent Maintainer's explicit TypeScript provider for ESLint,
TypeScript, and Vitest. CI also runs repository-owned frontend architecture,
dead-code, Stylelint, bundle, and source-budget checks through:

```bash
npm run dashboard:governance
npm run dashboard:verify
```

Use the model-free named tasks when these gates would otherwise produce long
transcripts:

```bash
/Users/Monsky/.codex/bin/codex-task dashboard-governance --json
/Users/Monsky/.codex/bin/codex-task dashboard-verify --json
```

`.agent-maintainer/dashboard-source-baseline.json` lists only files that already
exceed the redesign budgets. `scripts/check_dashboard_source_budgets.py` blocks
new oversized files and any increase to an existing exception. When a refactor
shrinks or removes an exception, refresh the baseline in the same PR to lock in
the improvement:

```bash
python3 scripts/check_dashboard_source_budgets.py --write-baseline
python3 scripts/check_dashboard_source_budgets.py
```

Never refresh that baseline merely to permit file growth. TypeScript dependency
rules are owned by dependency-cruiser; Python dependency rules remain owned by
Tach. A boundary change requires the corresponding architecture decision to be
updated instead of weakening either tool.
