from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import (
    analytical_digest,
    initialize_analytical_database,
    short_writer_transaction,
)
from codex_usage_tracker.kernel.models import CutoverState
from codex_usage_tracker.kernel.operational import (
    initialize_operational_database,
    kernel_paths,
    load_cutover_control,
    record_legacy_cache_metadata,
    rollback_cutover,
    transition_cutover,
)


def test_versioned_kernel_and_operational_paths_are_side_by_side(
    tmp_path: Path,
) -> None:
    paths = kernel_paths(tmp_path)

    assert paths.analytical.name == "codex-usage-kernel-v1.sqlite3"
    assert paths.operational.name == "codex-usage-kernel-operational-v1.sqlite3"
    assert paths.analytical != paths.operational


def test_cutover_control_is_explicit_atomic_and_rollback_safe(
    tmp_path: Path,
) -> None:
    path = kernel_paths(tmp_path).operational
    first = _artifact(tmp_path / "first.sqlite3", generation=1)
    second = _artifact(tmp_path / "second.sqlite3", generation=2)
    initialize_operational_database(path)
    assert load_cutover_control(path).state is CutoverState.ABSENT

    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=first,
        refresh_run_id="refresh-1",
    )
    transition_cutover(
        path,
        CutoverState.READY,
        integrity_digest=analytical_digest(first),
    )
    transition_cutover(
        path,
        CutoverState.ACTIVE,
        active_kernel_path=first,
        generation=1,
    )
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=second,
        refresh_run_id="refresh-2",
    )
    transition_cutover(
        path,
        CutoverState.READY,
        integrity_digest=analytical_digest(second),
    )
    transition_cutover(
        path,
        CutoverState.ACTIVE,
        active_kernel_path=second,
        generation=2,
    )

    restored = rollback_cutover(path)

    assert restored.state is CutoverState.ACTIVE
    assert restored.active_kernel_path == first
    assert restored.active_generation == 1
    assert restored.rollback_kernel_path == second


def test_failed_cutover_rejects_unbounded_failure_code(tmp_path: Path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=tmp_path / "staging.sqlite3",
        refresh_run_id="refresh-1",
    )

    with pytest.raises(ValueError, match="bounded failure code"):
        transition_cutover(
            path,
            CutoverState.FAILED,
            failure_code="x" * 65,
        )


def test_cutover_rejects_invalid_transition(tmp_path: Path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)

    with pytest.raises(ValueError, match="absent -> active"):
        transition_cutover(
            path,
            CutoverState.ACTIVE,
            active_kernel_path=tmp_path / "active.sqlite3",
            generation=1,
        )


def test_new_build_cannot_reuse_prior_integrity_digest(tmp_path: Path) -> None:
    path = kernel_paths(tmp_path).operational
    first = _artifact(tmp_path / "first.sqlite3", generation=1)
    second = _artifact(tmp_path / "second.sqlite3", generation=2)
    initialize_operational_database(path)
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=first,
        refresh_run_id="refresh-1",
    )
    transition_cutover(
        path,
        CutoverState.READY,
        integrity_digest=analytical_digest(first),
    )
    transition_cutover(
        path,
        CutoverState.ACTIVE,
        active_kernel_path=first,
        generation=1,
    )
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=second,
        refresh_run_id="refresh-2",
    )

    with pytest.raises(ValueError, match="ready requires"):
        transition_cutover(path, CutoverState.READY)


def test_ready_and_active_are_bound_to_one_validated_artifact(tmp_path: Path) -> None:
    path = kernel_paths(tmp_path).operational
    valid = _artifact(tmp_path / "valid.sqlite3", generation=1)
    other = _artifact(tmp_path / "other.sqlite3", generation=1)
    initialize_operational_database(path)
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=valid,
        refresh_run_id="refresh-1",
    )

    with pytest.raises(ValueError, match="digest"):
        transition_cutover(
            path,
            CutoverState.READY,
            integrity_digest="sha256:" + ("0" * 64),
        )
    transition_cutover(
        path,
        CutoverState.READY,
        integrity_digest=analytical_digest(valid),
    )
    with pytest.raises(ValueError, match="equal"):
        transition_cutover(
            path,
            CutoverState.ACTIVE,
            active_kernel_path=other,
            generation=1,
        )
    with pytest.raises(ValueError, match="contain generation"):
        transition_cutover(
            path,
            CutoverState.ACTIVE,
            active_kernel_path=valid,
            generation=2,
        )


@pytest.mark.parametrize("payload", [b"missing", b"not-a-sqlite-database"])
def test_ready_rejects_missing_or_corrupt_artifact(
    tmp_path: Path,
    payload: bytes,
) -> None:
    path = kernel_paths(tmp_path).operational
    staging = tmp_path / "staging.sqlite3"
    if payload != b"missing":
        staging.write_bytes(payload)
    initialize_operational_database(path)
    transition_cutover(
        path,
        CutoverState.BUILDING,
        staging_kernel_path=staging,
        refresh_run_id="refresh-1",
    )

    with pytest.raises(ValueError):
        transition_cutover(
            path,
            CutoverState.READY,
            integrity_digest="sha256:" + ("0" * 64),
        )


def test_legacy_cache_is_preserved_as_opaque_metadata_only(tmp_path: Path) -> None:
    path = kernel_paths(tmp_path).operational
    legacy = tmp_path / "codex-usage.sqlite3"
    legacy.write_bytes(b"legacy-schema-39-sentinel")
    initialize_operational_database(path)

    record_legacy_cache_metadata(path, legacy)

    assert load_cutover_control(path).legacy_cache_path == legacy
    assert legacy.read_bytes() == b"legacy-schema-39-sentinel"


def _artifact(path: Path, *, generation: int) -> Path:
    initialize_analytical_database(path)
    with short_writer_transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO generations(
                generation,
                source_revision_digest,
                created_at,
                high_water_digest,
                inserted_count,
                updated_count,
                deleted_count,
                canonical_count,
                excluded_count,
                parser_versions,
                integrity_status
            )
            VALUES (?, 'sha256:source', '2026-01-01T00:00:00Z',
                    'sha256:water', 0, 0, 0, 0, 0, '{}', 'valid')
            """,
            (generation,),
        )
    return path
