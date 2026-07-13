from __future__ import annotations

from codex_usage_tracker.store.compression_revisions import (
    read_compression_revision_vector,
    touch_compression_revisions,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


def test_revision_key_tracks_only_selected_detector_dependencies(tmp_path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as conn:
        init_db(conn)
        baseline = read_compression_revision_vector(
            conn,
            detector_families=("stale_context",),
            estimator_revision="estimator-v1",
        )
        touch_compression_revisions(conn, {"files"})
        unrelated = read_compression_revision_vector(
            conn,
            detector_families=("stale_context",),
            estimator_revision="estimator-v1",
        )
        touch_compression_revisions(conn, {"calls"})
        related = read_compression_revision_vector(
            conn,
            detector_families=("stale_context",),
            estimator_revision="estimator-v1",
        )

    assert unrelated.generation == baseline.generation + 1
    assert unrelated.cache_key == baseline.cache_key
    assert related.cache_key != unrelated.cache_key


def test_revision_key_changes_for_each_detector_specific_dependency(tmp_path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    cases = (
        ("file_rediscovery", "files"),
        ("shell_retry", "commands"),
        ("validation_repetition", "commands"),
        ("tool_output_bloat", "tools"),
        ("cache_break_resume", "threads"),
    )
    with connect(db_path) as conn:
        init_db(conn)
        for detector_family, dimension in cases:
            before = read_compression_revision_vector(
                conn,
                detector_families=(detector_family,),
                estimator_revision="estimator-v1",
            )
            touch_compression_revisions(conn, {dimension})
            after = read_compression_revision_vector(
                conn,
                detector_families=(detector_family,),
                estimator_revision="estimator-v1",
            )
            assert after.cache_key != before.cache_key
