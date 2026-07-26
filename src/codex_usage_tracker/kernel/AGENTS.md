# Kernel Development Instructions

Work only in `src/codex_usage_tracker/kernel`, `tests/kernel`, and the active
task's explicit allowlist.

- Start from a synthetic oracle or failing contract test.
- Do not import from a retired, historical, or removed transplant path.
- Read old implementation only through one manifest-approved
  `v0.25.1:<path>` source reference.
- Implement the smallest direct kernel owner; do not add compatibility shims,
  re-export packages, server-authored narrative analysis, OTel, or default
  content indexing.
- Keep normalized facts free of prompts, reasoning text, raw tool arguments,
  raw tool output, shell bodies, secrets, and full local paths.
- Preserve the integration publication guard through K9.
- Update disposition state, oracle evidence, performance, churn metrics, and
  the execution ledger in the owning task.
