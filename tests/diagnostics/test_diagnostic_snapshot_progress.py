from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.diagnostics.snapshots import refresh_diagnostic_snapshots


def test_batch_refresh_reports_each_persisted_snapshot_in_display_order(
    tmp_path: Path,
) -> None:
    progress: list[dict[str, object]] = []

    refresh_diagnostic_snapshots(
        db_path=tmp_path / "usage.sqlite3",
        progress_callback=lambda **payload: progress.append(payload),
    )

    assert [row["completed_units"] for row in progress] == list(range(1, 11))
    assert [row["current_unit"] for row in progress] == [
        "overview",
        "tool-output",
        "commands",
        "git-interactions",
        "file-reads",
        "file-modifications",
        "read-productivity",
        "concentration",
        "guided-summary",
        "usage-drain",
    ]
    assert all(row["stage"] == "persisting_snapshots" for row in progress)
    assert all(row["total_units"] == 10 for row in progress)
