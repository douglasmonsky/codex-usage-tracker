from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_usage_tracker.parser.jsonl_v1 import parse_codex_jsonl_v1
from codex_usage_tracker.store.api import query_session_usage, refresh_usage_index
from codex_usage_tracker.store.context_offsets import resolve_context_offset
from tests.store_dashboard_helpers import (
    SESSION_ID,
    _entry,
    _make_codex_home,
    _token_event,
)


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
@pytest.mark.parametrize("cwd", ["/tmp/ascii", "/tmp/Résumé-雪"])
def test_parser_records_exact_utf8_byte_offset(
    tmp_path: Path,
    newline: bytes,
    cwd: str,
) -> None:
    session_id = "019f9000-0000-7000-8000-000000000001"
    log_path = tmp_path / "rollout" / f"rollout-2026-07-24T00-00-00-{session_id}.jsonl"
    lines = [
        _entry("session_meta", {"id": session_id}),
        _entry(
            "turn_context",
            {"turn_id": "turn-utf8", "model": "gpt-5.5", "cwd": cwd},
        ),
        _token_event(100, 100),
    ]
    encoded_lines = [
        json.dumps(line, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + newline
        for line in lines
    ]
    log_path.parent.mkdir(parents=True)
    log_path.write_bytes(b"".join(encoded_lines))

    parsed = parse_codex_jsonl_v1(log_path)

    assert len(parsed.events) == 1
    assert parsed.events[0].source_byte_offset == sum(len(line) for line in encoded_lines[:2])


def test_append_only_refresh_preserves_existing_offsets_and_adds_new_offset(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    before = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    offsets_before = {str(row["record_id"]): int(row["source_byte_offset"]) for row in before}
    source_path = Path(str(before[0]["source_file"]))

    with source_path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(
            json.dumps(
                _entry(
                    "turn_context",
                    {"turn_id": "turn-appended", "model": "gpt-5.5", "effort": "high"},
                ),
                separators=(",", ":"),
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(500, 200), separators=(",", ":")) + "\n")

    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    after = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    offsets_after = {str(row["record_id"]): int(row["source_byte_offset"]) for row in after}

    assert offsets_after.items() >= offsets_before.items()
    assert len(offsets_after) == len(offsets_before) + 1


def test_context_offset_requires_current_source_provenance(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_path = Path(str(row["source_file"]))

    current = resolve_context_offset(
        db_path=db_path,
        record_id=str(row["record_id"]),
        source_file=source_path,
    )
    assert current.strategy == "offset_seek"
    assert current.reason == "validated"
    assert current.byte_offset == row["source_byte_offset"]

    clone_path = tmp_path / "cloned.jsonl"
    clone_path.write_bytes(source_path.read_bytes())
    cloned = resolve_context_offset(
        db_path=db_path,
        record_id=str(row["record_id"]),
        source_file=clone_path,
    )
    assert cloned.strategy == "sequential_fallback"
    assert cloned.reason == "source_path_mismatch"

    with source_path.open("ab") as handle:
        handle.write(b'{"type":"synthetic-rewrite"}\n')
    stale = resolve_context_offset(
        db_path=db_path,
        record_id=str(row["record_id"]),
        source_file=source_path,
    )
    assert stale.strategy == "sequential_fallback"
    assert stale.reason == "stale_provenance"


def test_context_offset_rejects_rewritten_source(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_path = Path(str(row["source_file"]))
    original_stat = source_path.stat()
    original = source_path.read_bytes()
    rewritten = original.replace(b"turn-a", b"turn-z", 1)
    assert len(rewritten) == len(original)
    source_path.write_bytes(rewritten)
    os.utime(
        source_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1),
    )

    resolution = resolve_context_offset(
        db_path=db_path,
        record_id=str(row["record_id"]),
        source_file=source_path,
    )

    assert resolution.strategy == "sequential_fallback"
    assert resolution.reason == "stale_provenance"
