"""Bounded, query-only evidence pages over database-v1 typed streams.

This module is deliberately a narrow transport boundary.  Selector ownership
stays with :mod:`selectors`, cursor integrity stays with :mod:`cursors`, and
this service owns only one read transaction, fixed stream statements, and the
bounded response envelope.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from codex_usage_tracker.agent_kernel.domain.plan_operands import PlanRequest
from codex_usage_tracker.agent_kernel.storage.database import open_read_only

from .cursors import CursorBinding, CursorCodec, CursorError
from .selectors import EvidenceReference, EvidenceSelectorError, EvidenceSelectorResolver

EVIDENCE_SCHEMA = "codex-usage-tracker.evidence-page.v1"
EVIDENCE_PLAN_ID = "evidence-page"
EVIDENCE_PLAN_VERSION = 1
MAX_EVIDENCE_LIMIT = 100
MAX_EVIDENCE_BYTES = 16_384
MAX_CURSOR_BYTES = 4_096
EVIDENCE_VIEWS = (
    "summary",
    "timeline",
    "calls",
    "tools",
    "resources",
    "state_changes",
    "allowance_interval",
)

Clock = Callable[[], int]
_CURSOR_TTL_US = 24 * 60 * 60 * 1_000_000
_FORBIDDEN_REQUEST_KEYS = frozenset(
    {"body", "expression", "raw_body", "raw_sql", "refresh", "sql", "write"}
)
_SELECTOR_PREFIXES = MappingProxyType(
    {
        "allowance-interval": "allowance_interval",
        "allowance-observation": "allowance_observation",
        "call": "call",
        "model-profile": "model_profile",
        "project": "project",
        "publication": "publication",
        "rate-card": "rate_card",
        "resource": "resource",
        "session": "session",
        "source-manifestation": "source_manifestation",
        "state-change": "state_change",
        "tool": "tool",
        "turn": "turn",
        "window": "window",
    }
)


class EvidenceContractError(ValueError):
    """An evidence request or page contract is malformed."""


class EvidenceServiceError(RuntimeError):
    """The selected committed snapshot cannot produce the requested page."""


def _finite(value: Any, label: str) -> None:
    if isinstance(value, Decimal) and not value.is_finite():
        raise EvidenceContractError(f"{label} contains a non-finite Decimal")
    if isinstance(value, float) and not math.isfinite(value):
        raise EvidenceContractError(f"{label} contains a non-finite float")


def _freeze(value: Any, label: str) -> Any:
    """Freeze JSON-shaped request values and reject executable-looking keys."""

    if value is None or isinstance(value, (str, int, bool, Decimal, float)):
        _finite(value, label)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceContractError(f"{label} requires string keys")
            if key.lower() in _FORBIDDEN_REQUEST_KEYS:
                raise EvidenceContractError(f"{label} contains forbidden key {key!r}")
            frozen[key] = _freeze(item, f"{label}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item, f"{label}[]") for item in value)
    raise EvidenceContractError(f"{label} contains unsupported {type(value).__name__}")


def _mapping(value: Mapping[str, Any], label: str) -> Mapping[str, Any]:
    frozen = _freeze(value, label)
    if not isinstance(frozen, Mapping):
        raise EvidenceContractError(f"{label} must be a mapping")
    return frozen


def _selector(value: Any, label: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EvidenceContractError(f"{label} must be a non-empty selector")
    if len(value.encode("utf-8")) > 256 or any(ch in value for ch in ("\x00", "\n", "\r")):
        raise EvidenceContractError(f"{label} is malformed")
    prefix, separator, logical_id = value.partition(":")
    if not separator or prefix not in _SELECTOR_PREFIXES or not logical_id.strip():
        raise EvidenceContractError(f"{label} has an unknown selector kind")
    if logical_id != logical_id.strip() or any(ch.isspace() for ch in logical_id):
        raise EvidenceContractError(f"{label} has a malformed logical ID")
    return value


def _positive_int(value: Any, label: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EvidenceContractError(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise EvidenceContractError(f"{label} must be at most {maximum}")
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            _plain(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EvidenceContractError("evidence value is not JSON-shaped") from error


def _row_mapping(row: Any, description: Sequence[Any] | None = None) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}  # noqa: SIM118
    if isinstance(row, Mapping):
        return dict(row)
    if description is None:
        raise EvidenceServiceError("SQLite row has no column description")
    return {column[0]: value for column, value in zip(description, row, strict=True)}


@dataclass(frozen=True, slots=True)
class EvidenceRequest:
    """Typed internal input for one bounded evidence page."""

    selector: str | None = None
    selector_role: str = "selector"
    view: str = "summary"
    boundary_pair: tuple[str, str] | None = None
    compatible_boundary_pair: tuple[str, str] | None = None
    direction: str = "forward"
    limit: int = MAX_EVIDENCE_LIMIT
    byte_limit: int = MAX_EVIDENCE_BYTES
    cursor: str | None = None
    publication_id: str | None = None
    expected_publication_id: str | None = None
    plan_id: str = EVIDENCE_PLAN_ID
    plan_version: int = EVIDENCE_PLAN_VERSION
    parameters: Mapping[str, Any] = field(default_factory=dict)
    gates: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        selectors = [value for value in (self.boundary_pair, self.compatible_boundary_pair) if value is not None]
        if (self.selector is None) == (len(selectors) == 0):
            raise EvidenceContractError(
                "evidence request requires exactly one selector or compatible boundary pair"
            )
        if self.selector is not None:
            object.__setattr__(self, "selector", _selector(self.selector, "selector"))
        if (
            not isinstance(self.selector_role, str)
            or not self.selector_role
            or self.selector_role != self.selector_role.strip()
            or any(character.isspace() for character in self.selector_role)
        ):
            raise EvidenceContractError("selector_role must be a non-empty token")
        if len(selectors) > 1:
            raise EvidenceContractError("boundary_pair and compatible_boundary_pair are aliases")
        if selectors:
            pair = selectors[0]
            if (
                isinstance(pair, (str, bytes))
                or not isinstance(pair, Sequence)
                or len(pair) != 2
            ):
                raise EvidenceContractError("compatible boundary pair must contain two selectors")
            normalized = (_selector(pair[0], "boundary_pair[0]"), _selector(pair[1], "boundary_pair[1]"))
            object.__setattr__(self, "boundary_pair", normalized)
            object.__setattr__(self, "compatible_boundary_pair", normalized)
        if self.view not in EVIDENCE_VIEWS:
            raise EvidenceContractError(f"evidence view {self.view!r} is not allowlisted")
        if self.direction not in {"forward", "backward"}:
            raise EvidenceContractError("evidence direction must be forward or backward")
        _positive_int(self.limit, "evidence limit", MAX_EVIDENCE_LIMIT)
        _positive_int(self.byte_limit, "evidence byte limit", MAX_EVIDENCE_BYTES)
        if self.cursor is not None:
            if not isinstance(self.cursor, str) or not self.cursor:
                raise EvidenceContractError("evidence cursor must be non-empty")
            if len(self.cursor.encode("utf-8")) > MAX_CURSOR_BYTES:
                raise EvidenceContractError("evidence cursor exceeds the maximum size")
        expected = self.publication_id
        if self.expected_publication_id is not None:
            if expected is not None and expected != self.expected_publication_id:
                raise EvidenceContractError("publication bindings disagree")
            expected = self.expected_publication_id
        if expected is not None:
            if not isinstance(expected, str) or not expected.strip() or expected != expected.strip():
                raise EvidenceContractError("publication binding must be a non-empty ID")
            object.__setattr__(self, "publication_id", expected)
            object.__setattr__(self, "expected_publication_id", expected)
        if not isinstance(self.plan_id, str) or not self.plan_id.strip() or any(ch.isspace() for ch in self.plan_id):
            raise EvidenceContractError("plan_id must be a non-empty token")
        _positive_int(self.plan_version, "plan_version")
        object.__setattr__(self, "parameters", _mapping(self.parameters, "parameters"))
        if not isinstance(self.gates, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, bool)
            for key, value in self.gates.items()
        ):
            raise EvidenceContractError("gates must be a string-to-boolean mapping")
        object.__setattr__(self, "gates", _mapping(self.gates, "gates"))

    @property
    def selectors(self) -> tuple[str, ...]:
        if self.selector is not None:
            return (self.selector,)
        assert self.boundary_pair is not None
        return self.boundary_pair

    @property
    def bound_publication_id(self) -> str | None:
        return self.publication_id


@dataclass(frozen=True, slots=True)
class EvidencePage:
    """Immutable typed evidence response envelope."""

    publication: Mapping[str, Any]
    coverage: Mapping[str, Any]
    resolved_selector: Mapping[str, Any]
    summary: Mapping[str, Any]
    boundaries: tuple[Mapping[str, Any], ...]
    rows: tuple[Mapping[str, Any], ...]
    view: str
    direction: str
    limit: int
    byte_limit: int
    returned_rows: int
    has_more: bool
    next_cursor: str | None
    response_bytes: int

    def __post_init__(self) -> None:
        if self.view not in EVIDENCE_VIEWS:
            raise EvidenceContractError("page view is not allowlisted")
        if self.direction not in {"forward", "backward"}:
            raise EvidenceContractError("page direction is invalid")
        _positive_int(self.limit, "page limit", MAX_EVIDENCE_LIMIT)
        _positive_int(self.byte_limit, "page byte limit", MAX_EVIDENCE_BYTES)
        if len(self.rows) > self.limit or len(self.rows) > MAX_EVIDENCE_LIMIT:
            raise EvidenceContractError("page row bound exceeded")
        if self.returned_rows != len(self.rows):
            raise EvidenceContractError("page returned row metadata is inconsistent")
        if self.has_more != (self.next_cursor is not None):
            raise EvidenceContractError("page cursor metadata is inconsistent")
        if isinstance(self.response_bytes, bool) or self.response_bytes < 0 or self.response_bytes > self.byte_limit:
            raise EvidenceContractError("page byte bound exceeded")
        object.__setattr__(self, "publication", _mapping(self.publication, "publication"))
        object.__setattr__(self, "coverage", _mapping(self.coverage, "coverage"))
        object.__setattr__(self, "resolved_selector", _mapping(self.resolved_selector, "resolved_selector"))
        object.__setattr__(self, "summary", _mapping(self.summary, "summary"))
        object.__setattr__(
            self,
            "boundaries",
            tuple(_mapping(item, "boundary") for item in self.boundaries),
        )
        object.__setattr__(self, "rows", tuple(_mapping(item, "row") for item in self.rows))

    @property
    def metadata(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "view": self.view,
                "direction": self.direction,
                "limit": self.limit,
                "byte_limit": self.byte_limit,
                "returned_rows": self.returned_rows,
                "has_more": self.has_more,
                "next_cursor": self.next_cursor,
                "response_bytes": self.response_bytes,
            }
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema": EVIDENCE_SCHEMA,
            "publication": _plain(self.publication),
            "coverage": _plain(self.coverage),
            "resolved_selector": _plain(self.resolved_selector),
            "summary": _plain(self.summary),
            "boundaries": _plain(self.boundaries),
            "rows": _plain(self.rows),
            "page": _plain(self.metadata),
        }


# The stream columns are fixed once, then each branch below supplies only
# constant table expressions.  No caller value is interpolated into SQL.
_STREAM_COLUMNS = (
    "event_kind",
    "logical_id",
    "event_at_us",
    "source_rank",
    "source_order",
    "event_kind_order",
    "transition_rank",
    "session_id",
    "turn_id",
    "turn_ordinal",
    "lifecycle_state",
    "state_basis",
    "transition_version",
    "context_window_tokens",
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "output_tokens",
    "token_basis",
    "transport_name",
    "semantic_operation",
    "tool_family",
    "write_intent",
    "resource_id",
    "resource_kind",
    "resource_label",
    "change_kind",
    "before_revision",
    "after_revision",
    "confidence",
    "allowance_used_percent",
    "allowance_remaining_percent",
    "allowance_ordinal",
    "reset_time_us",
    "model_profile_id",
    "model",
    "reasoning_effort",
    "service_tier",
    "call_id",
    "tool_id",
    "state_change_id",
    "allowance_observation_id",
    "occurrence_id",
    "manifestation_id",
    "source_id",
    "source_revision",
    "record_ordinal",
    "byte_start",
    "byte_end",
    "adapter_version",
    "project_id",
    "observed_duration_us",
    "output_bytes",
    "error_category",
    "before_context_epoch",
    "after_context_epoch",
)


def _branch(values: Mapping[str, str], source: str) -> str:
    expressions = [f"{values.get(column, 'NULL')} AS {column}" for column in _STREAM_COLUMNS]
    return "SELECT\n  " + ",\n  ".join(expressions) + "\n" + source


_OCCURRENCE_FIELDS = {
    "occurrence_id": "o.occurrence_id",
    "manifestation_id": "sm.manifestation_id",
    "source_id": "sm.source_id",
    "source_revision": "o.source_revision",
    "record_ordinal": "o.record_ordinal",
    "byte_start": "o.byte_start",
    "byte_end": "o.byte_end",
    "adapter_version": "o.adapter_version",
}

_STREAM_BRANCHES = (
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'session'",
            "logical_id": "s.session_id",
            "event_at_us": "s.start_at_us",
            "source_rank": "COALESCE(sm.source_rank, 0)",
            "source_order": "COALESCE(o.record_ordinal, 0)",
            "event_kind_order": "10",
            "session_id": "s.session_id",
            "lifecycle_state": "s.lifecycle_state",
            "state_basis": "s.state_basis",
            "transition_version": "s.transition_version",
            "project_id": "s.project_id",
        },
        """FROM sessions AS s
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = s.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'turn'",
            "logical_id": "t.turn_id",
            "event_at_us": "t.start_at_us",
            "source_rank": "COALESCE(sm.source_rank, 0)",
            "source_order": "COALESCE(t.start_source_order, o.record_ordinal, 0)",
            "event_kind_order": "20",
            "session_id": "t.session_id",
            "turn_id": "t.turn_id",
            "turn_ordinal": "t.ordinal",
            "lifecycle_state": "t.lifecycle_state",
            "state_basis": "t.state_basis",
            "transition_version": "t.transition_version",
        },
        """FROM turns AS t
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = t.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'call'",
            "logical_id": "mc.call_id",
            "event_at_us": "mc.event_at_us",
            "source_rank": "mc.source_rank",
            "source_order": "mc.source_order",
            "event_kind_order": "mc.event_kind_order",
            "transition_rank": "mc.transition_rank",
            "session_id": "mc.session_id",
            "turn_id": "mc.turn_id",
            "lifecycle_state": "mc.lifecycle_state",
            "state_basis": "mc.state_basis",
            "transition_version": "mc.transition_version",
            "context_window_tokens": "mc.context_window_tokens",
            "uncached_input_tokens": "mc.uncached_input_tokens",
            "cached_input_tokens": "mc.cached_input_tokens",
            "reasoning_tokens": "mc.reasoning_tokens",
            "output_tokens": "mc.output_tokens",
            "token_basis": "mc.token_basis",
            "model_profile_id": "mc.model_profile_id",
            "model": "mp.model",
            "reasoning_effort": "mp.reasoning_effort",
            "service_tier": "mp.service_tier",
            "call_id": "mc.call_id",
            "project_id": "s.project_id",
            "error_category": "mc.error_category",
        },
        """FROM model_calls_visible AS mc
        JOIN sessions AS s ON s.session_id = mc.session_id
        LEFT JOIN model_profiles AS mp ON mp.model_profile_id = mc.model_profile_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = mc.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'tool'",
            "logical_id": "ti.tool_id",
            "event_at_us": "ti.start_at_us",
            "source_rank": "ti.start_source_rank",
            "source_order": "ti.start_source_order",
            "event_kind_order": "ti.start_event_kind_order",
            "transition_rank": "ti.start_transition_rank",
            "session_id": "ti.session_id",
            "turn_id": "ti.turn_id",
            "lifecycle_state": "ti.lifecycle_state",
            "state_basis": "ti.state_basis",
            "transition_version": "ti.transition_version",
            "transport_name": "ti.transport_name",
            "semantic_operation": "ti.semantic_operation",
            "tool_family": "ti.tool_family",
            "write_intent": "ti.write_intent",
            "resource_id": "ti.primary_resource_id",
            "resource_kind": "r.resource_kind",
            "resource_label": "r.display_label",
            "tool_id": "ti.tool_id",
            "project_id": "s.project_id",
            "observed_duration_us": "ti.observed_duration_us",
            "output_bytes": "ti.output_bytes",
            "error_category": "ti.error_category",
        },
        """FROM tool_invocations AS ti
        JOIN sessions AS s ON s.session_id = ti.session_id
        LEFT JOIN resources AS r ON r.resource_id = ti.primary_resource_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = ti.start_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'resource'",
            "logical_id": "r.resource_id",
            "source_rank": "COALESCE(sm.source_rank, 0)",
            "source_order": "COALESCE(o.record_ordinal, 0)",
            "event_kind_order": "45",
            "resource_id": "r.resource_id",
            "resource_kind": "r.resource_kind",
            "resource_label": "r.display_label",
            "project_id": "r.project_id",
        },
        """FROM resources AS r
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = (
            SELECT oo.occurrence_id
              FROM source_occurrences AS oo
             WHERE oo.semantic_logical_id = r.resource_id
             ORDER BY oo.record_ordinal, oo.byte_start, oo.byte_end, oo.occurrence_id
             LIMIT 1
        )
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'state_change'",
            "logical_id": "sc.change_id",
            "event_at_us": "sc.event_at_us",
            "source_rank": "sc.source_rank",
            "source_order": "sc.source_order",
            "event_kind_order": "sc.event_kind_order",
            "transition_rank": "sc.transition_rank",
            "session_id": "sc.session_id",
            "turn_id": "sc.turn_id",
            "change_kind": "sc.change_kind",
            "resource_id": "sc.resource_id",
            "resource_kind": "r.resource_kind",
            "resource_label": "r.display_label",
            "before_revision": "sc.before_revision",
            "after_revision": "sc.after_revision",
            "confidence": "sc.confidence",
            "state_change_id": "sc.change_id",
            "project_id": "s.project_id",
        },
        """FROM state_changes AS sc
        JOIN sessions AS s ON s.session_id = sc.session_id
        JOIN resources AS r ON r.resource_id = sc.resource_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = sc.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'activity'",
            "logical_id": "a.activity_id",
            "event_at_us": "a.event_at_us",
            "source_rank": "a.source_rank",
            "source_order": "a.source_order",
            "event_kind_order": "a.event_kind_order",
            "transition_rank": "a.transition_rank",
            "session_id": "a.session_id",
            "turn_id": "a.turn_id",
            "lifecycle_state": "a.lifecycle_state",
            "state_basis": "a.state_basis",
            "transition_version": "a.transition_version",
            "project_id": "s.project_id",
        },
        """FROM activities AS a
        JOIN sessions AS s ON s.session_id = a.session_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = a.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'compaction'",
            "logical_id": "cb.compaction_id",
            "event_at_us": "cb.event_at_us",
            "source_rank": "cb.source_rank",
            "source_order": "cb.source_order",
            "event_kind_order": "cb.event_kind_order",
            "transition_rank": "cb.transition_rank",
            "session_id": "cb.session_id",
            "before_context_epoch": "cb.before_context_epoch",
            "after_context_epoch": "cb.after_context_epoch",
            "project_id": "s.project_id",
        },
        """FROM compaction_boundaries AS cb
        JOIN sessions AS s ON s.session_id = cb.session_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = cb.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'context_component'",
            "logical_id": "cc.component_id",
            "event_at_us": "cc.event_at_us",
            "source_rank": "cc.source_rank",
            "source_order": "cc.source_order",
            "event_kind_order": "cc.event_kind_order",
            "transition_rank": "cc.transition_rank",
            "session_id": "cc.session_id",
            "turn_id": "cc.turn_id",
            "project_id": "s.project_id",
        },
        """FROM context_components AS cc
        JOIN sessions AS s ON s.session_id = cc.session_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = cc.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'allowance_observation'",
            "logical_id": "ao.observation_id",
            "event_at_us": "ao.observed_at_us",
            "source_rank": "ao.source_rank",
            "source_order": "ao.source_order",
            "event_kind_order": "ao.event_kind_order",
            "transition_rank": "ao.transition_rank",
            "allowance_used_percent": "ao.used_percent",
            "allowance_remaining_percent": "ao.remaining_percent",
            "allowance_ordinal": "ao.observation_ordinal",
            "reset_time_us": "ao.reset_time_us",
            "allowance_observation_id": "ao.observation_id",
        },
        """FROM allowance_observations AS ao
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = ao.primary_occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
    _branch(
        {
            **_OCCURRENCE_FIELDS,
            "event_kind": "'lifecycle_transition'",
            "logical_id": "lt.transition_id",
            "event_at_us": "lt.transition_at_us",
            "source_rank": "lt.source_rank",
            "source_order": "lt.source_order",
            "event_kind_order": "lt.event_kind_order",
            "transition_rank": "lt.transition_rank",
            "session_id": "COALESCE(s.session_id, tr.session_id, mc.session_id, ti.session_id, a.session_id)",
            "turn_id": "COALESCE(tr.turn_id, mc.turn_id, ti.turn_id, a.turn_id)",
            "lifecycle_state": "lt.lifecycle_state",
            "state_basis": "lt.state_basis",
            "transition_version": "lt.transition_version",
            "call_id": "mc.call_id",
            "tool_id": "ti.tool_id",
            "project_id": "COALESCE(s.project_id, sp.project_id, mc_project.project_id, ti_project.project_id, a_project.project_id)",
            "error_category": "lt.terminal_error_category",
        },
        """FROM lifecycle_transitions AS lt
        LEFT JOIN sessions AS s
          ON lt.entity_kind = 'session' AND s.session_id = lt.entity_logical_id
        LEFT JOIN turns AS tr
          ON lt.entity_kind = 'turn' AND tr.turn_id = lt.entity_logical_id
        LEFT JOIN model_calls_visible AS mc
          ON lt.entity_kind = 'model_call' AND mc.call_id = lt.entity_logical_id
        LEFT JOIN tool_invocations AS ti
          ON lt.entity_kind = 'tool_invocation' AND ti.tool_id = lt.entity_logical_id
        LEFT JOIN activities AS a
          ON lt.entity_kind = 'activity' AND a.activity_id = lt.entity_logical_id
        LEFT JOIN sessions AS sp ON sp.session_id = tr.session_id
        LEFT JOIN sessions AS mc_session ON mc_session.session_id = mc.session_id
        LEFT JOIN projects AS mc_project ON mc_project.project_id = mc_session.project_id
        LEFT JOIN sessions AS ti_session ON ti_session.session_id = ti.session_id
        LEFT JOIN projects AS ti_project ON ti_project.project_id = ti_session.project_id
        LEFT JOIN sessions AS a_session ON a_session.session_id = a.session_id
        LEFT JOIN projects AS a_project ON a_project.project_id = a_session.project_id
        LEFT JOIN source_occurrences AS o ON o.occurrence_id = lt.occurrence_id
        LEFT JOIN source_manifestations AS sm ON sm.manifestation_key = o.manifestation_key""",
    ),
)

_STREAM_SQL = "\nUNION ALL\n".join(_STREAM_BRANCHES)
_SCOPE_PREDICATE = """(
       (scope.kind IN ('interval', 'allowance_interval', 'window')
        AND stream.event_at_us IS NOT NULL
        AND stream.event_at_us >= scope.start_us
        AND stream.event_at_us < scope.end_us)
    OR (scope.kind = 'publication')
    OR (scope.kind = 'session' AND stream.session_id = scope.logical_id)
    OR (scope.kind = 'turn' AND stream.turn_id = scope.logical_id)
    OR (scope.kind = 'call' AND stream.call_id = scope.logical_id)
    OR (scope.kind = 'tool' AND stream.tool_id = scope.logical_id)
    OR (scope.kind = 'resource' AND stream.resource_id = scope.logical_id)
    OR (scope.kind = 'state_change' AND stream.state_change_id = scope.logical_id)
    OR (scope.kind = 'project' AND stream.project_id = scope.logical_id)
    OR (scope.kind = 'model_profile' AND stream.model_profile_id = scope.logical_id)
    OR (scope.kind = 'allowance_observation'
        AND stream.allowance_observation_id = scope.logical_id)
    OR (scope.kind = 'source_manifestation'
        AND stream.manifestation_id = scope.logical_id)
)"""
_VIEW_FILTERS = MappingProxyType(
    {
        "timeline": "1 = 1",
        "calls": "stream.event_kind = 'call'",
        "tools": "stream.event_kind = 'tool'",
        "resources": "stream.event_kind = 'resource'",
        "state_changes": "stream.event_kind = 'state_change'",
        "allowance_interval": "stream.event_kind <> 'allowance_observation'",
    }
)
_ORDER_FIELDS = "time_missing, COALESCE(event_at_us, 0), source_rank, source_order, event_kind_order, logical_id, transition_rank"


def _page_sql(view: str, direction: str) -> str:
    comparison = ">" if direction == "forward" else "<"
    order = "ASC" if direction == "forward" else "DESC"
    return f"""WITH scope AS (
    SELECT ? AS kind, ? AS logical_id, ? AS start_us, ? AS end_us
), stream AS (
{_STREAM_SQL}
), scoped AS (
    SELECT stream.*, (stream.event_at_us IS NULL) AS time_missing
      FROM stream CROSS JOIN scope
     WHERE {_SCOPE_PREDICATE}
       AND {_VIEW_FILTERS[view]}
)
SELECT *
  FROM scoped
 WHERE ({_ORDER_FIELDS}) {comparison} (?, ?, ?, ?, ?, ?, ?)
 ORDER BY time_missing {order}, COALESCE(event_at_us, 0) {order},
          source_rank {order}, source_order {order},
          event_kind_order {order}, logical_id {order}, transition_rank {order}
 LIMIT ?"""


_FIRST_PAGE_SQL: Mapping[tuple[str, str], str] = MappingProxyType(
    {(view, direction): _page_sql(view, direction).replace(
        " WHERE (time_missing, COALESCE(event_at_us, 0), source_rank, source_order, event_kind_order, logical_id, transition_rank) "
        + (">" if direction == "forward" else "<")
        + " (?, ?, ?, ?, ?, ?, ?)",
        "",
    ) for view in _VIEW_FILTERS for direction in ("forward", "backward")}
)


def _first_page_sql(view: str, direction: str) -> str:
    # The replace above only removes the fixed keyset predicate; all remaining
    # SQL is assembled from module constants, never request text.
    return _FIRST_PAGE_SQL[(view, direction)]


_SUMMARY_SQL = MappingProxyType(
    {
        "session": """SELECT session_id AS logical_id, project_id, lifecycle_state,
                state_basis, transition_version, start_at_us, end_at_us,
                observed_duration_us, completion_basis
           FROM sessions WHERE session_id = ?""",
        "turn": """SELECT turn_id AS logical_id, session_id, ordinal,
                lifecycle_state, state_basis, transition_version, start_at_us,
                end_at_us, completion_basis
           FROM turns WHERE turn_id = ?""",
        "call": """SELECT mc.call_id AS logical_id, mc.session_id, mc.turn_id,
                mc.model_profile_id, mc.lifecycle_state, mc.state_basis,
                mc.transition_version, mc.event_at_us,
                mc.context_window_tokens, mc.uncached_input_tokens,
                mc.cached_input_tokens, mc.reasoning_tokens, mc.output_tokens,
                mc.token_basis, mc.finish_category, mc.error_category,
                mp.model, mp.reasoning_effort, mp.service_tier
           FROM model_calls_visible AS mc
           LEFT JOIN model_profiles AS mp ON mp.model_profile_id = mc.model_profile_id
          WHERE mc.call_id = ?""",
        "tool": """SELECT ti.tool_id AS logical_id, ti.session_id, ti.turn_id,
                ti.lifecycle_state, ti.state_basis, ti.transition_version,
                ti.transport_name, ti.semantic_operation, ti.tool_family,
                ti.write_intent, ti.primary_resource_id, ti.start_at_us,
                ti.terminal_at_us, ti.observed_duration_us, ti.output_bytes,
                ti.error_category, r.resource_kind, r.display_label
           FROM tool_invocations AS ti
           LEFT JOIN resources AS r ON r.resource_id = ti.primary_resource_id
          WHERE ti.tool_id = ?""",
        "resource": """SELECT resource_id AS logical_id, project_id,
                resource_kind, display_label, normalized_key,
                normalization_version
           FROM resources WHERE resource_id = ?""",
        "state_change": """SELECT change_id AS logical_id, session_id, turn_id,
                resource_id, change_kind, before_revision, after_revision,
                confidence, event_at_us
           FROM state_changes WHERE change_id = ?""",
        "allowance_observation": """SELECT observation_id AS logical_id,
                limit_id, cycle_id, plan_identity, window_kind, reset_identity,
                observation_ordinal, used_percent, remaining_percent,
                reset_time_us, observed_at_us
           FROM allowance_observations WHERE observation_id = ?""",
        "allowance_interval": """SELECT interval_id AS logical_id, limit_id,
                cycle_id, start_observation_id, end_observation_id, start_us,
                end_us, percent_delta, compatibility_basis, ratio_eligible
           FROM allowance_intervals WHERE interval_id = ?""",
        "project": """SELECT project_id AS logical_id, workspace_key,
                first_event_at_us, last_event_at_us
           FROM projects WHERE project_id = ?""",
        "model_profile": """SELECT model_profile_id AS logical_id, model,
                reasoning_effort, service_tier
           FROM model_profiles WHERE model_profile_id = ?""",
        "publication": """SELECT publication_id AS logical_id, operation_id,
                committed_at_us, observed_through_us, status
           FROM publications WHERE publication_id = ?""",
        "source_manifestation": """SELECT manifestation_id AS logical_id,
                source_id, content_revision, state, selected,
                first_seen_publication_id, last_seen_publication_id
           FROM source_manifestations WHERE manifestation_id = ?""",
        "rate_card": """SELECT rate_card_id AS logical_id, digest, source_name,
                effective_at_us, fetched_at_us, validation_status
           FROM rate_card_revisions WHERE digest = ? OR rate_card_id = ?
          ORDER BY rate_card_id""",
    }
)


def _request_digest(request: EvidenceRequest) -> str:
    payload = {
        "boundary_pair": request.boundary_pair,
        "byte_limit": request.byte_limit,
        "direction": request.direction,
        "gates": request.gates,
        "limit": request.limit,
        "parameters": request.parameters,
        "plan_id": request.plan_id,
        "plan_version": request.plan_version,
        "publication_id": request.bound_publication_id,
        "selector": request.selector,
        "selector_role": request.selector_role,
        "view": request.view,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _reference_mapping(reference: EvidenceReference) -> dict[str, Any]:
    canonical = f"{reference.selector_kind.replace('_', '-')}:" f"{reference.logical_id}"
    alias = reference.provenance.get("alias") if isinstance(reference.provenance, Mapping) else None
    return {
        "role": reference.role,
        "selector_kind": reference.selector_kind,
        "requested_selector": reference.selector,
        "canonical_selector": canonical,
        "logical_id": reference.logical_id,
        "provenance_kind": reference.provenance_kind,
        "alias_basis": alias,
        "provenance": reference.provenance,
    }


def _occurrence(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    occurrence_id = row.get("occurrence_id")
    if occurrence_id is None:
        return None
    return {
        "occurrence_id": occurrence_id,
        "manifestation_id": row.get("manifestation_id"),
        "source_id": row.get("source_id"),
        "source_revision": row.get("source_revision"),
        "record_ordinal": row.get("record_ordinal"),
        "byte_start": row.get("byte_start"),
        "byte_end": row.get("byte_end"),
        "adapter_version": row.get("adapter_version"),
    }


def _typed_row(row: Mapping[str, Any]) -> dict[str, Any]:
    event_kind = str(row["event_kind"])
    result: dict[str, Any] = {
        "event_kind": event_kind,
        "logical_id": row["logical_id"],
        "event_at_us": row.get("event_at_us"),
        "coordinates": {
            "event_at_us": row.get("event_at_us"),
            "source_rank": int(row.get("source_rank") or 0),
            "source_order": int(row.get("source_order") or 0),
            "event_kind_order": int(row.get("event_kind_order") or 0),
            "transition_rank": int(row.get("transition_rank") or 0),
        },
        "order_key": (
            1 if row.get("event_at_us") is None else 0,
            row.get("event_at_us"),
            int(row.get("source_rank") or 0),
            int(row.get("source_order") or 0),
            int(row.get("event_kind_order") or 0),
            row["logical_id"],
            int(row.get("transition_rank") or 0),
        ),
    }
    if row.get("session_id") is not None:
        result["session_id"] = row["session_id"]
    if row.get("turn_id") is not None:
        result["turn_id"] = row["turn_id"]
    if row.get("turn_ordinal") is not None:
        result["turn_ordinal"] = row["turn_ordinal"]
    if row.get("lifecycle_state") is not None:
        result["lifecycle"] = {
            "state": row.get("lifecycle_state"),
            "basis": row.get("state_basis"),
            "transition_version": row.get("transition_version"),
        }
    if any(row.get(name) is not None for name in (
        "context_window_tokens", "uncached_input_tokens", "cached_input_tokens",
        "reasoning_tokens", "output_tokens", "token_basis",
    )):
        result["tokens"] = {
            "context_window_tokens": row.get("context_window_tokens"),
            "uncached_input_tokens": row.get("uncached_input_tokens"),
            "cached_input_tokens": row.get("cached_input_tokens"),
            "reasoning_tokens": row.get("reasoning_tokens"),
            "output_tokens": row.get("output_tokens"),
            "basis": row.get("token_basis"),
        }
    if event_kind == "call" and row.get("model_profile_id") is not None:
        result["model_profile"] = {
            "logical_id": row.get("model_profile_id"),
            "model": row.get("model"),
            "reasoning_effort": row.get("reasoning_effort"),
            "service_tier": row.get("service_tier"),
        }
    if row.get("tool_id") is not None:
        result["tool_operation"] = {
            "tool_id": row.get("tool_id"),
            "transport": row.get("transport_name"),
            "semantic_operation": row.get("semantic_operation"),
            "tool_family": row.get("tool_family"),
            "write_intent": bool(row.get("write_intent")) if row.get("write_intent") is not None else None,
            "observed_duration_us": row.get("observed_duration_us"),
            "output_bytes": row.get("output_bytes"),
            "error_category": row.get("error_category"),
        }
    if row.get("resource_id") is not None:
        result["resource"] = {
            "resource_id": row.get("resource_id"),
            "kind": row.get("resource_kind"),
            "display_label": row.get("resource_label"),
        }
    if row.get("state_change_id") is not None:
        result["state_change"] = {
            "change_id": row.get("state_change_id"),
            "kind": row.get("change_kind"),
            "resource_id": row.get("resource_id"),
            "before_revision": row.get("before_revision"),
            "after_revision": row.get("after_revision"),
            "confidence": row.get("confidence"),
        }
    if row.get("allowance_observation_id") is not None:
        result["allowance"] = {
            "observation_id": row.get("allowance_observation_id"),
            "used_percent": row.get("allowance_used_percent"),
            "remaining_percent": row.get("allowance_remaining_percent"),
            "observation_ordinal": row.get("allowance_ordinal"),
            "reset_time_us": row.get("reset_time_us"),
        }
    occurrence = _occurrence(row)
    if occurrence is not None:
        result["occurrence_coordinates"] = occurrence
    if row.get("before_context_epoch") is not None:
        result["context_change"] = {
            "before_epoch": row.get("before_context_epoch"),
            "after_epoch": row.get("after_context_epoch"),
        }
    return result


def _scope_kind(reference: EvidenceReference) -> str:
    if reference.selector_kind == "window":
        return "window"
    return reference.selector_kind


def _boundary_summary(reference: EvidenceReference) -> tuple[int, int, tuple[Mapping[str, Any], ...]]:
    provenance = reference.provenance
    if reference.selector_kind != "allowance_interval":
        raise EvidenceServiceError("boundary summary requested for a non-interval selector")
    start_selector = provenance.get("start_observation_selector")
    end_selector = provenance.get("end_observation_selector")
    if not isinstance(start_selector, str) or not isinstance(end_selector, str):
        raise EvidenceServiceError("allowance interval boundary provenance is incomplete")
    start_id = start_selector.partition(":")[2]
    end_id = end_selector.partition(":")[2]
    return 0, 0, (
        {"role": "start_boundary", "selector": start_selector, "logical_id": start_id},
        {"role": "end_boundary", "selector": end_selector, "logical_id": end_id},
    )


class EvidenceService:
    """Execute one typed evidence request against one caller-owned snapshot."""

    def __init__(
        self,
        selector_provenance: Mapping[str, Any],
        cursor_codec: CursorCodec,
        *,
        clock: Clock | None = None,
        cursor_ttl_us: int = _CURSOR_TTL_US,
    ) -> None:
        if not isinstance(cursor_codec, CursorCodec):
            raise EvidenceContractError("evidence service requires a CursorCodec")
        if clock is not None and not callable(clock):
            raise EvidenceContractError("evidence service clock must be callable")
        if isinstance(cursor_ttl_us, bool) or cursor_ttl_us <= 0:
            raise EvidenceContractError("evidence cursor TTL must be positive")
        self._resolver = EvidenceSelectorResolver(selector_provenance)
        self._cursor_codec = cursor_codec
        self._clock = clock or (lambda: time.time_ns() // 1_000)
        self._cursor_ttl_us = cursor_ttl_us

    def read_path(self, path: Path, request: EvidenceRequest) -> EvidencePage:
        connection = open_read_only(Path(path))
        try:
            return self.read(connection, request)
        finally:
            connection.close()

    def read(self, connection: sqlite3.Connection, request: EvidenceRequest) -> EvidencePage:
        if not isinstance(connection, sqlite3.Connection):
            raise EvidenceServiceError("evidence service requires a SQLite connection")
        if not isinstance(request, EvidenceRequest):
            raise EvidenceContractError("evidence service requires EvidenceRequest")
        if connection.in_transaction:
            raise EvidenceServiceError("evidence service owns the read transaction")
        query_only = connection.execute("PRAGMA query_only").fetchone()
        if query_only is None or int(query_only[0]) != 1:
            raise EvidenceServiceError("evidence service requires PRAGMA query_only=1")

        connection.execute("BEGIN")
        try:
            publication, coverage = self._snapshot(connection)
            if request.bound_publication_id not in (None, publication["id"]):
                raise EvidenceServiceError(
                    "requested publication is stale or replaced; restart from the first page"
                )
            plan_request = PlanRequest(
                plan_id=request.plan_id,
                parameters=request.parameters,
                gates=request.gates,
            )
            references, scope, boundaries = self._resolve(
                connection, plan_request, request, publication["id"]
            )
            resolved_selector = self._resolved_selector(references)
            summary = self._summary(connection, references, scope, boundaries)
            digest = _request_digest(request)
            cursor_order = self._decode_cursor(request, publication["id"], digest)
            if request.view == "summary":
                rows: tuple[Mapping[str, Any], ...] = ()
                has_more = False
                next_cursor = None
                response_bytes = 0
            else:
                rows, has_more, next_cursor = self._page_rows(
                    connection,
                    request,
                    scope,
                    cursor_order,
                    publication["id"],
                    digest,
                )
                response_bytes = 0
            while True:
                page = EvidencePage(
                    publication=publication,
                    coverage=coverage,
                    resolved_selector=resolved_selector,
                    summary=summary,
                    boundaries=boundaries,
                    rows=rows,
                    view=request.view,
                    direction=request.direction,
                    limit=request.limit,
                    byte_limit=request.byte_limit,
                    returned_rows=len(rows),
                    has_more=has_more,
                    next_cursor=next_cursor,
                    response_bytes=response_bytes,
                )
                response_bytes = self._stable_response_bytes(page)
                if response_bytes <= request.byte_limit:
                    return page
                if len(rows) <= 1:
                    raise EvidenceServiceError(
                        f"response_budget_exceeded: {response_bytes} > "
                        f"{request.byte_limit}"
                    )
                rows = rows[:-1]
                has_more = True
                next_cursor = self._encode_cursor(
                    request,
                    publication["id"],
                    digest,
                    tuple(rows[-1]["order_key"]),
                )
                response_bytes = 0
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")

    def _snapshot(self, connection: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
        cursor = connection.execute(
            """SELECT p.publication_id, p.committed_at_us,
                    p.observed_through_us, p.status
               FROM publication_head AS h
               JOIN publications AS p ON p.publication_id = h.publication_id
              WHERE h.singleton = 1 AND p.status = 'committed'"""
        )
        rows = cursor.fetchall()
        if len(rows) != 1:
            raise EvidenceServiceError("snapshot has no unique committed publication")
        row = _row_mapping(rows[0], cursor.description)
        publication = {
            "id": str(row["publication_id"]),
            "committed_at_us": int(row["committed_at_us"]),
            "observed_through_us": int(row["observed_through_us"]),
            "status": str(row["status"]),
        }
        source_coverage: dict[str, Any] = {}
        for item in connection.execute(
            """SELECT source_id, selected_manifestation_count,
                    selected_manifestation_bytes, deferred_manifestation_count,
                    malformed_manifestation_count, missing_manifestation_count,
                    uncertain_manifestation_count, selected_complete_record_count,
                    tail_pending, indexed_from_us, indexed_through_us,
                    guaranteed_complete_from_us, guaranteed_complete_through_us,
                    clock_quality, clock_uncertainty_us
               FROM publication_source_coverage
              WHERE publication_id = ? ORDER BY source_id""",
            (publication["id"],),
        ):
            item = _row_mapping(item)
            source_coverage[str(item.pop("source_id"))] = item
        capabilities: dict[str, Any] = {}
        for item in connection.execute(
            """SELECT capability_id, eligible_entity_count,
                    observed_entity_count, unavailable_entity_count,
                    grade, basis
               FROM publication_capability_coverage
              WHERE publication_id = ? ORDER BY capability_id""",
            (publication["id"],),
        ):
            item = _row_mapping(item)
            capability_id = str(item.pop("capability_id"))
            capabilities[capability_id] = item
        return publication, {"sources": source_coverage, "capabilities": capabilities}

    def _resolve(
        self,
        connection: sqlite3.Connection,
        plan_request: PlanRequest,
        request: EvidenceRequest,
        publication_id: str,
    ) -> tuple[tuple[EvidenceReference, ...], dict[str, Any], tuple[Mapping[str, Any], ...]]:
        try:
            if request.selector is not None:
                prefix = request.selector.partition(":")[0]
                kind = _SELECTOR_PREFIXES[prefix]
                required: tuple[Mapping[str, Any], ...] = (
                    {
                        "role": request.selector_role,
                        "selector_kind": kind,
                        "selector": request.selector,
                    },
                )
                references = self._resolver.resolve(
                    connection, plan_request, required, publication_id=publication_id
                )
                reference = references[0]
                scope = self._scope_for_reference(connection, reference)
                boundaries = self._boundaries_for_reference(reference)
                return references, scope, boundaries
            assert request.boundary_pair is not None
            if any(
                item.partition(":")[0] != "allowance-observation"
                for item in request.boundary_pair
            ):
                raise EvidenceContractError("compatible boundary pairs must be allowance observations")
            required = (
                {
                    "role": "start_boundary",
                    "selector_kind": "allowance_observation",
                    "selector": request.boundary_pair[0],
                },
                {
                    "role": "end_boundary",
                    "selector_kind": "allowance_observation",
                    "selector": request.boundary_pair[1],
                },
            )
            references = self._resolver.resolve(
                connection, plan_request, required, publication_id=publication_id
            )
            start, end = self._allowance_pair(connection, references)
            boundaries = tuple(_reference_mapping(item) for item in references)
            return references, {
                "kind": "interval",
                "logical_id": f"{start['observation_id']}:{end['observation_id']}",
                "start_us": start["observed_at_us"],
                "end_us": end["observed_at_us"],
            }, boundaries
        except EvidenceContractError:
            raise
        except EvidenceSelectorError as error:
            raise EvidenceServiceError(f"evidence selector resolution failed: {error}") from error

    def _scope_for_reference(self, connection: sqlite3.Connection, reference: EvidenceReference) -> dict[str, Any]:
        kind = _scope_kind(reference)
        if reference.selector_kind == "allowance_interval":
            row = connection.execute(
                """SELECT start_us, end_us FROM allowance_intervals
                   WHERE interval_id = ?""",
                (reference.logical_id,),
            ).fetchone()
            if row is None:
                raise EvidenceServiceError("resolved allowance interval disappeared")
            return {"kind": kind, "logical_id": reference.logical_id, "start_us": row[0], "end_us": row[1]}
        if reference.selector_kind == "window":
            return {
                "kind": kind,
                "logical_id": reference.logical_id,
                "start_us": reference.provenance["start_us"],
                "end_us": reference.provenance["end_us"],
            }
        return {"kind": kind, "logical_id": reference.logical_id, "start_us": None, "end_us": None}

    def _boundaries_for_reference(self, reference: EvidenceReference) -> tuple[Mapping[str, Any], ...]:
        if reference.selector_kind != "allowance_interval":
            return ()
        provenance = reference.provenance
        start = provenance.get("start_observation_selector")
        end = provenance.get("end_observation_selector")
        if not isinstance(start, str) or not isinstance(end, str):
            raise EvidenceServiceError("allowance interval boundary provenance is incomplete")
        return (
            {"role": "start_boundary", "selector": start, "logical_id": start.partition(":")[2]},
            {"role": "end_boundary", "selector": end, "logical_id": end.partition(":")[2]},
        )

    def _allowance_pair(
        self, connection: sqlite3.Connection, references: tuple[EvidenceReference, ...]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        ids = (references[0].logical_id, references[1].logical_id)
        if ids[0] == ids[1]:
            raise EvidenceServiceError("allowance boundary pair must use distinct observations")
        rows = connection.execute(
            """SELECT o.observation_id, o.limit_id, o.cycle_id,
                    o.plan_identity, o.window_kind, o.reset_identity,
                    o.observation_ordinal, o.observed_at_us,
                    o.used_percent, o.remaining_percent, l.provider
               FROM allowance_observations AS o
               JOIN allowance_limits AS l ON l.limit_id = o.limit_id
              WHERE o.observation_id IN (?, ?)
              ORDER BY o.observation_ordinal, o.observation_id""",
            ids,
        ).fetchall()
        by_id = {_row_mapping(row)["observation_id"]: _row_mapping(row) for row in rows}
        if len(by_id) != len(set(ids)) or any(item not in by_id for item in ids):
            raise EvidenceServiceError("allowance boundary pair does not resolve")
        start, end = by_id[ids[0]], by_id[ids[1]]
        compatibility = ("limit_id", "cycle_id", "plan_identity", "window_kind", "reset_identity", "provider")
        if any(start[name] != end[name] for name in compatibility):
            raise EvidenceServiceError("allowance boundary pair is incompatible")
        if start["observed_at_us"] is None or end["observed_at_us"] is None:
            raise EvidenceServiceError("allowance boundaries require observed times")
        if end["observation_ordinal"] < start["observation_ordinal"]:
            raise EvidenceServiceError("allowance boundary pair is reversed")
        if end["observation_ordinal"] != start["observation_ordinal"] + 1:
            raise EvidenceServiceError("allowance boundary pair must be adjacent")
        if end["observed_at_us"] < start["observed_at_us"]:
            raise EvidenceServiceError("allowance boundary times are reversed")
        return start, end

    def _resolved_selector(self, references: tuple[EvidenceReference, ...]) -> Mapping[str, Any]:
        if len(references) == 1:
            return _reference_mapping(references[0])
        return {
            "selector_kind": "allowance_boundary_pair",
            "requested_selectors": tuple(item.selector for item in references),
            "canonical_selectors": tuple(
                f"{item.selector_kind.replace('_', '-')}:{item.logical_id}" for item in references
            ),
            "logical_ids": tuple(item.logical_id for item in references),
            "references": tuple(_reference_mapping(item) for item in references),
            "alias_basis": tuple(item.provenance.get("alias") for item in references),
        }

    def _summary(
        self,
        connection: sqlite3.Connection,
        references: tuple[EvidenceReference, ...],
        scope: Mapping[str, Any],
        boundaries: tuple[Mapping[str, Any], ...],
    ) -> Mapping[str, Any]:
        reference = references[0]
        kind = reference.selector_kind
        facts: Mapping[str, Any]
        statement = _SUMMARY_SQL.get(kind)
        if statement is None or kind == "window":
            facts = {"start_us": scope.get("start_us"), "end_us": scope.get("end_us")}
        else:
            parameters: tuple[Any, ...] = (reference.logical_id, reference.logical_id) if kind == "rate_card" else (reference.logical_id,)
            cursor = connection.execute(statement, parameters)
            rows = [_row_mapping(row, cursor.description) for row in cursor]
            if len(rows) != 1:
                raise EvidenceServiceError("resolved selector summary is unavailable")
            facts = rows[0]
        summary: dict[str, Any] = {
            "selector_kind": kind,
            "logical_id": reference.logical_id,
            "scope": {
                "kind": scope["kind"],
                "start_us": scope.get("start_us"),
                "end_us": scope.get("end_us"),
            },
            "facts": facts,
            "boundaries": boundaries,
        }
        if kind == "allowance_interval" and boundaries:
            summary["boundary_selectors"] = tuple(item["selector"] for item in boundaries)
        return summary

    def _decode_cursor(
        self, request: EvidenceRequest, publication_id: str, digest: str
    ) -> tuple[Any, ...] | None:
        if request.cursor is None:
            return None
        try:
            binding = self._cursor_codec.decode(
                request.cursor,
                expected_kind="evidence",
                expected_plan_id=request.plan_id,
                expected_plan_version=request.plan_version,
                expected_publication_id=publication_id,
                expected_request_digest=digest,
                expected_view=request.view,
                expected_direction=request.direction,
            )
        except CursorError:
            raise
        if len(binding.order) != 7:
            raise EvidenceServiceError("evidence cursor order is not the seven-part contract")
        return binding.order

    def _encode_cursor(
        self,
        request: EvidenceRequest,
        publication_id: str,
        digest: str,
        order: tuple[Any, ...],
    ) -> str:
        now = int(self._clock())
        return self._cursor_codec.encode(
            CursorBinding(
                kind="evidence",
                plan_id=request.plan_id,
                plan_version=request.plan_version,
                publication_id=publication_id,
                request_digest=digest,
                order=order,
                issued_at_us=now,
                expires_at_us=now + self._cursor_ttl_us,
                view=request.view,
                direction=request.direction,
                metadata={"order_contract": _ORDER_FIELDS.split(", ")},
            )
        )

    def _page_rows(
        self,
        connection: sqlite3.Connection,
        request: EvidenceRequest,
        scope: Mapping[str, Any],
        cursor_order: tuple[Any, ...] | None,
        publication_id: str,
        digest: str,
    ) -> tuple[tuple[Mapping[str, Any], ...], bool, str | None]:
        parameters: list[Any] = [scope["kind"], scope["logical_id"], scope.get("start_us"), scope.get("end_us")]
        if cursor_order is not None:
            normalized = self._cursor_parameters(cursor_order)
            parameters.extend(normalized)
            sql = _page_sql(request.view, request.direction)
        else:
            sql = _first_page_sql(request.view, request.direction)
        parameters.append(request.limit + 1)
        cursor = connection.execute(sql, tuple(parameters))
        raw_rows = [_row_mapping(row, cursor.description) for row in cursor]
        typed = [_typed_row(row) for row in raw_rows]
        selected: list[Mapping[str, Any]] = []
        for index, candidate in enumerate(typed[: request.limit]):
            candidate_rows = tuple([*selected, candidate])
            more = len(typed) > index + 1
            candidate_cursor = (
                self._encode_cursor(request, publication_id, digest, tuple(candidate["order_key"]))
                if more
                else None
            )
            if self._page_size(request, candidate_rows, more, candidate_cursor) > request.byte_limit:
                if not selected:
                    raise EvidenceServiceError("one evidence row exceeds the byte limit")
                break
            selected.append(candidate)
        if not selected:
            return (), False, None
        has_more = len(typed) > len(selected)
        next_cursor = (
            self._encode_cursor(request, publication_id, digest, tuple(selected[-1]["order_key"]))
            if has_more
            else None
        )
        return tuple(selected), has_more, next_cursor

    @staticmethod
    def _stable_response_bytes(page: EvidencePage) -> int:
        """Set and return the fixed-point size of the final canonical envelope."""

        measured = page.response_bytes
        for _ in range(8):
            object.__setattr__(page, "response_bytes", measured)
            current = len(_canonical_json_bytes(page.to_mapping()))
            if current == measured:
                return current
            measured = current
        raise EvidenceServiceError("evidence response byte measurement did not converge")

    @staticmethod
    def _cursor_parameters(order: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(order) != 7:
            raise EvidenceServiceError("evidence cursor order is malformed")
        time_missing, event_at_us, source_rank, source_order, event_kind_order, logical_id, transition_rank = order
        if time_missing not in (0, 1, False, True) or not isinstance(logical_id, str):
            raise EvidenceServiceError("evidence cursor order is malformed")
        return (
            int(bool(time_missing)),
            0 if event_at_us is None else event_at_us,
            source_rank,
            source_order,
            event_kind_order,
            logical_id,
            transition_rank,
        )

    @staticmethod
    def _page_size(
        request: EvidenceRequest,
        rows: tuple[Mapping[str, Any], ...],
        has_more: bool,
        next_cursor: str | None,
    ) -> int:
        envelope = {
            "schema": EVIDENCE_SCHEMA,
            "publication": {},
            "coverage": {},
            "resolved_selector": {},
            "summary": {},
            "boundaries": (),
            "rows": rows,
            "page": {
                "view": request.view,
                "direction": request.direction,
                "limit": request.limit,
                "byte_limit": request.byte_limit,
                "returned_rows": len(rows),
                "has_more": has_more,
                "next_cursor": next_cursor,
            },
        }
        return len(_canonical_json_bytes(envelope))


__all__ = [
    "EVIDENCE_PLAN_ID",
    "EVIDENCE_PLAN_VERSION",
    "EVIDENCE_SCHEMA",
    "EVIDENCE_VIEWS",
    "MAX_EVIDENCE_BYTES",
    "MAX_EVIDENCE_LIMIT",
    "EvidenceContractError",
    "EvidencePage",
    "EvidenceRequest",
    "EvidenceService",
    "EvidenceServiceError",
]
