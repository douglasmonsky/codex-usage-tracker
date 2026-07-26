from __future__ import annotations

import os
from pathlib import Path

from codex_usage_tracker.kernel.discovery import (
    PlanKind,
    SourceCursor,
    observe_source,
    plan_source,
)


def export_source_lifecycle_oracle(*, workspace: Path) -> dict[str, object]:
    """Export the frozen K1 lifecycle shape through the kernel planner."""

    return {
        "cases": [
            _oracle_new(workspace / "new"),
            _oracle_append(workspace / "appended", partial=False),
            _oracle_append(workspace / "partial", partial=True),
            _oracle_replace(workspace / "replaced"),
            _oracle_truncate(workspace / "truncated"),
            _oracle_archive(workspace / "archived"),
            _oracle_restore(workspace / "restored"),
        ]
    }


def test_source_lifecycle_uses_one_complete_line_cursor(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    path.parent.mkdir()
    path.write_text('{"type":"first"}\n', encoding="utf-8")

    initial = plan_source(observe_source(path), None)
    assert initial is not None
    assert initial.kind is PlanKind.NEW_SOURCE
    assert (initial.start_byte, initial.end_byte, initial.start_line) == (0, 17, 0)
    cursor = SourceCursor.from_plan(initial)

    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type":"second"}')
    assert plan_source(observe_source(path), cursor) is None

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    appended = plan_source(observe_source(path), cursor)
    assert appended is not None
    assert appended.kind is PlanKind.APPEND_SAFE
    assert (appended.start_byte, appended.end_byte, appended.start_line) == (
        17,
        35,
        1,
    )


def test_replacement_truncation_archive_and_restore_are_explicit(
    tmp_path: Path,
) -> None:
    active = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    active.parent.mkdir()
    active.write_text('{"type":"long-original-value"}\n', encoding="utf-8")
    original = plan_source(observe_source(active), None)
    assert original is not None
    cursor = SourceCursor.from_plan(original)

    active.write_text("{}\n", encoding="utf-8")
    truncated = plan_source(observe_source(active), cursor)
    assert truncated is not None
    assert truncated.kind is PlanKind.TRUNCATE_SOURCE
    assert truncated.replace_existing

    replacement = active.with_suffix(".replacement")
    replacement.write_text('{"type":"replacement"}\n', encoding="utf-8")
    os.replace(replacement, active)
    replaced = plan_source(observe_source(active), cursor)
    assert replaced is not None
    assert replaced.kind is PlanKind.REPLACE_SOURCE

    archived = tmp_path / "archived_sessions" / active.name
    archived.parent.mkdir()
    os.replace(active, archived)
    archived_plan = plan_source(observe_source(archived), None)
    assert archived_plan is not None
    assert archived_plan.observation.is_archived

    active.parent.mkdir(exist_ok=True)
    os.replace(archived, active)
    restored = plan_source(
        observe_source(active),
        SourceCursor.from_plan(archived_plan),
    )
    assert restored is not None
    assert restored.kind is PlanKind.REPLACE_SOURCE
    assert not restored.observation.is_archived


def test_rewrite_beyond_prefix_is_replacement_even_when_file_grows(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sessions" / "rollout-synthetic.jsonl"
    path.parent.mkdir()
    original = (b'{"padding":"' + b"a" * 9000 + b'"}\n')
    path.write_bytes(original)
    initial = plan_source(observe_source(path), None)
    assert initial is not None
    cursor = SourceCursor.from_plan(initial)

    rewritten = bytearray(original)
    rewritten[5000:5010] = b"bbbbbbbbbb"
    path.write_bytes(bytes(rewritten) + b'{"type":"later"}\n')

    plan = plan_source(observe_source(path), cursor)
    assert plan is not None
    assert plan.kind is PlanKind.REPLACE_SOURCE
    assert plan.start_byte == 0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalized(plan) -> dict[str, object]:
    if plan is None:
        return {"planned": False}
    return {
        "planned": True,
        "start_byte": plan.start_byte,
        "end_byte": plan.end_byte,
        "start_line": plan.start_line,
        "replace_existing": plan.replace_existing,
        "is_archived": plan.observation.is_archived,
    }


def _oracle_new(root: Path) -> dict[str, object]:
    path = root / "sessions" / "rollout-synthetic.jsonl"
    _write(path, '{"type":"synthetic"}\n')
    return {"name": "new", **_normalized(plan_source(observe_source(path), None))}


def _oracle_append(root: Path, *, partial: bool) -> dict[str, object]:
    path = root / "sessions" / "rollout-synthetic.jsonl"
    _write(path, '{"type":"first"}\n')
    initial = plan_source(observe_source(path), None)
    assert initial is not None
    cursor = SourceCursor.from_plan(initial)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"type":"second"}' + ("" if partial else "\n"))
    name = "partially_appended" if partial else "appended"
    return {
        "name": name,
        **_normalized(plan_source(observe_source(path), cursor)),
    }


def _oracle_replace(root: Path) -> dict[str, object]:
    path = root / "sessions" / "rollout-synthetic.jsonl"
    _write(path, '{"type":"original"}\n')
    initial = plan_source(observe_source(path), None)
    assert initial is not None
    cursor = SourceCursor.from_plan(initial)
    replacement = path.with_suffix(".replacement")
    _write(replacement, '{"type":"replacement"}\n')
    os.replace(replacement, path)
    return {
        "name": "replaced",
        **_normalized(plan_source(observe_source(path), cursor)),
    }


def _oracle_truncate(root: Path) -> dict[str, object]:
    path = root / "sessions" / "rollout-synthetic.jsonl"
    _write(path, '{"type":"long-original-value"}\n')
    initial = plan_source(observe_source(path), None)
    assert initial is not None
    cursor = SourceCursor.from_plan(initial)
    _write(path, "{}\n")
    return {
        "name": "truncated",
        **_normalized(plan_source(observe_source(path), cursor)),
    }


def _oracle_archive(root: Path) -> dict[str, object]:
    path = root / "archived_sessions" / "rollout-synthetic.jsonl"
    _write(path, '{"type":"archived"}\n')
    return {
        "name": "archived",
        **_normalized(plan_source(observe_source(path), None)),
    }


def _oracle_restore(root: Path) -> dict[str, object]:
    archived = root / "archived_sessions" / "rollout-synthetic.jsonl"
    active = root / "sessions" / archived.name
    _write(archived, '{"type":"restored"}\n')
    initial = plan_source(observe_source(archived), None)
    assert initial is not None
    cursor = SourceCursor.from_plan(initial)
    active.parent.mkdir(parents=True, exist_ok=True)
    os.replace(archived, active)
    return {
        "name": "restored",
        **_normalized(plan_source(observe_source(active), cursor)),
    }
