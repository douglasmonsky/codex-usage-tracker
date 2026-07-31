from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

import pytest

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
) -> list[dict[str, object]]:
    cursor = None
    rows: list[dict[str, object]] = []
    while True:
        page = _service().read(
            connection,
            _request(
                case,
                selector,
                direction=direction,
                limit=2,
                cursor=cursor,
            ),
        )
        rows.extend(dict(row) for row in page.rows)
        cursor = page.next_cursor
        if cursor is None:
            return rows


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
