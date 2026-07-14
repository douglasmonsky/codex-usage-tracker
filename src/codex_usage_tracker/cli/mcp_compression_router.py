"""Compatibility routers from legacy agentic tools to Compression Lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.cli.mcp_compression_router_payloads import (
    completed_action_payload,
    completed_investigation_payload,
    running_action_payload,
    running_investigation_payload,
)
from codex_usage_tracker.compression.api import (
    compression_candidate_detail,
    compression_candidates,
    compression_profile,
    start_compression_analysis,
)
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.payloads import CANDIDATE_PAGE_BUDGET_BYTES
from codex_usage_tracker.compression.simulation_api import compression_simulate
from codex_usage_tracker.compression.simulation_payloads import SIMULATION_BUDGET_BYTES
from codex_usage_tracker.reports.agentic_strategy import _normalize_agentic_goal

_COMPRESSION_GOALS = frozenset({"overview", "token_waste", "cache_failure", "workflow_churn"})
_COMPLETED_STATUSES = frozenset({"completed", "completed_with_warnings"})
_SELECTED_DETAIL_LIMIT = 1


def is_compression_router_goal(goal: str | None) -> bool:
    """Return whether a legacy broad goal should use Compression Lab first."""
    return (_normalize_agentic_goal(goal or "token_waste") or "token_waste") in _COMPRESSION_GOALS


def build_compression_investigation_router(
    *,
    db_path: Path,
    goal: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    """Build a legacy-schema investigation payload backed by Compression Lab."""
    state = _load_compression_router_state(
        db_path=db_path,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
    )
    if not state.completed:
        return running_investigation_payload(state, privacy_mode=privacy_mode)
    return completed_investigation_payload(state, privacy_mode=privacy_mode)


def build_compression_action_router(
    *,
    db_path: Path,
    goal: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
    privacy_mode: str,
) -> dict[str, Any]:
    """Build a legacy-schema action brief payload backed by Compression Lab."""
    state = _load_compression_router_state(
        db_path=db_path,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
    )
    if not state.completed:
        return running_action_payload(state, privacy_mode=privacy_mode)
    return completed_action_payload(state, privacy_mode=privacy_mode)


class _RouterState:
    def __init__(
        self,
        *,
        goal: str,
        filters: dict[str, Any],
        start_payload: dict[str, Any],
        profile_payload: dict[str, Any] | None = None,
        candidate_payload: dict[str, Any] | None = None,
        selected_details: list[dict[str, Any]] | None = None,
        simulation_payload: dict[str, Any] | None = None,
    ) -> None:
        self.goal = goal
        self.filters = filters
        self.start_payload = start_payload
        self.profile_payload = profile_payload
        self.candidate_payload = candidate_payload
        self.selected_details = selected_details or []
        self.simulation_payload = simulation_payload

    @property
    def run_id(self) -> str:
        return str(self.start_payload.get("run_id") or "")

    @property
    def completed(self) -> bool:
        return str(self.start_payload.get("status") or "") in _COMPLETED_STATUSES

    @property
    def candidates(self) -> list[dict[str, Any]]:
        if not self.candidate_payload:
            return []
        return [dict(row) for row in self.candidate_payload.get("candidates") or []]


def _load_compression_router_state(
    *,
    db_path: Path,
    goal: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    evidence_limit: int,
) -> _RouterState:
    normalized_goal = _normalize_agentic_goal(goal) or "token_waste"
    normalized_limit = max(1, int(evidence_limit or 1))
    scope = CompressionScope(
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    filters = {
        "since": since,
        "until": until,
        "thread": thread,
        "include_archived": include_archived,
        "evidence_limit": normalized_limit,
    }
    started = start_compression_analysis(db_path, scope, refresh=False)
    if str(started.get("status") or "") not in _COMPLETED_STATUSES:
        return _RouterState(goal=normalized_goal, filters=filters, start_payload=started)
    return _completed_router_state(
        db_path=db_path,
        goal=normalized_goal,
        filters=filters,
        start_payload=started,
        evidence_limit=normalized_limit,
    )


def _completed_router_state(
    *,
    db_path: Path,
    goal: str,
    filters: dict[str, Any],
    start_payload: dict[str, Any],
    evidence_limit: int,
) -> _RouterState:
    run_id = str(start_payload.get("run_id") or "")
    profile = compression_profile(db_path, run_id=run_id)
    candidates = compression_candidates(
        db_path,
        run_id=run_id,
        limit=evidence_limit,
        max_payload_bytes=CANDIDATE_PAGE_BUDGET_BYTES,
    )
    selected_ids = _selected_candidate_ids(candidates)
    return _RouterState(
        goal=goal,
        filters=filters,
        start_payload=start_payload,
        profile_payload=profile,
        candidate_payload=candidates,
        selected_details=_selected_details(db_path, selected_ids),
        simulation_payload=_selected_simulation(db_path, run_id, selected_ids),
    )


def _selected_candidate_ids(candidate_payload: dict[str, Any]) -> list[str]:
    rows = candidate_payload.get("candidates") or []
    return [
        str(row.get("candidate_id") or "")
        for row in rows[:_SELECTED_DETAIL_LIMIT]
        if row.get("candidate_id")
    ]


def _selected_details(db_path: Path, candidate_ids: list[str]) -> list[dict[str, Any]]:
    return [
        compression_candidate_detail(
            db_path,
            candidate_id=candidate_id,
            evidence_mode="handles",
            evidence_limit=10,
            max_excerpt_chars=0,
        )
        for candidate_id in candidate_ids
    ]


def _selected_simulation(
    db_path: Path,
    run_id: str,
    candidate_ids: list[str],
) -> dict[str, Any] | None:
    if not candidate_ids:
        return None
    return compression_simulate(
        db_path,
        run_id=run_id,
        candidate_ids=candidate_ids,
        max_payload_bytes=SIMULATION_BUDGET_BYTES,
    )
