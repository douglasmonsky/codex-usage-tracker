"""Deterministic adapters from synthetic K1 inputs to the v0.25.1 runtime."""

from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.core.models import SessionInfo
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.parser.api import parse_usage_events_from_file_with_state
from codex_usage_tracker.parser.state import ParserState
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.sources import (
    SourceParsePlan,
    source_logs_requiring_parse,
    upsert_source_file_metadata,
)

_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def export_accounting_oracle(
    *,
    fixture_root: Path,
    workspace: Path,
) -> dict[str, object]:
    """Load synthetic events through current persistence and export safe facts."""

    db_path = workspace / "oracle.sqlite3"
    logs_root = fixture_root / "logs"
    copy_path = next((logs_root / "archived_sessions").glob("*.jsonl"))
    child_path = next(
        path
        for path in (logs_root / "sessions").glob("*.jsonl")
        if path.name.endswith("00000000-0000-4000-8000-000000000002.jsonl")
    )
    parent_path = next(
        path
        for path in (logs_root / "sessions").glob("*.jsonl")
        if path.name.endswith("00000000-0000-4000-8000-000000000001.jsonl")
    )
    parser_stats: dict[str, int] = {}
    session_index = {
        "00000000-0000-4000-8000-000000000001": SessionInfo(
            session_id="00000000-0000-4000-8000-000000000001",
            thread_name="Synthetic parent",
            updated_at="2026-01-02T00:00:05Z",
        ),
        "00000000-0000-4000-8000-000000000099": SessionInfo(
            session_id="00000000-0000-4000-8000-000000000099",
            thread_name="Synthetic copied parent",
            updated_at="2026-01-01T00:00:06Z",
        ),
    }
    parsed_copy = parse_usage_events_from_file_with_state(
        copy_path,
        session_index=session_index,
        stats=parser_stats,
    )
    parsed_child = parse_usage_events_from_file_with_state(
        child_path,
        session_index=session_index,
        stats=parser_stats,
    )
    parsed_parent = parse_usage_events_from_file_with_state(
        parent_path,
        session_index=session_index,
        stats=parser_stats,
    )

    child_events = [
        replace(
            event,
            service_tier="fast",
            fast=1,
            service_tier_source="synthetic_fixture",
            service_tier_confidence="high",
        )
        for event in parsed_child.events
    ]
    for events, facts in (
        (parsed_copy.events, parsed_copy.diagnostic_facts),
        (child_events, parsed_child.diagnostic_facts),
        (parsed_parent.events, parsed_parent.diagnostic_facts),
    ):
        upsert_usage_events(events, db_path=db_path, diagnostic_facts=facts)
    upsert_usage_events([], db_path=db_path, replace_source_files=[copy_path])
    upsert_usage_events(
        parsed_copy.events,
        db_path=db_path,
        diagnostic_facts=parsed_copy.diagnostic_facts,
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM usage_events
            ORDER BY event_timestamp, source_file, line_number, record_id
            """
        ).fetchall()
        canonical = [row for row in rows if int(row["is_duplicate"]) == 0]
        allowance = conn.execute(
            """
            SELECT window_key, window_kind, used_percent, remaining_percent,
                   window_minutes, resets_at, plan_type, limit_id,
                   event_timestamp, model, effort
            FROM allowance_observations
            ORDER BY event_timestamp, window_key
            """
        ).fetchall()
        diagnostic_rows = conn.execute(
            """
            SELECT fact_type, fact_name, fact_category,
                   SUM(event_count) AS event_count,
                   MIN(confidence) AS confidence,
                   MAX(raw_content_included) AS raw_content_included
            FROM call_diagnostic_facts
            GROUP BY fact_type, fact_name, fact_category
            ORDER BY fact_type, fact_name, fact_category
            """
        ).fetchall()

    attached = annotate_thread_attachments([dict(row) for row in canonical])
    selected_allowance: dict[tuple[str, str], sqlite3.Row] = {}
    for row in allowance:
        selected_allowance[(str(row["window_key"]), str(row["window_kind"]))] = row

    return {
        "physical_counts": {
            "usage_events": len(rows),
            "duplicate_events": sum(int(row["is_duplicate"]) for row in rows),
            "archived_events": sum(int(row["is_archived"]) for row in rows),
            "malformed_or_unknown_events_skipped": sum(
                parser_stats.get(key, 0)
                for key in ("invalid_json", "unknown_event_shape", "skipped_events")
            ),
        },
        "canonical_counts": {
            "usage_events": len(canonical),
            "threads": len({str(row["thread_key"]) for row in canonical}),
            "turns": len({str(row["turn_id"]) for row in canonical}),
        },
        "token_totals": _token_totals(canonical),
        "by_thread": _group_tokens(canonical, ("thread_key",)),
        "by_model_effort": _group_tokens(canonical, ("model", "effort", "service_tier")),
        "by_time": _group_tokens(canonical, ("event_day",)),
        "canonical_identities": [
            {
                "record_id": str(row["record_id"]),
                "canonical_record_id": str(row["canonical_record_id"]),
                "is_duplicate": bool(row["is_duplicate"]),
                "duplicate_reason": row["duplicate_reason"],
            }
            for row in rows
        ],
        "canonical_promotion": {
            "active_original_is_canonical": any(
                not row["is_archived"]
                and not row["is_duplicate"]
                and row["upstream_usage_id"] == "envelope.event_id:evt-parent-2"
                for row in rows
            ),
            "archived_copy_is_duplicate": any(
                row["is_archived"]
                and row["is_duplicate"]
                and row["upstream_usage_id"] == "envelope.event_id:evt-parent-2"
                for row in rows
            ),
        },
        "parentage": [
            {
                "thread_key": str(row["thread_key"]),
                "thread_source": row["thread_source"],
                "parent_session_id": row["parent_session_id"],
                "agent_role": row["agent_role"],
                "agent_nickname": row["agent_nickname"],
            }
            for row in canonical
            if row["parent_session_id"] is not None
        ],
        "delayed_parent_attachment": [
            {
                "thread_attachment_key": row["thread_attachment_key"],
                "thread_attachment_label": row["thread_attachment_label"],
                "thread_attachment_relation": row["thread_attachment_relation"],
                "thread_attachment_parent_session_id": row[
                    "thread_attachment_parent_session_id"
                ],
            }
            for row in attached
            if row["parent_session_id"] is not None
        ],
        "allowance_observation_count": len(allowance),
        "allowance_selection": [
            {
                key: row[key]
                for key in (
                    "window_key",
                    "window_kind",
                    "used_percent",
                    "remaining_percent",
                    "window_minutes",
                    "resets_at",
                    "plan_type",
                    "limit_id",
                    "event_timestamp",
                    "model",
                    "effort",
                )
            }
            for row in selected_allowance.values()
        ],
        "diagnostic_facts": [dict(row) for row in diagnostic_rows],
        "parser_diagnostics": {
            key: parser_stats.get(key, 0)
            for key in (
                "invalid_json",
                "unknown_event_shape",
                "skipped_events",
            )
        },
        "privacy": {
            "raw_content_included": False,
            "source_paths": "repository_relative",
            "unknown_events": "parsed_counted_not_copied",
        },
    }


def export_source_lifecycle_oracle(*, workspace: Path) -> dict[str, object]:
    """Exercise the current source planner across the frozen lifecycle states."""

    workspace.mkdir(parents=True, exist_ok=True)
    return {
        "cases": [
            _new_case(workspace / "new"),
            _append_case(workspace / "appended", partial=False),
            _append_case(workspace / "partial", partial=True),
            _replacement_case(workspace / "replaced"),
            _truncation_case(workspace / "truncated"),
            _archived_case(workspace / "archived"),
            _restored_case(workspace / "restored"),
        ]
    }


def _token_totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    return {
        name: sum(
            int(row["input_tokens"]) - int(row["cached_input_tokens"])
            if name == "uncached_input_tokens"
            else int(row[name])
            for row in rows
        )
        for name in _TOKEN_FIELDS
    }


def _group_tokens(
    rows: list[sqlite3.Row],
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    groups: dict[tuple[object, ...], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        values = tuple(
            str(row["event_timestamp"])[:10] if key == "event_day" else row[key]
            for key in keys
        )
        groups[values].append(row)
    return [
        {
            **dict(zip(keys, values, strict=True)),
            "calls": len(group),
            **_token_totals(group),
        }
        for values, group in sorted(groups.items(), key=lambda item: tuple(str(v) for v in item[0]))
    ]


def _planner(workspace: Path) -> tuple[sqlite3.Connection, Path]:
    workspace.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(workspace / "planner.sqlite3")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn, workspace / "sessions" / "rollout-synthetic.jsonl"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _record_parsed(conn: sqlite3.Connection, plan: SourceParsePlan) -> None:
    upsert_source_file_metadata(
        conn,
        parsed_files=[
            (
                plan.path,
                [],
                {},
                ParserState(session_id="synthetic-session"),
                1,
                plan.source_metadata,
                plan.end_byte,
            )
        ],
    )
    conn.commit()


def _normalized_plan(plan: SourceParsePlan | None) -> dict[str, object]:
    if plan is None:
        return {"planned": False}
    return {
        "planned": True,
        "start_byte": plan.start_byte,
        "end_byte": plan.end_byte,
        "start_line": plan.start_line,
        "replace_existing": plan.replace_existing,
        "is_archived": bool(plan.source_metadata and plan.source_metadata.is_archived),
    }


def _new_case(workspace: Path) -> dict[str, object]:
    conn, path = _planner(workspace)
    try:
        _write(path, '{"type":"synthetic"}\n')
        return {"name": "new", **_normalized_plan(source_logs_requiring_parse(conn, [path])[0])}
    finally:
        conn.close()


def _append_case(workspace: Path, *, partial: bool) -> dict[str, object]:
    conn, path = _planner(workspace)
    try:
        _write(path, '{"type":"first"}\n')
        initial = source_logs_requiring_parse(conn, [path])[0]
        _record_parsed(conn, initial)
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"type":"second"}' + ("" if partial else "\n"))
        plans = source_logs_requiring_parse(conn, [path])
        name = "partially_appended" if partial else "appended"
        return {"name": name, **_normalized_plan(plans[0] if plans else None)}
    finally:
        conn.close()


def _replacement_case(workspace: Path) -> dict[str, object]:
    conn, path = _planner(workspace)
    try:
        _write(path, '{"type":"original"}\n')
        _record_parsed(conn, source_logs_requiring_parse(conn, [path])[0])
        replacement = path.with_suffix(".replacement")
        _write(replacement, '{"type":"replacement"}\n')
        os.replace(replacement, path)
        return {
            "name": "replaced",
            **_normalized_plan(source_logs_requiring_parse(conn, [path])[0]),
        }
    finally:
        conn.close()


def _truncation_case(workspace: Path) -> dict[str, object]:
    conn, path = _planner(workspace)
    try:
        _write(path, '{"type":"long-original-value"}\n')
        _record_parsed(conn, source_logs_requiring_parse(conn, [path])[0])
        _write(path, "{}\n")
        return {
            "name": "truncated",
            **_normalized_plan(source_logs_requiring_parse(conn, [path])[0]),
        }
    finally:
        conn.close()


def _archived_case(workspace: Path) -> dict[str, object]:
    conn, _path = _planner(workspace)
    path = workspace / "archived_sessions" / "rollout-synthetic.jsonl"
    try:
        _write(path, '{"type":"archived"}\n')
        return {
            "name": "archived",
            **_normalized_plan(source_logs_requiring_parse(conn, [path])[0]),
        }
    finally:
        conn.close()


def _restored_case(workspace: Path) -> dict[str, object]:
    conn, path = _planner(workspace)
    archived = workspace / "archived_sessions" / "rollout-synthetic.jsonl"
    try:
        _write(archived, '{"type":"restored"}\n')
        _record_parsed(conn, source_logs_requiring_parse(conn, [archived])[0])
        path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(archived, path)
        return {
            "name": "restored",
            **_normalized_plan(source_logs_requiring_parse(conn, [path])[0]),
        }
    finally:
        conn.close()
