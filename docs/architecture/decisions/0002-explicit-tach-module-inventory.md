# Explicit Tach Module Inventory

Tach is part of the Agent Maintainer hardening profile, but the root
`tach.toml` previously did not enumerate source modules. That made the
architecture check too vague: Tach could run, but the verifier could not trust
it as an explicit package-boundary contract.

The root Tach config now lists each non-`__init__` Python source module under
`src/codex_usage_tracker` as an explicit module. This is intentionally a
baseline inventory, not a claim that all dependency edges are already healthy.

Existing `tach.domain.toml` files remain the local domain-ownership notes. The
new root module inventory gives the verifier a concrete module set so later PRs
can address actual `tach` dependency violations incrementally instead of first
failing on missing configuration.

Follow-up work should add or reduce dependency edges in focused PRs. This
decision does not enable circular dependency blocking or resolve existing
architecture drift by itself.
