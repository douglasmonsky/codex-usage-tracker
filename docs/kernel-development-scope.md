# Kernel Development Scope

The active 0.26 integration tree is deliberately incomplete and
non-publishable. It contains only K1 `keep` paths, the small kernel skeleton,
and files explicitly introduced by the active reset task.

## Active search boundary

For K2-K9, begin every search in:

- `src/codex_usage_tracker/kernel/`;
- `tests/kernel/`; and
- the task's declared path allowlist.

Do not add the detached `v0.25.1` reference worktree to Serena, IntelliJ,
GitNexus, workspace search, test discovery, packaging, or generated output.
When an owned transplant needs historical behavior, inspect only the exact
`source_ref` recorded in `config/kernel-code-disposition-v1.json`, preferably
with `git show v0.25.1:<path>`.

## Forbidden patterns

- imports from removed 0.25 modules;
- compatibility namespaces or forwarding adapters;
- a publishable version or release artifact from integration/K1A-K9 refs;
- live or private usage fixtures;
- database or generated output inside the reference worktree; and
- unclassified files outside the active task allowlist.

Run `python scripts/check_kernel_scope.py` before every integration commit.
The detached reference and integration worktrees remain until the maintainer
explicitly authorizes deletion.
