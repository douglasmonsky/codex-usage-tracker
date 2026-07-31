"""Internal, immutable contracts for named fact-backed queries."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Any

QUERY_SCHEMA = "codex-usage-tracker.query.v1"
RESULT_SCHEMA = "codex-usage-tracker.result.v1"
MAX_PAGE_LIMIT = 100
MAX_CURSOR_BYTES = 4096
_DIGEST_LENGTH = 64
_GRADES = frozenset(
    {"exact", "deterministic", "configured_estimate", "model_inference", "unsupported"}
)
_FORBIDDEN_KEYS = frozenset(
    {"expression", "raw_sql", "sql", "user_expression", "refresh", "write"}
)


class QueryContractError(ValueError):
    """A typed query contract is malformed or outside the admitted surface."""


def _non_empty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryContractError(f"{label} must be a non-empty string")
    if value != value.strip() or any(character.isspace() for character in value):
        raise QueryContractError(f"{label} must not contain whitespace")
    return value


def _finite(value: Any, label: str) -> None:
    if isinstance(value, Decimal) and not value.is_finite():
        raise QueryContractError(f"{label} contains a non-finite Decimal")
    if isinstance(value, float) and not math.isfinite(value):
        raise QueryContractError(f"{label} contains a non-finite float")


def _freeze(value: Any, label: str) -> Any:
    """Recursively freeze JSON-shaped values and reject unsupported objects."""

    if value is None or isinstance(value, (str, int, bool, Decimal, float)):
        _finite(value, label)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise QueryContractError(f"{label} mappings require string keys")
            if key.lower() in _FORBIDDEN_KEYS:
                raise QueryContractError(f"{label} contains forbidden key {key!r}")
            frozen[key] = _freeze(item, f"{label}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item, f"{label}[]") for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item, f"{label}[]") for item in value)
    raise QueryContractError(f"{label} contains unsupported {type(value).__name__}")


def _mapping(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    frozen = _freeze(value, label)
    if not isinstance(frozen, Mapping):
        raise QueryContractError(f"{label} must be a mapping")
    return frozen


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise QueryContractError(f"{label} must be a positive integer")
    return value


def _optional_digest(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != _DIGEST_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise QueryContractError(f"{label} must be a lowercase SHA-256 digest")
    return value


@dataclass(frozen=True, slots=True)
class EvidenceSelection:
    """One ordered, exact selector chosen by the query contract."""

    role: str
    selector_kind: str
    selector_id: str
    selector: str | None = None
    provenance_kind: str | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_empty(self.role, "evidence role")
        _non_empty(self.selector_kind, "evidence selector kind")
        selector_id = _non_empty(self.selector_id, "evidence selector ID")
        if selector_id.lower() in {"unknown", "placeholder", "selector"}:
            raise QueryContractError("evidence selector ID must be exact, not a placeholder")
        if self.selector is not None:
            _non_empty(self.selector, "evidence selector")
        if self.provenance_kind is not None:
            _non_empty(self.provenance_kind, "evidence provenance kind")
        object.__setattr__(self, "provenance", _mapping(self.provenance, "evidence provenance"))

    @property
    def logical_id(self) -> str:
        """Compatibility spelling used by the selector provenance authority."""

        return self.selector_id

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "role": self.role,
            "selector_kind": self.selector_kind,
            "logical_id": self.selector_id,
        }
        if self.selector is not None:
            result["selector"] = self.selector
        if self.provenance_kind is not None:
            result["provenance_kind"] = self.provenance_kind
        if self.provenance:
            result["provenance"] = canonical_json_value(self.provenance)
        return result

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], index: int = 0) -> EvidenceSelection:
        if not isinstance(value, Mapping):
            raise QueryContractError(f"required_evidence[{index}] must be a mapping")
        selector_id = value.get("selector_id", value.get("logical_id"))
        if selector_id is None:
            selector_id = value.get("selector")
        if not isinstance(selector_id, str):
            raise QueryContractError(f"required_evidence[{index}] has no exact selector ID")
        selector_kind = value.get("selector_kind")
        if not isinstance(selector_kind, str):
            raise QueryContractError(
                f"required_evidence[{index}] has no exact selector kind"
            )
        return cls(
            role=value.get("role", f"selection_{index}"),
            selector_kind=selector_kind,
            selector_id=selector_id,
            selector=value.get("selector"),
            provenance_kind=value.get("provenance_kind"),
            provenance=value.get("provenance", {}),
        )


RequiredEvidence = EvidenceSelection


@dataclass(frozen=True, slots=True)
class QueryPage:
    """Bounded keyset page controls shared by query and result envelopes."""

    limit: int | None = None
    cursor: str | None = None
    include_exact_count: bool = False
    returned_rows: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None
    exact_count: int | None = None

    def __post_init__(self) -> None:
        if self.limit is not None and (
            isinstance(self.limit, bool) or not 1 <= self.limit <= MAX_PAGE_LIMIT
        ):
            raise QueryContractError(f"page limit must be between 1 and {MAX_PAGE_LIMIT}")
        if self.cursor is not None:
            _non_empty(self.cursor, "page cursor")
            if len(self.cursor.encode("utf-8")) > MAX_CURSOR_BYTES:
                raise QueryContractError("page cursor exceeds the maximum size")
        if not isinstance(self.include_exact_count, bool):
            raise QueryContractError("include_exact_count must be a boolean")
        if self.returned_rows is not None and (
            isinstance(self.returned_rows, bool) or not isinstance(self.returned_rows, int) or self.returned_rows < 0
        ):
            raise QueryContractError("returned_rows must be a non-negative integer")
        if self.has_more is not None and not isinstance(self.has_more, bool):
            raise QueryContractError("has_more must be a boolean")
        if self.next_cursor is not None:
            _non_empty(self.next_cursor, "next page cursor")
            if len(self.next_cursor.encode("utf-8")) > MAX_CURSOR_BYTES:
                raise QueryContractError("next page cursor exceeds the maximum size")
        if self.has_more is True and self.next_cursor is None:
            raise QueryContractError("a page with more rows requires a next cursor")
        if self.has_more is False and self.next_cursor is not None:
            raise QueryContractError("a final page cannot carry a next cursor")
        if self.exact_count is not None and (
            isinstance(self.exact_count, bool) or not isinstance(self.exact_count, int) or self.exact_count < 0
        ):
            raise QueryContractError("exact_count must be a non-negative integer")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "cursor": self.cursor,
            "include_exact_count": self.include_exact_count,
            "returned_rows": self.returned_rows,
            "has_more": self.has_more,
            "next_cursor": self.next_cursor,
            "exact_count": self.exact_count,
        }


@dataclass(frozen=True, slots=True)
class Publication:
    """The committed publication identity used by one read snapshot."""

    publication_id: str
    committed_at_us: int
    observed_through_us: int

    def __post_init__(self) -> None:
        _non_empty(self.publication_id, "publication ID")
        for label, value in (
            ("committed_at_us", self.committed_at_us),
            ("observed_through_us", self.observed_through_us),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise QueryContractError(f"{label} must be a non-negative integer")
        if self.committed_at_us < self.observed_through_us:
            raise QueryContractError("publication commit precedes its observed boundary")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.publication_id,
            "committed_at_us": self.committed_at_us,
            "observed_through_us": self.observed_through_us,
        }


@dataclass(frozen=True, slots=True)
class QueryRequest:
    """A named plan request; it cannot carry SQL, refresh, or user expressions."""

    question_id: str
    plan_id: str
    plan_version: int
    parameters: Mapping[str, Any] = field(default_factory=dict)
    gates: Mapping[str, bool] = field(default_factory=dict)
    required_evidence: tuple[EvidenceSelection, ...] = ()
    expected_publication_id: str | None = None
    page: QueryPage = field(default_factory=QueryPage)

    def __post_init__(self) -> None:
        _non_empty(self.question_id, "question ID")
        _non_empty(self.plan_id, "plan ID")
        _positive_int(self.plan_version, "plan version")
        parameters = _mapping(self.parameters, "request parameters")
        gates = _mapping(self.gates, "request gates")
        if any(not isinstance(key, str) or not isinstance(value, bool) for key, value in gates.items()):
            raise QueryContractError("request gates must be boolean values")
        evidence = self.required_evidence
        if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
            raise QueryContractError("required_evidence must be an ordered sequence")
        selections = tuple(
            item if isinstance(item, EvidenceSelection) else EvidenceSelection.from_mapping(item, index)
            for index, item in enumerate(evidence)
        )
        if len({item.role for item in selections}) != len(selections):
            raise QueryContractError("required evidence roles must be unique")
        if self.expected_publication_id is not None:
            _non_empty(self.expected_publication_id, "expected publication ID")
        if not isinstance(self.page, QueryPage):
            raise QueryContractError("page must be a QueryPage")
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "gates", gates)
        object.__setattr__(self, "required_evidence", selections)

    @property
    def expected_publication(self) -> str | None:
        return self.expected_publication_id

    @property
    def limit(self) -> int | None:
        return self.page.limit

    @property
    def cursor(self) -> str | None:
        return self.page.cursor

    @property
    def include_exact_count(self) -> bool:
        return self.page.include_exact_count

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": QUERY_SCHEMA,
            "question_id": self.question_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "parameters": dict(self.parameters),
            "gates": dict(self.gates),
            "required_evidence": [item.to_mapping() for item in self.required_evidence],
            "expected_publication_id": self.expected_publication_id,
            "page": self.page.to_mapping(),
        }


@dataclass(frozen=True, slots=True)
class QueryBatchRequest:
    """One atomic batch sharing a single publication snapshot."""

    request_id: str
    plans: tuple[QueryRequest, ...]
    expected_publication_id: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.request_id, "batch request ID")
        if (
            isinstance(self.plans, (str, bytes))
            or not isinstance(self.plans, Sequence)
            or not 1 <= len(self.plans) <= 8
        ):
            raise QueryContractError("query batch must contain 1 through 8 plans")
        if any(not isinstance(plan, QueryRequest) for plan in self.plans):
            raise QueryContractError("query batch accepts only QueryRequest plans")
        plans = tuple(self.plans)
        if len({(plan.question_id, plan.plan_id) for plan in plans}) != len(plans):
            raise QueryContractError("query batch cannot repeat a named plan")
        if self.expected_publication_id is not None:
            _non_empty(self.expected_publication_id, "batch publication ID")
        if any(
            plan.expected_publication_id not in {None, self.expected_publication_id}
            for plan in plans
        ):
            raise QueryContractError("plan and batch publication bindings disagree")
        object.__setattr__(self, "plans", plans)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": QUERY_SCHEMA,
            "request_id": self.request_id,
            "publication_id": self.expected_publication_id,
            "plans": [plan.to_mapping() for plan in self.plans],
        }


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One bounded named-plan result from one publication snapshot."""

    question_id: str
    plan_id: str
    plan_version: int
    publication: Publication
    grades: Mapping[str, str]
    metrics: Mapping[str, Any] = field(default_factory=dict)
    rows: tuple[Mapping[str, Any], ...] = ()
    caveats: tuple[str, ...] = ()
    evidence_selectors: tuple[EvidenceSelection, ...] = ()
    page: QueryPage = field(default_factory=QueryPage)
    request_digest: str | None = None

    def __post_init__(self) -> None:
        _non_empty(self.question_id, "result question ID")
        _non_empty(self.plan_id, "result plan ID")
        _positive_int(self.plan_version, "result plan version")
        if not isinstance(self.publication, Publication):
            raise QueryContractError("result publication must be a Publication")
        grades = _mapping(self.grades, "result grades")
        if any(not isinstance(value, str) or value not in _GRADES for value in grades.values()):
            raise QueryContractError("result grades contain an unsupported grade")
        metrics = _mapping(self.metrics, "result metrics")
        rows = self.rows
        if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
            raise QueryContractError("result rows must be an ordered sequence")
        frozen_rows = tuple(_mapping(row, f"result rows[{index}]") for index, row in enumerate(rows))
        caveats = self.caveats
        if isinstance(caveats, (str, bytes)) or not isinstance(caveats, Sequence):
            raise QueryContractError("result caveats must be an ordered sequence")
        if any(not isinstance(item, str) or not item.strip() for item in caveats):
            raise QueryContractError("result caveats must be non-empty strings")
        selections = tuple(
            item if isinstance(item, EvidenceSelection) else EvidenceSelection.from_mapping(item, index)
            for index, item in enumerate(self.evidence_selectors)
        )
        if not isinstance(self.page, QueryPage):
            raise QueryContractError("result page must be a QueryPage")
        digest = _optional_digest(self.request_digest, "result request digest")
        object.__setattr__(self, "grades", grades)
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "rows", frozen_rows)
        object.__setattr__(self, "caveats", tuple(caveats))
        object.__setattr__(self, "evidence_selectors", selections)
        object.__setattr__(self, "request_digest", digest)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "question_id": self.question_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "publication": self.publication.to_mapping(),
            "grades": dict(self.grades),
            "metrics": canonical_json_value(self.metrics),
            "rows": canonical_json_value(self.rows),
            "caveats": list(self.caveats),
            "evidence_selectors": [item.to_mapping() for item in self.evidence_selectors],
            "page": self.page.to_mapping(),
            "request_digest": self.request_digest,
        }


@dataclass(frozen=True, slots=True)
class QueryBatchResult:
    """Canonical result envelope for one atomic query batch."""

    request_id: str
    publication: Publication
    results: tuple[QueryResult, ...]
    coverage: Mapping[str, Any] = field(default_factory=dict)
    capabilities: Mapping[str, Any] = field(default_factory=dict)
    next_supported_questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.request_id, "batch result request ID")
        if not isinstance(self.publication, Publication):
            raise QueryContractError("batch result publication must be Publication")
        if (
            isinstance(self.results, (str, bytes))
            or not isinstance(self.results, Sequence)
            or not self.results
            or any(not isinstance(item, QueryResult) for item in self.results)
        ):
            raise QueryContractError("batch result requires typed plan results")
        results = tuple(self.results)
        if any(item.publication != self.publication for item in results):
            raise QueryContractError("batch result publications disagree")
        questions = tuple(self.next_supported_questions)
        if any(not isinstance(item, str) or not item for item in questions):
            raise QueryContractError("next supported question IDs are malformed")
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "coverage", _mapping(self.coverage, "batch coverage"))
        object.__setattr__(
            self,
            "capabilities",
            _mapping(self.capabilities, "batch capabilities"),
        )
        object.__setattr__(self, "next_supported_questions", questions)

    def to_mapping(self) -> dict[str, Any]:
        plan_results = []
        for result in self.results:
            item = result.to_mapping()
            item.pop("schema", None)
            item.pop("publication", None)
            plan_results.append(item)
        return {
            "schema": RESULT_SCHEMA,
            "request_id": self.request_id,
            "publication": self.publication.to_mapping(),
            "coverage": dict(self.coverage),
            "capabilities": dict(self.capabilities),
            "results": plan_results,
            "next_supported_questions": list(self.next_supported_questions),
        }


def canonical_json_value(value: Any) -> Any:
    """Return a deterministic JSON-safe value, including canonical Decimals."""

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise QueryContractError("cannot serialize a non-finite Decimal")
        rendered = format(value.normalize(), "f")
        return "0" if rendered == "-0" else rendered
    if isinstance(value, float):
        if not math.isfinite(value):
            raise QueryContractError("cannot serialize a non-finite float")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise QueryContractError("JSON mappings require string keys")
        return {key: canonical_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise QueryContractError("unordered sets are not JSON-safe")
    raise QueryContractError(f"cannot serialize {type(value).__name__} as JSON")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        canonical_json_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def serialize_request(request: QueryRequest) -> bytes:
    if not isinstance(request, QueryRequest):
        raise QueryContractError("request serialization requires a QueryRequest")
    return canonical_json_bytes(request.to_mapping())


def serialize_result(result: QueryResult) -> bytes:
    if not isinstance(result, QueryResult):
        raise QueryContractError("result serialization requires a QueryResult")
    return canonical_json_bytes(result.to_mapping())


def serialize_batch_result(result: QueryBatchResult) -> bytes:
    if not isinstance(result, QueryBatchResult):
        raise QueryContractError("serialize_batch_result requires QueryBatchResult")
    return canonical_json_bytes(result.to_mapping())


def request_sha256(request: QueryRequest) -> str:
    return hashlib.sha256(serialize_request(request)).hexdigest()


def result_sha256(result: QueryResult) -> str:
    return hashlib.sha256(serialize_result(result)).hexdigest()


request_digest = request_sha256
result_digest = result_sha256

NamedQueryRequest = QueryRequest
NamedQueryResult = QueryResult
QueryPublication = Publication


__all__ = [
    "EvidenceSelection",
    "MAX_CURSOR_BYTES",
    "MAX_PAGE_LIMIT",
    "NamedQueryRequest",
    "NamedQueryResult",
    "Publication",
    "QueryBatchRequest",
    "QueryBatchResult",
    "QueryContractError",
    "QueryPage",
    "QueryPublication",
    "QueryRequest",
    "QueryResult",
    "QUERY_SCHEMA",
    "RESULT_SCHEMA",
    "RequiredEvidence",
    "canonical_json_bytes",
    "canonical_json_value",
    "request_digest",
    "request_sha256",
    "result_digest",
    "result_sha256",
    "serialize_request",
    "serialize_batch_result",
    "serialize_result",
]
