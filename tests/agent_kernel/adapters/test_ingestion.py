from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl import parser
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.discovery import (
    discover_inventory,
    select_sources,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch

ROOT = Path(__file__).parents[1] / "fixtures" / "tiny-v1"
MANIFEST = ROOT / "manifest.json"


def _signature(result):
    return tuple(
        (
            observation.observation_type,
            observation.logical_id,
            observation.occurrence_id,
            observation.sort_key,
        )
        for observation in result.changes.observations
    )


def test_full_synthetic_ingestion_matches_ck03_accounting_and_has_no_bodies() -> None:
    result = ingest(ROOT, manifest=MANIFEST, workers=1, batch_size=32)
    assert result.metrics.sources_considered == 12
    assert result.metrics.sources_selected == 11
    assert result.metrics.sources_deferred == 1
    assert result.metrics.source_bytes_selected == 244657
    assert result.metrics.records_seen == 339
    assert result.metrics.diagnostics_emitted == 1
    assert result.changes.accounting.canonical_counts == {
        "activities": 5,
        "allowance_observations": 4,
        "allowance_limits": 1,
        "compaction_boundaries": 2,
        "model_calls": 100,
        "projects": 1,
        "resources": 25,
        "sessions": 10,
        "state_changes": 5,
        "tool_invocations": 25,
        "turns": 50,
    }
    assert result.changes.accounting.occurrence_counts["model_calls"] == 102
    assert result.changes.accounting.token_sums["uncached_input_tokens"].value == 53650
    assert result.changes.accounting.token_sums["cached_input_tokens"].value is None
    assert result.changes.accounting.token_sums["cached_input_tokens"].missing_count == 5
    assert result.changes.accounting.token_sums["reasoning_tokens"].value == 31850
    assert result.changes.accounting.token_sums["output_tokens"].value == 47450
    assert len({item.occurrence_id for item in result.changes.occurrences}) == len(result.changes.occurrences)
    forbidden = {"body", "command", "content", "diff", "patch", "prompt", "reasoning", "response", "stderr", "stdout", "tool_output"}
    assert all(str(key).lower() not in forbidden for item in result.changes.observations for key in item.payload)


def test_parallel_worker_counts_are_deterministic_and_bounded() -> None:
    baseline = ingest(ROOT, manifest=MANIFEST, workers=1, batch_size=32)
    for workers in (2, 4, 8):
        result = ingest(ROOT, manifest=MANIFEST, workers=workers, batch_size=32)
        assert _signature(result) == _signature(baseline)
        assert result.changes.accounting == baseline.changes.accounting
        assert result.metrics.max_queue_depth > 0


def test_named_history_windows_match_fixture_call_counts_and_coverage() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {
        "30_days": (4, 184519),
        "90_days": (10, 184519),
        "one_year": (34, 214584),
        "all_time": (100, 244657),
    }
    for name, (expected_calls, expected_bytes) in expected.items():
        window = manifest["history"]["windows"][name]
        result = ingest(
            ROOT,
            manifest=MANIFEST,
            window=(window["start_us"], window["end_us"]),
            workers=4,
            batch_size=32,
        )
        assert result.metrics.source_bytes_selected == expected_bytes
        assert result.changes.accounting.canonical_counts.get("model_calls", 0) == expected_calls


def test_ck02_identity_derivation_is_executable_for_emitted_observations() -> None:
    from codex_usage_tracker.agent_kernel.domain.identity import semantic_id

    result = ingest(ROOT, manifest=MANIFEST, workers=1, batch_size=32)
    kinds = {
        "ProjectObserved": "project",
        "SessionObserved": "session",
        "TurnBoundaryObserved": "turn",
        "ModelCallObserved": "call",
        "ToolLifecycleObserved": "tool",
        "ActivityLifecycleObserved": "activity",
        "CompactionObserved": "compaction",
        "StateChangeObserved": "state-change",
        "ResourceObserved": "resource",
    }
    for observation in result.changes.observations:
        kind = kinds.get(observation.observation_type)
        if kind is not None:
            assert observation.logical_id == semantic_id(kind, observation.identity_tuple)
    assert all(item.occurrence_id.startswith("source-occurrence:v1:") for item in result.changes.occurrences)


def test_malformed_records_flush_in_bounded_batches(tmp_path: Path) -> None:
    source = tmp_path / "malformed.jsonl"
    source.write_bytes(b"not-json\n" * 65)
    result = ingest(tmp_path, workers=1, batch_size=16)
    assert result.metrics.records_seen == 65
    assert result.metrics.diagnostics_emitted == 65
    assert result.metrics.batches_emitted >= 5


def test_worker_failure_emits_the_next_terminal_batch_without_deadlock(monkeypatch) -> None:
    plans = select_sources(discover_inventory(ROOT, manifest=MANIFEST), max_bytes=1 << 40)
    selected = tuple(plan for plan in plans if plan.inventory.selected)[:1]

    def fail_after_one(*args, **kwargs):
        plan = args[0]
        yield ParseBatch(
            source_rank=plan.inventory.source_rank,
            batch_index=0,
            observations=(),
            diagnostics=(),
            records_seen=1,
            complete_end=1,
            latest_source_order=0,
            done=False,
        )
        raise RuntimeError("synthetic worker failure")

    monkeypatch.setattr(parser, "iter_source_batches", fail_after_one)
    batches = list(parser.parse_sources(selected, workers=2, batch_size=1))
    assert [batch.batch_index for batch in batches] == [0, 1]
    assert batches[-1].done is True
    assert batches[-1].diagnostics[0].code == "worker_failure"
