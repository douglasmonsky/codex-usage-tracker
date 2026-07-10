"""Async dogfood job state and cache helpers for the MCP server."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.reports.agentic_dogfood import build_agentic_dogfood_report

DOGFOOD_JOBS: dict[str, dict[str, Any]] = {}
DOGFOOD_RESULT_CACHE: dict[str, dict[str, Any]] = {}
DOGFOOD_JOB_LOCK = threading.Lock()
_MAX_JOBS = 25
_MAX_RESULT_CACHE = 25


def utc_now() -> str:
    """Return the current UTC timestamp for job metadata."""
    return datetime.now(timezone.utc).isoformat()


def _copy_jsonable(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _file_fingerprint(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    return {
        "path": str(path),
        "exists": True,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _db_table_signature(
    connection: sqlite3.Connection,
    table_name: str,
    expressions: list[str],
) -> dict[str, Any]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if exists is None:
        return {"exists": False}
    columns = ", ".join(expressions)
    query = f"SELECT {columns} FROM {table_name}"  # nosec B608
    row = connection.execute(query).fetchone()
    return {"exists": True, "values": list(row or [])}


def _db_fingerprint(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}

    fingerprint: dict[str, Any] = {
        "path": str(path),
        "exists": True,
        "size": stat.st_size,
    }
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            connection.execute("PRAGMA query_only = ON")
            fingerprint["tables"] = {
                "usage_events": _db_table_signature(
                    connection,
                    "usage_events",
                    [
                        "COUNT(*)",
                        "COALESCE(MAX(event_timestamp), '')",
                        "COALESCE(MAX(record_id), '')",
                        "COALESCE(SUM(total_tokens), 0)",
                    ],
                ),
                "source_files": _db_table_signature(
                    connection,
                    "source_files",
                    [
                        "COUNT(*)",
                        "COALESCE(SUM(size_bytes), 0)",
                        "COALESCE(MAX(mtime_ns), 0)",
                        "COALESCE(MAX(parsed_until_line), 0)",
                        "COALESCE(MAX(latest_event_timestamp), '')",
                    ],
                ),
                "command_runs": _db_table_signature(
                    connection,
                    "command_runs",
                    ["COUNT(*)", "COALESCE(MAX(record_id), '')"],
                ),
                "file_events": _db_table_signature(
                    connection,
                    "file_events",
                    ["COUNT(*)", "COALESCE(MAX(record_id), '')"],
                ),
                "tool_calls": _db_table_signature(
                    connection,
                    "tool_calls",
                    ["COUNT(*)", "COALESCE(MAX(record_id), '')"],
                ),
                "content_fragments": _db_table_signature(
                    connection,
                    "content_fragments",
                    ["COUNT(*)", "COALESCE(MAX(record_id), '')"],
                ),
                "allowance_observations": _db_table_signature(
                    connection,
                    "allowance_observations",
                    [
                        "COUNT(*)",
                        "COALESCE(MAX(observed_at), '')",
                        "COALESCE(MAX(source_record_id), '')",
                    ],
                ),
            }
    except sqlite3.Error as exc:
        fingerprint["read_error"] = type(exc).__name__
    return fingerprint


def _cache_fingerprint(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "db": _db_fingerprint(params["db_path"]),
        "pricing": _file_fingerprint(params["pricing_path"]),
        "allowance": _file_fingerprint(params["allowance_path"]),
        "rate_card": _file_fingerprint(params["rate_card_path"]),
        "projects": _file_fingerprint(params["projects_path"]),
    }


def _cache_request(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "since": params["since"],
        "until": params["until"],
        "thread": params["thread"],
        "include_archived": params["include_archived"],
        "evidence_limit": params["evidence_limit"],
        "privacy_mode": params["privacy_mode"],
        "run_hypotheses": params["run_hypotheses"],
        "run_deep_investigations": params["run_deep_investigations"],
        "write_markdown": params["write_markdown"],
    }


def cache_key(params: dict[str, Any]) -> str:
    """Build a stable key from request arguments and source fingerprints."""
    material = {
        "kind": "dogfood-cache-key-v1",
        "request": _cache_request(params),
        "fingerprint": _cache_fingerprint(params),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cache_path(params: dict[str, Any], result_cache_key: str) -> Path:
    return params["cache_root"] / result_cache_key / "summary.json"


def _prune_result_cache() -> None:
    if len(DOGFOOD_RESULT_CACHE) <= _MAX_RESULT_CACHE:
        return
    removable = sorted(
        DOGFOOD_RESULT_CACHE.items(),
        key=lambda item: str(item[1].get("stored_at") or ""),
    )
    for result_cache_key, _entry in removable[
        : max(0, len(DOGFOOD_RESULT_CACHE) - _MAX_RESULT_CACHE)
    ]:
        DOGFOOD_RESULT_CACHE.pop(result_cache_key, None)


def load_cached_result(
    params: dict[str, Any], result_cache_key: str
) -> tuple[dict[str, Any] | None, str]:
    """Load a cached result from memory or the local cache directory."""
    cached = DOGFOOD_RESULT_CACHE.get(result_cache_key)
    if cached is not None:
        return _copy_jsonable(cached["result"]), "memory"
    path = _cache_path(params, result_cache_key)
    if not path.exists():
        return None, "miss"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "invalid"
    DOGFOOD_RESULT_CACHE[result_cache_key] = {
        "stored_at": utc_now(),
        "result": payload,
    }
    _prune_result_cache()
    return _copy_jsonable(payload), "disk"


def _store_cached_result(params: dict[str, Any], payload: dict[str, Any]) -> str:
    result_cache_key = cache_key(params)
    DOGFOOD_RESULT_CACHE[result_cache_key] = {
        "stored_at": utc_now(),
        "result": _copy_jsonable(payload),
    }
    _prune_result_cache()
    path = _cache_path(params, result_cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return result_cache_key


def prune_jobs() -> None:
    """Discard the oldest completed jobs beyond the in-process limit."""
    if len(DOGFOOD_JOBS) <= _MAX_JOBS:
        return
    removable = sorted(
        (job for job in DOGFOOD_JOBS.values() if job.get("status") not in {"queued", "running"}),
        key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
    )
    for job in removable[: max(0, len(DOGFOOD_JOBS) - _MAX_JOBS)]:
        DOGFOOD_JOBS.pop(str(job["job_id"]), None)


def job_status_payload(
    job_id: str,
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe status payload for an asynchronous job."""
    with DOGFOOD_JOB_LOCK:
        job = DOGFOOD_JOBS.get(job_id)
        if job is None:
            return {
                "schema": "codex-usage-tracker-async-job-status-v1",
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "not_found",
                "percent_complete": 0,
                "error": "Unknown dogfood job_id. Jobs are in-process and cleared when the MCP server restarts.",
            }
        payload = {
            "schema": "codex-usage-tracker-async-job-status-v1",
            "job_id": job["job_id"],
            "job_type": job["job_type"],
            "status": job["status"],
            "percent_complete": job["percent_complete"],
            "current_stage": job.get("current_stage"),
            "stages": list(job.get("stages", [])),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "error": job.get("error"),
            "filters": dict(job.get("filters", {})),
            "cache": dict(job.get("cache", {})),
            "result_cache": dict(job.get("result_cache", {})),
            "artifacts": dict(job.get("artifacts", {})),
            "result_available": bool(job.get("result")),
            "polling_note": (
                "Poll usage_dogfood_status until status is completed or failed, then call usage_dogfood_result."
            ),
        }
        if include_result and job.get("result") is not None:
            payload["result"] = job["result"]
        return _copy_jsonable(payload)


def _update_job(job_id: str, **updates: Any) -> None:
    with DOGFOOD_JOB_LOCK:
        job = DOGFOOD_JOBS[job_id]
        job.update(updates)
        job["updated_at"] = utc_now()


def _append_stage(job_id: str, stage: dict[str, Any]) -> None:
    with DOGFOOD_JOB_LOCK:
        job = DOGFOOD_JOBS[job_id]
        stages = list(job.get("stages", []))
        stages.append(stage)
        job["stages"] = stages
        job["current_stage"] = stage.get("stage")
        job["percent_complete"] = int(stage.get("percent") or job.get("percent_complete") or 0)
        if stage.get("cache_keys") is not None:
            job["cache"] = {
                "scope": "single_run_shared_reports",
                "cache_keys": list(stage["cache_keys"]),
            }
        job["updated_at"] = utc_now()


def run_job(job_id: str, params: dict[str, Any]) -> None:
    """Build the dogfood report and update its in-process job record."""
    _update_job(
        job_id,
        status="running",
        percent_complete=1,
        current_stage="start",
        started_at=utc_now(),
    )
    try:
        payload = build_agentic_dogfood_report(
            codex_home=params["codex_home"],
            db_path=params["db_path"],
            pricing_path=params["pricing_path"],
            allowance_path=params["allowance_path"],
            rate_card_path=params["rate_card_path"],
            projects_path=params["projects_path"],
            output_dir=params["output_dir"],
            since=params["since"],
            until=params["until"],
            thread=params["thread"],
            include_archived=params["include_archived"],
            evidence_limit=params["evidence_limit"],
            privacy_mode=params["privacy_mode"],
            refresh=params["refresh"],
            run_hypotheses=params["run_hypotheses"],
            run_deep_investigations=params["run_deep_investigations"],
            write_markdown=params["write_markdown"],
            progress_callback=lambda stage: _append_stage(job_id, stage),
        )
    except Exception as exc:  # pragma: no cover - integration failure path.
        _update_job(
            job_id,
            status="failed",
            current_stage="failed",
            error=f"{type(exc).__name__}: {exc}",
            completed_at=utc_now(),
        )
        return
    result_cache: dict[str, Any] = {
        "enabled": params["use_cache"],
        "cacheable": True,
        "hit": False,
        "source": None,
    }
    if params["use_cache"]:
        result_cache_key = _store_cached_result(params, payload)
        result_cache["cache_key"] = result_cache_key
        result_cache["source"] = "stored"
    _update_job(
        job_id,
        status="completed",
        percent_complete=100,
        current_stage="write_artifacts",
        completed_at=utc_now(),
        result=payload,
        cache=payload.get("cache", {}),
        result_cache=result_cache,
        artifacts=payload.get("artifacts", {}),
    )
