#!/usr/bin/env python3
"""Qualify bounded EvidenceService pages at the frozen synthetic scales.

The scale copy is deliberately query-only evidence.  A compact, publication-
valid structural-v2 snapshot is built with the real fixture publisher, then
the temporary copy receives deterministic body-free model-call facts so the
two frozen call counts can be exercised without reading or persisting local
Codex data.  The publication receipt is retained as the snapshot binding; the
temporary augmentation is never presented as a new publication.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import platform
import resource
import sqlite3
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import codex_usage_tracker.agent_kernel.evidence.service as evidence_service  # noqa: E402
from codex_usage_tracker.agent_kernel.evidence.cursors import (  # noqa: E402
    CursorCodec,
    CursorTamperedError,
)
from codex_usage_tracker.agent_kernel.evidence.service import (  # noqa: E402
    EVIDENCE_VIEWS,
    MAX_EVIDENCE_BYTES,
    MAX_EVIDENCE_LIMIT,
    EvidenceRequest,
    EvidenceService,
    EvidenceServiceError,
)
from tests.agent_kernel.evidence.test_service import (  # noqa: E402
    _assert_page_plan_contract,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (  # noqa: E402
    build_question_scenarios,
)
from tests.agent_kernel.fixtures.published_v2 import (  # noqa: E402
    PUBLICATION_ID,
    publish_structural_snapshot,
    published_question_case,
)

SCHEMA = "codex-usage-tracker.evidence-scale-qualification.v1"
DEPENDENCY_SHA = "d1c9fd745b7a273d2f68cbeb1f18f1302d59f883"
OUTPUT = ROOT / "docs" / "decisions" / "evidence" / "ck08r3" / "evidence-scale-qualification.json"
GATES = ROOT / "docs" / "decisions" / "evidence" / "ck08r0" / "corrective-gates-v1.json"
R3A_AUTHORITY = ROOT / "docs" / "decisions" / "evidence" / "ck08r3a" / "evidence-service-supersession-authority.json"
LANE_SCHEMA = GATES.with_name("corrective-lane-evidence-v1.schema.json")
CURSOR_SECRET = b"ck08r3-synthetic-evidence-scale-secret"
PAGE_LIMIT = MAX_EVIDENCE_LIMIT
CALL_TAIL_CAPACITY = 32_000
SCALE_BATCH_SIZE = 10_000
SQL_P95_BUDGET_MS = 250.0
SERVICE_P95_BUDGET_MS = 750.0
PROFILE_NAMES = ("standard", "production")
SELECTOR_SCOPE_KINDS = (
    "allowance_interval",
    "allowance_observation",
    "call",
    "model_profile",
    "project",
    "publication",
    "rate_card",
    "resource",
    "session",
    "source_manifestation",
    "state_change",
    "tool",
    "turn",
    "window",
)
PAGED_VIEWS = tuple(view for view in EVIDENCE_VIEWS if view != "summary")
_BASE_TIME_US = 1_767_225_600_000_000
_HISTORICAL_BLOCKER_DIGEST = "ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471"

# These are the exact selected CK-08R3A consumer/support bytes at the accepted
# exact-main base.  They are checked before a measurement so a result can
# never silently drift onto a different consumer or fixture seam.
FROZEN_RUNTIME_DEPENDENCIES = {
    "src/codex_usage_tracker/agent_kernel/evidence/service.py": "4458ffb03adeed838fcda992747dbaeb192ccf59728b3a54e1527abc4d0651fb",
    "src/codex_usage_tracker/agent_kernel/evidence/cursors.py": "49ff796a86bea4908179468684902b360447746a6eceb4293d6f77a6d202ee13",
    "config/agent-kernel/selector-provenance-v1.json": "1a5ad492d7684b8050a71606af918d0e5964fffd32826c5ae0479d829131b41b",
    "src/codex_usage_tracker/agent_kernel/storage/analytical.sql": "34b6aab813dbd520f1894ac3ccbce1a1b3ff4552a11f0a83597a897a0c8f7486",
    "src/codex_usage_tracker/agent_kernel/storage/schema.py": "9850a431729c7eb8d5347278d0434f0849d1843297645547ee2dcd66a0359b77",
    "tests/agent_kernel/fixtures/oracles/cases_v2.py": "4ab32f4f924aef5f71e3b3d48478e5ae33eb86736a3b75de4b52621f4dae679b",
    "tests/agent_kernel/fixtures/published_v2.py": "eca815c5a47067bdc56759018e12fd7a25f446eb6d716236869cbef875ce8515",
    "tests/agent_kernel/evidence/test_service.py": "bc01c3149101f0fd6c787e23a00c7bd2b2ec21628e8508223b8828df1f13390b",
}


class QualificationFailure(RuntimeError):
    """A first fail-closed scale failure that must be retained in evidence."""

    def __init__(self, gate: str, profile: str, reason: str) -> None:
        super().__init__(reason)
        self.gate = gate
        self.profile = profile
        self.reason = reason

    def as_mapping(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "stage": "scale",
            "profile": self.profile,
            "reason": self.reason,
            "admission": "none",
            "production_execution_skipped": self.profile == "standard",
            "required_follow_up": "Retain the first failure and route the physical or fixture defect separately.",
        }


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one object")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_value(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _p95(samples: Sequence[float]) -> float:
    if not samples:
        raise ValueError("cannot calculate p95 without samples")
    ordered = sorted(samples)
    return ordered[((95 * len(ordered) + 99) // 100) - 1]


def _rss_bytes() -> int:
    maximum = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(maximum if platform.system() == "Darwin" else maximum * 1024)


def _load_authority() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    gates = _json(GATES)
    lane = next(item for item in gates["lanes"] if item["id"] == "CK-08R3")
    expected_schema = {
        "schema": SCHEMA,
        "path": "docs/decisions/evidence/ck08r0/corrective-lane-evidence-v1.schema.json",
        "sha256": _sha(LANE_SCHEMA),
        "definition": "#/$defs/evidenceScale",
    }
    if lane["evidence_schema"] != expected_schema:
        raise ValueError("CK-08R3 evidence schema authority is stale")
    if gates["scale"]["sample_count"] != 5:
        raise ValueError("CK-08R3 requires exactly five timing samples")
    if gates["scale"]["evidence"] != {
        "maximum_rows": MAX_EVIDENCE_LIMIT,
        "maximum_bytes": MAX_EVIDENCE_BYTES,
        "first_and_deep_pages_required": True,
        "exact_count_forbidden": True,
    }:
        raise ValueError("CK-08R3 evidence budgets differ from corrective-gates-v1")

    authority = _json(R3A_AUTHORITY)
    selected = authority["selected_successor"]
    selected_service = next(
        item
        for item in selected["required_artifacts"]
        if item["path"] == "src/codex_usage_tracker/agent_kernel/evidence/service.py"
    )
    if selected_service["sha256"] != FROZEN_RUNTIME_DEPENDENCIES[selected_service["path"]]:
        raise ValueError("CK-08R3A selected EvidenceService digest is not the frozen seam")
    for relative_path, expected_sha in FROZEN_RUNTIME_DEPENDENCIES.items():
        actual_sha = _sha(ROOT / relative_path)
        if actual_sha != expected_sha:
            raise ValueError(f"frozen CK-08R3 runtime dependency stale: {relative_path}")

    receipts: list[dict[str, Any]] = []
    for name in PROFILE_NAMES:
        fixture = gates["scale"]["fixtures"][name]
        path = ROOT / fixture["path"]
        actual_sha = _sha(path)
        if actual_sha != fixture["sha256"]:
            raise ValueError(f"{name} corrective scale profile is stale")
        profile = _json(path)
        if profile["model_calls"] != fixture["model_calls"]:
            raise ValueError(f"{name} profile model-call count differs from authority")
        if profile["seed"] != fixture["seed"] or profile["history_days"] != fixture["history_days"]:
            raise ValueError(f"{name} profile seed or history differs from authority")
        receipts.append(
            {
                "name": name,
                "path": fixture["path"],
                "sha256": actual_sha,
                "model_calls": int(fixture["model_calls"]),
                "seed": int(fixture["seed"]),
                "history_days": int(fixture["history_days"]),
                "source_manifestations": int(profile["source_manifestations"]),
                "semantic_cases": list(profile["semantic_cases"]),
                "publication_receipt_required": True,
            }
        )
    return gates, receipts


def _service() -> EvidenceService:
    return EvidenceService(
        _json(ROOT / "config/agent-kernel/selector-provenance-v1.json"),
        CursorCodec(CURSOR_SECRET, clock=lambda: 500),
        clock=lambda: 500,
    )


def _published_session(
    root: Path,
    *,
    variant: str = "stable_rebuild_selector",
) -> tuple[sqlite3.Connection, dict[str, Any], str, dict[str, Any]]:
    original = next(
        item
        for item in build_question_scenarios()["cases"]
        if item["question_id"] == "Q-OPS-04" and item["variant"] == variant
    )
    profile = original["source_profile"]
    mutation = original["semantic_mutation"]
    database = root / "database-v1.sqlite3"
    receipt = publish_structural_snapshot(
        root / "fixture",
        database,
        include_late_call=bool(profile["late_event"]),
        null_cached_tokens=bool(profile["missing_cached_input"]),
        variant_native_turn_id=str(mutation["native_turn_id"]),
    )
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    case = published_question_case(connection, original)
    selector = next(
        str(item["selector"])
        for item in case["required_evidence"]
        if item["selector_kind"] == "session"
    )
    connection.execute("PRAGMA query_only = ON")
    return connection, case, selector, {
        "publication_id": PUBLICATION_ID,
        "artifact_manifest_sha256": str(receipt["artifact_manifest_sha256"]),
        "schema_contract_sha256": str(
            connection.execute(
                "SELECT schema_contract_sha256 FROM publications WHERE publication_id = ?",
                (PUBLICATION_ID,),
            ).fetchone()[0]
        ),
        "status": str(
            connection.execute(
                "SELECT status FROM publications WHERE publication_id = ?",
                (PUBLICATION_ID,),
            ).fetchone()[0]
        ),
    }


def _request(
    case: Mapping[str, Any],
    selector: str,
    *,
    view: str,
    direction: str,
    selector_role: str = "selector",
    plan_id: str = "evidence-page",
    limit: int = PAGE_LIMIT,
    byte_limit: int = MAX_EVIDENCE_BYTES,
    cursor: str | None = None,
    publication_id: str | None = PUBLICATION_ID,
    expected_publication_id: str | None = None,
) -> EvidenceRequest:
    request = case["request"]
    return EvidenceRequest(
        selector=selector,
        selector_role=selector_role,
        view=view,
        direction=direction,
        limit=limit,
        byte_limit=byte_limit,
        cursor=cursor,
        publication_id=publication_id,
        expected_publication_id=expected_publication_id,
        plan_id=plan_id,
        parameters=request["parameters"],
        gates=request["gates"],
    )


def _explain(
    connection: sqlite3.Connection,
    *,
    view: str,
    direction: str,
    scope: Mapping[str, Any],
    cursor_order: tuple[Any, ...] | None,
    publication_id: str,
) -> tuple[str, tuple[Any, ...], tuple[tuple[int, int, int, str], ...]]:
    sql, parameters = evidence_service._page_statement(
        view,
        direction,
        scope,
        cursor_order,
        publication_id,
        PAGE_LIMIT,
    )
    rows = tuple(
        (int(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)
    )
    _assert_page_plan_contract(
        connection,
        rows,
        view=view,
        cursor_order=cursor_order,
    )
    if "COUNT(" in sql.upper() or "LIMIT ?" not in sql:
        raise QualificationFailure(
            "exact_count_or_limit_contract",
            "unknown",
            "page SQL must use LIMIT plus one and must not request exact count",
        )
    return sql, parameters, rows


def _insert_scale_calls(
    connection: sqlite3.Connection,
    *,
    profile_name: str,
    target_calls: int,
    session_id: str,
) -> dict[str, Any]:
    visible_before = int(
        connection.execute(
            "SELECT COUNT(*) FROM model_calls_visible WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    )
    if visible_before > target_calls:
        raise ValueError(f"base publication already exceeds {profile_name} scale")
    remaining = target_calls - visible_before
    if remaining == 0:
        return {"visible_before": visible_before, "inserted": 0, "visible_after": visible_before}

    template_row = connection.execute("SELECT * FROM model_call_tail LIMIT 1").fetchone()
    if template_row is None:
        raise ValueError("synthetic publication has no model-call template")
    template = dict(template_row)
    occurrence_template_row = connection.execute(
        "SELECT * FROM source_occurrences LIMIT 1"
    ).fetchone()
    if occurrence_template_row is None:
        raise ValueError("synthetic publication has no occurrence template")
    occurrence_template = dict(occurrence_template_row)
    tail_columns = [row[1] for row in connection.execute("PRAGMA table_info(model_call_tail)")]
    base_columns = [row[1] for row in connection.execute("PRAGMA table_info(model_calls)")]
    occurrence_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(source_occurrences)")
    ]
    profile_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(model_profiles)")
    ]
    existing_tail = int(
        connection.execute(
            "SELECT COUNT(*) FROM model_call_tail WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    )
    max_tail_ordinal = int(
        connection.execute("SELECT COALESCE(MAX(tail_ordinal), 0) FROM model_call_tail").fetchone()[0]
    )
    tail_capacity = CALL_TAIL_CAPACITY - max_tail_ordinal
    if tail_capacity < 0:
        raise ValueError("synthetic publication tail exceeds the accepted 32,000-row bound")
    tail_count = min(remaining, tail_capacity)
    base_count = remaining - tail_count
    if max_tail_ordinal + tail_count > CALL_TAIL_CAPACITY:
        raise ValueError("synthetic scale would exceed the accepted tail bound")

    scale_profile_id = f"model-profile:ck08r3-scale:{profile_name}"
    scale_identity_version = "synthetic-evidence-scale-v1"
    if connection.execute(
        "SELECT 1 FROM model_profiles WHERE model_profile_id = ?",
        (scale_profile_id,),
    ).fetchone() is not None:
        raise ValueError("synthetic scale profile identity already exists")
    profile_template_row = connection.execute(
        "SELECT * FROM model_profiles LIMIT 1"
    ).fetchone()
    if profile_template_row is None:
        raise ValueError("synthetic publication has no model-profile template")
    profile_row = dict(profile_template_row)
    profile_row["model_profile_id"] = scale_profile_id
    profile_row["model"] = "synthetic-scale"
    occurrence_record_base = int(
        connection.execute(
            "SELECT COALESCE(MAX(record_ordinal), 0) FROM source_occurrences"
        ).fetchone()[0]
    ) + 1
    occurrence_byte_base = int(
        connection.execute(
            "SELECT COALESCE(MAX(byte_end), 0) FROM source_occurrences"
        ).fetchone()[0]
    ) + 1_000
    identity_insert = (
        "INSERT INTO identity_registry "
        "(logical_id, entity_kind, identity_version, identity_cbor, identity_sha256, "
        "first_seen_publication_id, last_seen_publication_id) VALUES (?, ?, ?, ?, ?, ?, ?)"
    )

    connection.execute("PRAGMA query_only = OFF")
    try:
        profile_identity = f"identity:{scale_profile_id}".encode()
        connection.execute(
            identity_insert,
            (
                scale_profile_id,
                "model_profile",
                scale_identity_version,
                profile_identity,
                hashlib.sha256(profile_identity).hexdigest(),
                PUBLICATION_ID,
                PUBLICATION_ID,
            ),
        )
        connection.execute(
            f"INSERT INTO model_profiles ({','.join(profile_columns)}) "
            f"VALUES ({','.join('?' for _ in profile_columns)})",
            tuple(profile_row[column] for column in profile_columns),
        )

        def insert_rows(table: str, columns: list[str], start: int, count: int, storage_class: str) -> None:
            if count == 0:
                return
            placeholders = ",".join("?" for _ in columns)
            statement = (
                f"INSERT INTO {table} ({','.join(columns)}) "
                f"VALUES ({placeholders})"
            )
            identity_values: list[tuple[Any, ...]] = []
            occurrence_values: list[tuple[Any, ...]] = []
            location_values: list[tuple[Any, ...]] = []
            values: list[tuple[Any, ...]] = []

            def flush() -> None:
                if not values:
                    return
                connection.executemany(identity_insert, identity_values)
                connection.executemany(
                    "INSERT INTO source_occurrences "
                    f"({','.join(occurrence_columns)}) "
                    f"VALUES ({','.join('?' for _ in occurrence_columns)})",
                    occurrence_values,
                )
                connection.executemany(
                    "INSERT INTO model_call_locations (call_id, storage_class) VALUES (?, ?)",
                    location_values,
                )
                connection.executemany(statement, values)
                identity_values.clear()
                occurrence_values.clear()
                location_values.clear()
                values.clear()

            for offset in range(count):
                ordinal = start + offset
                row = dict(template)
                call_id = f"call:ck08r3:{profile_name}:{ordinal:07d}"
                occurrence_id = f"source-occurrence:ck08r3:{profile_name}:{ordinal:07d}"
                row["call_id"] = call_id
                row["adapter_native_call_key"] = f"ck08r3-{profile_name}-{ordinal:07d}"
                row["session_id"] = session_id
                row["model_profile_id"] = scale_profile_id
                row["event_at_us"] = _BASE_TIME_US + ordinal
                row["source_order"] = _BASE_TIME_US + ordinal
                row["storage_class"] = storage_class
                row["primary_occurrence_id"] = occurrence_id
                if table == "model_call_tail":
                    row["tail_ordinal"] = max_tail_ordinal + offset + 1
                occurrence = dict(occurrence_template)
                occurrence["occurrence_id"] = occurrence_id
                occurrence["semantic_logical_id"] = call_id
                occurrence["record_ordinal"] = occurrence_record_base + ordinal
                occurrence["byte_start"] = occurrence_byte_base + (ordinal * 2)
                occurrence["byte_end"] = occurrence_byte_base + (ordinal * 2) + 1
                occurrence["first_seen_publication_id"] = PUBLICATION_ID
                call_identity = f"identity:{call_id}".encode()
                occurrence_identity = f"identity:{occurrence_id}".encode()
                identity_values.append(
                    (
                        call_id,
                        "model_call",
                        scale_identity_version,
                        call_identity,
                        hashlib.sha256(call_identity).hexdigest(),
                        PUBLICATION_ID,
                        PUBLICATION_ID,
                    )
                )
                identity_values.append(
                    (
                        occurrence_id,
                        "source_occurrence",
                        scale_identity_version,
                        occurrence_identity,
                        hashlib.sha256(occurrence_identity).hexdigest(),
                        PUBLICATION_ID,
                        PUBLICATION_ID,
                    )
                )
                occurrence_values.append(
                    tuple(occurrence[column] for column in occurrence_columns)
                )
                location_values.append((call_id, storage_class))
                values.append(tuple(row[column] for column in columns))
                if len(values) == SCALE_BATCH_SIZE:
                    flush()
            flush()

        first_ordinal = visible_before
        insert_rows("model_call_tail", tail_columns, first_ordinal, tail_count, "tail")
        insert_rows("model_calls", base_columns, first_ordinal + tail_count, base_count, "base")
        connection.commit()
    finally:
        connection.execute("PRAGMA query_only = ON")

    visible_after = int(
        connection.execute(
            "SELECT COUNT(*) FROM model_calls_visible WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]
    )
    if visible_after != target_calls:
        raise ValueError(
            f"{profile_name} synthetic model-call count {visible_after} != {target_calls}"
        )
    return {
        "visible_before": visible_before,
        "inserted": remaining,
        "inserted_tail": tail_count,
        "inserted_base": base_count,
        "tail_before": existing_tail,
        "tail_after": int(
            connection.execute(
                "SELECT COUNT(*) FROM model_call_tail WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        ),
        "visible_after": visible_after,
        "scale_profile_id": scale_profile_id,
    }


def _call_order_oracle(
    connection: sqlite3.Connection,
    session_id: str,
) -> tuple[tuple[tuple[Any, ...], ...], tuple[tuple[Any, ...], ...]]:
    """Build call order independently from EvidenceService SQL/rendering."""

    def facts() -> Any:
        for table in ("model_calls", "model_call_tail"):
            for row in connection.execute(
                f"""SELECT call_id, event_at_us, source_rank, source_order,
                           event_kind_order, transition_rank,
                           primary_occurrence_id, o.semantic_logical_id
                      FROM {table} AS mc
                      JOIN source_occurrences AS o
                        ON o.occurrence_id = mc.primary_occurrence_id
                     WHERE mc.session_id = ?""",
                (session_id,),
            ):
                occurrence = row[6]
                semantic_logical_id = row[7]
                if occurrence is None or semantic_logical_id != row[0]:
                    raise ValueError(
                        "synthetic scale call does not own a matching typed occurrence"
                    )
                event_at = None if row[1] is None else int(row[1])
                yield (
                    1 if event_at is None else 0,
                    0 if event_at is None else event_at,
                    int(row[2]),
                    int(row[3]),
                    int(row[4]),
                    str(row[0]),
                    int(row[5]),
                )

    sample_size = PAGE_LIMIT * 2
    return (
        tuple(heapq.nsmallest(sample_size, facts())),
        tuple(heapq.nlargest(sample_size, facts())),
    )


def _read_page(
    service: EvidenceService,
    connection: sqlite3.Connection,
    case: Mapping[str, Any],
    selector: str,
    *,
    view: str,
    direction: str,
    selector_role: str = "selector",
    plan_id: str = "evidence-page",
    cursor: str | None = None,
    limit: int = PAGE_LIMIT,
    byte_limit: int = MAX_EVIDENCE_BYTES,
) -> tuple[Any, float]:
    if int(connection.execute("PRAGMA query_only").fetchone()[0]) != 1:
        raise ValueError("scale connection left query-only mode")
    started = time.perf_counter_ns()
    page = service.read(
        connection,
        _request(
            case,
            selector,
            view=view,
            direction=direction,
            selector_role=selector_role,
            plan_id=plan_id,
            cursor=cursor,
            limit=limit,
            byte_limit=byte_limit,
        ),
    )
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    return page, round(elapsed_ms, 6)


def _assert_monotonic(rows: Sequence[Mapping[str, Any]], direction: str) -> None:
    keys = [tuple(row["order_key"]) for row in rows]
    assert len(keys) == len(set(keys)), "duplicate seven-part evidence order key"
    assert keys == sorted(keys, reverse=direction == "backward"), "evidence order is not monotonic"


def _plan_details(plan: Sequence[tuple[int, int, int, str]]) -> list[str]:
    return [row[3] for row in plan]


def _scope_selectors(
    connection: sqlite3.Connection,
    case: Mapping[str, Any],
    session_id: str,
) -> tuple[tuple[str, str, Mapping[str, Any], str, str], ...]:
    """Resolve one deterministic selector for every accepted scope kind."""

    values = {
        "allowance_interval": connection.execute(
            "SELECT interval_id FROM allowance_intervals ORDER BY interval_id LIMIT 1"
        ).fetchone(),
        "allowance_observation": connection.execute(
            "SELECT observation_id FROM allowance_observations ORDER BY observation_id LIMIT 1"
        ).fetchone(),
        "call": connection.execute(
            "SELECT call_id FROM model_calls_visible WHERE model_profile_id IN "
            "(SELECT model_profile_id FROM model_profiles WHERE model = 'synthetic-model') "
            "ORDER BY call_id LIMIT 1"
        ).fetchone(),
        "model_profile": connection.execute(
            "SELECT model_profile_id FROM model_profiles WHERE model <> 'synthetic-scale' "
            "ORDER BY model_profile_id LIMIT 1"
        ).fetchone(),
        "project": connection.execute(
            "SELECT project_id FROM projects ORDER BY project_id LIMIT 1"
        ).fetchone(),
        "publication": (PUBLICATION_ID,),
        "rate_card": connection.execute(
            "SELECT rate_card_digest FROM publications WHERE publication_id = ?",
            (PUBLICATION_ID,),
        ).fetchone(),
        "resource": connection.execute(
            "SELECT resource_id FROM resources ORDER BY resource_id LIMIT 1"
        ).fetchone(),
        "session": (session_id,),
        "source_manifestation": connection.execute(
            "SELECT manifestation_id FROM source_manifestations ORDER BY manifestation_id LIMIT 1"
        ).fetchone(),
        "state_change": connection.execute(
            "SELECT change_id FROM state_changes ORDER BY change_id LIMIT 1"
        ).fetchone(),
        "tool": connection.execute(
            "SELECT tool_id FROM tool_invocations ORDER BY tool_id LIMIT 1"
        ).fetchone(),
        "turn": connection.execute(
            "SELECT turn_id FROM turns ORDER BY turn_id LIMIT 1"
        ).fetchone(),
    }
    window_case = next(
        item
        for item in build_question_scenarios()["cases"]
        if any(evidence["selector_kind"] == "window" for evidence in item["required_evidence"])
    )
    window_item = next(
        evidence
        for evidence in window_case["required_evidence"]
        if evidence["selector_kind"] == "window"
    )
    selectors: list[tuple[str, str, Mapping[str, Any], str, str]] = []
    for kind in SELECTOR_SCOPE_KINDS:
        if kind == "window":
            selectors.append(
                (
                    kind,
                    str(window_item["selector"]),
                    window_case,
                    str(window_item["role"]),
                    str(window_case["request"]["plan_id"]),
                )
            )
            continue
        value = values[kind]
        if value is None:
            raise ValueError(f"synthetic scope selector {kind} has no owner row")
        logical_id = str(value[0])
        selector = f"{kind.replace('_', '-')}:{logical_id}"
        selectors.append((kind, selector, case, "selector", "evidence-page"))
    return tuple(selectors)


def _run_scope_matrix(
    service: EvidenceService,
    connection: sqlite3.Connection,
    case: Mapping[str, Any],
    session_id: str,
) -> dict[str, Any]:
    selectors = _scope_selectors(connection, case, session_id)
    outcomes = 0
    nonempty = 0
    deep_pages = 0
    for _kind, selector, request_case, selector_role, plan_id in selectors:
        for view in EVIDENCE_VIEWS:
            for direction in ("forward", "backward"):
                page, _elapsed = _read_page(
                    service,
                    connection,
                    request_case,
                    selector,
                    view=view,
                    direction=direction,
                    limit=3,
                    selector_role=selector_role,
                    plan_id=plan_id,
                )
                outcomes += 1
                if page.returned_rows:
                    nonempty += 1
                assert page.returned_rows <= MAX_EVIDENCE_LIMIT
                assert page.response_bytes <= MAX_EVIDENCE_BYTES
                observed = list(page.rows)
                if page.next_cursor is not None:
                    deep, _deep_elapsed = _read_page(
                        service,
                        connection,
                        request_case,
                        selector,
                        view=view,
                        direction=direction,
                        selector_role=selector_role,
                        plan_id=plan_id,
                        cursor=page.next_cursor,
                        limit=3,
                    )
                    deep_pages += 1
                    assert deep.returned_rows <= MAX_EVIDENCE_LIMIT
                    assert deep.response_bytes <= MAX_EVIDENCE_BYTES
                    observed.extend(deep.rows)
                _assert_monotonic(observed, direction)
    return {
        "selectors": len(selectors),
        "selector_kinds": [item[0] for item in selectors],
        "views": len(EVIDENCE_VIEWS),
        "directions": 2,
        "outcomes": outcomes,
        "deep_pages": deep_pages,
        "nonempty_pages": nonempty,
        "passed": True,
    }


def _run_scale_profile(
    root: Path,
    *,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    profile_name = str(profile["name"])
    target_calls = int(profile["model_calls"])
    connection, case, selector, publication = _published_session(
        root / profile_name,
    )
    service = _service()
    session_id = selector.partition(":")[2]
    try:
        late_event_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM model_calls_visible "
                "WHERE session_id = ? AND event_at_us = ? AND source_order = ?",
                (session_id, 125, 92),
            ).fetchone()[0]
        )
        if late_event_count != 1:
            raise QualificationFailure(
                "late_event_fixture",
                profile_name,
                f"expected one synthetic late event, found {late_event_count}",
            )
        materialization = _insert_scale_calls(
            connection,
            profile_name=profile_name,
            target_calls=target_calls,
            session_id=session_id,
        )
        oracle_forward, oracle_backward = _call_order_oracle(connection, session_id)
        materialization["typed_provenance"] = True

        scope = {"kind": "session", "logical_id": session_id}
        pages: dict[str, dict[str, dict[str, Any]]] = {}
        plan_count = 0
        maximum_rows = 0
        maximum_bytes = 0
        selected_top_level: dict[str, Any] | None = None
        for view in PAGED_VIEWS:
            pages[view] = {}
            for direction in ("forward", "backward"):
                first, first_ms = _read_page(
                    service,
                    connection,
                    case,
                    selector,
                    view=view,
                    direction=direction,
                )
                first_sql, first_parameters, first_plan = _explain(
                    connection,
                    view=view,
                    direction=direction,
                    scope=scope,
                    cursor_order=None,
                    publication_id=PUBLICATION_ID,
                )
                plan_count += 1
                deep_order = tuple(first.rows[-1]["order_key"]) if first.rows else None
                deep_sql, deep_parameters, deep_plan = _explain(
                    connection,
                    view=view,
                    direction=direction,
                    scope=scope,
                    cursor_order=deep_order,
                    publication_id=PUBLICATION_ID,
                )
                plan_count += 1
                deep = None
                deep_ms = None
                if first.next_cursor is not None:
                    deep, deep_ms = _read_page(
                        service,
                        connection,
                        case,
                        selector,
                        view=view,
                        direction=direction,
                        cursor=first.next_cursor,
                    )
                observed = list(first.rows)
                if deep is not None:
                    observed.extend(deep.rows)
                _assert_monotonic(observed, direction)
                for page in (first, deep):
                    if page is None:
                        continue
                    maximum_rows = max(maximum_rows, page.returned_rows)
                    maximum_bytes = max(maximum_bytes, page.response_bytes)
                pages[view][direction] = {
                    "first": {
                        "rows": first.returned_rows,
                        "response_bytes": first.response_bytes,
                        "has_more": first.next_cursor is not None,
                        "timing_ms": first_ms,
                        "order": [list(row["order_key"]) for row in first.rows],
                        "plan_details": _plan_details(first_plan),
                    },
                    "deep": None
                    if deep is None
                    else {
                        "rows": deep.returned_rows,
                        "response_bytes": deep.response_bytes,
                        "has_more": deep.next_cursor is not None,
                        "timing_ms": deep_ms,
                        "order": [list(row["order_key"]) for row in deep.rows],
                        "plan_details": _plan_details(deep_plan),
                    },
                    "sql": first_sql,
                    "deep_sql": deep_sql,
                    "first_parameters": list(first_parameters),
                    "deep_parameters": list(deep_parameters),
                }
                if view == "timeline" and direction == "forward":
                    selected_top_level = {
                        "first": first,
                        "deep": deep,
                        "first_sql": first_sql,
                        "deep_sql": deep_sql,
                        "first_plan": first_plan,
                        "deep_plan": deep_plan,
                    }

        assert selected_top_level is not None
        call_checks: dict[str, Any] = {}
        expected_forward = oracle_forward
        expected_backward = oracle_backward
        for direction, expected in (
            ("forward", expected_forward),
            ("backward", expected_backward),
        ):
            first_order = tuple(tuple(item) for item in pages["calls"][direction]["first"]["order"])
            first_matches = first_order == expected[: len(first_order)]
            deep_payload = pages["calls"][direction]["deep"]
            deep_order = () if deep_payload is None else tuple(tuple(item) for item in deep_payload["order"])
            deep_matches = deep_order == expected[len(first_order) : len(first_order) + len(deep_order)]
            first_deep_unique = len(set(first_order + deep_order)) == len(first_order + deep_order)
            if not (first_matches and deep_matches and first_deep_unique):
                raise QualificationFailure(
                    "call_order_oracle",
                    profile_name,
                    f"{direction} call page order diverged from the typed oracle",
                )
            call_checks[direction] = {
                "oracle_rows": target_calls,
                "first_matches_oracle": first_matches,
                "deep_matches_oracle": deep_matches,
                "first_deep_unique": first_deep_unique,
                "typed_provenance": True,
            }

        timing_samples: list[float] = []
        sql_timing_samples: list[float] = []
        timeline_scope = scope
        first_sql, first_parameters = evidence_service._page_statement(
            "timeline",
            "forward",
            timeline_scope,
            None,
            PUBLICATION_ID,
            PAGE_LIMIT,
        )
        for _ in range(5):
            _page, elapsed = _read_page(
                service,
                connection,
                case,
                selector,
                view="timeline",
                direction="forward",
            )
            timing_samples.append(elapsed)
            started = time.perf_counter_ns()
            connection.execute(first_sql, first_parameters).fetchall()
            sql_timing_samples.append(round((time.perf_counter_ns() - started) / 1_000_000, 6))
        service_p95 = _p95(timing_samples)
        sql_p95 = _p95(sql_timing_samples)
        if service_p95 > SERVICE_P95_BUDGET_MS or sql_p95 > SQL_P95_BUDGET_MS:
            raise QualificationFailure(
                "evidence_page_budget",
                profile_name,
                f"p95 exceeded P4 evidence budget: sql={sql_p95:.3f}ms service={service_p95:.3f}ms",
            )

        matrix = _run_scope_matrix(service, connection, case, session_id)
        byte_page, _byte_ms = _read_page(
            service,
            connection,
            case,
            selector,
            view="timeline",
            direction="forward",
            limit=PAGE_LIMIT,
            byte_limit=7_000,
        )
        encoded_byte_page = json.dumps(
            byte_page.to_mapping(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if (
            not 0 < byte_page.returned_rows < PAGE_LIMIT
            or not byte_page.has_more
            or byte_page.next_cursor is None
            or byte_page.response_bytes != len(encoded_byte_page)
            or byte_page.response_bytes > 7_000
        ):
            raise QualificationFailure(
                "evidence_response_budget",
                profile_name,
                "byte-truncated page did not shrink to a bounded continuation",
            )

        cursor_checks: dict[str, bool] = {
            "exact_count_off": all("COUNT(" not in item["sql"].upper() for item in pages["timeline"].values()),
            "late_event_present": late_event_count == 1,
            "byte_truncation_bounded": (
                0 < byte_page.returned_rows < PAGE_LIMIT
                and byte_page.has_more
                and byte_page.next_cursor is not None
                and byte_page.response_bytes == len(encoded_byte_page)
                and byte_page.response_bytes <= 7_000
            ),
            "query_only": int(connection.execute("PRAGMA query_only").fetchone()[0]) == 1,
        }
        cursor = selected_top_level["first"].next_cursor
        if cursor is None:
            raise QualificationFailure(
                "cursor_progression",
                profile_name,
                "timeline first page did not produce a deep-page cursor",
            )
        tampered = cursor[:-1] + ("A" if cursor[-1] != "A" else "B")
        try:
            service.read(
                connection,
                _request(
                    case,
                    selector,
                    view="timeline",
                    direction="forward",
                    cursor=tampered,
                ),
            )
        except CursorTamperedError as error:
            if "signature" not in str(error):
                raise QualificationFailure(
                    "evidence_cursor_contract",
                    profile_name,
                    f"tampered cursor failed for an unexpected reason: {error}",
                ) from error
            cursor_checks["tampered_cursor_rejected"] = True
        else:
            cursor_checks["tampered_cursor_rejected"] = False
        try:
            service.read(
                connection,
                _request(
                    case,
                    selector,
                    view="timeline",
                    direction="forward",
                    publication_id=None,
                    expected_publication_id="publication:synthetic-replacement",
                    cursor=cursor,
                ),
            )
        except EvidenceServiceError as error:
            if "stale or replaced" not in str(error):
                raise QualificationFailure(
                    "evidence_cursor_contract",
                    profile_name,
                    f"replacement cursor failed for an unexpected reason: {error}",
                ) from error
            cursor_checks["replaced_publication_rejected"] = True
        else:
            cursor_checks["replaced_publication_rejected"] = False
        if not all(cursor_checks.values()):
            raise QualificationFailure(
                "evidence_cursor_contract",
                profile_name,
                f"cursor or exact-count contract failed: {cursor_checks}",
            )

        database_path = root / profile_name / "database-v1.sqlite3"
        database_bytes = database_path.stat().st_size
        database_sha = _sha(database_path)
        selected_first = selected_top_level["first"]
        selected_deep = selected_top_level["deep"]
        return {
            "name": profile_name,
            "model_calls": target_calls,
            "materialization": materialization,
            "base_publication_receipt": publication,
            "database_bytes": database_bytes,
            "database_sha256": database_sha,
            "timing_samples_ms": timing_samples,
            "timing_p95_ms": service_p95,
            "sql_timing_samples_ms": sql_timing_samples,
            "sql_p95_ms": sql_p95,
            "rss_bytes": _rss_bytes(),
            "budget": {
                "performance_class": "P4",
                "sql_p95_ms": SQL_P95_BUDGET_MS,
                "service_p95_ms": SERVICE_P95_BUDGET_MS,
                "response_bytes": MAX_EVIDENCE_BYTES,
                "passed": True,
            },
            "matrix": matrix,
            "late_event_count": late_event_count,
            "call_oracle": call_checks,
            "cursor_checks": cursor_checks,
            "plan_count": plan_count,
            "maximum_rows": maximum_rows,
            "maximum_response_bytes": maximum_bytes,
            "selected": {
                "selector": selector,
                "direction": "next",
                "sql": selected_top_level["first_sql"] + "\n-- deep page\n" + selected_top_level["deep_sql"],
                "explain": [
                    {"page": "first", "plan": [dict(zip(("select_id", "order", "from_id", "detail"), row, strict=True)) for row in selected_top_level["first_plan"]]},
                    {"page": "deep", "plan": [dict(zip(("select_id", "order", "from_id", "detail"), row, strict=True)) for row in selected_top_level["deep_plan"]]},
                ],
                "first_page_order": [list(row["order_key"]) for row in selected_first.rows],
                "deep_page_order": []
                if selected_deep is None
                else [list(row["order_key"]) for row in selected_deep.rows],
                "rows": max(
                    selected_first.returned_rows,
                    0 if selected_deep is None else selected_deep.returned_rows,
                ),
                "response_bytes": max(
                    selected_first.response_bytes,
                    0 if selected_deep is None else selected_deep.response_bytes,
                ),
            },
        }
    except QualificationFailure:
        raise
    except (AssertionError, sqlite3.Error, ValueError, TypeError) as error:
        raise QualificationFailure(
            "evidence_scale_invariant",
            profile_name,
            f"{type(error).__name__}: {error}",
        ) from error
    finally:
        connection.close()


def _failure_payload(
    *,
    profile: Mapping[str, Any],
    publication: str,
    fixture_digest: str,
    failure: Mapping[str, Any],
    partial: Mapping[str, Any] | None,
) -> dict[str, Any]:
    selected = {} if partial is None else dict(partial.get("selected", {}))
    return {
        "schema": SCHEMA,
        "dependency_sha": DEPENDENCY_SHA,
        "fixture_digest": fixture_digest,
        "publication_digest": publication,
        "selector": str(selected.get("selector", "session:unavailable")),
        "direction": "next",
        "sql": str(selected.get("sql", "scale qualification stopped before page SQL")),
        "explain": selected.get("explain", [{"failure": dict(failure)}]),
        "first_page_order": selected.get("first_page_order", []),
        "deep_page_order": selected.get("deep_page_order", []),
        "gap_duplicate_checks": {
            "scale_execution": "stopped_on_first_failure",
            "first_failure_retained": True,
            "production_execution_skipped": profile["name"] == "standard",
        },
        "rows": int(selected.get("rows", 0)),
        "response_bytes": int(selected.get("response_bytes", 0)),
        "timing_samples_ms": [0, 0, 0, 0, 0],
        "rss_bytes": _rss_bytes(),
        "first_failure": dict(failure),
        "noise": [
            {
                "kind": "historical_ck08r3_blocker",
                "artifact_sha256": _HISTORICAL_BLOCKER_DIGEST,
                "claim": "retained predecessor reproduction; not current truth",
            }
        ],
    }


def collect() -> dict[str, Any]:
    """Run both frozen scales and return one strict evidenceScale object."""

    _gates, profiles = _load_authority()
    fixture_digest = _sha_value(
        {
            "profiles": profiles,
            "recipe": "publication-valid-structural-v2-plus-query-only-synthetic-model-call-rows-v1",
            "tail_capacity": CALL_TAIL_CAPACITY,
            "page_limit": PAGE_LIMIT,
            "byte_limit": MAX_EVIDENCE_BYTES,
        }
    )
    results: list[dict[str, Any]] = []
    failure: QualificationFailure | None = None
    with tempfile.TemporaryDirectory(prefix="ck08r3-evidence-scale-") as directory:
        root = Path(directory)
        for profile in profiles:
            try:
                results.append(_run_scale_profile(root, profile=profile))
            except QualificationFailure as error:
                failure = error
                break
        publication_digest = (
            results[0]["base_publication_receipt"]["artifact_manifest_sha256"]
            if results
            else "0" * 64
        )
        if failure is not None:
            partial = results[-1] if results else None
            return _failure_payload(
                profile={"name": failure.profile},
                publication=publication_digest,
                fixture_digest=fixture_digest,
                failure=failure.as_mapping(),
                partial=partial,
            )

    assert len(results) == len(PROFILE_NAMES)
    production = results[-1]
    return {
        "schema": SCHEMA,
        "dependency_sha": DEPENDENCY_SHA,
        "fixture_digest": fixture_digest,
        "publication_digest": production["base_publication_receipt"]["artifact_manifest_sha256"],
        "selector": production["selected"]["selector"],
        "direction": production["selected"]["direction"],
        "sql": production["selected"]["sql"],
        "explain": production["selected"]["explain"],
        "first_page_order": production["selected"]["first_page_order"],
        "deep_page_order": production["selected"]["deep_page_order"],
        "gap_duplicate_checks": {
            "synthetic_only": True,
            "publication_base_committed": all(
                item["base_publication_receipt"]["status"] == "committed"
                for item in results
            ),
            "query_only_one_snapshot": all(
                item["cursor_checks"]["query_only"] for item in results
            ),
            "typed_selector_seven_part_oracle": all(
                all(check["first_matches_oracle"] and check["deep_matches_oracle"] for check in item["call_oracle"].values())
                for item in results
            ),
            "first_deep_no_gaps_or_duplicates": all(
                all(check["first_deep_unique"] for check in item["call_oracle"].values())
                for item in results
            ),
            "all_views_scopes_directions": all(item["matrix"]["passed"] for item in results),
            "late_event_fixture": all(item["late_event_count"] == 1 for item in results),
            "exact_count_requested": False,
            "byte_truncation_bounded": all(
                item["cursor_checks"]["byte_truncation_bounded"] for item in results
            ),
            "cursor_tamper_and_replacement_rejected": all(
                item["cursor_checks"]["tampered_cursor_rejected"]
                and item["cursor_checks"]["replaced_publication_rejected"]
                for item in results
            ),
            "scale_execution": "standard_and_production_passed",
        },
        "rows": int(production["selected"]["rows"]),
        "response_bytes": int(production["selected"]["response_bytes"]),
        "timing_samples_ms": production["timing_samples_ms"],
        "rss_bytes": int(production["rss_bytes"]),
        "first_failure": None,
        "noise": [
            {
                "kind": "profile_measurements",
                "profiles": results,
                "budget": {
                    "performance_class": "P4",
                    "sql_p95_ms": SQL_P95_BUDGET_MS,
                    "service_p95_ms": SERVICE_P95_BUDGET_MS,
                    "response_bytes": MAX_EVIDENCE_BYTES,
                },
            },
            {
                "kind": "historical_ck08r3_blocker",
                "artifact_sha256": _HISTORICAL_BLOCKER_DIGEST,
                "claim": "retained predecessor reproduction; not current truth",
            },
            {
                "kind": "publication_boundary",
                "claim": "Each temporary scale copy retains a committed publication receipt; synthetic scale rows are query-only augmentation and are not re-published or used to rewrite publication metadata.",
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    payload = collect()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(_json_bytes(payload))
    print(
        json.dumps(
            {
                "output": arguments.output.as_posix(),
                "schema": payload["schema"],
                "first_failure": None
                if payload["first_failure"] is None
                else payload["first_failure"]["gate"],
                "fixture_digest": payload["fixture_digest"],
                "publication_digest": payload["publication_digest"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
