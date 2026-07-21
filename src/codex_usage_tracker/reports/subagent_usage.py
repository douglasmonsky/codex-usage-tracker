"""Stable aggregate report for observed subagent usage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.projects import validate_privacy_mode
from codex_usage_tracker.pricing import (
    PricingConfig,
    annotate_rows_with_efficiency,
    load_pricing_config,
)
from codex_usage_tracker.store.subagent_usage_queries import (
    query_subagent_usage_buckets,
)

_METRIC_KEYS = (
    "calls",
    "turns",
    "observed_spawns",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "latest_event",
)
_NON_CAUSAL_CAVEAT = (
    "Observed comparison only; it does not show that subagents caused the difference."
)


@dataclass(frozen=True)
class SubagentUsageReport:
    """Stable subagent usage payload with a compact Markdown representation."""

    data: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return dict(self.data)

    def render(self) -> str:
        return render_subagent_usage(self.data)


def build_subagent_usage_report(
    *,
    db_path: Path,
    pricing_path: Path,
    since: str | None = None,
    parent_thread: str | None = None,
    agent_role: str | None = None,
    subagent_type: str | None = None,
    include_archived: bool = False,
    limit: int = 10,
    privacy_mode: str = "normal",
) -> SubagentUsageReport:
    """Build an aggregate-only observed subagent usage report."""

    validated_since = _validate_since(since)
    _validate_limit(limit)
    validated_privacy_mode = validate_privacy_mode(privacy_mode)
    pricing = load_pricing_config(pricing_path)
    queried = query_subagent_usage_buckets(
        db_path,
        since=validated_since,
        parent_thread=parent_thread,
        agent_role=agent_role,
        subagent_type=subagent_type,
        include_archived=include_archived,
        limit=limit,
    )

    cohorts = queried["cohorts"]
    priced_direct = _price_bucket(cohorts["direct"], pricing)
    priced_subagent = _price_bucket(cohorts["subagent"], pricing)
    priced_attributable = _price_bucket(cohorts["attributable_subagent"], pricing)
    observed_spawns = _number(priced_attributable["observed_spawns"])
    direct_calls = _number(priced_direct["calls"])
    subagent_calls = _number(priced_subagent["calls"])
    direct_turns = _number(priced_direct["turns"])
    subagent_turns = _number(priced_subagent["turns"])
    direct_tokens = _number(priced_direct["total_tokens"])
    subagent_tokens = _number(priced_subagent["total_tokens"])
    direct_cost = _number_or_none(priced_direct["estimated_cost_usd"])
    subagent_cost = _number_or_none(priced_subagent["estimated_cost_usd"])

    summary = {
        **priced_subagent,
        "subagent_calls": int(subagent_calls),
        "subagent_turns": int(subagent_turns),
        "total_tokens_per_observed_spawn": _ratio(
            _number(priced_attributable["total_tokens"]), observed_spawns
        ),
        "calls_per_observed_spawn": _ratio(_number(priced_attributable["calls"]), observed_spawns),
        "turns_per_observed_spawn": _ratio(_number(priced_attributable["turns"]), observed_spawns),
        "estimated_cost_usd_per_observed_spawn": _ratio(
            _number_or_none(priced_attributable["estimated_cost_usd"]),
            observed_spawns,
        ),
        "subagent_call_share": _ratio(subagent_calls, direct_calls + subagent_calls),
        "subagent_turn_share": _ratio(subagent_turns, direct_turns + subagent_turns),
        "subagent_token_share": _ratio(subagent_tokens, direct_tokens + subagent_tokens),
        "subagent_estimated_cost_share": _covered_cost_share(subagent_cost, direct_cost),
    }
    direct_comparison = _comparison_bucket(priced_direct)
    subagent_comparison = _comparison_bucket(priced_subagent)
    comparison = {
        "direct": direct_comparison,
        "subagent": subagent_comparison,
        "deltas": _comparison_deltas(subagent_comparison, direct_comparison),
    }
    breakdowns = queried["breakdowns"]
    by_role = _price_breakdown(
        breakdowns["role"],
        pricing,
        total_tokens=subagent_tokens,
        total_spawns=observed_spawns,
    )
    by_type = _price_breakdown(
        breakdowns["type"],
        pricing,
        total_tokens=subagent_tokens,
        total_spawns=observed_spawns,
    )
    top_parent_threads = _price_breakdown(
        breakdowns["parent"],
        pricing,
        total_tokens=subagent_tokens,
        total_spawns=observed_spawns,
        pseudonymize=validated_privacy_mode in {"redacted", "strict"},
    )
    coverage = _coverage(queried["coverage"], priced_subagent["pricing_coverage"])
    filters = {
        "since": validated_since,
        "parent_thread": _private_parent_label(parent_thread, privacy_mode=validated_privacy_mode),
        "agent_role": agent_role,
        "subagent_type": subagent_type,
        "include_archived": include_archived,
        "limit": limit,
        "privacy_mode": validated_privacy_mode,
    }
    definitions = {
        "observed_spawn": "A distinct subagent session present in aggregate usage rows.",
        "subagent_cohort": (
            "Rows explicitly marked as subagent or carrying non-empty subagent type or "
            "parent linkage metadata."
        ),
        "direct_cohort": "Rows in the matching base scope not matching the subagent cohort.",
        "per_spawn_usage": "Uses only subagent usage attributable to an observed spawn.",
        "observed_comparison_not_causal": True,
    }
    warnings = _warnings(summary, coverage, pricing)

    payload = {
        "schema_id": "codex-usage-tracker.subagent-usage.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": filters,
        "definitions": definitions,
        "summary": summary,
        "comparison": comparison,
        "by_role": by_role,
        "by_type": by_type,
        "top_parent_threads": top_parent_threads,
        "coverage": coverage,
        "warnings": warnings,
    }
    return SubagentUsageReport(payload)


def render_subagent_usage(data: dict[str, Any]) -> str:
    """Render a compact Markdown view of a subagent usage payload."""

    summary = data["summary"]
    lines = ["# Observed subagent usage"]
    if not _number(summary["calls"]):
        lines.extend(["", "No observed subagent usage matched these filters."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            (
                f"Observed {summary['observed_spawns']} spawns across "
                f"{summary['calls']} calls using {summary['total_tokens']} tokens "
                f"({_format_ratio(summary['total_tokens_per_observed_spawn'])} tokens per spawn)."
            ),
            "",
            (
                f"Subagent usage was {_format_percent(summary['subagent_token_share'])} of "
                "observed direct-plus-subagent tokens; tokens per call were "
                f"{_format_ratio(data['comparison']['subagent']['tokens_per_call'])} for "
                "subagents versus "
                f"{_format_ratio(data['comparison']['direct']['tokens_per_call'])} direct. "
                f"{_NON_CAUSAL_CAVEAT}"
            ),
        ]
    )
    _render_breakdown(lines, "By role", data["by_role"])
    _render_breakdown(lines, "By type", data["by_type"])
    _render_breakdown(lines, "Top parent threads", data["top_parent_threads"])
    return "\n".join(lines)


def _validate_since(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        raise ValueError("since must be a non-empty ISO-8601 date or datetime")
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("since must be an ISO-8601 date or datetime") from exc
    return candidate


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 through 100")


def _price_bucket(bucket: dict[str, Any], pricing: PricingConfig) -> dict[str, Any]:
    rows = annotate_rows_with_efficiency(bucket["model_buckets"], pricing)
    covered_costs = [
        row["estimated_cost_usd"]
        for row in rows
        if isinstance(row["estimated_cost_usd"], int | float)
    ]
    return {
        **_metrics(bucket["metrics"]),
        "estimated_cost_usd": (
            round(sum(float(value) for value in covered_costs), 6) if covered_costs else None
        ),
        "pricing_coverage": _pricing_coverage(rows),
    }


def _metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics.get(key) for key in _METRIC_KEYS}


def _pricing_coverage(rows: list[dict[str, Any]]) -> dict[str, int]:
    coverage = {
        "priced_model_count": 0,
        "estimated_model_count": 0,
        "unpriced_model_count": 0,
        "priced_tokens": 0,
        "estimated_tokens": 0,
        "unpriced_tokens": 0,
    }
    for row in rows:
        tokens = int(_number(row.get("total_tokens")))
        if row.get("pricing_model") is None:
            coverage["unpriced_model_count"] += 1
            coverage["unpriced_tokens"] += tokens
        elif row.get("pricing_estimated") is True:
            coverage["estimated_model_count"] += 1
            coverage["estimated_tokens"] += tokens
        else:
            coverage["priced_model_count"] += 1
            coverage["priced_tokens"] += tokens
    return coverage


def _price_breakdown(
    buckets: list[dict[str, Any]],
    pricing: PricingConfig,
    *,
    total_tokens: int | float,
    total_spawns: int | float,
    pseudonymize: bool = False,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for bucket in buckets:
        label = str(bucket["group_key"])
        priced = _price_bucket(bucket, pricing)
        row = {
            "group_key": (
                _parent_digest(label) if pseudonymize and label != "unknown parent" else label
            ),
            **priced,
            "subagent_token_share": _ratio(_number(priced["total_tokens"]), total_tokens),
            "observed_spawn_share": _ratio(_number(priced["observed_spawns"]), total_spawns),
        }
        if isinstance(bucket.get("role_mix"), list):
            row["role_mix"] = [dict(item) for item in bucket["role_mix"]]
        result.append(row)
    return result


def _coverage(coverage: dict[str, Any], pricing_coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "missing_session_rows": int(coverage["missing_session_rows"]),
        "missing_session_tokens": int(coverage["missing_session_tokens"]),
        "missing_role_spawns": int(coverage["missing_role_spawns"]),
        "missing_type_spawns": int(coverage["missing_type_spawns"]),
        "pricing": dict(pricing_coverage),
    }


def _warnings(
    summary: dict[str, Any], coverage: dict[str, int], pricing: PricingConfig
) -> list[str]:
    warnings: list[str] = []
    if coverage["missing_session_rows"]:
        warnings.append("Some subagent usage could not be attributed to an observed spawn.")
    if summary["pricing_coverage"]["unpriced_model_count"]:
        warnings.append("Estimated cost excludes models without local pricing.")
    if pricing.error:
        warnings.append("The local pricing configuration could not be loaded.")
    elif not pricing.loaded:
        warnings.append("No local pricing configuration was loaded.")
    return warnings


def _ratio(numerator: int | float | None, denominator: int | float) -> float | None:
    return float(numerator) / float(denominator) if numerator is not None and denominator else None


def _covered_cost_share(subagent: float | None, direct: float | None) -> float | None:
    if subagent is None and direct is None:
        return None
    subagent_cost = subagent or 0.0
    direct_cost = direct or 0.0
    return _ratio(subagent_cost, subagent_cost + direct_cost)


def _comparison_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        **bucket,
        "tokens_per_call": _ratio(_number(bucket["total_tokens"]), _number(bucket["calls"])),
        "tokens_per_turn": _ratio(_number(bucket["total_tokens"]), _number(bucket["turns"])),
        "cache_ratio": _ratio(
            _number(bucket["cached_input_tokens"]), _number(bucket["input_tokens"])
        ),
        "output_token_ratio": _ratio(
            _number(bucket["output_tokens"]), _number(bucket["total_tokens"])
        ),
        "reasoning_output_ratio": _ratio(
            _number(bucket["reasoning_output_tokens"]), _number(bucket["output_tokens"])
        ),
    }


def _comparison_deltas(subagent: dict[str, Any], direct: dict[str, Any]) -> dict[str, float | None]:
    keys = (
        "tokens_per_call",
        "tokens_per_turn",
        "cache_ratio",
        "output_token_ratio",
        "reasoning_output_ratio",
    )
    return {key: _difference(subagent[key], direct[key]) for key in keys}


def _difference(left: object, right: object) -> float | None:
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        return None
    return float(left) - float(right)


def _number(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _number_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _private_parent_label(label: str | None, *, privacy_mode: str) -> str | None:
    if label is None or privacy_mode == "normal":
        return label
    return _parent_digest(label)


def _parent_digest(label: str) -> str:
    digest = hashlib.sha256(label.encode("utf-8")).hexdigest()[:8]
    return f"Parent {digest}"


def _format_ratio(value: object) -> str:
    return f"{value:.2f}" if isinstance(value, int | float) else "n/a"


def _format_percent(value: object) -> str:
    return f"{value:.1%}" if isinstance(value, int | float) else "n/a"


def _render_breakdown(lines: list[str], heading: str, rows: list[dict[str, Any]]) -> None:
    lines.extend(["", f"## {heading}"])
    if not rows:
        lines.append("No observed usage.")
        return
    lines.extend(
        f"- {row['group_key']}: {row['total_tokens']} tokens, {row['observed_spawns']} spawns"
        for row in rows
    )
