from __future__ import annotations

import json
import sqlite3
import statistics
import time
from pathlib import Path

from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import load_cutover_control


def test_bounded_allowance_read_stays_within_common_query_budget(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-allowance-performance.jsonl"
    source.parent.mkdir()
    rows: list[dict[str, object]] = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "allowance-performance"},
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
    ]
    rows.extend(_allowance_event(index) for index in range(100))
    source.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="performance",
    )
    control = load_cutover_control(runtime.kernel.operational)
    assert control.active_kernel_path is not None
    with sqlite3.connect(control.active_kernel_path) as connection:
        connection.execute(
            """
            WITH RECURSIVE sequence(value) AS (
                SELECT 1
                UNION ALL
                SELECT value + 1 FROM sequence WHERE value < 99900
            )
            INSERT INTO model_calls(
                model_call_id, canonical_call_id, source_id, thread_id,
                turn_id, event_at, turn_ordinal, model, effort,
                service_tier, origin, context_window, input_tokens,
                cached_input_tokens, output_tokens, reasoning_tokens,
                upstream_total_tokens, upstream_cumulative_tokens,
                rate_limit_observation_id, duplicate_state, duplicate_reason,
                fingerprint_version, source_offset, generation
            )
            SELECT printf('call_%032x', sequence.value),
                   printf('fp_%064x', sequence.value),
                   seed.source_id, seed.thread_id, seed.turn_id,
                   '2026-01-01T00:00:50.500Z', seed.turn_ordinal,
                   seed.model, seed.effort, seed.service_tier, seed.origin,
                   seed.context_window, 100, 80, 10, 4, 110, NULL, NULL,
                   'canonical', NULL, seed.fingerprint_version,
                   seed.source_offset + sequence.value + 1000,
                   seed.generation
            FROM sequence
            CROSS JOIN (
                SELECT * FROM model_calls ORDER BY model_call_id LIMIT 1
            ) AS seed
            """
        )
        for copy_number in range(1, 5):
            connection.execute(
                """
                INSERT INTO allowance_observations(
                    allowance_observation_id, source_id, observed_at,
                    window_kind, limit_id, plan_type, used_percent,
                    duration_minutes, resets_at, model, service_tier,
                    source_model_call_id, generation, duplicate_state,
                    provenance, validation_warnings
                )
                SELECT printf(
                           'allow_%032x',
                           ? * 1000000 + allowance_state_key
                       ),
                       source_id, observed_at, window_kind,
                       printf('performance-limit-%d', ?), plan_type,
                       used_percent, duration_minutes, resets_at, model,
                       service_tier, NULL, generation, duplicate_state,
                       provenance, validation_warnings
                FROM allowance_observations
                WHERE limit_id = 'performance-limit'
                """,
                (copy_number, copy_number),
            )
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: (source,),
    )
    application.allowance({"limit": 500})

    samples = []
    for _sample in range(10):
        started = time.perf_counter()
        result = application.allowance({"limit": 500})
        samples.append((time.perf_counter() - started) * 1000)

    p95 = statistics.quantiles(samples, n=100, method="inclusive")[94]
    print(f"allowance_read_p95_ms={p95:.3f}")
    assert result["returned_count"] == 500
    # Shared CI runners consistently add about 25% over the local 400-430 ms
    # distribution. Keep a narrow ceiling that still catches a material query
    # regression without making runner scheduling noise release-blocking.
    assert p95 <= 550, f"allowance read p95 {p95:.3f} ms exceeded 550 ms"


def _allowance_event(index: int) -> dict[str, object]:
    second = index + 1
    return {
        "event_id": f"event-{index:03d}",
        "timestamp": f"2026-01-01T00:{second // 60:02d}:{second % 60:02d}Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "rate_limits": {
                "plan_type": "synthetic",
                "limit_id": "performance-limit",
                "primary": {
                    "used_percent": index + 1,
                    "window_minutes": 300,
                    "resets_at": 1767243600,
                },
            },
            "info": {
                "last_token_usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 80,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 4,
                    "total_tokens": 110,
                }
            },
        },
    }
