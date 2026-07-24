"""Payload builders for Compression Lab MCP compatibility routing."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.core.projects import validate_privacy_mode


def running_investigation_payload(
    state: Any,
    *,
    privacy_mode: str,
) -> dict[str, Any]:
    privacy_mode = validate_privacy_mode(privacy_mode)
    next_call_value = next_call(state.start_payload, default_tool="usage_compression_status")
    return {
        **agentic_base(state, privacy_mode=privacy_mode),
        "summary": {
            "finding_count": 1,
            "top_finding": "Compression Lab analysis is still running",
            "confidence": "compression_analysis_running",
            "source_reports": ["codex-usage-tracker-compression-api-v1"],
        },
        "findings": [
            {
                "finding": "Compression Lab analysis is still running",
                "evidence_count": 0,
                "evidence_summary": {"row_count": 0},
                "evidence": [],
                "confidence": "compression_analysis_running",
                "why_it_matters": "Compression Lab runs asynchronously so broad waste analysis does not block the MCP call.",
                "recommended_action": "Poll status, then read the profile and selected candidate details.",
                "verify_with": ["usage_compression_status", "usage_compression_profile"],
                "missing_access": "Candidate evidence is available after the analysis completes.",
                "privacy_notes": "No raw content or indexed fragments are returned by this router.",
            }
        ],
        "recommended_next_tools": [tool(next_call_value)],
        "compression_lab": compression_lab_payload(state, next_call=next_call_value),
        "caveats": router_caveats(state.start_payload),
    }


def completed_investigation_payload(
    state: Any,
    *,
    privacy_mode: str,
) -> dict[str, Any]:
    privacy_mode = validate_privacy_mode(privacy_mode)
    evidence = [compact_candidate(row) for row in state.candidates]
    top = evidence[0] if evidence else None
    finding = (
        f"{top['family']} is the strongest Compression Lab candidate"
        if top
        else "Compression Lab found no strong candidates"
    )
    confidence = (
        top.get("confidence", "insufficient_local_evidence")
        if top
        else "insufficient_local_evidence"
    )
    return {
        **agentic_base(state, privacy_mode=privacy_mode),
        "summary": {
            "finding_count": 1,
            "top_finding": finding,
            "confidence": confidence,
            "source_reports": ["codex-usage-tracker-compression-api-v1"],
        },
        "findings": [
            {
                "finding": finding,
                "evidence_count": len(evidence),
                "evidence_summary": {"row_count": len(evidence)},
                "evidence": evidence,
                "confidence": confidence,
                "why_it_matters": "Compression Lab estimates overlap-adjusted local token exposure before recommending workflow changes.",
                "recommended_action": candidate_action(top),
                "verify_with": [
                    "usage_compression_candidate_detail",
                    "usage_compression_simulate",
                ],
                "missing_access": "Heuristic estimates cannot prove whether the original work was valuable.",
                "privacy_notes": "Selected details use handles only; no excerpts or raw fragments are returned.",
            }
        ],
        "recommended_next_tools": completed_next_tools(state),
        "compression_lab": compression_lab_payload(state),
        "caveats": router_caveats(state.start_payload),
    }


def running_action_payload(state: Any, *, privacy_mode: str) -> dict[str, Any]:
    privacy_mode = validate_privacy_mode(privacy_mode)
    next_call_value = next_call(state.start_payload, default_tool="usage_compression_status")
    return {
        **action_base(state, privacy_mode=privacy_mode),
        "summary": {
            "action_count": 1,
            "top_action_family": "compression_analysis_running",
            "source_reports": ["codex-usage-tracker-compression-api-v1"],
        },
        "actions": [
            {
                "family": "compression_analysis_running",
                "finding": "Compression Lab analysis is still running",
                "confidence": "compression_analysis_running",
                "evidence": [],
                "likely_waste_pattern": "Unknown until the async Compression Lab profile completes.",
                "recommended_workflow_change": "Poll status, then inspect the completed profile and strongest candidates.",
                "recommended_existing_tool": None,
                "recommended_custom_solution": "Use the Compression Lab polling lifecycle for broad token-waste questions.",
                "how_to_verify": "Call usage_compression_status, then usage_compression_profile.",
                "recommended_next_tools": ["usage_compression_status", "usage_compression_profile"],
                "missing_access": "Candidate evidence is not available until the analysis completes.",
            }
        ],
        "recommended_next_tools": [str(next_call_value["tool"])],
        "compression_lab": compression_lab_payload(state, next_call=next_call_value),
        "caveats": router_caveats(state.start_payload),
    }


def completed_action_payload(state: Any, *, privacy_mode: str) -> dict[str, Any]:
    privacy_mode = validate_privacy_mode(privacy_mode)
    actions = [
        {
            "family": str(candidate.get("family") or "compression_candidate"),
            "finding": f"{candidate.get('pattern') or candidate.get('family') or 'Compression candidate'}",
            "confidence": str(candidate.get("confidence") or "unknown"),
            "evidence": [compact_candidate(candidate)],
            "likely_waste_pattern": "Compression Lab found overlap-adjusted local token exposure in this candidate family.",
            "recommended_workflow_change": candidate_action(candidate),
            "recommended_existing_tool": recommended_existing_tool(candidate),
            "recommended_custom_solution": "Turn the repeated pattern into a project note, helper command, or skill rule if it recurs.",
            "how_to_verify": "Re-run Compression Lab after changing workflow and compare adjusted likely savings.",
            "recommended_next_tools": [
                "usage_compression_candidate_detail",
                "usage_compression_simulate",
            ],
            "missing_access": "Aggregate estimates cannot decide whether the original work was semantically valuable.",
        }
        for candidate in state.candidates[:1]
    ]
    if not actions:
        actions.append(no_candidate_action())
    return {
        **action_base(state, privacy_mode=privacy_mode),
        "summary": {
            "action_count": len(actions),
            "top_action_family": actions[0]["family"] if actions else None,
            "source_reports": ["codex-usage-tracker-compression-api-v1"],
        },
        "actions": actions,
        "recommended_next_tools": [
            "usage_compression_candidates",
            "usage_compression_candidate_detail",
            "usage_compression_simulate",
        ],
        "compression_lab": compression_lab_payload(state),
        "caveats": router_caveats(state.start_payload),
    }


def agentic_base(state: Any, *, privacy_mode: str) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker-agentic-investigation-v1",
        "content_mode": "compression_lab_router",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "goal": state.goal,
        "filters": {**state.filters, "detail_mode": "compact"},
    }


def action_base(state: Any, *, privacy_mode: str) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker-action-brief-v1",
        "content_mode": "compression_lab_router",
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
        "privacy_mode": privacy_mode,
        "goal": state.goal,
        "filters": dict(state.filters),
    }


def compression_lab_payload(
    state: Any,
    *,
    next_call: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "codex-usage-tracker-compression-api-v1",
        "run_id": state.run_id,
        "status": state.start_payload.get("status"),
        "start": compact_response(state.start_payload),
        "next": next_call or next_call_from_state(state),
    }
    if state.profile_payload is not None:
        payload["profile"] = compact_response(state.profile_payload)
    if state.candidate_payload is not None:
        payload["candidates"] = compact_response(state.candidate_payload)
    if state.selected_details:
        payload["selected_details"] = [
            compact_detail_response(detail) for detail in state.selected_details
        ]
    if state.simulation_payload is not None:
        payload["simulation"] = compact_response(state.simulation_payload)
    return payload


def compact_response(payload: dict[str, Any]) -> dict[str, Any]:
    omitted = {"claims", "evidence"}
    return {key: value for key, value in payload.items() if key not in omitted}


def compact_detail_response(payload: dict[str, Any]) -> dict[str, Any]:
    compact = compact_response(payload)
    candidate = compact.get("candidate")
    if isinstance(candidate, dict) and candidate.get("candidate_id"):
        compact["candidate_id"] = str(candidate["candidate_id"])
    return compact


def compact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate_id",
        "family",
        "pattern",
        "confidence",
        "observed_exposure_tokens",
        "adjusted_estimate",
        "estimator",
    )
    return {key: candidate[key] for key in keys if key in candidate}


def candidate_action(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "Keep the Compression Lab profile as a baseline and re-run after more usage accumulates."
    family = str(candidate.get("family") or "")
    if family == "shell_churn":
        return "Convert repeated probes into a focused command, script, or repo task."
    if family == "repeated_file_rediscovery":
        return "Capture stable facts in project notes or a helper so future turns do not rediscover the same files."
    if family == "stale_context":
        return "Start a fresh thread with a short handoff when old context no longer helps the next step."
    return "Inspect the selected candidate detail, then test one workflow change and re-run Compression Lab."


def recommended_existing_tool(candidate: dict[str, Any]) -> dict[str, str] | None:
    family = str(candidate.get("family") or "")
    if family in {"stale_context", "repeated_file_rediscovery"}:
        return {
            "tool": "Headroom",
            "reason": "Use when available to judge context pressure before continuing long work.",
        }
    return None


def no_candidate_action() -> dict[str, Any]:
    return {
        "family": "no_compression_candidate",
        "finding": "Compression Lab found no strong candidate in this scope",
        "confidence": "insufficient_local_evidence",
        "evidence": [],
        "likely_waste_pattern": "No supported local signal crossed the current detector thresholds.",
        "recommended_workflow_change": "Widen the scope, include archived sessions, or wait for more usage evidence.",
        "recommended_existing_tool": None,
        "recommended_custom_solution": "No custom fix is justified from this result alone.",
        "how_to_verify": "Re-run usage_compression_start with a broader scope.",
        "recommended_next_tools": ["usage_compression_start"],
        "missing_access": "No candidate evidence was selected.",
    }


def completed_next_tools(state: Any) -> list[dict[str, Any]]:
    run_id = state.run_id
    tools = [tool({"tool": "usage_compression_candidates", "arguments": {"run_id": run_id}})]
    if state.candidates:
        candidate_id = str(state.candidates[0].get("candidate_id") or "")
        tools.append(
            tool(
                {
                    "tool": "usage_compression_candidate_detail",
                    "arguments": {"candidate_id": candidate_id},
                }
            )
        )
        tools.append(
            tool(
                {
                    "tool": "usage_compression_simulate",
                    "arguments": {"run_id": run_id, "candidate_ids": [candidate_id]},
                }
            )
        )
    return tools


def tool(next_call_value: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": str(next_call_value.get("tool") or ""),
        "reason": "Compression Lab lifecycle step for this broad usage-waste question.",
        "default_arguments": dict(next_call_value.get("arguments") or {}),
    }


def next_call_from_state(state: Any) -> dict[str, Any]:
    source = state.candidate_payload or state.profile_payload or state.start_payload
    return next_call(source)


def next_call(
    payload: dict[str, Any] | None,
    *,
    default_tool: str = "usage_compression_profile",
) -> dict[str, Any]:
    next_call_value = dict((payload or {}).get("next") or {})
    tool_name = str(next_call_value.get("tool") or default_tool)
    arguments = dict(next_call_value.get("arguments") or {})
    return {"tool": tool_name, "arguments": arguments}


def router_caveats(payload: dict[str, Any]) -> list[str]:
    caveats = [
        "Compression Lab estimates are heuristic local ranges, not an official OpenAI usage ledger.",
        "Broad legacy tools route to compact Compression Lab lifecycle payloads for token-waste goals.",
    ]
    caveats.extend(str(value) for value in payload.get("caveats") or [])
    return list(dict.fromkeys(caveats))
