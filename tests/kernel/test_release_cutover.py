from __future__ import annotations

import json
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_AUDITED_MAIN = "d8da9bccdb6674e7dca4c0872c36a1346949dc13"
_QUALIFIED_INTEGRATION = "e5651313f3368836797279f40be8331103723995"
_CUTOVER_MERGE = "fb948d486b2c4c1205325f6a72789bdc0458d275"


def test_release_cutover_records_exact_qualified_topology() -> None:
    evidence = json.loads(
        (_ROOT / "config/kernel-release-cutover-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence == {
        "schema": "codex-usage-tracker.kernel-release-cutover.v1",
        "version": "0.26.0",
        "audited_main_sha": _AUDITED_MAIN,
        "qualified_integration_sha": _QUALIFIED_INTEGRATION,
        "cutover_merge_sha": _CUTOVER_MERGE,
        "main_delta_paths": [],
        "mainline_port_prs": [],
    }
    parents = subprocess.run(
        ["git", "show", "--no-patch", "--format=%P", _CUTOVER_MERGE],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().split()
    assert parents == [_AUDITED_MAIN, _QUALIFIED_INTEGRATION]
