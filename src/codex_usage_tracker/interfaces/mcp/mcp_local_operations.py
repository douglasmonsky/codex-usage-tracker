"""Explicit local-file operations exposed through compatibility MCP profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.dashboard.api import generate_dashboard
from codex_usage_tracker.pricing.allowance import write_allowance_template
from codex_usage_tracker.pricing.api import (
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.store.api import export_usage_csv as export_csv


def generate_usage_dashboard(
    output_path: str | None = None,
    limit: int = 5000,
    since: str | None = None,
    privacy_mode: str = "normal",
    include_archived: bool = False,
) -> dict[str, Any]:
    """Generate a local hoverable HTML dashboard from aggregate-only usage metrics."""
    output = Path(output_path).expanduser() if output_path else DEFAULT_DASHBOARD_PATH
    generated = generate_dashboard(
        DEFAULT_DB_PATH,
        output_path=output,
        limit=limit,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        since=since,
        privacy_mode=privacy_mode,
        include_archived=include_archived,
    )
    return {
        "schema": "codex-usage-tracker-dashboard-v1",
        "dashboard_path": str(generated),
        "file_url": generated.resolve().as_uri(),
        "opened": False,
        "limit": None if limit <= 0 else limit,
        "since": since,
        "privacy_mode": privacy_mode,
        "include_archived": include_archived,
    }


def export_usage_csv(
    output_path: str,
    limit: int | None = None,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Export aggregate Codex token usage rows to a local CSV file."""
    output = Path(output_path).expanduser()
    rows = export_csv(
        output_path=output,
        db_path=DEFAULT_DB_PATH,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    return {
        "schema": "codex-usage-tracker-export-v1",
        "rows": rows,
        "csv_path": str(output),
        "limit": limit,
        "privacy_mode": privacy_mode,
    }


def init_usage_pricing_config(force: bool = False) -> dict[str, Any]:
    """Write a local pricing template for optional cost estimates."""
    output = write_pricing_template(DEFAULT_PRICING_PATH, force=force)
    return {
        "schema": "codex-usage-tracker-init-pricing-v1",
        "pricing_path": str(output),
        "created": True,
    }


def init_usage_allowance_config(force: bool = False) -> dict[str, Any]:
    """Write a local template for optional Codex allowance windows."""
    output = write_allowance_template(DEFAULT_ALLOWANCE_PATH, force=force)
    return {
        "schema": "codex-usage-tracker-init-allowance-v1",
        "allowance_path": str(output),
        "created": True,
    }


def update_usage_pricing_config(
    tier: str = "standard", include_estimates: bool = True
) -> dict[str, Any]:
    """Fetch OpenAI-published text-token pricing into the local pricing config."""
    result = update_pricing_from_openai_docs(
        DEFAULT_PRICING_PATH,
        tier=tier,
        include_estimates=include_estimates,
    )
    return {
        "schema": "codex-usage-tracker-update-pricing-v1",
        "pricing_path": str(result.path),
        "source_url": result.source_url,
        "tier": result.tier,
        "fetched_at": result.fetched_at,
        "model_count": result.model_count,
        "estimated_model_count": result.estimated_model_count,
        "backup_path": str(result.backup_path) if result.backup_path else None,
    }
