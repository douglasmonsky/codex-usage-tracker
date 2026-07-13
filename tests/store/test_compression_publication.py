from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.store.compression_candidates import (
    get_compression_candidate,
    replace_compression_candidates,
)
from codex_usage_tracker.store.compression_publication import publish_compression_run
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    get_compression_run,
    update_compression_run,
)
from tests.store.test_compression_runs import cache_key, candidate


def test_typed_publication_matches_mapping_candidate_detail(tmp_path: Path) -> None:
    mapping_db = tmp_path / "mapping.sqlite3"
    typed_db = tmp_path / "typed.sqlite3"
    model = candidate("cmp_typed", likely=80)
    create_compression_run(mapping_db, run_id="mapping", **cache_key("rev-1"))
    create_compression_run(typed_db, run_id="typed", **cache_key("rev-1"))

    replace_compression_candidates(
        mapping_db,
        run_id="mapping",
        candidates=[model.as_dict()],
    )
    publish_compression_run(
        typed_db,
        run_id="typed",
        candidates=[model],
        status="completed",
        completed_detectors=1,
        total_detectors=1,
        aggregate_profile={"run_id": "typed", "candidate_count": 1},
        public_profile={"run_id": "typed", "candidate_count": 1},
        source_generation=3,
    )

    mapping_detail = get_compression_candidate(mapping_db, candidate_id="cmp_typed")
    typed_detail = get_compression_candidate(typed_db, candidate_id="cmp_typed")
    assert mapping_detail is not None and typed_detail is not None
    mapping_detail.pop("run_id")
    typed_detail.pop("run_id")
    assert typed_detail == mapping_detail
    run = get_compression_run(typed_db, run_id="typed")
    assert run is not None
    assert run["status"] == "completed"
    assert run["candidate_count"] == 1
    assert run["public_profile"] == {"run_id": "typed", "candidate_count": 1}


def test_publication_rolls_back_supersede_and_can_retry(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    old_model = candidate("cmp_old", likely=70)
    new_model = candidate("cmp_new", likely=80)
    create_compression_run(db_path, run_id="old", **cache_key("rev-1"))
    replace_compression_candidates(
        db_path,
        run_id="old",
        candidates=[old_model.as_dict()],
    )
    update_compression_run(
        db_path,
        run_id="old",
        status="completed",
        aggregate_profile={"run_id": "old"},
        public_profile={"run_id": "old"},
    )
    create_compression_run(db_path, run_id="new", status="running", **cache_key("rev-2"))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_compression_claim
            BEFORE INSERT ON compression_candidate_records
            BEGIN
                SELECT RAISE(ABORT, 'synthetic claim failure');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="synthetic claim failure"):
        publish_compression_run(
            db_path,
            run_id="new",
            candidates=[new_model],
            status="completed",
            completed_detectors=1,
            total_detectors=1,
            aggregate_profile={"run_id": "new"},
            public_profile={"run_id": "new"},
            source_generation=4,
            supersede_run_id="old",
        )

    old_run = get_compression_run(db_path, run_id="old")
    new_run = get_compression_run(db_path, run_id="new")
    assert old_run is not None and old_run["status"] == "completed"
    assert new_run is not None and new_run["status"] == "running"
    assert get_compression_candidate(db_path, candidate_id="cmp_old") is not None
    assert get_compression_candidate(db_path, candidate_id="cmp_new") is None

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TRIGGER fail_compression_claim")
    publish_compression_run(
        db_path,
        run_id="new",
        candidates=[new_model],
        status="completed",
        completed_detectors=1,
        total_detectors=1,
        aggregate_profile={"run_id": "new"},
        public_profile={"run_id": "new"},
        source_generation=4,
        supersede_run_id="old",
    )

    assert get_compression_run(db_path, run_id="old") is None
    assert get_compression_candidate(db_path, candidate_id="cmp_old") is None
    assert get_compression_candidate(db_path, candidate_id="cmp_new") is not None
