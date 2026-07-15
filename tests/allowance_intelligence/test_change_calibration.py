from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_change_detector_calibration_smoke_controls_false_positives() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "calibrate_allowance_change_detector.py"),
            "--simulations",
            "1000",
            "--seed",
            "20260715",
            "--permutations",
            "99",
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["simulations"] == 1000
    assert payload["familywise_alpha"] == 0.05
    assert set(payload["false_positives_by_family"]) == {
        "gaussian",
        "heteroskedastic",
        "outlier_contaminated",
        "skewed",
    }
    assert payload["wilson_upper_95"] <= 0.05
