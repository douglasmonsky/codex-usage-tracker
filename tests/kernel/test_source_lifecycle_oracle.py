from __future__ import annotations

import json
from pathlib import Path

_FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "accounting-oracle-v1"
_LIFECYCLE_PATH = _FIXTURE_ROOT / "source-lifecycle.json"


def _lifecycle() -> dict[str, object]:
    assert _LIFECYCLE_PATH.is_file(), "K1 source-lifecycle oracle is missing"
    return json.loads(_LIFECYCLE_PATH.read_text(encoding="utf-8"))


def test_source_lifecycle_oracle_names_every_required_state() -> None:
    lifecycle = _lifecycle()

    assert lifecycle["schema"] == "codex-usage-tracker.kernel-source-lifecycle.v1"
    assert [case["name"] for case in lifecycle["cases"]] == [
        "new",
        "appended",
        "partially_appended",
        "replaced",
        "truncated",
        "archived",
        "restored",
    ]


def test_current_source_planner_reproduces_lifecycle_oracle(tmp_path: Path) -> None:
    lifecycle = _lifecycle()
    from tests.kernel.test_ingest_lifecycle import export_source_lifecycle_oracle

    observed = export_source_lifecycle_oracle(workspace=tmp_path)

    assert observed == lifecycle["expected"]
