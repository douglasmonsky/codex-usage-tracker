from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.content import (
    CONTENT_FINGERPRINT_SAMPLE_BYTES,
    ContextComposition,
)
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.query import QueryRequest, QueryService


def _source(root: Path) -> Path:
    source = root / "codex-home" / "sessions" / "synthetic-content.jsonl"
    source.parent.mkdir(parents=True)
    rows = [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "synthetic-content-session"},
        },
        {
            "timestamp": "2026-01-01T00:00:01Z",
            "type": "turn_context",
            "payload": {
                "turn_id": "synthetic-turn",
                "model": "gpt-synthetic",
                "cwd": "/private/synthetic-project",
            },
        },
        {
            "timestamp": "2026-01-01T00:00:02Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hello context"}],
            },
        },
        {
            "timestamp": "2026-01-01T00:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "functions.exec_command",
                "arguments": '{"api_key":"secret-value","cmd":"synthetic"}',
                "access_token": "ghp_syntheticcredential",
                "client_secret": "synthetic-client-secret",
                "working_directory": "/Users/alice/private-project",
                "file_path": "/Users/alice/private-project/private.txt",
            },
        },
        {
            "timestamp": "2026-01-01T00:00:04Z",
            "type": "event_msg",
            "payload": {
                "type": "mcp_tool_call_end",
                "tool_name": "mcp__synthetic__query",
                "server_name": "synthetic",
                "arguments": {"query": "Bearer synthetic-secret"},
            },
        },
        {
            "event_id": "synthetic-token-event",
            "timestamp": "2026-01-01T00:00:05Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 100,
                        "cached_input_tokens": 60,
                        "output_tokens": 20,
                        "reasoning_output_tokens": 5,
                        "total_tokens": 120,
                    },
                    "model_context_window": 200000,
                },
            },
        },
    ]
    source.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    return source


def _runtime(tmp_path: Path) -> RuntimePaths:
    runtime = RuntimePaths(
        codex_home=tmp_path / "codex-home",
        cache_root=tmp_path / "cache",
    )
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [_source(tmp_path)],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="content-contract",
    )
    return runtime


def _accounting_total(runtime: RuntimePaths) -> int:
    result = QueryService(runtime.kernel.operational).execute(
        QueryRequest(
            dataset="calls",
            operation="aggregate",
            measures=("total_tokens",),
        )
    )
    return int(result.rows[0]["total_tokens"])


def test_content_is_disabled_by_default_and_refresh_does_not_create_it(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)

    assert content.status() == {
        "state": "disabled",
        "store_redacted_fragments": False,
        "indexed_generation": None,
        "estimator": None,
    }
    assert not runtime.content.exists()
    assert _accounting_total(runtime) == 120


def test_unavailable_content_database_does_not_break_accounting_status(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    runtime.content.write_bytes(b"not sqlite")

    assert ContextComposition(
        runtime.content,
        runtime.kernel.operational,
    ).status()["state"] == "unavailable"
    assert KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
    ).status()["content"]["state"] == "unavailable"
    assert _accounting_total(runtime) == 120


def test_opt_in_index_disable_and_delete_leave_accounting_intact(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    accounting_before = runtime.kernel.analytical.read_bytes()

    with pytest.raises(ValueError, match="privacy confirmation"):
        content.enable(privacy_confirmed=False)
    enabled = content.enable(
        privacy_confirmed=True,
        store_redacted_fragments=True,
    )
    indexed = content.index()

    assert enabled["state"] == "enabled"
    assert indexed["indexed_generation"] == 1
    assert indexed["events"] == 4
    assert set(indexed["categories"]) == {"host", "mcp", "message", "tool"}
    assert runtime.content.stat().st_mode & 0o777 == 0o600
    assert runtime.kernel.analytical.read_bytes() == accounting_before

    assert content.disable()["state"] == "disabled"
    assert _accounting_total(runtime) == 120
    assert content.delete()["state"] == "disabled"
    assert not runtime.content.exists()
    assert runtime.kernel.analytical.read_bytes() == accounting_before
    assert _accounting_total(runtime) == 120


def test_fragments_are_redacted_and_never_exposed_by_query_results(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True, store_redacted_fragments=True)
    content.index()

    with sqlite3.connect(runtime.content) as connection:
        fragments = "\n".join(
            row[0]
            for row in connection.execute(
                "SELECT redacted_text FROM redacted_fragments ORDER BY event_id"
            )
        )
    assert "secret-value" not in fragments
    assert "synthetic-secret" not in fragments
    assert "ghp_syntheticcredential" not in fragments
    assert "synthetic-client-secret" not in fragments
    assert "/Users/alice/private-project" not in fragments
    assert "/private/synthetic-project" not in fragments
    assert "[REDACTED]" in fragments

    result = QueryService(
        runtime.kernel.operational,
        content_path=runtime.content,
    ).execute(
        QueryRequest(
            dataset="context",
            operation="aggregate",
            dimensions=("category",),
            measures=("events", "observed_bytes", "estimated_tokens"),
            order_by="observed_bytes",
            limit=25,
        )
    )
    encoded = json.dumps(result.rows)
    assert "secret-value" not in encoded
    assert "synthetic-secret" not in encoded
    assert result.grade == "estimated"
    assert result.coverage["unattributed_input_tokens"] is None
    assert result.coverage["source_generation"] == 1
    assert result.coverage["generation_lag"] == 0
    assert result.coverage["observed_through"] == "2026-01-01T00:00:04Z"
    assert result.coverage["measures"]["observed_bytes"]["basis"] == (
        "exact_observed_utf8_bytes"
    )
    assert result.coverage["measures"]["estimated_tokens"]["basis"] == (
        "tokenizer_estimate"
    )


class _WordEstimator:
    identifier = "synthetic-word-estimator-v1"

    def estimate(self, value: str) -> int:
        return len(value.split())


class _CharacterEstimator:
    identifier = "synthetic-character-estimator-v2"

    def estimate(self, value: str) -> int:
        return len(value)


def test_optional_estimator_is_labeled_and_coverage_is_explicit(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    content.index(estimator=_WordEstimator())

    result = QueryService(
        runtime.kernel.operational,
        content_path=runtime.content,
    ).execute(
        QueryRequest(
            dataset="context",
            operation="aggregate",
            dimensions=("category",),
            measures=("observed_bytes", "estimated_tokens"),
            limit=25,
        )
    )

    assert result.grade == "estimated"
    estimate_coverage = result.coverage["measures"]["estimated_tokens"]
    assert estimate_coverage["coverage_percent"] == 100.0
    assert estimate_coverage["estimator"] == "synthetic-word-estimator-v1"
    assert all(row["estimated_tokens"] is not None for row in result.rows)


def test_estimator_transition_rebuilds_values_and_provenance(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)

    first = content.index(estimator=_WordEstimator())
    with sqlite3.connect(runtime.content) as connection:
        word_total = int(
            connection.execute(
                "SELECT SUM(estimated_tokens) FROM composition_events"
            ).fetchone()[0]
        )

    second = content.index(estimator=_CharacterEstimator())
    with sqlite3.connect(runtime.content) as connection:
        character_total = int(
            connection.execute(
                "SELECT SUM(estimated_tokens) FROM composition_events"
            ).fetchone()[0]
        )

    third = content.index()
    with sqlite3.connect(runtime.content) as connection:
        missing_estimates = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM composition_events
                WHERE estimated_tokens IS NULL
                """
            ).fetchone()[0]
        )

    assert first["events"] == 4
    assert second["events"] == 4
    assert character_total > word_total
    assert content.status()["estimator"] is None
    assert third["events"] == 4
    assert missing_estimates == 4


def test_content_failure_rolls_back_without_affecting_accounting(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    accounting_before = runtime.kernel.analytical.read_bytes()

    class BrokenEstimator:
        identifier = "broken"

        def estimate(self, value: str) -> int:
            raise RuntimeError("synthetic estimator failure")

    with pytest.raises(RuntimeError, match="synthetic estimator failure"):
        content.index(estimator=BrokenEstimator())

    assert content.status()["indexed_generation"] is None
    assert runtime.kernel.analytical.read_bytes() == accounting_before
    assert _accounting_total(runtime) == 120


def test_content_index_hydrates_only_newly_committed_source_rows(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    first = content.index()
    with sqlite3.connect(runtime.content) as connection:
        first_ids = {
            row[0]
            for row in connection.execute(
                "SELECT event_id FROM composition_events"
            )
        }

    source = tmp_path / "codex-home" / "sessions" / "synthetic-content.jsonl"
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:06Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": "new context"}
                        ],
                    },
                },
                separators=(",", ":"),
            )
            + "\n"
        )
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="content-append",
    )

    second = content.index()
    third = content.index()
    with sqlite3.connect(runtime.content) as connection:
        final_ids = {
            row[0]
            for row in connection.execute(
                "SELECT event_id FROM composition_events"
            )
        }

    assert first["events"] == 4
    assert second["events"] == 1
    assert third["events"] == 0
    assert first_ids < final_ids


def test_inode_replacement_retires_prior_source_rows_and_fragments(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True, store_redacted_fragments=True)
    content.index()
    source = tmp_path / "codex-home" / "sessions" / "synthetic-content.jsonl"
    prior_inode = source.stat().st_ino
    replacement = source.with_suffix(".replacement")
    replacement.write_bytes(source.read_bytes())
    replacement.replace(source)
    assert source.stat().st_ino != prior_inode

    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
    ).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="content-replacement",
    )
    indexed = content.index()

    with sqlite3.connect(runtime.content) as connection:
        event_count = int(
            connection.execute("SELECT COUNT(*) FROM composition_events").fetchone()[0]
        )
        source_count = int(
            connection.execute(
                "SELECT COUNT(DISTINCT source_id) FROM composition_events"
            ).fetchone()[0]
        )
        fragment_count = int(
            connection.execute("SELECT COUNT(*) FROM redacted_fragments").fetchone()[0]
        )

    assert indexed["events"] == 4
    assert event_count == 4
    assert source_count == 1
    assert fragment_count == 4


def test_context_batch_holds_one_read_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    content.index()
    request = QueryRequest(
        dataset="context",
        operation="aggregate",
        measures=("events",),
    )
    original = QueryService._execute_one
    calls = 0

    def execute_with_concurrent_commit(
        service,
        connection,
        normalized,
        generation,
    ):
        nonlocal calls
        result = original(service, connection, normalized, generation)
        calls += 1
        if calls == 1:
            with sqlite3.connect(runtime.content, timeout=5) as writer:
                writer.execute(
                    """
                    INSERT INTO composition_events(
                        event_id,
                        source_id,
                        category,
                        observed_bytes,
                        estimated_tokens,
                        source_offset,
                        generation
                    )
                    VALUES ('ctx_concurrent', 'src_concurrent', 'host', 7, NULL, 0, 1)
                    """
                )
        return result

    monkeypatch.setattr(
        QueryService,
        "_execute_one",
        execute_with_concurrent_commit,
    )
    service = QueryService(
        runtime.kernel.operational,
        content_path=runtime.content,
    )
    first, second = service.execute_batch((request, request))

    assert first.rows == second.rows == ({"events": 4},)


def test_context_rejects_event_level_operations(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    content.index()
    service = QueryService(
        runtime.kernel.operational,
        content_path=runtime.content,
    )

    for operation in ("rows", "timeline"):
        with pytest.raises(ValueError, match="operation is not supported"):
            service.execute(
                QueryRequest(
                    dataset="context",
                    operation=operation,
                    dimensions=("category",),
                    measures=("events",),
                )
            )


def test_no_change_content_index_reads_only_bounded_source_samples(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = _runtime(tmp_path)
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    content.index()
    source = (
        tmp_path / "codex-home" / "sessions" / "synthetic-content.jsonl"
    ).resolve()
    original_open = Path.open
    observed = {"bytes": 0}

    class CountingReader:
        def __init__(self, handle) -> None:
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def read(self, size: int = -1):
            payload = self._handle.read(size)
            observed["bytes"] += len(payload)
            return payload

        def readline(self, size: int = -1):
            payload = self._handle.readline(size)
            observed["bytes"] += len(payload)
            return payload

    def counting_open(path: Path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return CountingReader(handle) if path.resolve() == source else handle

    monkeypatch.setattr(Path, "open", counting_open)

    assert content.index()["events"] == 0
    assert observed["bytes"] <= 3 * CONTENT_FINGERPRINT_SAMPLE_BYTES
