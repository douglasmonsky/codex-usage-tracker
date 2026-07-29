from __future__ import annotations

import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_a = importlib.import_module("candidate_a")
adapter_module = importlib.import_module("candidate_a.adapter")
evidence_module = importlib.import_module("candidate_a.evidence")
ingest_module = importlib.import_module("candidate_a.ingest")
maintenance_module = importlib.import_module("candidate_a.maintenance")
schema_module = importlib.import_module("candidate_a.schema")

Adapter = adapter_module.Adapter
EvidenceContractError = evidence_module.EvidenceContractError
all_evidence_rows = evidence_module.all_evidence_rows
evidence_page = evidence_module.evidence_page
resolve_selector = evidence_module.resolve_selector
apply_ordinary_change = maintenance_module.apply_ordinary_change
apply_source_phase = maintenance_module.apply_source_phase
database = schema_module.database

_TINY_FIXTURE = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_AGENT_PERF_CONTRACT = (
    _REPO_ROOT
    / "experiments"
    / "physical-architecture"
    / "candidate_a"
    / "agent-perf-workload.json"
)
_PHYSICAL_CORES = 10


@pytest.fixture
def fixture() -> Any:
    return shared.load_fixture_bundle(_TINY_FIXTURE)


@pytest.fixture
def built(
    fixture: Any,
    tmp_path: Path,
) -> tuple[Any, Any]:
    artifact = candidate_a.build_artifact(fixture, tmp_path / "candidate-a.sqlite")
    return fixture, artifact


def _table_columns(connection: Any, table: str) -> dict[str, str]:
    return {
        str(row["name"]): str(row["type"])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }


def _request(
    *,
    fixture: Any,
    case: Any,
    run_root: Path,
) -> Any:
    run_root.mkdir()
    return shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=run_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )


def test_schema_is_typed_compact_and_deduplicated(
    built: tuple[Any, Any],
) -> None:
    fixture, artifact = built
    accounting = fixture.oracle["accounting"]
    expected_counts = accounting["canonical_counts"]

    with database(artifact.path, read_only=True) as connection:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )
        }
        assert "events" not in tables
        assert "sequence" not in tables
        assert "model_calls" in tables
        assert "tool_invocations" in tables
        assert "session_usage_current" in tables
        assert "tool_family_current" in tables

        prohibited_columns = {
            "body",
            "content",
            "event_json",
            "payload",
            "raw",
            "raw_body",
            "raw_content",
            "raw_json",
            "text",
        }
        for table in sorted(tables - {"sqlite_stat1", "sqlite_stat4"}):
            columns = _table_columns(connection, table)
            assert not prohibited_columns.intersection(columns)
            for name, declared_type in columns.items():
                if name.endswith("_at_us") or name == "event_at_us":
                    assert declared_type == "INTEGER"

        assert (
            connection.execute("SELECT count(*) FROM model_calls").fetchone()[0]
            == expected_counts["model_calls"]
            == 100
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM tool_invocations"
            ).fetchone()[0]
            == expected_counts["tool_invocations"]
        )
        model_columns = _table_columns(connection, "model_calls")
        assert {
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        }.issubset(model_columns)
        assert (
            connection.execute(
                "SELECT value FROM metadata WHERE key='raw_content_stored'"
            ).fetchone()[0]
            == "false"
        )

        timeline_indexes = {
            str(row["name"])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_schema
                WHERE type='index' AND name LIKE '%timeline%'
                """
            )
        }
        assert {
            "model_calls_timeline",
            "tools_start_timeline",
            "turns_timeline",
        }.issubset(timeline_indexes)

    assert artifact.stats.occurrence_rows > expected_counts["model_calls"]
    assert fixture.oracle["source_lifecycle"]["model_call_occurrences"] == 102


def test_recent_history_prunes_only_nonoverlapping_trusted_sources(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = fixture.manifest["history"]["windows"]["30_days"]
    skipped_paths = {
        source.absolute_path
        for source in fixture.sources
        if source.time_range_confidence == "trusted"
        and source.time_range_hint is not None
        and not (
            source.time_range_hint[0] <= int(window["end_us"])
            and source.time_range_hint[1] > int(window["start_us"])
        )
    }
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path in skipped_paths:
            raise AssertionError(f"skipped source body was opened: {path.name}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    artifact = candidate_a.build_artifact(
        fixture,
        tmp_path / "recent-30-days.sqlite",
        history_selection="30_days",
    )

    assert artifact.stats.source_files_inventoried == 12
    assert artifact.stats.source_bytes_inventoried == 244_657
    assert artifact.stats.source_files_selected == 7
    assert artifact.stats.source_bytes_selected == 184_519
    assert artifact.stats.source_files_parsed == 7
    assert artifact.stats.source_bytes_parsed == 184_519
    assert artifact.stats.source_files_deferred == 5
    assert artifact.stats.source_bytes_deferred == 60_138

    with database(artifact.path, read_only=True) as connection:
        assert (
            connection.execute("SELECT count(*) FROM model_calls").fetchone()[0]
            == fixture.manifest["history"]["selections"]["30_days"]["calls"]
            == 4
        )
        selected = {
            str(row["source_path"])
            for row in connection.execute(
                """
                SELECT source_path
                FROM source_manifestations
                WHERE selected = 1
                """
            )
        }
        assert {
            "sources/active/source-0000.jsonl",
            "sources/active/source-0001.jsonl",
            "sources/active/source-0006.jsonl",
            "sources/archived/exact-copy.jsonl",
            "sources/replaced/revision-1.jsonl",
            "sources/truncated/truncated.jsonl",
            "sources/malformed/malformed.jsonl",
        } == selected


def test_all_time_preserves_every_persisted_source(
    built: tuple[Any, Any],
) -> None:
    _, artifact = built
    assert artifact.stats.source_files_inventoried == 12
    assert artifact.stats.source_bytes_inventoried == 244_657
    assert artifact.stats.source_files_selected == 11
    assert artifact.stats.source_bytes_selected == 244_657
    assert artifact.stats.source_files_parsed == 11
    assert artifact.stats.source_bytes_parsed == 244_657
    assert artifact.stats.source_files_deferred == 1
    assert artifact.stats.source_bytes_deferred == 0


def test_source_hint_half_open_interval_against_closed_history_window(
    fixture: Any,
) -> None:
    window = fixture.manifest["history"]["windows"]["30_days"]
    start_us = int(window["start_us"])
    end_us = int(window["end_us"])
    source = next(
        item
        for item in fixture.sources
        if item.time_range_confidence == "trusted"
    )

    def is_selected(
        *,
        hint: tuple[int, int] | None,
        confidence: str,
    ) -> bool:
        candidate = replace(
            source,
            time_range_hint=hint,
            time_range_confidence=confidence,
        )
        candidate_fixture = replace(fixture, sources=(candidate,))
        selected = ingest_module._selected_sources(
            candidate_fixture,
            history_selection="30_days",
            start_us=start_us,
            end_us=end_us,
        )
        return bool(selected)

    assert not is_selected(
        hint=(start_us - 10, start_us),
        confidence="trusted",
    )
    assert is_selected(
        hint=(end_us, end_us + 10),
        confidence="trusted",
    )
    assert is_selected(
        hint=(start_us - 10, start_us),
        confidence="uncertain",
    )
    assert is_selected(hint=None, confidence="unavailable")


def test_default_initial_build_defers_and_restores_indexes_before_publication(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, int]] = []
    original_drop = ingest_module._drop_secondary_indexes
    original_restore = ingest_module._restore_secondary_indexes

    def observed_drop(connection: Any) -> tuple[str, ...]:
        statements = original_drop(connection)
        events.append(("drop", len(statements)))
        return statements

    def observed_restore(
        connection: Any,
        statements: tuple[str, ...],
    ) -> int:
        assert connection.execute(
            "SELECT count(*) FROM publications"
        ).fetchone()[0] == 0
        elapsed_ns = original_restore(connection, statements)
        events.append(("restore", len(statements)))
        return elapsed_ns

    monkeypatch.setattr(
        ingest_module,
        "_drop_secondary_indexes",
        observed_drop,
    )
    monkeypatch.setattr(
        ingest_module,
        "_restore_secondary_indexes",
        observed_restore,
    )
    artifact = candidate_a.build_artifact(
        fixture,
        tmp_path / "default-deferred.sqlite",
    )

    assert events[0][0] == "drop"
    assert events[1][0] == "restore"
    assert events[0][1] == events[1][1]
    assert events[0][1] > 0
    assert artifact.stats.secondary_indexes_deferred == events[0][1]
    assert artifact.stats.secondary_indexes_restored == events[1][1]
    assert artifact.stats.index_maintenance_ns > 0
    with database(artifact.path, read_only=True) as connection:
        schema_module.validate_database(connection)
        assert connection.execute(
            """
            SELECT count(*)
            FROM sqlite_schema
            WHERE type = 'index' AND sql IS NOT NULL
            """
        ).fetchone()[0] == events[1][1]


def test_explicit_present_build_keeps_secondary_indexes_present(
    fixture: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_drop(_connection: Any) -> tuple[str, ...]:
        raise AssertionError("explicit present mode dropped secondary indexes")

    monkeypatch.setattr(
        ingest_module,
        "_drop_secondary_indexes",
        unexpected_drop,
    )
    artifact = candidate_a.build_artifact(
        fixture,
        tmp_path / "explicit-present.sqlite",
        defer_secondary_indexes=False,
    )

    assert artifact.stats.secondary_indexes_deferred == 0
    assert artifact.stats.secondary_indexes_restored == 0
    assert artifact.stats.index_maintenance_ns == 0
    with database(artifact.path, read_only=True) as connection:
        schema_module.validate_database(connection)


def test_deferred_default_is_deterministic_and_oracle_equivalent_to_present(
    fixture: Any,
    tmp_path: Path,
) -> None:
    default_first = candidate_a.build_artifact(
        fixture,
        tmp_path / "default-first.sqlite",
    )
    default_second = candidate_a.build_artifact(
        fixture,
        tmp_path / "default-second.sqlite",
    )
    present = candidate_a.build_artifact(
        fixture,
        tmp_path / "present.sqlite",
        defer_secondary_indexes=False,
    )

    assert ingest_module.file_sha256(
        default_first.path
    ) == ingest_module.file_sha256(default_second.path)
    with (
        database(default_first.path, read_only=True) as default_connection,
        database(present.path, read_only=True) as present_connection,
    ):
        for table, expected in fixture.oracle["accounting"][
            "canonical_counts"
        ].items():
            assert default_connection.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0] == present_connection.execute(
                f'SELECT count(*) FROM "{table}"'
            ).fetchone()[0]
            if table in {"model_calls", "tool_invocations", "turns"}:
                assert default_connection.execute(
                    f'SELECT count(*) FROM "{table}"'
                ).fetchone()[0] == expected


def test_evidence_merge_is_gap_free_stable_and_keyset_paginated(
    built: tuple[Any, Any],
) -> None:
    fixture, artifact = built
    with database(artifact.path, read_only=True) as connection:
        rows_by_seven = all_evidence_rows(
            connection,
            publication_id=artifact.publication_id,
            page_size=7,
        )
        rows_by_thirty_seven = all_evidence_rows(
            connection,
            publication_id=artifact.publication_id,
            page_size=37,
        )
        assert rows_by_seven == rows_by_thirty_seven
        assert len(rows_by_seven) > 100

        order_keys = [tuple(row["order_key"]) for row in rows_by_seven]
        assert order_keys == sorted(order_keys)
        assert len(order_keys) == len(set(order_keys))
        first_timestamp = order_keys[0][0]
        assert sum(key[0] == first_timestamp for key in order_keys) > 1

        page = evidence_page(
            connection,
            publication_id=artifact.publication_id,
            page_size=7,
        )
        assert page.next_cursor is not None
        assert page.full_scan_count == 0
        assert page.temporary_sort_count == 0
        assert page.query_plans

        tampered = ("A" if page.next_cursor[0] != "A" else "B") + page.next_cursor[1:]
        with pytest.raises(EvidenceContractError, match="signature"):
            evidence_page(
                connection,
                publication_id=artifact.publication_id,
                page_size=7,
                cursor=tampered,
            )
        with pytest.raises(EvidenceContractError, match="publication differs"):
            evidence_page(
                connection,
                publication_id="publication:candidate-a:different",
                page_size=7,
                cursor=page.next_cursor,
            )

        selector = fixture.oracle["evidence"]["selector_samples"]["session"]
        resolved = resolve_selector(connection, str(selector))
        assert resolved is not None
        assert resolved["selector"] == selector
        assert "body" not in resolved


@pytest.mark.parametrize(
    "change",
    [
        "tool_terminal_transition",
        "tool_plus_state_change",
        "2000_call_tail",
        "late_event",
    ],
)
def test_ordinary_changes_are_incremental_and_preserve_lifecycle_semantics(
    fixture: Any,
    tmp_path: Path,
    change: str,
) -> None:
    artifact = candidate_a.build_artifact(
        fixture,
        tmp_path / f"{change}.sqlite",
    )
    with database(artifact.path, read_only=True) as connection:
        call_count_before = int(
            connection.execute("SELECT count(*) FROM model_calls").fetchone()[0]
        )
        minimum_event_before = int(
            connection.execute(
                "SELECT min(event_at_us) FROM model_calls"
            ).fetchone()[0]
        )
        tool_count_before = int(
            connection.execute(
                "SELECT count(*) FROM tool_invocations"
            ).fetchone()[0]
        )
        open_tools_before = int(
            connection.execute(
                "SELECT count(*) FROM tool_invocations WHERE terminal_at_us IS NULL"
            ).fetchone()[0]
        )

    stats = apply_ordinary_change(artifact.path, change)
    assert stats.source_files_rescanned == 0
    assert stats.source_bytes_rescanned == 0
    assert stats.writer_transactions == 1

    with database(artifact.path, read_only=True) as connection:
        if change == "tool_terminal_transition":
            assert (
                connection.execute(
                    "SELECT count(*) FROM tool_invocations"
                ).fetchone()[0]
                == tool_count_before
            )
            assert open_tools_before == 1
            assert (
                connection.execute(
                    """
                    SELECT count(*)
                    FROM tool_invocations
                    WHERE terminal_at_us IS NULL
                    """
                ).fetchone()[0]
                == 0
            )
            assert stats.facts_inserted == 0
            assert stats.facts_updated == 1
        elif change == "tool_plus_state_change":
            row = connection.execute(
                """
                SELECT preceding_activity_count, causal_attribution
                FROM state_changes
                ORDER BY event_at_us DESC, change_id DESC
                LIMIT 1
                """
            ).fetchone()
            assert row["preceding_activity_count"] == 2
            assert row["causal_attribution"] is None
        elif change == "2000_call_tail":
            assert (
                connection.execute("SELECT count(*) FROM model_calls").fetchone()[0]
                == call_count_before + 2_000
            )
            assert stats.facts_inserted == 2_000
            assert stats.dirty_keys == 1
        elif change == "late_event":
            assert (
                connection.execute(
                    "SELECT min(event_at_us) FROM model_calls"
                ).fetchone()[0]
                == minimum_event_before - 1
            )


def test_source_phases_and_selectors_reconcile_on_clean_rebuild(
    fixture: Any,
    tmp_path: Path,
) -> None:
    first = candidate_a.build_artifact(fixture, tmp_path / "first.sqlite")
    second = candidate_a.build_artifact(fixture, tmp_path / "second.sqlite")
    selector = str(fixture.oracle["evidence"]["selector_samples"]["session"])

    with database(first.path) as connection:
        for phase_artifact in fixture.phases:
            expected = tuple(
                str(json.loads(line)["payload"]["occurrence_id"])
                for line in phase_artifact.absolute_path.read_text(
                    encoding="utf-8"
                ).splitlines()
            )
            actual = apply_source_phase(
                connection,
                fixture,
                group=phase_artifact.group,
                phase=phase_artifact.phase,
            )
            assert actual == expected
        connection.commit()

    with (
        database(first.path, read_only=True) as first_connection,
        database(second.path, read_only=True) as second_connection,
    ):
        assert resolve_selector(first_connection, selector) == resolve_selector(
            second_connection,
            selector,
        )


def test_all_mandatory_workloads_pass_with_only_optional_writer_unsupported(
    fixture: Any,
    tmp_path: Path,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=_PHYSICAL_CORES)
    results: dict[str, Any] = {}

    for case in matrix.cases:
        request = _request(
            fixture=fixture,
            case=case,
            run_root=tmp_path / case.case_id,
        )
        result = Adapter().execute(request)
        results[case.case_id] = result
        if case.candidate_capability is None:
            assert result.outcome is shared.RunOutcome.PASSED, case.case_id

    unsupported = {
        case_id
        for case_id, result in results.items()
        if result.outcome is shared.RunOutcome.UNSUPPORTED
    }
    assert unsupported == {"build.writer.partitioned_staging"}

    for case_id, result in results.items():
        if case_id.startswith("query."):
            assert result.measurements.oracle_equivalent
            assert result.measurements.selector_pages_gap_free
            assert result.measurements.response_bytes <= 16_384
            assert result.measurements.duplicated_representation_bytes == 0

    assert results["build.index.present"].measurements.merge_time_ns == 0
    assert results["build.index.deferred"].measurements.merge_time_ns > 0
    assert results["build.index.rebuilt"].measurements.merge_time_ns > 0
    default_build = results["build.scale.tiny"]
    assert default_build.oracle_results["index_mode"] == "deferred"
    assert default_build.measurements.merge_time_ns > 0
    assert (
        default_build.oracle_results["secondary_indexes_deferred"]
        == default_build.oracle_results["secondary_indexes_restored"]
        > 0
    )
    present_build = results["build.index.present"]
    assert present_build.oracle_results["index_mode"] == "present"
    assert present_build.oracle_results["secondary_indexes_deferred"] == 0
    assert present_build.oracle_results["secondary_indexes_restored"] == 0


def test_agent_perf_contract_is_pinned_to_standard_fixture_and_matrix() -> None:
    contract = shared.load_agent_perf_workload(_AGENT_PERF_CONTRACT)
    matrix = shared.build_workload_matrix(physical_cores=_PHYSICAL_CORES)

    assert contract.candidate_id == "A"
    assert contract.fixture_profile == "standard"
    assert contract.fixture_revision == shared.FIXTURE_REVISION
    assert (
        contract.fixture_manifest_digest
        == "b5b938232e199793f49d7ab0bf67d360ea658f332f15e5d53449d4327c821f26"
    )
    assert (
        contract.fixture_oracle_digest
        == "ca44e370f96923c1b3537f1b18089109e1d609d0fcd78bf995deb71d27353bc2"
    )
    assert contract.workload_id == "build.scale.standard"
    assert contract.workload_matrix_digest == matrix.digest
    assert contract.minimum_unprofiled_runs == 5
    assert contract.profile_is_attribution_only
    assert contract.command_argv == (
        "{python}",
        "-m",
        "candidate_a.workload",
        "--fixture",
        "{fixture_root}",
        "--output",
        "{output_root}",
    )
