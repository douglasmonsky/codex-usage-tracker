from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.evidence import (
    EvidenceRequest,
    EvidenceService,
    EvidenceView,
)
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths

_ORACLE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "accounting-oracle-v1"
)


def test_every_logical_selector_resolves_to_bounded_evidence(tmp_path: Path) -> None:
    service, analytical, selectors = _service(tmp_path / "first")
    before = analytical.read_bytes()

    for selector in selectors.values():
        result = service.read(
            EvidenceRequest(selector=selector, view=EvidenceView.SUMMARY)
        )
        assert result.selector == selector
        assert result.generation == 1
        assert result.rows
        assert result.destination.startswith("/evidence/")
        assert result.coverage["content_included"] is False

    thread = selectors["thread"]
    first = service.read(
        EvidenceRequest(
            selector=thread,
            view=EvidenceView.TIMELINE,
            limit=1,
            live=True,
        )
    )
    second = service.read(
        EvidenceRequest(
            selector=thread,
            view=EvidenceView.TIMELINE,
            limit=1,
            cursor=first.next_cursor,
            live=True,
        )
    )
    assert first.truncated
    assert first.next_cursor
    assert first.rows != second.rows
    assert first.destination.endswith(
        "view=timeline&live=1"
    )
    assert analytical.read_bytes() == before
    assert "SYNTHETIC_TOOL_ARGUMENT_SENTINEL" not in repr(first)
    with pytest.raises(ValueError, match="cursor"):
        service.read(
            EvidenceRequest(
                selector=thread,
                view=EvidenceView.TIMELINE,
                limit=2,
                cursor=first.next_cursor,
                live=True,
            )
        )


def test_views_return_only_foundational_rows_and_reject_invalid_scope(
    tmp_path: Path,
) -> None:
    service, _analytical, selectors = _service(tmp_path)

    for view in (
        EvidenceView.CALLS,
        EvidenceView.TOOLS,
        EvidenceView.ACTIVITIES,
    ):
        result = service.read(
            EvidenceRequest(selector=selectors["thread"], view=view)
        )
        assert result.matched_count >= result.returned_count
        assert result.grade == "exact"
    allowance = service.read(
        EvidenceRequest(
            selector=selectors["allowance"],
            view=EvidenceView.ALLOWANCE,
        )
    )
    assert allowance.rows[0]["allowance"]
    assert 0 <= allowance.rows[0]["used_percent"] <= 100

    with pytest.raises(ValueError, match="not found"):
        service.read(EvidenceRequest(selector="thread:missing"))
    with pytest.raises(ValueError, match="allowance selector"):
        service.read(
            EvidenceRequest(
                selector=selectors["thread"],
                view=EvidenceView.ALLOWANCE,
            )
        )
    for selector_kind in ("call", "tool"):
        selector = selectors[selector_kind]
        with pytest.raises(ValueError, match="thread or turn"):
            service.read(
                EvidenceRequest(
                    selector=selector,
                    view=EvidenceView.ACTIVITIES,
                )
            )
        timeline = service.read(
            EvidenceRequest(selector=selector, view=EvidenceView.TIMELINE)
        )
        assert all(
            row["event_kind"] != "activity"
            and not str(row["event_id"]).startswith("activity:")
            for row in timeline.rows
        )


def test_selectors_and_destinations_survive_clean_rebuild(tmp_path: Path) -> None:
    first, _analytical, selectors = _service(tmp_path / "first")
    second, _rebuilt, rebuilt_selectors = _service(tmp_path / "second")

    assert rebuilt_selectors == selectors
    for selector in selectors.values():
        original = first.read(EvidenceRequest(selector=selector))
        rebuilt = second.read(EvidenceRequest(selector=selector))
        assert rebuilt.selector == original.selector
        assert rebuilt.destination == original.destination
        assert rebuilt.rows == original.rows


def _service(
    root: Path,
) -> tuple[EvidenceService, Path, dict[str, str]]:
    paths = kernel_paths(root / "cache")
    sources = sorted((_ORACLE_ROOT / "logs").glob("**/*.jsonl"))
    KernelIngestor(paths.analytical, paths.operational).refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="evidence-fixture",
    )
    with sqlite3.connect(paths.analytical) as connection:
        selectors = {
            "thread": "thread:"
            + connection.execute(
                """
                SELECT logical_thread_id
                FROM threads
                WHERE thread_id IN (
                    SELECT thread_id
                    FROM (
                        SELECT thread_id FROM model_calls
                        WHERE duplicate_state = 'canonical'
                        UNION ALL
                        SELECT thread_id FROM tool_calls
                        UNION ALL
                        SELECT thread_id FROM activity_events
                    )
                    GROUP BY thread_id
                    HAVING COUNT(*) >= 2
                )
                ORDER BY logical_thread_id
                LIMIT 1
                """
            ).fetchone()[0],
            "turn": "turn:"
            + connection.execute(
                """
                SELECT COALESCE(source_turn_id_hash, turn_id)
                FROM turns ORDER BY turn_id LIMIT 1
                """
            ).fetchone()[0],
            "call": "call:"
            + connection.execute(
                """
                SELECT canonical_call_id FROM model_calls
                WHERE duplicate_state = 'canonical'
                ORDER BY model_call_id LIMIT 1
                """
            ).fetchone()[0],
            "tool": "tool:"
            + connection.execute(
                "SELECT tool_call_id FROM tool_calls ORDER BY tool_call_id LIMIT 1"
            ).fetchone()[0],
            "allowance": "allowance:"
            + connection.execute(
                """
                SELECT allowance_observation_id
                FROM allowance_observations
                ORDER BY allowance_observation_id LIMIT 1
                """
            ).fetchone()[0],
        }
    return EvidenceService(paths.operational), paths.analytical, selectors
