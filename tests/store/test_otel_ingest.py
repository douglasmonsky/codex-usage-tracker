from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.store.otel_ingest import (
    discover_otel_sources,
    ingest_otel_completion_files,
)
from tests.otel_helpers import (
    append_text,
    completion_attributes,
    initialized_connection,
    synthetic_fast_completion,
    synthetic_otlp_line,
    synthetic_standard_completion,
    write_lines,
)


def test_discovery_is_bounded_and_deterministic(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    write_lines(directory / "codex-completions.jsonl", [])
    write_lines(directory / "codex-completions-20260716.jsonl", [])
    write_lines(directory / "unrelated.jsonl", [])

    assert [path.name for path in discover_otel_sources(directory)] == [
        "codex-completions-20260716.jsonl",
        "codex-completions.jsonl",
    ]
    assert discover_otel_sources(tmp_path / "missing") == []


def test_incremental_ingest_reads_each_complete_line_once(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    write_lines(source, [synthetic_fast_completion("conversation-a", 100)])
    with initialized_connection(tmp_path) as conn:
        first = ingest_otel_completion_files(conn, directory)
        append_text(source, synthetic_standard_completion("conversation-b", 200) + "\n")
        second = ingest_otel_completion_files(conn, directory)
        rows = conn.execute("SELECT fingerprint FROM otel_completion_events").fetchall()

    assert first.imported == 1
    assert second.imported == 1
    assert second.duplicates == 0
    assert len(rows) == 2


def test_partial_last_line_is_retried_after_append(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    complete = synthetic_otlp_line(attributes=completion_attributes())
    source.parent.mkdir(parents=True)
    source.write_text(complete[:-1], encoding="utf-8")
    with initialized_connection(tmp_path) as conn:
        assert ingest_otel_completion_files(conn, directory).imported == 0
        source.write_text(complete + "\n", encoding="utf-8")
        assert ingest_otel_completion_files(conn, directory).imported == 1


def test_rotation_and_reread_do_not_duplicate_semantic_completion(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    current = directory / "codex-completions.jsonl"
    rotated = directory / "codex-completions-20260716.jsonl"
    line = synthetic_otlp_line(attributes=completion_attributes()) + "\n"
    current.parent.mkdir(parents=True)
    current.write_text(line, encoding="utf-8")
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        current.replace(rotated)
        current.write_text(line, encoding="utf-8")
        result = ingest_otel_completion_files(conn, directory)
        count = conn.execute("SELECT COUNT(*) FROM otel_completion_events").fetchone()[0]

    assert count == 1
    assert result.duplicates >= 1


def test_truncation_or_inode_replacement_resets_cursor_safely(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        synthetic_otlp_line(
            attributes=completion_attributes(conversation_id="synthetic-a")
        )
        + "\n",
        encoding="utf-8",
    )
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        source.unlink()
        source.write_text(
            synthetic_otlp_line(
                attributes=completion_attributes(conversation_id="synthetic-b")
            )
            + "\n",
            encoding="utf-8",
        )
        assert ingest_otel_completion_files(conn, directory).imported == 1


def test_same_inode_same_size_rewrite_resets_cursor_safely(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    first_line = synthetic_otlp_line(
        attributes=completion_attributes(conversation_id="synthetic-a")
    )
    replacement_line = synthetic_otlp_line(
        attributes=completion_attributes(conversation_id="synthetic-b")
    )
    assert len(first_line) == len(replacement_line)
    source.parent.mkdir(parents=True)
    source.write_text(first_line + "\n", encoding="utf-8")

    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        first_stat = source.stat()
        source.write_text(replacement_line + "\n", encoding="utf-8")
        replacement_stat = source.stat()
        result = ingest_otel_completion_files(conn, directory)

    assert first_stat.st_ino == replacement_stat.st_ino
    assert first_stat.st_size == replacement_stat.st_size
    assert result.imported == 1


def test_legacy_cursor_without_anchor_is_reread_once(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    write_lines(source, [synthetic_otlp_line(attributes=completion_attributes())])

    with initialized_connection(tmp_path) as conn:
        assert ingest_otel_completion_files(conn, directory).imported == 1
        conn.execute("UPDATE otel_completion_sources SET resume_anchor = NULL")

        legacy_resume = ingest_otel_completion_files(conn, directory)
        anchored_resume = ingest_otel_completion_files(conn, directory)

    assert legacy_resume.imported == 0
    assert legacy_resume.duplicates == 1
    assert anchored_resume.imported == 0
    assert anchored_resume.duplicates == 0


def test_rotation_between_discovery_and_open_reads_replacement_from_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    replacement = tmp_path / "replacement.jsonl"
    write_lines(source, [synthetic_fast_completion("conversation-a", 100)])

    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        write_lines(
            replacement,
            [
                synthetic_fast_completion(
                    "conversation-b-with-a-longer-synthetic-identifier", 200
                ),
                synthetic_standard_completion("conversation-c", 300),
            ],
        )
        real_open = Path.open
        rotated = False

        def rotate_before_open(path: Path, *args: object, **kwargs: object):
            nonlocal rotated
            if path == source and args and args[0] == "rb" and not rotated:
                rotated = True
                source.unlink()
                replacement.replace(source)
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", rotate_before_open)
        result = ingest_otel_completion_files(conn, directory)
        event_count = conn.execute(
            "SELECT COUNT(*) FROM otel_completion_events"
        ).fetchone()[0]
        cursor = conn.execute(
            """
            SELECT device, inode, parsed_offset
            FROM otel_completion_sources
            WHERE source_path = ?
            """,
            (str(source.resolve()),),
        ).fetchone()

    source_stat = source.stat()
    assert result.imported == 2
    assert event_count == 3
    assert tuple(cursor) == (
        source_stat.st_dev,
        source_stat.st_ino,
        source_stat.st_size,
    )


def test_ingest_never_persists_body_or_arbitrary_attributes(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    attributes = completion_attributes()
    attributes["secret.attribute"] = "synthetic-secret-value"
    write_lines(
        directory / "codex-completions.jsonl",
        [
            synthetic_otlp_line(
                attributes=attributes, body="synthetic-private-body"
            )
        ],
    )
    with initialized_connection(tmp_path) as conn:
        ingest_otel_completion_files(conn, directory)
        rows = conn.execute("SELECT * FROM otel_completion_events").fetchall()
        encoded = json.dumps([dict(row) for row in rows], sort_keys=True)

    assert "synthetic-private-body" not in encoded
    assert "synthetic-secret-value" not in encoded
    assert "secret.attribute" not in encoded


def test_cursor_advances_past_complete_invalid_lines(tmp_path: Path) -> None:
    directory = tmp_path / "otel"
    source = directory / "codex-completions.jsonl"
    write_lines(source, ["{"])

    with initialized_connection(tmp_path) as conn:
        first = ingest_otel_completion_files(conn, directory)
        second = ingest_otel_completion_files(conn, directory)
        cursor = conn.execute(
            "SELECT parsed_line, parsed_offset FROM otel_completion_sources"
        ).fetchone()

    assert first.diagnostics["otel_invalid_json"] == 1
    assert second.diagnostics == {}
    assert tuple(cursor) == (1, source.stat().st_size)
