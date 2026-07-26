# Codex Usage Tracker — Kernel Integration

This branch is the deliberately incomplete, non-publishable 0.26 Product
Kernel Reset workspace. It is not the released 0.25 product and must not be
installed as a plugin or MCP server.

Active development is limited to the lean data kernel, synthetic accounting
oracle, release-safety infrastructure, and the task-specific paths named in
the reset roadmap.

- Product roadmap: `docs/roadmap/product-kernel-reset.md`
- Execution ledger: `docs/roadmap/product-kernel-reset-execution.md`
- Active search policy: `docs/kernel-development-scope.md`
- Frozen code disposition: `config/kernel-code-disposition-v1.json`
- Frozen retired surfaces: `config/kernel-retired-surfaces-v1.json`

Run the current phase gate with:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
just v
```

The public 0.25.1 implementation remains available at the immutable
`v0.25.1` tag. Do not restore legacy runtime modules into this integration
tree; transplant only the bounded behavior owned by the active kernel task.
