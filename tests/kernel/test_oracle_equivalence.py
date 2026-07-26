from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "accounting-oracle-v1"
_ORACLE_PATH = _FIXTURE_ROOT / "expected.json"


def _oracle() -> dict[str, object]:
    assert _ORACLE_PATH.is_file(), "K1 accounting oracle is missing"
    return json.loads(_ORACLE_PATH.read_text(encoding="utf-8"))


def test_accounting_oracle_declares_every_frozen_semantic() -> None:
    oracle = _oracle()

    assert oracle["schema"] == "codex-usage-tracker.kernel-accounting-oracle.v1"
    assert oracle["fixture_version"] == 2
    assert oracle["source_ref"] == "v0.25.1"
    assert oracle["expected"].keys() >= {
        "physical_counts",
        "canonical_counts",
        "token_totals",
        "by_thread",
        "by_model_effort",
        "by_time",
        "canonical_identities",
        "canonical_promotion",
        "parentage",
        "delayed_parent_attachment",
        "allowance_observation_count",
        "allowance_selection",
        "diagnostic_facts",
        "parser_diagnostics",
        "privacy",
    }
    assert oracle["expected"]["token_totals"].keys() == {
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    }
    assert oracle["expected"]["canonical_promotion"] == {
        "active_original_is_canonical": True,
        "archived_copy_is_duplicate": True,
    }
    assert oracle["expected"]["allowance_observation_count"] > len(
        oracle["expected"]["allowance_selection"]
    )
    assert len(oracle["expected"]["by_time"]) >= 2


def test_current_runtime_reproduces_accounting_oracle(tmp_path: Path) -> None:
    oracle = _oracle()
    from tests.kernel.oracle_support import export_accounting_oracle

    observed = export_accounting_oracle(
        fixture_root=_FIXTURE_ROOT,
        workspace=tmp_path,
    )

    assert observed == oracle["expected"]


def test_oracle_fixture_is_complete_and_repository_relative() -> None:
    oracle = _oracle()
    source_files = oracle["source_files"]

    assert isinstance(source_files, list)
    assert source_files
    for relative in source_files:
        assert isinstance(relative, str)
        assert not Path(relative).is_absolute()
        assert (_FIXTURE_ROOT / relative).is_file()
        assert (_FIXTURE_ROOT / relative).is_relative_to(_REPO_ROOT)
