"""Developer-profile MCP tools for bounded dogfood analyses."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    DOGFOOD_JOB_LOCK as _DOGFOOD_JOB_LOCK,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    DOGFOOD_JOBS as _DOGFOOD_JOBS,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    cache_key as _dogfood_cache_key,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    job_status_payload as _dogfood_job_status_payload,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    load_cached_result as _load_cached_dogfood_result,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    prune_jobs as _prune_dogfood_jobs,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    register_job as _register_dogfood_job,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    run_job as _run_dogfood_job,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood import (
    utc_now as _utc_now,
)
from codex_usage_tracker.reports.agentic_dogfood import (
    DEFAULT_AGENTIC_DOGFOOD_DIR,
)


def usage_dogfood_start(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "strict",
    refresh: bool = True,
    run_hypotheses: bool = False,
    run_deep_investigations: bool = False,
    write_markdown: bool = True,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Start async aggregate dogfood diagnostics and return a polling job id."""
    job_id = uuid.uuid4().hex
    now = _utc_now()
    params = {
        "codex_home": DEFAULT_CODEX_HOME,
        "db_path": DEFAULT_DB_PATH,
        "pricing_path": DEFAULT_PRICING_PATH,
        "allowance_path": DEFAULT_ALLOWANCE_PATH,
        "rate_card_path": DEFAULT_RATE_CARD_PATH,
        "projects_path": DEFAULT_PROJECTS_PATH,
        "output_dir": DEFAULT_AGENTIC_DOGFOOD_DIR / "jobs" / job_id,
        "since": since,
        "until": until,
        "thread": thread,
        "include_archived": include_archived,
        "evidence_limit": max(1, evidence_limit),
        "privacy_mode": privacy_mode,
        "refresh": refresh,
        "run_hypotheses": run_hypotheses,
        "run_deep_investigations": run_deep_investigations,
        "write_markdown": write_markdown,
        "use_cache": use_cache,
        "cache_root": DEFAULT_AGENTIC_DOGFOOD_DIR / "cache",
    }
    cache_key = _dogfood_cache_key(params)
    cache_hit_payload: dict[str, Any] | None = None
    cache_source = "disabled"
    if use_cache and not refresh:
        cache_hit_payload, cache_source = _load_cached_dogfood_result(params, cache_key)
    with _DOGFOOD_JOB_LOCK:
        if cache_hit_payload is not None:
            _DOGFOOD_JOBS[job_id] = {
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "completed",
                "percent_complete": 100,
                "current_stage": "result_cache",
                "stages": [
                    {
                        "stage": "result_cache",
                        "percent": 100,
                        "status": "completed",
                        "source": cache_source,
                    }
                ],
                "created_at": now,
                "updated_at": now,
                "started_at": now,
                "completed_at": now,
                "error": None,
                "filters": {
                    "since": since,
                    "until": until,
                    "thread": thread,
                    "include_archived": include_archived,
                    "evidence_limit": max(1, evidence_limit),
                    "privacy_mode": privacy_mode,
                    "refresh": refresh,
                    "run_hypotheses": run_hypotheses,
                    "run_deep_investigations": run_deep_investigations,
                    "use_cache": use_cache,
                },
                "cache": cache_hit_payload.get("cache", {}),
                "result_cache": {
                    "enabled": use_cache,
                    "cacheable": True,
                    "hit": True,
                    "source": cache_source,
                    "cache_key": cache_key,
                },
                "artifacts": cache_hit_payload.get("artifacts", {}),
                "result": cache_hit_payload,
            }
            _prune_dogfood_jobs()
        else:
            _DOGFOOD_JOBS[job_id] = {
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "queued",
                "percent_complete": 0,
                "current_stage": "queued",
                "stages": [],
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "filters": {
                    "since": since,
                    "until": until,
                    "thread": thread,
                    "include_archived": include_archived,
                    "evidence_limit": max(1, evidence_limit),
                    "privacy_mode": privacy_mode,
                    "refresh": refresh,
                    "run_hypotheses": run_hypotheses,
                    "run_deep_investigations": run_deep_investigations,
                    "use_cache": use_cache,
                },
                "cache": {},
                "result_cache": {
                    "enabled": use_cache,
                    "cacheable": True,
                    "hit": False,
                    "source": cache_source if use_cache and not refresh else None,
                    "cache_key": cache_key,
                    "miss_reason": cache_source
                    if use_cache and not refresh
                    else "refresh_requested"
                    if use_cache
                    else "disabled",
                },
                "artifacts": {},
                "result": None,
            }
        _prune_dogfood_jobs()
    _register_dogfood_job(job_id, cache_key)
    if cache_hit_payload is not None:
        return _dogfood_job_status_payload(job_id)
    worker = threading.Thread(
        target=_run_dogfood_job,
        args=(job_id, params),
        name=f"codex-usage-dogfood-{job_id[:8]}",
        daemon=True,
    )
    worker.start()
    return _dogfood_job_status_payload(job_id)


def usage_dogfood_status(job_id: str, include_result: bool = False) -> dict[str, Any]:
    """Poll async dogfood progress percent, stage, cache keys, and completion state."""
    return _dogfood_job_status_payload(job_id, include_result=include_result)


def usage_dogfood_result(job_id: str) -> dict[str, Any]:
    """Return completed async dogfood payload or current status when still running."""
    status = _dogfood_job_status_payload(job_id, include_result=True)
    if status.get("status") != "completed":
        return status
    result = status.get("result")
    return result if isinstance(result, dict) else status
