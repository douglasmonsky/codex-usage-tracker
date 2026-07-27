from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY_PATH = _REPO_ROOT / "config" / "kernel-development-efficiency-v1.json"
_METRICS = {
    "contract_red_test_runs",
    "focused_test_runs",
    "broad_verification_runs",
    "duplicate_broad_runs",
    "blocking_gate_findings",
    "non_behavioral_gate_findings",
    "gate_remediation_lines",
    "verification_wall_seconds",
    "style_only_commits",
}


def test_development_efficiency_policy_is_decision_complete() -> None:
    payload = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))

    assert payload["schema"] == "codex-usage-tracker.kernel-development-efficiency.v1"
    assert payload["baseline_task"] == "K1"
    assert set(payload["metric_definitions"]) == _METRICS
    assert [task["task_id"] for task in payload["tasks"]] == [
        "K1",
        "K1A",
        "K2",
        "K3",
        "K4",
        "K5",
        "K6",
        "K7",
        "K8",
        "K9",
        "K10",
        "K11",
        "K12",
        "K13",
        "K14",
        "K15",
        "K16",
    ]
    assert all(task.keys() >= _METRICS for task in payload["tasks"])


def test_retired_churn_gates_have_named_replacements() -> None:
    payload = json.loads(_POLICY_PATH.read_text(encoding="utf-8"))
    actions = payload["retired_or_adjusted_gates"]

    assert actions
    for action in actions:
        assert action["action"] in {"retired", "adjusted"}
        assert action["replacement"]
