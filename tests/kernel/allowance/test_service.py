from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)
from codex_usage_tracker.kernel.schema import SCHEMA_VERSION

from ..interfaces.support import active_runtime, synthetic_sources


def test_allowance_service_returns_reset_aware_local_facts_and_estimates(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    assert control.active_generation is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        source_id = connection.execute(
            "SELECT source_id FROM sources ORDER BY source_id LIMIT 1"
        ).fetchone()[0]
        for observation_id, observed_at, used_percent in (
            (
                "allow_00000000000000000000000000000001",
                "2026-01-01T00:00:00.000Z",
                10.0,
            ),
            (
                "allow_00000000000000000000000000000002",
                "2026-01-01T00:00:03.000Z",
                12.0,
            ),
        ):
            connection.execute(
                """
                INSERT INTO allowance_observations(
                    allowance_observation_id, source_id, observed_at,
                    window_kind, limit_id, plan_type, used_percent,
                    duration_minutes, resets_at, model, service_tier,
                    source_model_call_id, generation, duplicate_state,
                    provenance, validation_warnings
                )
                VALUES (?, ?, ?, 'primary', 'k8-limit', 'synthetic', ?,
                        300, '2026-01-01T05:00:00Z', NULL, NULL, NULL, ?,
                        'canonical', 'synthetic fixture', '[]')
                """,
                (
                    observation_id,
                    source_id,
                    observed_at,
                    used_percent,
                    control.active_generation,
                ),
            )
        connection.execute(
            """
            INSERT INTO generations(
                generation, source_revision_digest, created_at,
                high_water_digest, inserted_count, updated_count,
                deleted_count, canonical_count, excluded_count,
                latest_event_at, parser_versions, integrity_status
            )
            SELECT ?, 'sha256:future', '2026-01-01T00:00:04Z',
                   'sha256:future-water', 2, 0, 0, 2, 0,
                   '2026-01-01T00:00:04Z', 'synthetic', 'valid'
            """,
            (control.active_generation + 1,),
        )
        connection.execute(
            """
            INSERT INTO allowance_observations(
                allowance_observation_id, source_id, observed_at,
                window_kind, limit_id, plan_type, used_percent,
                duration_minutes, resets_at, model, service_tier,
                source_model_call_id, generation, duplicate_state,
                provenance, validation_warnings
            )
                VALUES (
                    'allow_00000000000000000000000000000003',
                    ?,
                    '2026-01-01T00:00:01.500Z',
                    'primary', 'k8-limit', 'synthetic', 11,
                    300, '2026-01-01T05:00:00Z', NULL, NULL, NULL, ?,
                    'canonical', 'synthetic future fixture', '[]')
            """,
            (source_id, control.active_generation + 1),
        )
        connection.execute(
            """
            INSERT INTO model_calls(
                model_call_id, canonical_call_id, source_id, thread_id,
                turn_id, event_at, turn_ordinal, model, effort,
                service_tier, origin, context_window, input_tokens,
                cached_input_tokens, output_tokens, reasoning_tokens,
                upstream_total_tokens, upstream_cumulative_tokens,
                rate_limit_observation_id, duplicate_state, duplicate_reason,
                fingerprint_version, source_offset, generation
            )
                SELECT
                    'call_00000000000000000000000000000003',
                    'fp_0000000000000000000000000000000000000000000000000000000000000003',
                    source_id,
                    thread_id,
                   turn_id, '2026-01-01T00:00:02.500Z', turn_ordinal,
                   model, effort, service_tier, origin, context_window,
                   1000000, 0, 1000000, 0, 2000000, NULL, NULL,
                   'canonical', NULL, fingerprint_version,
                   source_offset + 1000000, ?
            FROM model_calls
            ORDER BY model_call_id
            LIMIT 1
            """,
            (control.active_generation + 1,),
        )
    _write_rate_card(runtime.cache_root / "rate-card.json")
    app = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )
    operational_before = runtime.kernel.operational.read_bytes()
    analytical_before = control.active_kernel_path.read_bytes()

    result = app.allowance({"limit": 100})

    interval = next(
        item
        for item in result["intervals"]
        if item["allowance_observation_id"]
        == "allow_00000000000000000000000000000002"
    )
    assert result["schema"] == "codex-usage-tracker.allowance-efficiency.v1"
    assert result["generation"] == control.active_generation
    assert (
        interval["previous_observation_id"]
        == "allow_00000000000000000000000000000001"
    )
    assert interval["grade"] == "deterministic"
    assert interval["used_percent"] == 12
    assert interval["remaining_percent"] == 88
    assert interval["fact_basis"] == {
        "used_percent": "upstream_observed",
        "remaining_percent": "deterministic_complement",
    }
    assert interval["delta_used_percent"] == 2
    assert interval["local_usage"] == {
        "uncached_input_tokens": 90,
        "cached_input_tokens": 210,
        "reasoning_tokens": 28,
        "output_tokens": 60,
        "total_tokens": 360,
        "calls": 2,
        "turns": 2,
    }
    assert interval["estimated_cost_usd"] == pytest.approx(0.00231)
    assert interval["estimated_credits"] == pytest.approx(0.001155)
    assert interval["pricing_coverage"]["coverage_percent"] == 100
    assert (
        interval["evidence_selector"]
        == "allowance:allow_00000000000000000000000000000002"
    )
    assert interval["limitations"] == ["outside_usage_possible"]
    assert runtime.kernel.operational.read_bytes() == operational_before
    assert control.active_kernel_path.read_bytes() == analytical_before


def test_allowance_cursor_is_bound_to_publication_identity(tmp_path: Path) -> None:
    runtime = active_runtime(tmp_path)
    app = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )

    first = app.allowance({"limit": 1})
    assert first["next_cursor"] is not None
    with sqlite3.connect(runtime.kernel.operational) as connection:
        connection.execute(
            "UPDATE cutover_control SET integrity_digest = "
            "'generation-sha256:synthetic-republication' WHERE singleton = 1"
        )

    with pytest.raises(ValueError, match="publication"):
        app.allowance({"limit": 1, "cursor": first["next_cursor"]})


def test_explicit_refresh_rebuilds_pre_k8_schema_before_allowance_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = active_runtime(tmp_path)
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        connection.execute("DROP VIEW allowance_intervals")
        connection.execute("PRAGMA user_version = 1")
    legacy_path = control.active_kernel_path
    legacy_bytes = legacy_path.read_bytes()
    app = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )

    with pytest.raises(ValueError, match="schema identity"):
        app.allowance({"limit": 1})

    ingestor = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    )
    real_promote = ingestor._promote

    def fail_upgrade_promotion(*_args, **_kwargs):
        raise RuntimeError("synthetic upgrade promotion failure")

    monkeypatch.setattr(ingestor, "_promote", fail_upgrade_promotion)
    with pytest.raises(
        RuntimeError,
        match="synthetic upgrade promotion failure",
    ):
        ingestor.refresh(
            list(synthetic_sources()),
            trigger=RefreshTrigger.CLI_REFRESH,
            owner_id="schema-upgrade-failed",
        )
    failed = load_cutover_control(runtime.kernel.operational)
    assert failed.active_kernel_path == legacy_path
    assert failed.active_generation == control.active_generation
    assert legacy_path.read_bytes() == legacy_bytes

    monkeypatch.setattr(ingestor, "_promote", real_promote)
    result = ingestor.refresh(
        list(synthetic_sources()),
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="schema-upgrade",
    )
    rebuilt = load_cutover_control(runtime.kernel.operational)

    assert result.planner_reason == "new_source"
    assert result.generation > (control.active_generation or 0)
    assert rebuilt.active_schema == SCHEMA_VERSION
    assert rebuilt.legacy_cache_path == legacy_path
    assert legacy_path.read_bytes() == legacy_bytes
    assert app.allowance({"limit": 1})["generation"] == result.generation


def test_appended_allowance_observation_uses_incremental_refresh(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-allowance.jsonl"
    source.parent.mkdir()
    initial = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "allowance-session"},
        },
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "turn-1",
                "model": "gpt-synthetic",
                "effort": "low",
            },
        },
        _allowance_event("event-1", "2026-01-01T00:00:01Z", 10),
    ]
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in initial),
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="first",
    )
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _allowance_event(
                    "event-2",
                    "2026-01-01T00:00:02Z",
                    12,
                )
            )
            + "\n"
        )
    second = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.WATCHER,
        owner_id="watcher",
    )
    runtime = RuntimePaths(
        tmp_path / "codex-home",
        tmp_path / "cache",
    )
    app = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: (source,),
    )

    result = app.allowance({"limit": 10})

    assert first.planner_reason == "new_source"
    assert second.planner_reason == "append_safe"
    assert second.generation == first.generation + 1
    assert result["generation"] == second.generation
    assert result["returned_count"] == 2
    assert any(
        interval["grade"] == "deterministic"
        and interval["delta_used_percent"] == 2
        for interval in result["intervals"]
    )


def test_copied_call_exclusion_propagates_to_allowance_observations(
    tmp_path: Path,
) -> None:
    active = tmp_path / "sessions" / "rollout-active.jsonl"
    archived = tmp_path / "archived_sessions" / "rollout-copy.jsonl"
    for path, session in (
        (active, "active-session"),
        (archived, "copy-session"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": session},
            },
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "turn_context",
                "payload": {
                    "turn_id": "turn-1",
                    "model": "gpt-synthetic",
                    "effort": "low",
                },
            },
            _allowance_event("shared-event", "2026-01-01T00:00:01Z", 10),
        ]
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
    paths = kernel_paths(tmp_path / "cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [archived, active],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="copy-fixture",
    )
    control = load_cutover_control(paths.operational)
    assert control.active_kernel_path is not None

    with sqlite3.connect(control.active_kernel_path) as connection:
        states = connection.execute(
            """
            SELECT sources.archive_state,
                   allowance_observations.duplicate_state
            FROM allowance_observations
            JOIN sources USING (source_id)
            ORDER BY sources.archive_state
            """
        ).fetchall()

    assert states == [("active", "canonical"), ("archived", "copied")]


def _allowance_event(
    event_id: str,
    timestamp: str,
    used_percent: int,
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "plan_type": "synthetic",
                "limit_id": "append-limit",
                "primary": {
                    "used_percent": used_percent,
                    "window_minutes": 300,
                    "resets_at": 1767243600,
                },
            },
            "info": {
                "last_token_usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 5,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                    "total_tokens": 12,
                }
            },
        },
    }


def _write_rate_card(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "codex-usage-tracker.kernel-rate-card.v1",
                "source": {
                    "name": "Synthetic rate card",
                    "url": "https://example.invalid/rates",
                    "effective_at": "2026-01-01",
                    "fetched_at": "2026-01-02",
                },
                "models": {
                    "gpt-5.4": {
                        "input_per_million": 10,
                        "cached_input_per_million": 1,
                        "output_per_million": 20,
                        "credits_input_per_million": 5,
                        "credits_cached_input_per_million": 0.5,
                        "credits_output_per_million": 10,
                        "confidence": "exact",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
