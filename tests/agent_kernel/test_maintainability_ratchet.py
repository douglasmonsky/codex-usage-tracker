import hashlib
import json
import sys

import pytest

import scripts.check_kernel_maintainability as checker
from scripts.check_kernel_maintainability import (
    DEFAULT_BASELINE,
    maintainability_failures,
    normalized_findings,
)


def code(size):
    body = "".join(f"    if x.get({n}):\n        y += {n}\n" for n in range(size))
    return f"def choose(x):\n    y = 0\n{body}    return y\n"


def test_normalized_maintainability_ratchet(tmp_path, monkeypatch) -> None:
    baseline = json.loads(DEFAULT_BASELINE.read_text())
    assert baseline["dependency_sha"] == "306cef37eea2ae017aca824d898cc435f7e1bea0"
    assert baseline["tool_identity"] == "xenon==0.9.3;radon==6.0.1"
    assert baseline["scope_ownership"]["source_root"].endswith("agent_kernel")
    assert not maintainability_failures()
    source = tmp_path / "agent_kernel"
    source.mkdir()
    module = source / "sample.py"
    module.write_text(code(24))
    baseline["baseline_findings"] = normalized_findings(source)
    previous = baseline["baseline_findings"]
    monkeypatch.setattr(checker, "_previous_findings", lambda _: previous)
    saved = tmp_path / "baseline.json"
    saved.write_text(json.dumps(baseline))
    assert not maintainability_failures(source, baseline_path=saved)
    baseline["dependency_sha"] = "0" * 40
    saved.write_text(json.dumps(baseline))
    assert maintainability_failures(source, baseline_path=saved)
    baseline["dependency_sha"] = "306cef37eea2ae017aca824d898cc435f7e1bea0"
    saved.write_text(json.dumps(baseline))
    before = normalized_findings(source)
    module.write_text("\n\n" + code(24))
    assert normalized_findings(source) == before
    module.write_text(code(25))
    assert maintainability_failures(source, baseline_path=saved)
    baseline["baseline_findings"] = normalized_findings(source)
    saved.write_text(json.dumps(baseline))
    assert maintainability_failures(source, baseline_path=saved)

    module.write_text(code(12))
    baseline["baseline_findings"] = normalized_findings(source)
    saved.write_text(json.dumps(baseline))
    assert not maintainability_failures(source, baseline_path=saved)

    (source / "new.py").write_text(code(24))
    baseline["baseline_findings"] = normalized_findings(source)
    saved.write_text(json.dumps(baseline))
    assert maintainability_failures(source, baseline_path=saved)


def test_installed_baseline_rejects_byte_different_serialization(tmp_path, monkeypatch) -> None:
    saved = tmp_path / "baseline.json"
    saved.write_bytes(DEFAULT_BASELINE.read_bytes())
    monkeypatch.setattr(checker, "DEFAULT_BASELINE", saved)
    assert hashlib.sha256(DEFAULT_BASELINE.read_bytes()).hexdigest() == (
        checker._EXPECTED_BASELINE_SHA256
    )
    assert not maintainability_failures(baseline_path=saved)
    saved.write_text(json.dumps(json.loads(saved.read_text())))
    assert maintainability_failures(baseline_path=saved) == ["baseline"]


def test_duplicate_normalized_identity_fails_closed(tmp_path, monkeypatch) -> None:
    source = tmp_path / "agent_kernel"
    source.mkdir()
    (source / "sample.py").write_text(code(24) + "\n" + code(24))
    baseline = json.loads(DEFAULT_BASELINE.read_text())
    baseline["baseline_findings"] = normalized_findings(source)
    saved = tmp_path / "baseline.json"
    saved.write_text(json.dumps(baseline))
    monkeypatch.setattr(checker, "_previous_findings", lambda _: baseline["baseline_findings"])
    findings = normalized_findings(source)
    assert len([item for item in findings if item["id"] == "sample.py:choose"]) == 2
    assert maintainability_failures(source, baseline_path=saved) == ["baseline"]


def test_frozen_spike_and_cli_fail_closed(tmp_path, monkeypatch) -> None:
    spike = tmp_path / "kernel"
    spike.mkdir()
    (spike / "regression.py").write_text(code(24))
    monkeypatch.setattr(checker, "SPIKE_ROOT", spike)
    assert maintainability_failures()
    monkeypatch.setattr(sys, "argv", ["checker", "--unexpected"])
    with pytest.raises(SystemExit):
        checker.main()
