"""One-snapshot internal query service for admitted CK-08 named plans."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..domain.plan_operands import PlanRequest, evaluate_plan
from ..evidence.cursors import CursorBinding, CursorCodec
from ..storage.database import open_read_only
from .compiler import DatabaseV1FactCompiler, FactCompilation
from .contracts import (
    EvidenceSelection,
    Publication,
    QueryBatchRequest,
    QueryBatchResult,
    QueryContractError,
    QueryPage,
    QueryRequest,
    QueryResult,
    canonical_json_bytes,
    canonical_json_value,
    serialize_batch_result,
)
from .registry import QueryDefinition, QueryRegistry

Clock = Callable[[], int]
_CURSOR_TTL_US = 24 * 60 * 60 * 1_000_000


class QueryServiceError(RuntimeError):
    """A query cannot be answered completely from the selected snapshot."""


def _snapshot(
    connection: sqlite3.Connection,
) -> tuple[Publication, dict[str, Any], dict[str, Any]]:
    row = connection.execute(
        """
        SELECT p.publication_id, p.committed_at_us, p.observed_through_us
          FROM publication_head AS h
          JOIN publications AS p ON p.publication_id = h.publication_id
         WHERE h.singleton = 1 AND p.status = 'committed'
        """
    ).fetchall()
    if len(row) != 1:
        raise QueryServiceError("snapshot has no unique committed publication")
    publication = Publication(
        publication_id=str(row[0][0]),
        committed_at_us=int(row[0][1]),
        observed_through_us=int(row[0][2]),
    )
    coverage: dict[str, Any] = {}
    capabilities: dict[str, Any] = {}
    for item in connection.execute(
        """
        SELECT capability_id, grade, eligible_entity_count,
               observed_entity_count, unavailable_entity_count
          FROM publication_capability_coverage
         WHERE publication_id = ?
         ORDER BY capability_id
        """,
        (publication.publication_id,),
    ):
        capability = str(item[0])
        capabilities[capability] = {
            "available": int(item[4]) == 0,
            "grade": str(item[1]),
        }
        coverage[capability] = {
            "eligible": int(item[2]),
            "observed": int(item[3]),
            "unavailable": int(item[4]),
        }
    if not capabilities:
        raise QueryServiceError("snapshot capability coverage is missing")
    return publication, coverage, capabilities


def _evidence(reference: Any) -> EvidenceSelection:
    return EvidenceSelection(
        role=reference.role,
        selector_kind=reference.selector_kind,
        selector_id=reference.logical_id,
        selector=reference.selector,
        provenance_kind=reference.provenance_kind,
        provenance=reference.provenance,
    )


def _row_key(row: Mapping[str, Any], entry: QueryDefinition) -> tuple[Any, ...]:
    """Return a stable keyset identity for an already contract-sorted row."""

    normalized = canonical_json_value(row)
    digest = hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()
    values: list[Any] = []
    for token in entry.order:
        field = token.removesuffix("_asc").removesuffix("_desc")
        aliases = (
            field,
            f"{field}_us",
            "logical_id" if field == "entity_id" else field,
        )
        values.append(next((normalized[name] for name in aliases if name in normalized), None))
    values.append(digest)
    return tuple(values)


class QueryService:
    """Execute admitted named requests without refresh, writes, or projections."""

    def __init__(
        self,
        registry: QueryRegistry,
        plan_operands: Mapping[str, Any],
        selector_provenance: Mapping[str, Any],
        cursor_codec: CursorCodec,
        *,
        clock: Clock,
        cursor_ttl_us: int = _CURSOR_TTL_US,
    ) -> None:
        if not isinstance(registry, QueryRegistry):
            raise QueryContractError("query service requires a QueryRegistry")
        if not callable(clock) or cursor_ttl_us <= 0:
            raise QueryContractError("query service clock or cursor TTL is invalid")
        self._registry = registry
        self._plan_operands = plan_operands
        self._selector_provenance = selector_provenance
        self._cursor_codec = cursor_codec
        self._clock = clock
        self._cursor_ttl_us = cursor_ttl_us

    def execute_path(self, path: Path, batch: QueryBatchRequest) -> QueryBatchResult:
        connection = open_read_only(Path(path))
        try:
            return self.execute(connection, batch)
        finally:
            connection.close()

    def execute(
        self,
        connection: sqlite3.Connection,
        batch: QueryBatchRequest,
    ) -> QueryBatchResult:
        if not isinstance(connection, sqlite3.Connection):
            raise QueryServiceError("query service requires a SQLite connection")
        if not isinstance(batch, QueryBatchRequest):
            raise QueryContractError("query service requires QueryBatchRequest")
        if connection.in_transaction:
            raise QueryServiceError("query service owns the read transaction")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise QueryServiceError("query service requires PRAGMA query_only=1")

        entries = tuple(self._registry.validate(request) for request in batch.plans)
        connection.execute("BEGIN")
        try:
            publication, coverage, capabilities = _snapshot(connection)
            expected = batch.expected_publication_id
            if expected is not None and expected != publication.publication_id:
                raise QueryServiceError(
                    "requested publication is stale or replaced; restart from the first page"
                )
            results = tuple(
                self._execute_plan(connection, request, entry, publication)
                for request, entry in zip(batch.plans, entries, strict=True)
            )
            envelope = QueryBatchResult(
                request_id=batch.request_id,
                publication=publication,
                results=results,
                coverage=coverage,
                capabilities=capabilities,
            )
            encoded = serialize_batch_result(envelope)
            byte_budget = max(
                int(
                    max(budget.response_bytes for budget in entry.performance_budgets)
                    * 1.25
                )
                for entry in entries
            )
            if len(encoded) > byte_budget:
                raise QueryServiceError(
                    f"response_budget_exceeded: {len(encoded)} > {byte_budget}"
                )
            return envelope
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")

    def _execute_plan(
        self,
        connection: sqlite3.Connection,
        request: QueryRequest,
        entry: QueryDefinition,
        publication: Publication,
    ) -> QueryResult:
        plan_request = PlanRequest(
            plan_id=request.plan_id,
            parameters=request.parameters,
            gates=request.gates,
        )
        selector_ids = {
            item.role: item.selector or f"{item.selector_kind.replace('_', '-')}:{item.selector_id}"
            for item in request.required_evidence
        }
        compilation = DatabaseV1FactCompiler(
            self._plan_operands,
            self._selector_provenance,
            tuple(item.to_mapping() for item in request.required_evidence),
        ).compile(
            connection,
            plan_request,
            selector_ids=selector_ids,
        )
        if compilation.publication_id != publication.publication_id:
            raise QueryServiceError("compiler publication differs inside one snapshot")
        evaluation = evaluate_plan(
            self._plan_operands,
            compilation.request,
            compilation.facts,
        )
        rows = tuple(canonical_json_value(row) for row in evaluation.rows)
        page_rows, page = self._page(rows, request, entry, compilation, publication)
        return QueryResult(
            question_id=request.question_id,
            plan_id=request.plan_id,
            plan_version=request.plan_version,
            publication=publication,
            grades=entry.grades,
            rows=page_rows,
            evidence_selectors=tuple(
                _evidence(reference) for reference in compilation.evidence_references
            ),
            page=page,
            request_digest=compilation.request_digest,
        )

    def _page(
        self,
        rows: tuple[Mapping[str, Any], ...],
        request: QueryRequest,
        entry: QueryDefinition,
        compilation: FactCompilation,
        publication: Publication,
    ) -> tuple[tuple[Mapping[str, Any], ...], QueryPage]:
        limit = request.page.limit or entry.default_rows
        start = 0
        if request.page.cursor is not None:
            binding = self._cursor_codec.decode(
                request.page.cursor,
                expected_kind="query",
                expected_plan_id=request.plan_id,
                expected_plan_version=request.plan_version,
                expected_publication_id=publication.publication_id,
                expected_request_digest=compilation.request_digest,
            )
            keys = tuple(_row_key(row, entry) for row in rows)
            try:
                start = keys.index(binding.order) + 1
            except ValueError as error:
                raise QueryServiceError(
                    "cursor key is stale or replaced; restart from the first page"
                ) from error
        selected = rows[start : start + limit]
        has_more = start + len(selected) < len(rows)
        next_cursor = None
        if has_more and selected:
            issued_at_us = self._clock()
            next_cursor = self._cursor_codec.encode(
                CursorBinding(
                    kind="query",
                    plan_id=request.plan_id,
                    plan_version=request.plan_version,
                    publication_id=publication.publication_id,
                    request_digest=compilation.request_digest,
                    order=_row_key(selected[-1], entry),
                    issued_at_us=issued_at_us,
                    expires_at_us=issued_at_us + self._cursor_ttl_us,
                    metadata={"order_contract": list(entry.order)},
                )
            )
        return selected, QueryPage(
            limit=limit,
            include_exact_count=request.page.include_exact_count,
            returned_rows=len(selected),
            has_more=has_more,
            next_cursor=next_cursor,
            exact_count=len(rows) if request.page.include_exact_count else None,
        )


__all__ = ["QueryService", "QueryServiceError"]
