# Agent Maintainer Hardening Branch Roadmap

Branch: `refactor/secret-scan-hardening`

## Goal

Adopt the latest Agent Maintainer ratchet and a small set of low-noise hardening
checks without mixing in broad Python refactors or large documentation cleanup.

## Completed Chunks

- Upgrade generated Agent Maintainer guidance and add local `just` wrappers.
- Add a latest-main ratchet baseline for existing file-length and structure debt.
- Enable configured `gitleaks` secret scanning with allowlists for ignored local
  artifacts and intentional fake-secret fixtures.
- Fix the publish workflow glob flagged by `actionlint`.
- Format TOML configuration with Taplo.
- Enable repo-configured `yamllint`.

## Finish On This Branch

- Enable Taplo as an Agent Maintainer gate now that TOML is formatted.
- Enable GitHub workflow schema validation with explicit `check-jsonschema`
  arguments.
- Re-run focused validation for the newly enabled gates.

## Follow-Up PRs

- Markdown linting: needs a dedicated docs cleanup because the current repo has
  hundreds of historical spacing and inline-HTML findings.
- pip-audit: needs a pinned dependency input or lock/constraints strategy before
  it can be enabled safely.
- Bandit: needs triage for SQL construction warnings and false-positive string
  literals before blocking.
- Zizmor: needs a repo-specific invocation/config pass before it gives useful
  results.
- Large Python refactors: use `agent_maintainer ratchet next` plus the raw
  baseline to split oversized modules such as `reports/api.py`,
  `store/content_index.py`, and `cli/mcp_server.py`.

## Validation

- `python3 scripts/check_release.py`
- `git diff --check`
- `python -m agent_maintainer guidance --check`
- Focused direct checks for each enabled optional gate.
