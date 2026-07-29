from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.agent_kernel.contracts.reference.selectors import format_selector
from tests.agent_kernel.fixtures.oracles.common import canonical_json_bytes

_SELECTOR_PREFIXES = {
    "allowance_interval": "allowance-interval",
    "allowance_observation": "allowance-observation",
    "call": "call",
    "model_profile": "model-profile",
    "project": "project",
    "publication": "publication",
    "rate_card": "rate-card",
    "resource": "resource",
    "session": "session",
    "source_manifestation": "source-manifestation",
    "state_change": "state-change",
    "tool": "tool",
    "turn": "turn",
    "window": "window",
}
_SELECTOR_IDENTITIES = dict(_SELECTOR_PREFIXES)


@dataclass(frozen=True)
class QuestionCase:
    oracle_id: str
    observed_facts: dict[str, Any]
    coordinate: dict[str, Any]
    input_digest: str
    inputs: dict[str, Any]
    contract: dict[str, Any]
    caveats: list[str]
    selector_ids: dict[str, str]
    selectors: dict[str, dict[str, Any]]


@dataclass
class _HistoryBucket:
    calls: int = 0
    sessions: int = 0
    turns: int = 0
    _last_session: str | None = None
    _last_turn: str | None = None
    _sessions: set[str] = field(default_factory=set)
    _turns: set[str] = field(default_factory=set)

    def observe(self, session_id: str, turn_id: str, *, streaming: bool) -> None:
        self.calls += 1
        if streaming:
            if session_id != self._last_session:
                self.sessions += 1
                self._last_session = session_id
            if turn_id != self._last_turn:
                self.turns += 1
                self._last_turn = turn_id
            return
        self._sessions.add(session_id)
        self._turns.add(turn_id)

    def finish(self, *, streaming: bool) -> None:
        if not streaming:
            self.sessions = len(self._sessions)
            self.turns = len(self._turns)


class SourceLedger:
    """Candidate-independent aggregate ledger derived from exact source bytes."""

    def __init__(
        self,
        *,
        history_windows: dict[str, dict[str, Any]],
        streaming: bool,
        source_manifestations: int,
    ) -> None:
        self.history_windows = history_windows
        self.streaming = streaming
        self.source_manifestations = source_manifestations
        self.question_cases: dict[str, QuestionCase] = {}
        self.selector_coordinates: dict[str, dict[str, Any]] = {}
        self.slice_records: dict[str, dict[str, Any]] = {}
        self.control_records: dict[str, dict[str, Any]] = {}
        self.phase_occurrences: dict[str, Any] = {}
        self.history: dict[str, dict[str, int]] = {}
        self.event_kind_counts: dict[str, int] = {}
        self._history_buckets = {
            name: _HistoryBucket()
            for name in history_windows
        }
        self._pending_cases: dict[
            str,
            tuple[dict[str, Any], dict[str, Any]],
        ] = {}
        self._model_call_occurrences = 0
        self._canonical_model_calls = 0
        self._tool_starts = 0
        self._tool_terminals = 0
        self._allowance_observations = 0
        self._allowance_repeats = 0
        self._allowance_reset_boundaries = 0
        self._previous_allowance_percent: str | None = None
        self._previous_allowance_reset: str | None = None
        self._resource_ids: set[str] = set()
        self._session_call_counts: Counter[str] = Counter()
        self._session_tool_counts: Counter[str] = Counter()
        self._token_fields = (
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        )
        self._token_observed_counts = {field: 0 for field in self._token_fields}
        self._token_observed_sums = {field: 0 for field in self._token_fields}

    def observe(
        self,
        record: dict[str, Any],
        coordinate: dict[str, Any],
        *,
        canonical: bool,
    ) -> None:
        event_kind = str(record["type"])
        self.event_kind_counts[event_kind] = (
            self.event_kind_counts.get(event_kind, 0) + 1
        )
        payload = record["payload"]

        if event_kind == "selector_anchor":
            kind = str(payload["selector_kind"])
            selector = format_selector(
                kind,
                str(payload["logical_id"]),
                _SELECTOR_PREFIXES,
                _SELECTOR_IDENTITIES,
            )
            self.selector_coordinates[selector] = coordinate
            if kind == "publication":
                self.control_records["publication"] = dict(payload)
            elif kind == "rate_card":
                self.control_records["rate_card"] = dict(payload)
            elif kind == "tool":
                self.control_records["tool_identity"] = dict(payload)
        elif event_kind == "slice_control":
            self.slice_records[str(payload["slice"])] = dict(payload)
        elif event_kind == "allowance_compatibility":
            self.control_records["allowance_compatibility"] = dict(payload)
        elif event_kind == "late_parent":
            self.control_records["late_parent"] = dict(payload)
        elif event_kind == "oracle_case":
            self._pending_cases[str(payload["oracle_id"])] = (
                dict(payload),
                coordinate,
            )
        elif event_kind == "model_call":
            self._model_call_occurrences += 1
            if canonical:
                self._canonical_model_calls += 1
                self._session_call_counts[str(payload["session_id"])] += 1
                for field in self._token_fields:
                    value = payload["tokens"][field]
                    if value is not None:
                        self._token_observed_counts[field] += 1
                        self._token_observed_sums[field] += int(value)
                self._observe_history(record)
        elif event_kind == "tool_start":
            self._tool_starts += 1
            self._session_tool_counts[str(payload["session_id"])] += 1
            resource_id = payload.get("resource_id")
            if isinstance(resource_id, str):
                self._resource_ids.add(resource_id)
        elif event_kind == "tool_terminal":
            self._tool_terminals += 1
        elif event_kind == "allowance_observation" and canonical:
            self._observe_allowance(payload)

    def _observe_history(self, record: dict[str, Any]) -> None:
        payload = record["payload"]
        event_at_us = int(record["event_at_us"])
        session_id = str(payload["session_id"])
        turn_id = str(payload["turn_id"])
        for name, window in self.history_windows.items():
            selected_session = window.get("session_id")
            if selected_session is not None and selected_session != session_id:
                continue
            if int(window["start_us"]) <= event_at_us <= int(window["end_us"]):
                self._history_buckets[name].observe(
                    session_id,
                    turn_id,
                    streaming=self.streaming,
                )

    def _observe_allowance(self, payload: dict[str, Any]) -> None:
        self._allowance_observations += 1
        used = str(payload["used_percent"])
        reset = str(payload["reset_identity"])
        if self._previous_allowance_percent == used:
            self._allowance_repeats += 1
        if self._previous_allowance_reset is not None and self._previous_allowance_reset != reset:
            self._allowance_reset_boundaries += 1
        self._previous_allowance_percent = used
        self._previous_allowance_reset = reset

    def finish(self) -> None:
        for name, bucket in self._history_buckets.items():
            bucket.finish(streaming=self.streaming)
            window = self.history_windows[name]
            self.history[name] = {
                "calls": bucket.calls,
                "end_us": int(window["end_us"]),
                "sessions": bucket.sessions,
                "start_us": int(window["start_us"]),
                "turns": bucket.turns,
            }
        for oracle_id, (payload, coordinate) in self._pending_cases.items():
            selectors = {}
            for kind, logical_id in payload["selector_ids"].items():
                selector = format_selector(
                    kind,
                    logical_id,
                    _SELECTOR_PREFIXES,
                    _SELECTOR_IDENTITIES,
                )
                selectors[selector] = self.selector_coordinates[selector]
            observed_facts = dict(payload["observed_facts"])
            if "occurrence_coordinates" in observed_facts:
                observed_facts["occurrence_coordinates"] = [coordinate]
            self.question_cases[oracle_id] = QuestionCase(
                oracle_id=oracle_id,
                observed_facts=observed_facts,
                coordinate=coordinate,
                input_digest=hashlib.sha256(
                    canonical_json_bytes(payload["inputs"])
                ).hexdigest(),
                inputs=dict(payload["inputs"]),
                contract=dict(payload["contract"]),
                caveats=list(payload["caveats"]),
                selector_ids=dict(payload["selector_ids"]),
                selectors=selectors,
            )

    @property
    def stream_aggregates(self) -> dict[str, int]:
        return {
            "allowance_observations": self._allowance_observations,
            "allowance_repeated_observations": self._allowance_repeats,
            "allowance_reset_boundaries": self._allowance_reset_boundaries,
            "canonical_model_calls": self._canonical_model_calls,
            "model_call_occurrences": self._model_call_occurrences,
            "open_tool_invocations": self._tool_starts - self._tool_terminals,
            "oracle_cases": len(self.question_cases),
            "publications": int("publication" in self.control_records),
            "rate_cards": int("rate_card" in self.control_records),
            "resources": len(self._resource_ids),
            "selector_anchors": len(self.selector_coordinates),
            "source_manifestations": self.source_manifestations,
            "tool_invocations": self._tool_starts,
        }

    @property
    def accounting_inputs(self) -> dict[str, Any]:
        return {
            "canonical_model_calls": self._canonical_model_calls,
            "observed_counts": dict(self._token_observed_counts),
            "observed_sums": dict(self._token_observed_sums),
        }

    @property
    def cardinality_histograms(self) -> dict[str, list[dict[str, int]]]:
        def histogram(values: Counter[str]) -> list[dict[str, int]]:
            counts = Counter(values.values())
            return [
                {"count": count, "value": value}
                for value, count in sorted(counts.items())
            ]

        return {
            "calls_per_session": histogram(self._session_call_counts),
            "resources_per_project": [
                {
                    "count": 1,
                    "value": len(self._resource_ids),
                }
            ],
            "tools_per_session": histogram(
                Counter(
                    {
                        session_id: self._session_tool_counts.get(session_id, 0)
                        for session_id in self._session_call_counts
                    }
                )
            ),
        }


def _coordinate(
    source: dict[str, Any],
    *,
    ordinal: int,
    byte_start: int,
    byte_end: int,
) -> dict[str, Any]:
    return {
        "adapter_version": source["adapter_version"],
        "byte_end": byte_end,
        "byte_start": byte_start,
        "manifestation_id": source["manifestation_id"],
        "record_ordinal": ordinal,
        "record_range": [ordinal, ordinal],
        "revision": source["revision"],
        "source_path": source["path"],
    }


def read_source_ledger(root: Path, manifest: dict[str, Any]) -> SourceLedger:
    """Rebuild ledger from persisted bytes without generator semantic helpers."""

    ledger = SourceLedger(
        history_windows=manifest["history"]["windows"],
        streaming=False,
        source_manifestations=manifest["source_layout"]["manifestations"],
    )
    for source in manifest["sources"]:
        if not source["persisted_when_requested"]:
            continue
        path = root / source["path"]
        if not path.exists():
            continue
        body = path.read_bytes()
        byte_start = 0
        for ordinal, line in enumerate(body.splitlines(keepends=True)):
            byte_end = byte_start + len(line)
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                byte_start = byte_end
                continue
            coordinate = _coordinate(
                source,
                ordinal=ordinal,
                byte_start=byte_start,
                byte_end=byte_end,
            )
            ledger.observe(
                record,
                coordinate,
                canonical=source["state"] != "archived",
            )
            byte_start = byte_end
    ledger.phase_occurrences = dict(manifest["phase_occurrence_mappings"])
    ledger.finish()
    return ledger


def coordinate_resolves(
    root: Path,
    selector: str,
    coordinate: dict[str, Any],
) -> bool:
    """Resolve one selector to the exact persisted record byte range."""

    path = root / coordinate["source_path"]
    if not path.exists():
        return False
    body = path.read_bytes()
    start = int(coordinate["byte_start"])
    end = int(coordinate["byte_end"])
    if not 0 <= start < end <= len(body):
        return False
    try:
        record = json.loads(body[start:end])
    except json.JSONDecodeError:
        return False
    logical_id = selector.partition(":")[2]
    payload = record.get("payload", {})
    return payload.get("logical_id") == logical_id
