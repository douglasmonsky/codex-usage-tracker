# Completion gates
- Run focused tests first, then all tests for touched domains.
- Run Ruff check and format check, Pyright/Mypy as configured, Xenon, Tach, release sanity, and `git diff --check`.
- For public contract, schema, plugin, dashboard, or packaging changes, run the repository full CI/Agent Maintainer gate and package build/smoke checks.
- Review `git status`, diff stat, actual diff, and staged files for private data before committing.
- Push feature branch, open PR, wait for required checks, and squash merge ordinary feature PRs.