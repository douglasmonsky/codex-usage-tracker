"""Strict HTTP v2 request facade over transport-independent application services."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from urllib.parse import parse_qs, unquote

from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG
from codex_usage_tracker.analytics.analysis_models import (
    ANALYSIS_GOALS,
    AnalysisRequest,
    ComparisonWindow,
)
from codex_usage_tracker.application.allowance import get_allowance
from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.application.analyze import AnalysisRuntime, analyze_usage
from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.errors import ApplicationError
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.application.job_status import get_job_status
from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import (
    ALL_QUERY_MEASURES,
    QUERY_ENTITY_CAPABILITIES,
    QueryFilters,
    QueryRequest,
)
from codex_usage_tracker.application.query_validation import normalize_query_filters
from codex_usage_tracker.application.refresh import default_job_service, refresh_usage
from codex_usage_tracker.application.requests import (
    JobStatusRequest,
    RefreshRequest,
    RequestScope,
    StatusRequest,
)
from codex_usage_tracker.application.status import get_status
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.evidence.models import (
    EvidenceAmbiguityError,
    EvidenceHistoryMismatchError,
    EvidenceNotFoundError,
    EvidenceRequest,
)
from codex_usage_tracker.interfaces.http.serialization import (
    HttpRequestError,
    decode_json_object,
    read_bounded_body,
    serialize_http_payload,
)

HTTP_V2_ROUTES = {
    ("GET", "/api/v2/status"),
    ("POST", "/api/v2/refresh"),
    ("POST", "/api/v2/analyze"),
    ("POST", "/api/v2/query"),
    ("POST", "/api/v2/evidence"),
    ("POST", "/api/v2/allowance"),
    ("GET", "/api/v2/jobs/{job_id}"),
    ("GET", "/api/v2/capabilities"),
}

_BODY_LIMITS = {
    "/api/v2/refresh": 4 * 1024,
    "/api/v2/analyze": 32 * 1024,
    "/api/v2/query": 32 * 1024,
    "/api/v2/evidence": 16 * 1024,
    "/api/v2/allowance": 16 * 1024,
}
_TOKEN_REQUIRED = {"/api/v2/refresh", "/api/v2/analyze"}
_OUTPUT_LIMITS = {
    "/api/v2/status": 64 * 1024,
    "/api/v2/refresh": 128 * 1024,
    "/api/v2/jobs/{job_id}": 128 * 1024,
    "/api/v2/analyze": 512 * 1024,
    "/api/v2/query": 256 * 1024,
    "/api/v2/evidence": 128 * 1024,
    "/api/v2/allowance": 256 * 1024,
    "/api/v2/capabilities": 64 * 1024,
}


class HttpV2Services(Protocol):
    def status(self, request: StatusRequest) -> object: ...
    def refresh(self, request: RefreshRequest) -> object: ...
    def analyze(self, request: AnalysisRequest) -> object: ...
    def query(self, request: QueryRequest) -> object: ...
    def evidence(self, request: EvidenceRequest) -> object: ...
    def allowance(self, request: AllowanceRequest) -> object: ...
    def job_status(self, request: JobStatusRequest) -> object: ...
    def capabilities(self) -> object: ...


@dataclass
class ApplicationHttpV2Services:
    """Application-service implementation shared by the live localhost server."""

    db_path: Path = DEFAULT_DB_PATH
    pricing_path: Path = DEFAULT_PRICING_PATH
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH
    codex_home: Path = DEFAULT_CODEX_HOME

    def __post_init__(self) -> None:
        self.job_service = default_job_service()
        self.analysis_runtime = AnalysisRuntime(
            job_service=self.job_service,
            pricing_fingerprint=_path_fingerprint(self.pricing_path),
            rate_card_fingerprint=_path_fingerprint(self.rate_card_path),
            thresholds_fingerprint=_path_fingerprint(self.thresholds_path),
            catalog_version=_catalog_fingerprint(),
        )

    def status(self, request: StatusRequest) -> object:
        return get_status(
            replace(
                request,
                db_path=self.db_path,
                pricing_path=self.pricing_path,
                codex_home=self.codex_home,
            )
        )

    def refresh(self, request: RefreshRequest) -> object:
        outcome = refresh_usage(
            request,
            codex_home=self.codex_home,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            job_service=self.job_service,
        )
        return outcome.result if outcome.result is not None else outcome.job

    def analyze(self, request: AnalysisRequest) -> object:
        normalized = replace(request, filters=normalize_query_filters(request.filters))
        context = build_request_context(
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            scope=_request_scope(normalized.filters, normalized.history),
        )
        outcome = analyze_usage(
            normalized,
            replace(context, analysis_runtime=self.analysis_runtime),
        )
        return outcome.completed if outcome.completed is not None else outcome.job

    def query(self, request: QueryRequest) -> object:
        return query_usage(
            request,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            allowance_path=self.allowance_path,
        )

    def evidence(self, request: EvidenceRequest) -> object:
        return get_evidence(
            request,
            db_path=self.db_path,
            pricing_path=self.pricing_path,
            job_service=self.job_service,
        )

    def allowance(self, request: AllowanceRequest) -> object:
        result = get_allowance(request, db_path=self.db_path, job_service=self.job_service)
        payload = dict(result.payload)
        payload.setdefault("schema", result.result_schema)
        return payload

    def job_status(self, request: JobStatusRequest) -> object:
        return get_job_status(request, job_service=self.job_service)

    def capabilities(self) -> object:
        return {
            "schema": "codex-usage-tracker.capabilities.v2",
            "analysis_goals": list(ANALYSIS_GOALS),
            "query_entities": {
                name: {
                    "identity": capability.identity,
                    "measures": sorted(capability.measures),
                    "group_by": sorted(capability.group_by),
                }
                for name, capability in QUERY_ENTITY_CAPABILITIES.items()
            },
            "query_measures": sorted(ALL_QUERY_MEASURES),
            "allowance_operations": ["status", "series", "evidence", "analysis"],
            "evidence_selector_kinds": ["finding", "call", "thread", "allowance", "analysis"],
        }


@dataclass(frozen=True)
class HttpV2Response:
    status: int
    payload: dict[str, object]
    headers: Mapping[str, str]


class HttpV2Facade:
    """Decode HTTP state into typed requests and invoke one application facade."""

    def __init__(self, services: HttpV2Services) -> None:
        self.services = services

    def handle(
        self,
        *,
        method: str,
        path: str,
        query: str,
        body: bytes,
        content_type: str,
        authorized: bool,
    ) -> HttpV2Response:
        try:
            return self._handle(method.upper(), path, query, body, content_type, authorized)
        except HttpRequestError as exc:
            return _error(exc.status, exc.code, exc.message)
        except EvidenceHistoryMismatchError as exc:
            return _error(404, "evidence_history_mismatch", str(exc))
        except EvidenceNotFoundError as exc:
            return _error(404, "evidence_not_found", str(exc))
        except EvidenceAmbiguityError as exc:
            return _error(409, "evidence_ambiguous", str(exc))
        except (ApplicationError, TypeError, ValueError) as exc:
            return _error(400, "invalid_request", str(exc))

    def handle_stream(
        self,
        *,
        method: str,
        path: str,
        query: str,
        stream: BinaryIO,
        content_length: str | None,
        content_type: str,
        authorized: bool,
    ) -> HttpV2Response:
        """Read a bounded server request body before using the pure dispatcher."""
        try:
            body = (
                read_bounded_body(
                    stream,
                    content_length=content_length,
                    max_bytes=_BODY_LIMITS[path],
                )
                if method.upper() == "POST" and path in _BODY_LIMITS
                else b""
            )
        except HttpRequestError as exc:
            return _error(exc.status, exc.code, exc.message)
        return self.handle(
            method=method,
            path=path,
            query=query,
            body=body,
            content_type=content_type,
            authorized=authorized,
        )

    def _handle(
        self,
        method: str,
        path: str,
        query: str,
        body: bytes,
        content_type: str,
        authorized: bool,
    ) -> HttpV2Response:
        route_path = _route_path(path)
        allow = _allowed_method(route_path)
        if allow is None:
            return _error(404, "not_found", "Unknown API endpoint")
        if method != allow:
            return _error(405, "method_not_allowed", "Method not allowed", {"Allow": allow})
        if route_path in _TOKEN_REQUIRED and not authorized:
            return _error(403, "forbidden", "Valid local API token required")

        if method == "GET":
            result = self._get(route_path, path, query)
        else:
            payload = decode_json_object(
                body,
                content_type=content_type,
                max_bytes=_BODY_LIMITS[route_path],
            )
            result = self._post(route_path, payload)
        payload = serialize_http_payload(result)
        encoded_size = len(json.dumps(payload, separators=(",", ":")).encode())
        if encoded_size > _OUTPUT_LIMITS[route_path]:
            return _error(500, "response_too_large", "Response exceeds the route output limit")
        status = 202 if method == "POST" and payload.get("schema") == "codex-usage-tracker.job.v1" else 200
        return HttpV2Response(status, payload, {})

    def _get(self, route_path: str, path: str, query: str) -> object:
        params = _query_params(query)
        if route_path == "/api/v2/status":
            _reject_unknown(params, {"history", "freshness_threshold_seconds"})
            scope = RequestScope(history=cast(Any, _one(params, "history", "active")))
            threshold = _integer(_one(params, "freshness_threshold_seconds", "300"), "freshness_threshold_seconds")
            return self.services.status(StatusRequest(scope=scope, freshness_threshold_seconds=threshold))
        if route_path == "/api/v2/capabilities":
            _reject_unknown(params, set())
            return self.services.capabilities()
        _reject_unknown(params, {"include_result"})
        job_id = unquote(path.removeprefix("/api/v2/jobs/"))
        return self.services.job_status(
            JobStatusRequest(job_id=job_id, include_result=_boolean(_one(params, "include_result", "0")))
        )

    def _post(self, path: str, payload: dict[str, object]) -> object:
        if path == "/api/v2/refresh":
            _reject_unknown(payload, {"history", "aggregate_only", "execution"})
            return self.services.refresh(RefreshRequest(**payload))  # type: ignore[arg-type]
        if path == "/api/v2/analyze":
            return self.services.analyze(_analysis_request(payload))
        if path == "/api/v2/query":
            return self.services.query(_query_request(payload))
        if path == "/api/v2/evidence":
            _reject_unknown(payload, {item.name for item in fields(EvidenceRequest)})
            return self.services.evidence(EvidenceRequest(**payload))  # type: ignore[arg-type]
        _reject_unknown(payload, {item.name for item in fields(AllowanceRequest)})
        return self.services.allowance(AllowanceRequest(**payload))  # type: ignore[arg-type]


def _analysis_request(payload: dict[str, object]) -> AnalysisRequest:
    allowed = {item.name for item in fields(AnalysisRequest)}
    _reject_unknown(payload, allowed)
    values = dict(payload)
    values["filters"] = _filters(values.get("filters"))
    comparison = values.get("comparison")
    if comparison is not None:
        if not isinstance(comparison, Mapping):
            raise ValueError("comparison must be an object")
        _reject_unknown(comparison, {"since", "until"}, prefix="comparison.")
        values["comparison"] = ComparisonWindow(**dict(comparison))  # type: ignore[arg-type]
    return AnalysisRequest(**values)  # type: ignore[arg-type]


def _query_request(payload: dict[str, object]) -> QueryRequest:
    _reject_unknown(payload, {item.name for item in fields(QueryRequest)})
    values = dict(payload)
    values["filters"] = _filters(values.get("filters"))
    for name in ("measures", "group_by"):
        if name in values:
            values[name] = _strings(values[name], name)
    return QueryRequest(**values)  # type: ignore[arg-type]


def _filters(value: object) -> QueryFilters:
    if value is None:
        return QueryFilters()
    if not isinstance(value, Mapping):
        raise ValueError("filters must be an object")
    _reject_unknown(value, {item.name for item in fields(QueryFilters)}, prefix="filters.")
    return QueryFilters(**dict(value))  # type: ignore[arg-type]


def _request_scope(filters: QueryFilters, history: str) -> RequestScope:
    return RequestScope(
        since=filters.since,
        until=filters.until,
        history=cast(Any, history),
        project=filters.project,
        thread_key=filters.thread_key,
        model=filters.model,
        effort=filters.effort,
    )


def _strings(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be an array of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must contain only strings")
    return tuple(cast(Sequence[str], value))


def _route_path(path: str) -> str:
    if path.startswith("/api/v2/jobs/") and path != "/api/v2/jobs/":
        return "/api/v2/jobs/{job_id}"
    return path


def _allowed_method(path: str) -> str | None:
    for method, candidate in HTTP_V2_ROUTES:
        if candidate == path:
            return method
    return None


def _query_params(query: str) -> dict[str, list[str]]:
    return parse_qs(query, keep_blank_values=True, strict_parsing=False)


def _one(params: Mapping[str, list[str]], name: str, default: str) -> str:
    values = params.get(name)
    if values is None:
        return default
    if len(values) != 1:
        raise ValueError(f"{name} must appear once")
    return values[0]


def _integer(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _boolean(value: str) -> bool:
    if value in {"1", "true"}:
        return True
    if value in {"0", "false"}:
        return False
    raise ValueError("boolean query parameters must be 0, 1, false, or true")


def _reject_unknown(
    payload: Mapping[str, object], allowed: set[str], *, prefix: str = ""
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise HttpRequestError(400, "invalid_request", f"unsupported field: {prefix}{unknown[0]}")


def _path_fingerprint(path: Path) -> str:
    content = path.read_bytes() if path.is_file() else b"missing"
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _catalog_fingerprint() -> str:
    payload = [
        {
            "goal": goal,
            "strategy_id": entry.strategy.strategy_id,
            "strategy_version": entry.strategy.strategy_version,
        }
        for goal, entry in sorted(ANALYSIS_CATALOG.items())
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _error(
    status: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> HttpV2Response:
    return HttpV2Response(
        status,
        {
            "schema": "codex-usage-tracker.error.v1",
            "error": {"code": code, "message": message},
        },
        headers or {},
    )
