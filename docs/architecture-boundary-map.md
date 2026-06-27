# Architecture Boundary Map

This branch introduces a local `tach` map for dependency visibility. It is not
yet a strict release gate.

## Local Commands

```bash
tach report src/codex_usage_tracker/usage_drain_reports.py --dependencies --usages
tach map -o /tmp/codex-usage-tracker-tach-map.json
tach check
```

`tach report` and `tach map` are expected to run locally. `tach check` currently
reports known boundary debt and should not be treated as a failed release gate
until the later `chore/tach-strict-local` branch.

## Intended Direction

The current map uses coarse file-level modules. The intended dependency
direction is:

1. `core`: shared models, schema, paths, formatting, privacy helpers.
2. `pricing`: pricing and allowance helpers, depending only on core.
3. `parsing`: JSONL parsing, diagnostic fact extraction, and explicit raw
   context loading.
4. `persistence`: SQLite schema, migrations, refresh cursors, query helpers,
   and thread summaries.
5. `reports`: application report assembly and stable JSON payloads.
6. `diagnostics`: diagnostic snapshots, usage-drain research reports, and
   related aggregate-only analysis.
7. `dashboard_api`: dashboard generation, localhost API, and HTTP helpers.
8. `adapters`: CLI, MCP, package entrypoint, and plugin installer wrappers.

Broadly, adapters may call inward; dashboard/API may call report,
diagnostic, persistence, parser, pricing, and core surfaces; diagnostic/report
layers may call lower layers; low-level modules should avoid reaching upward.

## Current Boundary Debt

As of this branch, `tach check` reports 13 import violations:

- `context.py` imports `store.query_usage_record`. This mixes explicit raw
  context loading with persistence read models. A later split should move the
  read-model access behind a small query facade or place context loading above
  persistence.
- `store.py` imports parser refresh functions and constants. This reflects the
  current refresh orchestration living inside persistence. A later split should
  isolate refresh orchestration from lower-level database modules.
- `store_sources.py` imports parser state helpers. This is related to the same
  refresh-state boundary and should move with the refresh orchestration split.
- `support.py` imports `diagnostics.run_doctor`. Support bundle assembly is
  currently reaching upward into runtime diagnostics; a later split should
  expose a smaller diagnostic summary contract or move support assembly into an
  adapter/report layer.

These are intentionally not fixed in this branch. They are candidates for the
upcoming parser/store/context branch sequence.
