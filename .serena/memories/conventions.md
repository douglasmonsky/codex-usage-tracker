# Conventions
- Keep source files under 600 physical / 450 source lines; keep PRs at or below the configured file ceiling.
- Use typed immutable dataclasses for compression contracts; IDs derive deterministically from stable scope/evidence fields.
- Store adapters return plain mappings; domain modules own typed conversion.
- Detector claims must be component-bounded and never substitute whole-call totals for observed component evidence.
- Default MCP/API output remains aggregate-first and compact; raw excerpts require explicit local drilldown.
- Use Conventional Commit subjects and explicit staging; do not work directly on `main`.