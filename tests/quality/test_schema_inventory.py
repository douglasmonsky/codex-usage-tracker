from __future__ import annotations

import re
from pathlib import Path

from codex_usage_tracker.core.json_contracts import known_json_schemas
from tests.release_catalog import RELEASE_SCHEMA_IDS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATTERN = re.compile(r"codex-usage-tracker(?:-[a-z0-9-]+-v[0-9]+|\.[a-z0-9-]+\.v[0-9]+)")


def test_runtime_schema_registry_matches_release_inventory() -> None:
    assert set(known_json_schemas()) == RELEASE_SCHEMA_IDS


def test_emitted_schemas_are_registered_documented_and_released() -> None:
    emitted: set[str] = set()
    runtime_roots = (
        REPO_ROOT / "src" / "codex_usage_tracker",
        REPO_ROOT / "frontend" / "dashboard" / "src",
    )
    for root in runtime_roots:
        for path in root.rglob("*"):
            if path.suffix in {".js", ".json", ".py", ".ts", ".tsx"}:
                emitted.update(SCHEMA_PATTERN.findall(path.read_text(encoding="utf-8")))

    documentation = "\n".join(
        (REPO_ROOT / path).read_text(encoding="utf-8")
        for path in ("docs/contracts.md", "docs/cli-json-schemas.md")
    )
    documented = set(SCHEMA_PATTERN.findall(documentation))

    assert emitted <= RELEASE_SCHEMA_IDS
    assert documented >= RELEASE_SCHEMA_IDS
