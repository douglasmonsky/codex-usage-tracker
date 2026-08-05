from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

import codex_usage_tracker.agent_kernel.evidence.service as evidence_service
from codex_usage_tracker.agent_kernel.evidence.cursors import CursorCodec
from codex_usage_tracker.agent_kernel.evidence.service import (
    EvidenceContractError,
    EvidenceRequest,
    EvidenceService,
    EvidenceServiceError,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.published_v2 import (
    PUBLICATION_ID,
    publish_structural_snapshot,
    published_question_case,
)

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT = _ROOT / "config/agent-kernel/selector-provenance-v1.json"
_SECRET = b"ck08-evidence-service-synthetic-secret"
_FORBIDDEN_PLAN_MARKERS = (
    "SCAN stream",
    "MATERIALIZE model_calls_visible",
    "AUTOMATIC COVERING INDEX",
)
_TEMP_SORT_MARKER = "USE TEMP B-TREE FOR ORDER BY"
_PORTABLE_SESSION_SORT_VIEWS = frozenset({"timeline", "allowance_interval"})
_SESSION_LOOKUP = "SEARCH s USING PRIMARY KEY (session_id=?)"
_OCCURRENCE_LOOKUP = "SEARCH o USING PRIMARY KEY (occurrence_id=?) LEFT-JOIN"
_MANIFESTATION_LOOKUP = (
    "SEARCH sm USING INDEX source_manifestations_by_occurrence_key "
    "(manifestation_key=?) LEFT-JOIN"
)
_LIFECYCLE_LOOKUP = (
    "SEARCH lt USING INDEX evidence_lifecycle_by_session_order (session_id=?)"
)
_BOUND_HEAD_LOOKUP = "SEARCH bound_head USING PRIMARY KEY (singleton=?)"
_BOUND_HEAD_EXISTS_LOOKUP = (
    "SEARCH bound_head EXISTS USING PRIMARY KEY (singleton=?)"
)


def _service() -> EvidenceService:
    contract = json.loads(_CONTRACT.read_text(encoding="utf-8"))
    return EvidenceService(
        contract,
        CursorCodec(_SECRET, clock=lambda: 500),
        clock=lambda: 500,
    )


def _published(
    tmp_path: Path,
) -> tuple[sqlite3.Connection, dict[str, object], str]:
    original = next(
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] == "Q-OPS-04"
        and item["variant"] == "equal_time_event"
    )
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database = tmp_path / "database-v1.sqlite3"
    publish_structural_snapshot(
        tmp_path / "fixture",
        database,
        include_late_call=bool(profile["late_event"]),
        null_cached_tokens=bool(profile["missing_cached_input"]),
        variant_native_turn_id=str(mutation["native_turn_id"]),
    )
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    required = case["required_evidence"]
    assert isinstance(required, list)
    session_selector = next(
        str(item["selector"])
        for item in required
        if item["selector_kind"] == "session"
    )
    connection.execute("PRAGMA query_only = ON")
    return connection, case, session_selector


def _request(
    case: dict[str, object],
    selector: str,
    *,
    view: str = "timeline",
    direction: str = "forward",
    limit: int = 3,
    byte_limit: int = 16_384,
    cursor: str | None = None,
    publication_id: str = PUBLICATION_ID,
) -> EvidenceRequest:
    request = case["request"]
    assert isinstance(request, dict)
    return EvidenceRequest(
        selector=selector,
        view=view,
        direction=direction,
        limit=limit,
        byte_limit=byte_limit,
        cursor=cursor,
        publication_id=publication_id,
        parameters=request["parameters"],  # type: ignore[arg-type]
        gates=request["gates"],  # type: ignore[arg-type]
    )


def _all_pages(
    connection: sqlite3.Connection,
    case: dict[str, object],
    selector: str,
    *,
    direction: str,
    view: str = "timeline",
) -> list[dict[str, object]]:
    cursor = None
    rows: list[dict[str, object]] = []
    while True:
        page = _service().read(
            connection,
            _request(
                case,
                selector,
                view=view,
                direction=direction,
                limit=2,
                cursor=cursor,
            ),
        )
        rows.extend(dict(row) for row in page.rows)
        cursor = page.next_cursor
        if cursor is None:
            return rows


def _add_synthetic_activities(
    connection: sqlite3.Connection,
    selector: str,
    count: int,
) -> None:
    session_id = selector.partition(":")[2]
    turn = connection.execute(
        """
        SELECT turn_id, primary_occurrence_id
          FROM turns
         WHERE session_id = ?
         ORDER BY ordinal, turn_id
         LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    assert turn is not None
    turn_id, occurrence_id = str(turn[0]), str(turn[1])
    assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
    connection.execute("PRAGMA query_only = OFF")
    try:
        for index in range(count):
            activity_id = f"activity:physical:{index:05d}"
            identity_bytes = activity_id.encode("utf-8")
            connection.execute(
                """
                INSERT INTO identity_registry (
                  logical_id, entity_kind, identity_version, identity_cbor,
                  identity_sha256, first_seen_publication_id,
                  last_seen_publication_id
                ) VALUES (?, 'activity', 'v1', ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    identity_bytes,
                    hashlib.sha256(identity_bytes).hexdigest(),
                    PUBLICATION_ID,
                    PUBLICATION_ID,
                ),
            )
            event_order = 10_000 + index
            connection.execute(
                """
                INSERT INTO activities (
                  activity_id, session_id, turn_id, activity_kind,
                  lifecycle_state, state_basis, transition_version,
                  event_at_us, source_rank, source_order, event_kind_order,
                  transition_rank, primary_occurrence_id,
                  first_seen_publication_id, last_seen_publication_id
                ) VALUES (?, ?, ?, 'synthetic', 'succeeded', 'synthetic', 1,
                          ?, 0, ?, 50, 0, ?, ?, ?)
                """,
                (
                    activity_id,
                    session_id,
                    turn_id,
                    event_order,
                    event_order,
                    occurrence_id,
                    PUBLICATION_ID,
                    PUBLICATION_ID,
                ),
            )
        connection.commit()
    finally:
        connection.execute("PRAGMA query_only = ON")


def _add_unrelated_lifecycle_history(
    connection: sqlite3.Connection,
    count: int,
) -> None:
    """Add synthetic foreign-session lifecycle rows without changing target facts."""

    if count == 0:
        return
    target_session = str(
        connection.execute(
            "SELECT session_id FROM sessions ORDER BY session_id LIMIT 1"
        ).fetchone()[0]
    )
    occurrence_id = str(
        connection.execute(
            "SELECT occurrence_id FROM source_occurrences ORDER BY occurrence_id LIMIT 1"
        ).fetchone()[0]
    )
    project_id = str(
        connection.execute(
            "SELECT project_id FROM sessions WHERE session_id = ?",
            (target_session,),
        ).fetchone()[0]
    )
    foreign_session = "session:synthetic-unrelated-lifecycle"
    connection.execute("PRAGMA query_only = OFF")
    try:
        identity_bytes = foreign_session.encode("utf-8")
        connection.execute(
            """
            INSERT INTO identity_registry (
              logical_id, entity_kind, identity_version, identity_cbor,
              identity_sha256, first_seen_publication_id,
              last_seen_publication_id
            ) VALUES (?, 'session', 'v1', ?, ?, ?, ?)
            """,
            (
                foreign_session,
                identity_bytes,
                hashlib.sha256(identity_bytes).hexdigest(),
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
        connection.execute(
            """
            INSERT INTO sessions (
              session_id, adapter_native_session_key, identity_version,
              project_id, lifecycle_state, state_basis, transition_version,
              primary_occurrence_id, first_seen_publication_id,
              last_seen_publication_id
            ) VALUES (?, ?, 'v1', ?, 'unknown', 'synthetic', 0, ?, ?, ?)
            """,
            (
                foreign_session,
                "synthetic-unrelated-lifecycle",
                project_id,
                occurrence_id,
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
        lifecycle_rows = []
        for version in range(1, count + 1):
            transition_id = f"lifecycle-transition:synthetic-unrelated:{version:05d}"
            identity_bytes = transition_id.encode("utf-8")
            connection.execute(
                """
                INSERT INTO identity_registry (
                  logical_id, entity_kind, identity_version, identity_cbor,
                  identity_sha256, first_seen_publication_id,
                  last_seen_publication_id
                ) VALUES (?, 'lifecycle-transition', 'v1', ?, ?, ?, ?)
                """,
                (
                    transition_id,
                    identity_bytes,
                    hashlib.sha256(identity_bytes).hexdigest(),
                    PUBLICATION_ID,
                    PUBLICATION_ID,
                ),
            )
            lifecycle_rows.append(
                (
                    transition_id,
                    foreign_session,
                    "session",
                    "unknown",
                    "synthetic",
                    version,
                    1_000_000 + version,
                    0,
                    version,
                    10,
                    0,
                    occurrence_id,
                    None,
                    0,
                    PUBLICATION_ID,
                    foreign_session,
                )
            )
        connection.executemany(
            "INSERT INTO lifecycle_transitions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            lifecycle_rows,
        )
        connection.commit()
    finally:
        connection.execute("PRAGMA query_only = ON")


def _explain_rows(
    connection: sqlite3.Connection,
    view: str,
    direction: str,
    scope: Mapping[str, Any],
    cursor_order: tuple[Any, ...] | None,
) -> tuple[tuple[int, int, int, str], ...]:
    sql, parameters = evidence_service._page_statement(
        view,
        direction,
        scope,
        cursor_order,
        PUBLICATION_ID,
        7,
    )
    return tuple(
        (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)
    )


def _assert_unique_manifestation_lookup(connection: sqlite3.Connection) -> None:
    indexes = connection.execute("PRAGMA index_list(source_manifestations)").fetchall()
    matching = [
        row
        for row in indexes
        if str(row[1]) == "source_manifestations_by_occurrence_key"
    ]
    assert len(matching) == 1
    assert int(matching[0][2]) == 1
    columns = connection.execute(
        "PRAGMA index_info(source_manifestations_by_occurrence_key)"
    ).fetchall()
    assert [str(row[2]) for row in columns] == ["manifestation_key"]


def _is_session_branch_metadata(detail: str) -> bool:
    return detail == _BOUND_HEAD_EXISTS_LOOKUP or (
        detail.startswith("SCALAR SUBQUERY ")
        and detail.removeprefix("SCALAR SUBQUERY ").isdigit()
    )


def _descendants(
    rows: tuple[tuple[int, int, int, str], ...],
    node_id: int,
) -> tuple[tuple[int, int, int, str], ...]:
    children_by_parent: dict[int, list[tuple[int, int, int, str]]] = {}
    for row in rows:
        children_by_parent.setdefault(row[1], []).append(row)
    descendants: list[tuple[int, int, int, str]] = []
    pending = [node_id]
    while pending:
        parent = pending.pop()
        children = sorted(children_by_parent.get(parent, ()), key=lambda row: row[0])
        descendants.extend(children)
        pending.extend(row[0] for row in children)
    return tuple(descendants)


def _leftmost_branch(
    rows: tuple[tuple[int, int, int, str], ...],
    node_id: int,
) -> bool:
    rows_by_id = {row[0]: row for row in rows}
    children_by_parent: dict[int, list[tuple[int, int, int, str]]] = {}
    for row in rows:
        children_by_parent.setdefault(row[1], []).append(row)
    current = node_id
    while current in rows_by_id:
        parent = rows_by_id[current][1]
        siblings = sorted(children_by_parent.get(parent, ()), key=lambda row: row[0])
        if not siblings or siblings[0][0] != current:
            return False
        current = parent
    return True


def _session_branch_parent_candidates(
    rows: tuple[tuple[int, int, int, str], ...],
) -> tuple[int, ...]:
    children_by_parent: dict[int, list[tuple[int, int, int, str]]] = {}
    for row in rows:
        children_by_parent.setdefault(row[1], []).append(row)
    candidates: list[int] = []
    for parent, children in children_by_parent.items():
        ordered = sorted(children, key=lambda row: row[0])
        details = tuple(row[3] for row in ordered)
        required = (
            _SESSION_LOOKUP,
            _OCCURRENCE_LOOKUP,
            _MANIFESTATION_LOOKUP,
        )
        if any(details.count(detail) != 1 for detail in required):
            continue
        if details.count(_TEMP_SORT_MARKER) > 1:
            continue
        if any(
            detail not in required
            and detail != _TEMP_SORT_MARKER
            and not _is_session_branch_metadata(detail)
            for detail in details
        ):
            continue
        positions = {detail: details.index(detail) for detail in required}
        if not (
            positions[_SESSION_LOOKUP]
            < positions[_OCCURRENCE_LOOKUP]
            < positions[_MANIFESTATION_LOOKUP]
        ):
            continue
        marker_position = (
            details.index(_TEMP_SORT_MARKER)
            if _TEMP_SORT_MARKER in details
            else None
        )
        if marker_position is not None and marker_position <= positions[
            _MANIFESTATION_LOOKUP
        ]:
            continue
        metadata = [
            row
            for row in ordered
            if _is_session_branch_metadata(row[3])
        ]
        if len(metadata) > 1:
            continue
        for row in metadata:
            if row[3].startswith("SCALAR SUBQUERY "):
                descendants = _descendants(rows, row[0])
                assert len(descendants) == 1
                assert descendants[0][3] == _BOUND_HEAD_LOOKUP
        candidates.append(parent)
    return tuple(candidates)


def _assert_session_marker_branch_ownership(
    rows: tuple[tuple[int, int, int, str], ...],
) -> None:
    candidates = _session_branch_parent_candidates(rows)
    assert len(candidates) == 1, (candidates, rows)
    session_parent = candidates[0]
    assert _leftmost_branch(rows, session_parent), (session_parent, rows)
    markers = [row for row in rows if row[3] == _TEMP_SORT_MARKER]
    if markers:
        assert markers[0][1] == session_parent, (session_parent, markers, rows)


def _assert_page_plan_contract(
    connection: sqlite3.Connection,
    rows: tuple[tuple[int, int, int, str], ...],
    *,
    view: str,
    cursor_order: tuple[Any, ...] | None,
) -> None:
    details = tuple(row[3] for row in rows)
    assert not any(
        marker in "\n".join(details) for marker in _FORBIDDEN_PLAN_MARKERS
    ), details
    temp_markers = [detail for detail in details if "USE TEMP B-TREE" in detail]
    markers = [row for row in rows if row[3] == _TEMP_SORT_MARKER]
    allows_session_sort = (
        cursor_order is not None and view in _PORTABLE_SESSION_SORT_VIEWS
    )
    if view in _PORTABLE_SESSION_SORT_VIEWS:
        assert _LIFECYCLE_LOOKUP in details, details
    if not allows_session_sort:
        assert temp_markers == [], (view, cursor_order, details)
        return

    assert temp_markers in ([], [_TEMP_SORT_MARKER]), (view, cursor_order, details)
    assert len(markers) <= 1, (view, cursor_order, details)
    if not markers:
        _assert_session_marker_branch_ownership(rows)
        return

    _assert_session_marker_branch_ownership(rows)
    _assert_unique_manifestation_lookup(connection)


def test_evidence_contract_is_closed_and_bounded() -> None:
    with pytest.raises(EvidenceContractError, match="exactly one"):
        EvidenceRequest()
    with pytest.raises(EvidenceContractError, match="exactly one"):
        EvidenceRequest(
            selector="session:session:v1:synthetic",
            boundary_pair=(
                "allowance-observation:one",
                "allowance-observation:two",
            ),
        )
    with pytest.raises(EvidenceContractError, match="allowlisted"):
        EvidenceRequest(selector="session:session:v1:synthetic", view="raw")
    with pytest.raises(EvidenceContractError, match="at most 100"):
        EvidenceRequest(selector="session:session:v1:synthetic", limit=101)
    with pytest.raises(EvidenceContractError, match="forbidden key"):
        EvidenceRequest(
            selector="session:session:v1:synthetic",
            parameters={"sql": "SELECT 1"},
        )


def test_evidence_pages_are_query_only_keyset_bound_and_reversible(
    tmp_path: Path,
) -> None:
    connection, case, selector = _published(tmp_path)
    summary = _service().read(
        connection,
        _request(case, selector, view="summary"),
    )
    assert summary.rows == ()
    assert summary.resolved_selector["selector_kind"] == "session"
    assert summary.publication["id"] == PUBLICATION_ID
    assert summary.response_bytes == len(
        json.dumps(
            summary.to_mapping(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )

    forward = _all_pages(
        connection,
        case,
        selector,
        direction="forward",
    )
    backward = _all_pages(
        connection,
        case,
        selector,
        direction="backward",
    )
    connection.close()

    forward_keys = [tuple(row["order_key"]) for row in forward]
    backward_keys = [tuple(row["order_key"]) for row in backward]
    assert forward_keys == sorted(forward_keys)
    assert backward_keys == list(reversed(forward_keys))
    assert len(forward_keys) == len(set(forward_keys))
    token_row = next(row for row in forward if "tokens" in row)
    tokens = token_row["tokens"]
    assert isinstance(tokens, Mapping)
    assert {
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
    } <= set(tokens)


def test_evidence_page_shrinks_to_final_encoded_byte_limit(
    tmp_path: Path,
) -> None:
    connection, case, selector = _published(tmp_path)
    page = _service().read(
        connection,
        _request(case, selector, limit=10, byte_limit=7_000),
    )
    encoded = json.dumps(
        page.to_mapping(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    connection.close()

    assert 0 < len(page.rows) < 10
    assert page.has_more is True
    assert page.next_cursor is not None
    assert page.response_bytes == len(encoded) <= 7_000


def test_evidence_rejects_cursor_tamper_replacement_and_writer_connection(
    tmp_path: Path,
) -> None:
    connection, case, selector = _published(tmp_path)
    first = _service().read(
        connection,
        _request(case, selector, limit=1),
    )
    assert first.next_cursor is not None
    version, payload, signature = first.next_cursor.split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = ".".join((version, payload, signature))
    with pytest.raises(ValueError, match="signature"):
        _service().read(
            connection,
            _request(case, selector, limit=1, cursor=tampered),
        )

    with pytest.raises(EvidenceServiceError, match="stale or replaced"):
        _service().read(
            connection,
            _request(
                case,
                selector,
                publication_id="publication:v1:replacement",
            ),
        )

    connection.execute("PRAGMA query_only = OFF")
    with pytest.raises(EvidenceServiceError, match="query_only"):
        _service().read(connection, _request(case, selector))
    connection.close()


def test_evidence_compatible_allowance_boundaries_are_typed_and_windowless(
    tmp_path: Path,
) -> None:
    connection, case, _ = _published(tmp_path)
    observations = connection.execute(
        """
        SELECT observation_id
          FROM allowance_observations
         ORDER BY observation_ordinal, observation_id
         LIMIT 2
        """
    ).fetchall()
    assert len(observations) == 2
    request = case["request"]
    assert isinstance(request, dict)
    page = _service().read(
        connection,
        EvidenceRequest(
            boundary_pair=tuple(
                f"allowance-observation:{row[0]}" for row in observations
            ),
            view="allowance_interval",
            publication_id=PUBLICATION_ID,
            parameters=request["parameters"],  # type: ignore[arg-type]
            gates=request["gates"],  # type: ignore[arg-type]
        ),
    )
    duplicate = f"allowance-observation:{observations[0][0]}"
    with pytest.raises(EvidenceServiceError, match="distinct observations"):
        _service().read(
            connection,
            EvidenceRequest(
                boundary_pair=(duplicate, duplicate),
                view="allowance_interval",
                publication_id=PUBLICATION_ID,
                parameters=request["parameters"],  # type: ignore[arg-type]
                gates=request["gates"],  # type: ignore[arg-type]
            ),
        )
    connection.close()

    assert page.resolved_selector["selector_kind"] == "allowance_boundary_pair"
    assert len(page.boundaries) == 2
    assert page.summary["scope"]["kind"] == "interval"


def test_evidence_summary_resolves_all_14_selector_and_six_provenance_kinds(
    tmp_path: Path,
) -> None:
    selected: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for case in build_question_scenarios()["cases"]:
        for item in case["required_evidence"]:
            selected.setdefault(str(item["selector_kind"]), (case, item))
    assert len(selected) == 14

    provenance_kinds: set[str] = set()
    for index, (kind, (original, original_evidence)) in enumerate(
        sorted(selected.items())
    ):
        profile = original["source_profile"]
        mutation = original["semantic_mutation"]
        case_root = tmp_path / f"{index:02d}-{kind}"
        database = case_root / "database-v1.sqlite3"
        publish_structural_snapshot(
            case_root / "fixture",
            database,
            include_late_call=bool(profile["late_event"]),
            null_cached_tokens=bool(profile["missing_cached_input"]),
            variant_native_turn_id=str(mutation["native_turn_id"]),
        )
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        case = published_question_case(connection, original)
        connection.execute("PRAGMA query_only = ON")
        evidence = next(
            item
            for item in case["required_evidence"]
            if item["role"] == original_evidence["role"]
        )
        request = case["request"]
        assert isinstance(request, dict)
        parameters = request["parameters"]
        selector_role = "selector"
        plan_id = "evidence-page"
        if kind == "window":
            selector_role = str(original_evidence["role"])
            plan_id = str(request["plan_id"])
        page = _service().read(
            connection,
            EvidenceRequest(
                selector=str(evidence["selector"]),
                selector_role=selector_role,
                view="summary",
                publication_id=PUBLICATION_ID,
                plan_id=plan_id,
                parameters=parameters,  # type: ignore[arg-type]
                gates=request["gates"],  # type: ignore[arg-type]
            ),
        )
        connection.close()
        assert page.resolved_selector["selector_kind"] == kind
        provenance_kinds.add(str(page.resolved_selector["provenance_kind"]))

    assert provenance_kinds == {
        "configured_artifact",
        "derived_boundary_pair",
        "publication_commit",
        "request_derivation",
        "source_inventory",
        "source_occurrence",
    }


def test_first_and_deep_physical_plans_prune_unbounded_shapes(
    tmp_path: Path,
) -> None:
    connection, _case, selector = _published(tmp_path)
    scope = {
        "kind": "session",
        "logical_id": selector.partition(":")[2],
        "start_us": None,
        "end_us": None,
    }
    deep_order = (0, 0, 0, 0, 0, "activity:physical:00000", 0)
    for view in (
        "timeline",
        "calls",
        "tools",
        "resources",
        "state_changes",
        "allowance_interval",
    ):
        for direction in ("forward", "backward"):
            for cursor_order in (None, deep_order):
                rows = _explain_rows(connection, view, direction, scope, cursor_order)
                _assert_page_plan_contract(
                    connection,
                    rows,
                    view=view,
                    cursor_order=cursor_order,
                )
    connection.close()


def test_session_marker_branch_ownership_rejects_structural_mutations(
    tmp_path: Path,
) -> None:
    connection, _case, selector = _published(tmp_path)
    try:
        scope = {
            "kind": "session",
            "logical_id": selector.partition(":")[2],
            "start_us": None,
            "end_us": None,
        }
        deep_order = (0, 0, 0, 0, 0, "activity:physical:00000", 0)
        rows = _explain_rows(
            connection,
            "timeline",
            "forward",
            scope,
            deep_order,
        )
        markers = [row for row in rows if row[3] == _TEMP_SORT_MARKER]
        if not markers:
            pytest.skip("SQLite build emitted the portable plan marker-free")
        marker = markers[0]

        def assert_rejected(
            mutated: tuple[tuple[int, int, int, str], ...],
        ) -> None:
            with pytest.raises(AssertionError):
                _assert_page_plan_contract(
                    connection,
                    mutated,
                    view="timeline",
                    cursor_order=deep_order,
                )

        calls_parent = next(
            row[1]
            for row in rows
            if row[3].startswith("SEARCH mc USING INDEX")
        )
        tools_parent = next(
            row[1]
            for row in rows
            if row[3].startswith("SEARCH ti USING INDEX")
        )
        lifecycle_parent = next(
            row[1] for row in rows if row[3] == _LIFECYCLE_LOOKUP
        )
        for foreign_parent in (calls_parent, tools_parent, lifecycle_parent, 0):
            assert_rejected(
                tuple(
                    (row[0], foreign_parent, row[2], row[3])
                    if row[0] == marker[0]
                    else row
                    for row in rows
                )
            )

        assert_rejected(
            rows
            + ((max(row[0] for row in rows) + 1, marker[1], 0, _TEMP_SORT_MARKER),)
        )
        assert_rejected(
            tuple(
                (row[0], row[1], row[2], "SCAN o")
                if row[3] == _OCCURRENCE_LOOKUP
                else row
                for row in rows
            )
        )
        ambiguous_rows = tuple(
            row
            for row in rows
            if row[1] != calls_parent
            or row[3]
            in {
                _SESSION_LOOKUP,
                _OCCURRENCE_LOOKUP,
                _MANIFESTATION_LOOKUP,
            }
            or _is_session_branch_metadata(row[3])
        )
        assert_rejected(ambiguous_rows)
    finally:
        connection.close()


def test_activity_scale_keeps_decode_and_work_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decoded_counts: list[int] = []
    progress_counts: list[int] = []
    original_typed_row = evidence_service._typed_row

    def count_decodes(row: Mapping[str, Any]) -> dict[str, Any]:
        decoded_counts[-1] += 1
        return original_typed_row(row)

    monkeypatch.setattr(evidence_service, "_typed_row", count_decodes)
    for count in (2_000, 10_000):
        connection, case, selector = _published(tmp_path / f"activities-{count}")
        _add_synthetic_activities(connection, selector, count)
        rows = _explain_rows(
            connection,
            "timeline",
            "forward",
            {
                "kind": "session",
                "logical_id": selector.partition(":")[2],
                "start_us": None,
                "end_us": None,
            },
            None,
        )
        _assert_page_plan_contract(
            connection,
            rows,
            view="timeline",
            cursor_order=None,
        )
        callback_count = 0

        def progress() -> int:
            nonlocal callback_count
            callback_count += 1
            return 0

        decoded_counts.append(0)
        connection.set_progress_handler(progress, 100)
        try:
            page = _service().read(
                connection,
                _request(case, selector, view="timeline", limit=7),
            )
        finally:
            connection.set_progress_handler(None, 0)
        progress_counts.append(callback_count)
        connection.close()
        assert len(page.rows) == 7
        assert page.has_more is True
        assert page.next_cursor is not None
        assert decoded_counts[-1] == 8

    assert progress_counts[0] > 0
    assert progress_counts[1] <= progress_counts[0] * 4
    assert max(progress_counts) <= 200


def test_foreign_lifecycle_history_does_not_change_session_page_work(
    tmp_path: Path,
) -> None:
    callback_counts: list[int] = []
    baseline_rows: list[dict[str, object]] | None = None
    for count in (0, 1_000, 5_000):
        connection, case, selector = _published(tmp_path / f"foreign-{count}")
        _add_unrelated_lifecycle_history(connection, count)
        scope = {
            "kind": "session",
            "logical_id": selector.partition(":")[2],
            "start_us": None,
            "end_us": None,
        }
        for direction in ("forward", "backward"):
            for cursor_order in (None, (0, 0, 0, 0, 0, "activity:physical:00000", 0)):
                rows = _explain_rows(
                    connection,
                    "timeline",
                    direction,
                    scope,
                    cursor_order,
                )
                _assert_page_plan_contract(
                    connection,
                    rows,
                    view="timeline",
                    cursor_order=cursor_order,
                )
        callback_count = 0

        def progress() -> int:
            nonlocal callback_count
            callback_count += 1
            return 0

        connection.set_progress_handler(progress, 100)
        try:
            page = _service().read(
                connection,
                _request(case, selector, view="timeline", limit=7),
            )
        finally:
            connection.set_progress_handler(None, 0)
        callback_counts.append(callback_count)
        rows = [dict(row) for row in page.rows]
        if baseline_rows is None:
            baseline_rows = rows
        assert rows == baseline_rows
        assert len(rows) <= 7
        connection.close()

    assert callback_counts[0] > 0
    assert callback_counts[1:] == [callback_counts[0], callback_counts[0]]


def test_rate_card_pages_remain_valid_empty_and_query_only(
    tmp_path: Path,
) -> None:
    connection, case, _selector = _published(tmp_path)
    digest = connection.execute(
        "SELECT rate_card_digest FROM publications WHERE publication_id = ?",
        (PUBLICATION_ID,),
    ).fetchone()[0]
    selector = f"rate-card:{digest}"
    request = _request(case, selector, view="timeline", limit=7)
    summary = _service().read(connection, _request(case, selector, view="summary"))
    assert summary.resolved_selector["selector_kind"] == "rate_card"
    assert summary.summary["facts"]
    for direction in ("forward", "backward"):
        page = _service().read(
            connection,
            replace_request_direction(request, direction),
        )
        assert page.rows == ()
        assert page.has_more is False
        assert page.next_cursor is None
    connection.close()


def test_calls_pages_match_independent_base_and_tail_order(
    tmp_path: Path,
) -> None:
    connection, case, selector = _published(tmp_path)
    session_id = selector.partition(":")[2]
    base_and_tail = connection.execute(
        """
        SELECT call_id, event_at_us, source_rank, source_order,
               event_kind_order, transition_rank
          FROM model_calls
         WHERE session_id = ?
        UNION ALL
        SELECT call_id, event_at_us, source_rank, source_order,
               event_kind_order, transition_rank
          FROM model_call_tail
         WHERE session_id = ?
        """,
        (session_id, session_id),
    ).fetchall()

    def order_key(row: sqlite3.Row) -> tuple[Any, ...]:
        event_at_us = row[1]
        return (
            1 if event_at_us is None else 0,
            0 if event_at_us is None else event_at_us,
            int(row[2]),
            int(row[3]),
            int(row[4]),
            str(row[0]),
            int(row[5]),
        )

    expected = [
        (str(row[0]), *order_key(row))
        for row in sorted(base_and_tail, key=order_key)
    ]
    forward = _all_pages(
        connection,
        case,
        selector,
        direction="forward",
        view="calls",
    )
    backward = _all_pages(
        connection,
        case,
        selector,
        direction="backward",
        view="calls",
    )
    connection.close()
    observed = [(str(row["logical_id"]), *tuple(row["order_key"])) for row in forward]
    assert observed == expected
    assert len(observed) == len(set(observed))
    assert [str(row["logical_id"]) for row in backward] == [
        str(row["logical_id"]) for row in reversed(forward)
    ]


def replace_request_direction(request: EvidenceRequest, direction: str) -> EvidenceRequest:
    return EvidenceRequest(
        selector=request.selector,
        boundary_pair=request.boundary_pair,
        selector_role=request.selector_role,
        view=request.view,
        direction=direction,
        limit=request.limit,
        byte_limit=request.byte_limit,
        cursor=request.cursor,
        publication_id=request.bound_publication_id,
        plan_id=request.plan_id,
        plan_version=request.plan_version,
        parameters=request.parameters,
        gates=request.gates,
    )
