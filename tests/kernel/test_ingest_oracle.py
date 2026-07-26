from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import kernel_paths

_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
)
_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "accounting-oracle-v1"


def export_accounting_oracle(
    *,
    fixture_root: Path,
    workspace: Path,
) -> dict[str, object]:
    """Export K1 accounting semantics through the content-free kernel."""

    paths = kernel_paths(workspace / "cache")
    sources = sorted(
        (fixture_root / "logs").rglob("*.jsonl"),
        key=lambda path: (
            "000000000001" not in path.name,
            "000000000002" not in path.name,
            str(path),
        ),
    )
    KernelIngestor(paths.analytical, paths.operational).refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="oracle",
    )
    with sqlite3.connect(paths.analytical) as connection:
        connection.row_factory = sqlite3.Row
        calls = connection.execute(
            """
            SELECT model_calls.*, sources.archive_state
            FROM model_calls
            JOIN sources USING (source_id)
            ORDER BY event_at, model_call_id
            """
        ).fetchall()
        canonical = [
            row for row in calls if row["duplicate_state"] == "canonical"
        ]
        diagnostics = connection.execute(
            """
            SELECT SUM(parse_warning_count), SUM(unsupported_shape_count)
            FROM sources
            """
        ).fetchone()
        allowance_count = connection.execute(
            "SELECT COUNT(*) FROM allowance_observations"
        ).fetchone()[0]
        root_threads = connection.execute(
            """
            SELECT COUNT(
                DISTINCT COALESCE(
                    parent.logical_thread_id,
                    child.logical_thread_id
                )
            )
            FROM threads AS child
            LEFT JOIN threads AS parent
              ON parent.logical_thread_id = child.parent_logical_thread_id
            WHERE child.thread_id IN (
                SELECT DISTINCT thread_id
                FROM model_calls
                WHERE duplicate_state = 'canonical'
            )
            """
        ).fetchone()[0]
        canonical_turns = connection.execute(
            """
            SELECT COUNT(DISTINCT turn_id)
            FROM model_calls
            WHERE duplicate_state = 'canonical'
            """
        ).fetchone()[0]
        parentage = connection.execute(
            """
            SELECT subagent_role, subagent_nickname
            FROM threads
            WHERE subagent_role IS NOT NULL
            """
        ).fetchall()
    return {
        "physical_counts": {
            "usage_events": len(calls),
            "duplicate_events": sum(
                row["duplicate_state"] != "canonical" for row in calls
            ),
            "archived_events": sum(
                row["archive_state"] == "archived" for row in calls
            ),
            "malformed_or_unknown_events_skipped": int(diagnostics[0] or 0)
            + int(diagnostics[1] or 0),
        },
        "canonical_counts": {
            "usage_events": len(canonical),
            "threads": int(root_threads),
            "turns": int(canonical_turns),
        },
        "token_totals": _token_totals(canonical),
        "by_model_effort": _group(canonical, ("model", "effort")),
        "by_time": _group(canonical, ("event_day",)),
        "canonical_promotion": {
            "active_original_is_canonical": any(
                row["archive_state"] == "active"
                and row["duplicate_state"] == "canonical"
                and row["canonical_call_id"]
                for row in calls
            ),
            "archived_copy_is_duplicate": any(
                row["archive_state"] == "archived"
                and row["duplicate_state"] == "copied"
                for row in calls
            ),
        },
        "parentage": [
            {
                "agent_role": row["subagent_role"],
                "agent_nickname": row["subagent_nickname"],
            }
            for row in parentage
        ],
        "allowance_observation_count": int(allowance_count),
        "parser_diagnostics": {
            "invalid_json": int(diagnostics[0] or 0),
            "unknown_event_shape": int(diagnostics[1] or 0),
            "skipped_events": 0,
        },
        "privacy": {
            "raw_content_included": False,
            "source_paths": "repository_relative",
            "unknown_events": "parsed_counted_not_copied",
        },
    }


def test_rebuild_produces_identical_stable_fact_ids(tmp_path: Path) -> None:
    assert _stable_ids(_FIXTURE_ROOT, tmp_path / "first") == _stable_ids(
        _FIXTURE_ROOT,
        tmp_path / "second",
    )


def _stable_ids(
    fixture_root: Path,
    workspace: Path,
) -> dict[str, list[tuple[object, ...]]]:
    paths = kernel_paths(workspace / "cache")
    sources = sorted(
        (fixture_root / "logs").rglob("*.jsonl"),
        key=lambda path: (
            "000000000001" not in path.name,
            "000000000002" not in path.name,
            str(path),
        ),
    )
    KernelIngestor(paths.analytical, paths.operational).refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="stable-id-oracle",
    )
    with sqlite3.connect(paths.analytical) as connection:
        return {
            table: connection.execute(query).fetchall()
            for table, query in {
                "threads": (
                    "SELECT thread_id, parent_logical_thread_id "
                    "FROM threads ORDER BY thread_id"
                ),
                "turns": (
                    "SELECT turn_id, thread_id FROM turns ORDER BY turn_id"
                ),
                "model_calls": (
                    "SELECT model_call_id, canonical_call_id, thread_id, turn_id "
                    "FROM model_calls ORDER BY model_call_id"
                ),
                "allowance": (
                    "SELECT allowance_observation_id, source_model_call_id "
                    "FROM allowance_observations "
                    "ORDER BY allowance_observation_id"
                ),
            }.items()
        }


def _token_totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    totals = {
        name: sum(int(row[name]) for row in rows)
        for name in _TOKEN_FIELDS
    }
    return {
        "input_tokens": totals["input_tokens"],
        "cached_input_tokens": totals["cached_input_tokens"],
        "uncached_input_tokens": (
            totals["input_tokens"] - totals["cached_input_tokens"]
        ),
        "output_tokens": totals["output_tokens"],
        "reasoning_output_tokens": totals["reasoning_tokens"],
        "total_tokens": totals["input_tokens"] + totals["output_tokens"],
    }


def _group(
    rows: list[sqlite3.Row],
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        values = tuple(
            str(row["event_at"])[:10] if key == "event_day" else row[key]
            for key in keys
        )
        groups[values].append(row)
    return [
        {
            **dict(zip(keys, values, strict=True)),
            "calls": len(group),
            **_token_totals(group),
        }
        for values, group in sorted(
            groups.items(),
            key=lambda item: tuple(str(value) for value in item[0]),
        )
    ]
