"""Aggregate diagnostic concentration snapshot analysis."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from codex_usage_tracker.store.api import connect
from codex_usage_tracker.store.schema import init_db

DIAGNOSTIC_HISTORY_ACTIVE = "active"
DIAGNOSTIC_HISTORY_ALL = "all"
SAFE_PATH_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:@*+-]{1,80}$")
SENSITIVE_LABEL_PREFIXES = ("sk-", "sk_", "ghp_", "github_pat_", "xox")


def compute_concentration(
    *,
    db_path: Path,
    include_archived: bool,
) -> dict[str, Any]:
    where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                record_id,
                session_id,
                event_timestamp,
                source_file,
                cwd,
                total_tokens
            FROM usage_events
            {where}
            ORDER BY event_timestamp, record_id
            """
        ).fetchall()
        source_row = conn.execute(
            f"SELECT COUNT(DISTINCT source_file) AS source_logs_scanned FROM usage_events {where}"
        ).fetchone()

    source_groups: dict[str, dict[str, Any]] = {}
    cwd_groups: dict[str, dict[str, Any]] = {}
    day_groups: dict[str, dict[str, Any]] = {}
    total_tokens = 0
    for row in rows:
        tokens = _int_value(row["total_tokens"])
        total_tokens += tokens
        record_id = str(row["record_id"])
        session_id = _optional_str(row["session_id"])
        _add_concentration_row(
            source_groups,
            key=_source_group_key(row["source_file"]),
            label=_source_group_label(row["source_file"], session_id=session_id),
            group_hash=_source_group_hash(row["source_file"]),
            tokens=tokens,
            record_id=record_id,
            session_id=session_id,
        )
        cwd_ref = _cwd_group_ref(row["cwd"])
        _add_concentration_row(
            cwd_groups,
            key=cwd_ref["group_hash"],
            label=cwd_ref["label"],
            group_hash=cwd_ref["group_hash"],
            tokens=tokens,
            record_id=record_id,
            session_id=session_id,
        )
        day = _day_label(row["event_timestamp"])
        _add_concentration_row(
            day_groups,
            key=day,
            label=day,
            group_hash=_stable_hash(day),
            tokens=tokens,
            record_id=record_id,
            session_id=session_id,
        )

    dimensions = [
        _concentration_dimension(
            "source_log",
            "Source Log / Session",
            source_groups,
            total_tokens=total_tokens,
        ),
        _concentration_dimension("cwd", "Cwd / Project", cwd_groups, total_tokens=total_tokens),
        _concentration_dimension("day", "Day", day_groups, total_tokens=total_tokens),
    ]
    metrics = _concentration_metrics(dimensions)
    return {
        "meta": {
            "source_logs_scanned": _int_value(source_row["source_logs_scanned"]),
        },
        "summary": {
            "usage_rows": len(rows),
            "total_tokens": total_tokens,
            "dimension_count": len(dimensions),
            "history_scope": _history_scope(include_archived),
        },
        "metrics": metrics,
        "dimensions": dimensions,
        "largest_impact_rows": _largest_impact_rows(dimensions),
        "privacy": concentration_privacy_metadata(),
    }


def _add_concentration_row(
    groups: dict[str, dict[str, Any]],
    *,
    key: str,
    label: str,
    group_hash: str,
    tokens: int,
    record_id: str,
    session_id: str | None,
) -> None:
    group = groups.setdefault(
        key,
        {
            "label": label,
            "group_hash": group_hash,
            "total_tokens": 0,
            "usage_rows": 0,
            "largest_record_id": None,
            "largest_call_tokens": 0,
            "session_ids": set(),
        },
    )
    group["total_tokens"] = int(group["total_tokens"]) + tokens
    group["usage_rows"] = int(group["usage_rows"]) + 1
    if tokens > int(group["largest_call_tokens"]):
        group["largest_call_tokens"] = tokens
        group["largest_record_id"] = record_id
    if session_id:
        group["session_ids"].add(session_id)


def _concentration_dimension(
    dimension: str,
    label: str,
    groups: dict[str, dict[str, Any]],
    *,
    total_tokens: int,
) -> dict[str, Any]:
    rows = [
        _concentration_group_row(dimension, group, total_tokens=total_tokens)
        for group in groups.values()
    ]
    rows = sorted(
        rows,
        key=lambda row: (-int(row["total_tokens"]), -int(row["usage_rows"]), row["label"]),
    )
    return {
        "dimension": dimension,
        "label": label,
        "group_count": len(rows),
        "total_tokens": total_tokens,
        "top_1_share": _top_share(rows, 1, total_tokens=total_tokens),
        "top_3_share": _top_share(rows, 3, total_tokens=total_tokens),
        "top_5_share": _top_share(rows, 5, total_tokens=total_tokens),
        "effective_group_count": _effective_group_count(rows, total_tokens=total_tokens),
        "top_rows": rows[:10],
    }


def _concentration_group_row(
    dimension: str,
    group: dict[str, Any],
    *,
    total_tokens: int,
) -> dict[str, Any]:
    session_ids = sorted(group["session_ids"])
    return {
        "dimension": dimension,
        "label": group["label"],
        "group_hash": group["group_hash"],
        "usage_rows": int(group["usage_rows"]),
        "total_tokens": int(group["total_tokens"]),
        "share": _rounded_ratio(int(group["total_tokens"]), total_tokens),
        "largest_record_id": group["largest_record_id"],
        "largest_call_tokens": int(group["largest_call_tokens"]),
        "session_id": session_ids[0] if len(session_ids) == 1 else None,
    }


def _concentration_metrics(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in dimensions:
        dimension_key = str(dimension["dimension"])
        for top_n in (1, 3, 5):
            rows.append(
                {
                    "metric": f"top_{top_n}_{dimension_key}_share",
                    "dimension": dimension_key,
                    "top_n": top_n,
                    "share": dimension[f"top_{top_n}_share"],
                }
            )
    return rows


def _largest_impact_rows(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in dimensions:
        for row in dimension["top_rows"]:
            rows.append(dict(row))
    return sorted(
        rows,
        key=lambda row: (
            -float(row["share"]),
            -int(row["total_tokens"]),
            row["dimension"],
            row["label"],
        ),
    )[:15]


def _top_share(
    rows: list[dict[str, Any]],
    top_n: int,
    *,
    total_tokens: int,
) -> float:
    return _rounded_ratio(sum(int(row["total_tokens"]) for row in rows[:top_n]), total_tokens)


def _effective_group_count(
    rows: list[dict[str, Any]],
    *,
    total_tokens: int,
) -> float:
    if total_tokens <= 0:
        return 0.0
    hhi = sum((int(row["total_tokens"]) / total_tokens) ** 2 for row in rows)
    return round(1 / hhi, 6) if hhi else 0.0


def _source_group_key(value: object) -> str:
    return _source_group_hash(value)


def _source_group_hash(value: object) -> str:
    source = value if isinstance(value, str) and value else "unknown_source"
    return _stable_hash(source)


def _source_group_label(value: object, *, session_id: str | None) -> str:
    if session_id:
        return f"session:{session_id[:8]}"
    return f"source:{_source_group_hash(value)}"


def _cwd_group_ref(value: object) -> dict[str, str]:
    if isinstance(value, str) and value:
        path_ref = _path_ref_from_token(value)
        if path_ref is not None:
            return {"label": path_ref["path_label"], "group_hash": path_ref["path_hash"]}
    return {"label": "unknown_cwd", "group_hash": _stable_hash("unknown_cwd")}


def _day_label(value: object) -> str:
    if isinstance(value, str):
        match = re.match(r"^\d{4}-\d{2}-\d{2}", value)
        if match:
            return match.group(0)
    return "unknown_day"


def concentration_privacy_metadata() -> dict[str, str]:
    return {
        "source_log_label_policy": "session_id_prefix_or_source_hash",
        "cwd_label_policy": "basename_only",
        "hash_policy": "sha256_12",
        "raw_source_paths_included": "false",
        "raw_cwd_paths_included": "false",
    }


def _path_ref_from_token(token: str) -> dict[str, str] | None:
    raw = token.strip()
    if not raw or raw == "-" or _is_shell_separator(raw) or _looks_like_assignment(raw):
        return None
    if raw.startswith(("$", "`")) or "://" in raw:
        return None
    label = _safe_path_label(raw)
    if label is None:
        return None
    path_hash = _stable_hash(raw)
    return {"path_key": path_hash, "path_label": label, "path_hash": path_hash}


def _safe_path_label(token: str) -> str | None:
    normalized = token.rstrip("/")
    label = (
        normalized
        if normalized in {".", ".."}
        else normalized.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    )
    if not label:
        return None
    lowered = label.lower()
    if lowered.startswith(SENSITIVE_LABEL_PREFIXES):
        return "path"
    return label if SAFE_PATH_LABEL_RE.fullmatch(label) else "path"


def _is_shell_separator(token: str) -> bool:
    return token in {"&&", "||", ";", "|"}


def _looks_like_assignment(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token))


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _history_scope(include_archived: bool) -> str:
    return DIAGNOSTIC_HISTORY_ALL if include_archived else DIAGNOSTIC_HISTORY_ACTIVE


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _rounded_ratio(numerator: int, denominator: int) -> float:
    return round(_ratio(numerator, denominator), 6)
