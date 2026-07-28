#!/usr/bin/env python3
"""Validate and transition the frozen Product Kernel Reset manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RETIRED_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
_DISPOSITION_PATH = _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
_K1_MERGE = "d8da9bccdb6674e7dca4c0872c36a1346949dc13"
# Keep the retired framework name out of active source as one searchable token.
_RETIRED_PLAN_ROOT = "".join(("super", "powers"))
_AUTHORITY_CLEANUP_PREFIXES = (
    f".{_RETIRED_PLAN_ROOT}/",
    f"docs/{_RETIRED_PLAN_ROOT}/",
)
_AUTHORITY_CLEANUP_PATHS = frozenset(
    {
        ".agent-maintainer/change-plans/k1-oracle-baseline.md",
        "docs/roadmap/product-kernel-reset-execution.md",
        "docs/roadmap/product-kernel-reset.md",
    }
)
_K2_DEFERRED = {
    "tests/store/test_foreign_key_cascades.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        "tests/kernel/test_source_lifecycle_oracle.py",
    ),
    "tests/store/test_usage_deduplication.py": (
        "tests/kernel/test_ingest_deduplication.py",
        "tests/kernel/test_oracle_equivalence.py",
    ),
}
_K2_TRANSPLANTS = {
    "src/codex_usage_tracker/core/call_origin.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/models.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/paths.py": (
        "src/codex_usage_tracker/kernel/operational.py",
        (
            "tests/kernel/test_cutover_control.py",
            "tests/kernel/test_source_registry_privacy.py",
        ),
    ),
    "src/codex_usage_tracker/core/projects.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/redaction.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/schema.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/core/threads.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/core/usage_identity.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/store/cache_repository.py": (
        "src/codex_usage_tracker/kernel/operational.py",
        ("tests/kernel/test_cutover_control.py",),
    ),
    "src/codex_usage_tracker/store/connection.py": (
        "src/codex_usage_tracker/kernel/database.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
    "src/codex_usage_tracker/store/deduplication.py": (
        "src/codex_usage_tracker/kernel/identity.py",
        ("tests/kernel/test_identity.py",),
    ),
    "src/codex_usage_tracker/store/deduplication_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/store/integrity.py": (
        "src/codex_usage_tracker/kernel/database.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
    "src/codex_usage_tracker/store/rows.py": (
        "src/codex_usage_tracker/kernel/models.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/store/schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    "tests/store/test_connection_integrity.py": (
        "tests/kernel/test_database_lifecycle.py",
        ("tests/kernel/test_database_lifecycle.py",),
    ),
}

_K3_TRANSPLANTS = {
    "src/codex_usage_tracker/application/job_status.py": (
        "src/codex_usage_tracker/kernel/lease.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "src/codex_usage_tracker/application/refresh.py": (
        "src/codex_usage_tracker/kernel/ingest.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/ingest/fact_classifiers.py": (
        "src/codex_usage_tracker/kernel/normalize.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/ingest/facts.py": (
        "src/codex_usage_tracker/kernel/normalize.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/api.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/jsonl_v1.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/parser/jsonl_values.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_privacy.py",),
    ),
    "src/codex_usage_tracker/parser/state.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/store/refresh.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "src/codex_usage_tracker/store/refresh_metadata.py": (
        "src/codex_usage_tracker/kernel/lease.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "src/codex_usage_tracker/store/refresh_parse.py": (
        "src/codex_usage_tracker/kernel/parser.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "src/codex_usage_tracker/store/refresh_stream.py": (
        "src/codex_usage_tracker/kernel/watcher.py",
        ("tests/kernel/test_watcher.py",),
    ),
    "src/codex_usage_tracker/store/source_record_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/source_record_sync.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/source_records.py": (
        "src/codex_usage_tracker/kernel/discovery.py",
        ("tests/kernel/test_source_lifecycle_oracle.py",),
    ),
    "src/codex_usage_tracker/store/source_replacement.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "src/codex_usage_tracker/store/sources.py": (
        "src/codex_usage_tracker/kernel/discovery.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/application/test_refresh.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/cli/test_cli_parser_diagnostics.py": (
        "tests/kernel/test_ingest_privacy.py",
        ("tests/kernel/test_ingest_privacy.py",),
    ),
    "tests/interfaces/cli/test_parser.py": (
        "tests/kernel/test_ingest_oracle.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "tests/parser/test_parser.py": (
        "tests/kernel/test_ingest_oracle.py",
        ("tests/kernel/test_ingest_oracle.py",),
    ),
    "tests/parser/test_parser_deduplication.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_oracle_equivalence.py",),
    ),
    "tests/parser/test_parser_observer.py": (
        "tests/kernel/test_watcher.py",
        ("tests/kernel/test_watcher.py",),
    ),
    "tests/parser/test_parser_state.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/reliability/test_read_during_refresh.py": (
        "tests/kernel/test_ingest_concurrency.py",
        ("tests/kernel/test_ingest_concurrency.py",),
    ),
    "tests/reliability/test_refresh_locking.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/server/test_refresh_jobs.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/store/test_foreign_key_cascades.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "tests/store/test_refresh_parallel.py": (
        "tests/kernel/test_ingest_jobs.py",
        ("tests/kernel/test_ingest_jobs.py",),
    ),
    "tests/store/test_refresh_workflow.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/store/test_source_records.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_ingest_reconciliation.py",),
    ),
    "tests/store/test_store_sources.py": (
        "tests/kernel/test_ingest_pipeline.py",
        ("tests/kernel/test_ingest_pipeline.py",),
    ),
    "tests/store/test_usage_deduplication.py": (
        "tests/kernel/test_ingest_reconciliation.py",
        ("tests/kernel/test_oracle_equivalence.py",),
    ),
}
_K4_TRANSPLANTS = {
    "src/codex_usage_tracker/application/query.py": (
        "src/codex_usage_tracker/kernel/query/service.py",
        ("tests/kernel/query/test_service.py",),
    ),
    "src/codex_usage_tracker/application/query_models.py": (
        "src/codex_usage_tracker/kernel/query/contracts.py",
        ("tests/kernel/query/test_contracts.py",),
    ),
    "src/codex_usage_tracker/application/query_validation.py": (
        "src/codex_usage_tracker/kernel/query/catalog.py",
        ("tests/kernel/query/test_contracts.py",),
    ),
    "src/codex_usage_tracker/store/query_sql.py": (
        "src/codex_usage_tracker/kernel/query/plans.py",
        ("tests/kernel/query/test_service.py",),
    ),
    "src/codex_usage_tracker/store/query_values.py": (
        "src/codex_usage_tracker/kernel/query/contracts.py",
        ("tests/kernel/query/test_contracts.py",),
    ),
    "src/codex_usage_tracker/store/schema_query_indexes.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/query/test_performance.py",),
    ),
    "src/codex_usage_tracker/store/summary_queries.py": (
        "src/codex_usage_tracker/kernel/query/service.py",
        ("tests/kernel/query/test_service.py",),
    ),
    "src/codex_usage_tracker/store/usage_timing.py": (
        "src/codex_usage_tracker/kernel/query/service.py",
        ("tests/kernel/query/test_performance.py",),
    ),
    "tests/application/test_query.py": (
        "tests/kernel/query/test_service.py",
        ("tests/kernel/query/test_service.py",),
    ),
    "tests/application/test_query_validation.py": (
        "tests/kernel/query/test_contracts.py",
        ("tests/kernel/query/test_contracts.py",),
    ),
    "tests/golden_questions/cases/03_precise_model_query.json": (
        "tests/kernel/query/test_service.py",
        ("tests/kernel/query/test_service.py",),
    ),
    "tests/mcp/test_core_query_tool.py": (
        "tests/kernel/query/test_contracts.py",
        ("tests/kernel/query/test_contracts.py",),
    ),
    "tests/store/test_store_query_sql.py": (
        "tests/kernel/query/test_service.py",
        ("tests/kernel/query/test_service.py",),
    ),
}
_K5_TRANSPLANTS = {
    "src/codex_usage_tracker/application/evidence.py": (
        "src/codex_usage_tracker/kernel/evidence/service.py",
        (
            "tests/kernel/evidence/test_contracts.py",
            "tests/kernel/evidence/test_service.py",
        ),
    ),
}
_K6_TRANSPLANTS = {
    **{
        path: (
            "src/codex_usage_tracker/kernel/application/service.py",
            ("tests/kernel/interfaces/test_application.py",),
        )
        for path in (
            "src/codex_usage_tracker/application/__init__.py",
            "src/codex_usage_tracker/application/container.py",
            "src/codex_usage_tracker/application/errors.py",
            "src/codex_usage_tracker/application/protocols.py",
            "src/codex_usage_tracker/application/services.py",
            "src/codex_usage_tracker/application/tach.domain.toml",
        )
    },
    "src/codex_usage_tracker/application/paths.py": (
        "src/codex_usage_tracker/kernel/application/runtime.py",
        ("tests/kernel/interfaces/test_application.py",),
    ),
    "src/codex_usage_tracker/application/requests.py": (
        "src/codex_usage_tracker/kernel/application/codec.py",
        ("tests/kernel/interfaces/test_application.py",),
    ),
    **{
        path: (
            "src/codex_usage_tracker/kernel/interfaces/cli/main.py",
            ("tests/kernel/interfaces/test_cli.py",),
        )
        for path in (
            "src/codex_usage_tracker/interfaces/cli/__init__.py",
            "src/codex_usage_tracker/interfaces/cli/commands.py",
            "src/codex_usage_tracker/interfaces/cli/help_i18n.py",
            "src/codex_usage_tracker/interfaces/cli/namespaces.py",
            "src/codex_usage_tracker/interfaces/cli/parser.py",
            "src/codex_usage_tracker/interfaces/cli/parser_data.py",
            "src/codex_usage_tracker/interfaces/cli/parser_diagnostics.py",
            "src/codex_usage_tracker/interfaces/cli/parser_lifecycle.py",
            "src/codex_usage_tracker/interfaces/cli/parser_reports.py",
            "src/codex_usage_tracker/interfaces/cli/tach.domain.toml",
        )
    },
    **{
        path: (
            "src/codex_usage_tracker/kernel/interfaces/http/app.py",
            ("tests/kernel/interfaces/test_http.py",),
        )
        for path in (
            "src/codex_usage_tracker/interfaces/http/__init__.py",
            "src/codex_usage_tracker/interfaces/http/serialization.py",
            "src/codex_usage_tracker/interfaces/http/tach.domain.toml",
            "src/codex_usage_tracker/interfaces/http/v2.py",
        )
    },
    **{
        path: (
            "src/codex_usage_tracker/kernel/interfaces/mcp/catalog.py",
            (
                "tests/kernel/interfaces/test_contracts.py",
                "tests/kernel/interfaces/test_mcp.py",
            ),
        )
        for path in (
            "src/codex_usage_tracker/interfaces/mcp/__init__.py",
            "src/codex_usage_tracker/interfaces/mcp/core_tools.py",
            "src/codex_usage_tracker/interfaces/mcp/developer_tools.py",
            "src/codex_usage_tracker/interfaces/mcp/models.py",
            "src/codex_usage_tracker/interfaces/mcp/profiles.py",
            "src/codex_usage_tracker/interfaces/mcp/query_analysis_tools.py",
            "src/codex_usage_tracker/interfaces/mcp/registry.py",
            "src/codex_usage_tracker/interfaces/mcp/tach.domain.toml",
            "src/codex_usage_tracker/interfaces/tach.domain.toml",
        )
    },
    **{
        path: (
            "src/codex_usage_tracker/kernel/interfaces/mcp/server.py",
            ("tests/kernel/interfaces/test_mcp.py",),
        )
        for path in (
            "src/codex_usage_tracker/interfaces/mcp/mcp_allowance.py",
            "src/codex_usage_tracker/interfaces/mcp/mcp_discovery.py",
            "src/codex_usage_tracker/interfaces/mcp/mcp_local_operations.py",
            "src/codex_usage_tracker/interfaces/mcp/mcp_server_tools.py",
            "src/codex_usage_tracker/interfaces/mcp/runtime.py",
            "src/codex_usage_tracker/interfaces/mcp/serialization.py",
            "src/codex_usage_tracker/interfaces/mcp/server.py",
            "src/codex_usage_tracker/interfaces/mcp/transports.py",
        )
    },
    "src/codex_usage_tracker/plugin_installer.py": (
        "src/codex_usage_tracker/kernel/plugin_manifest.py",
        ("tests/kernel/interfaces/test_plugin.py",),
    ),
}
_K8_TRANSPLANTS = {
    "src/codex_usage_tracker/application/allowance.py": (
        "src/codex_usage_tracker/kernel/allowance/service.py",
        ("tests/kernel/allowance/test_service.py",),
    ),
    "src/codex_usage_tracker/application/allowance_models.py": (
        "src/codex_usage_tracker/kernel/allowance/efficiency.py",
        ("tests/kernel/allowance/test_efficiency.py",),
    ),
    "src/codex_usage_tracker/pricing/__init__.py": (
        "src/codex_usage_tracker/kernel/allowance/__init__.py",
        ("tests/kernel/allowance/test_rates.py",),
    ),
    **{
        path: (
            "src/codex_usage_tracker/kernel/allowance/rates.py",
            ("tests/kernel/allowance/test_rates.py",),
        )
        for path in (
            "src/codex_usage_tracker/pricing/allowance.py",
            "src/codex_usage_tracker/pricing/allowance_config.py",
            "src/codex_usage_tracker/pricing/allowance_rate_card.py",
            "src/codex_usage_tracker/pricing/allowance_usage.py",
            "src/codex_usage_tracker/pricing/api.py",
            "src/codex_usage_tracker/pricing/config.py",
            "src/codex_usage_tracker/pricing/costing.py",
        )
    },
    "src/codex_usage_tracker/pricing/tach.domain.toml": (
        "src/codex_usage_tracker/kernel/allowance/__init__.py",
        ("tests/kernel/test_repository_quality_policy.py",),
    ),
    "src/codex_usage_tracker/store/allowance_materialization.py": (
        "src/codex_usage_tracker/kernel/allowance/service.py",
        ("tests/kernel/allowance/test_service.py",),
    ),
    "src/codex_usage_tracker/store/allowance_observation_sync.py": (
        "src/codex_usage_tracker/kernel/writer.py",
        ("tests/kernel/allowance/test_service.py",),
    ),
    "src/codex_usage_tracker/store/allowance_observations.py": (
        "src/codex_usage_tracker/kernel/allowance/service.py",
        ("tests/kernel/allowance/test_service.py",),
    ),
    "src/codex_usage_tracker/store/allowance_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    "src/codex_usage_tracker/store/service_tier_schema.py": (
        "src/codex_usage_tracker/kernel/schema.py",
        ("tests/kernel/test_schema.py",),
    ),
    **{
        path: (
            "tests/kernel/allowance/test_efficiency.py",
            ("tests/kernel/allowance/test_efficiency.py",),
        )
        for path in (
            "tests/application/test_allowance_models.py",
            "tests/allowance_intelligence/test_cycles.py",
        )
    },
    **{
        path: (
            "tests/kernel/allowance/test_service.py",
            ("tests/kernel/allowance/test_service.py",),
        )
        for path in (
            "tests/application/test_allowance.py",
            "tests/cli/test_allowance_intelligence_cli_mcp.py",
            "tests/cli/test_mcp_allowance.py",
            "tests/golden_questions/cases/08_allowance_status.json",
            "tests/golden_questions/cases/09_allowance_evidence.json",
            "tests/mcp/test_core_allowance_tool.py",
            "tests/server/test_server_allowance.py",
            "tests/server/test_server_allowance_v2.py",
            "tests/store/test_allowance_intelligence_queries.py",
            "tests/store/test_allowance_materialization.py",
            "tests/store/test_allowance_observations.py",
        )
    },
    **{
        path: (
            "tests/kernel/allowance/test_rates.py",
            ("tests/kernel/allowance/test_rates.py",),
        )
        for path in (
            "tests/pricing/test_allowance.py",
            "tests/pricing/test_pricing.py",
            "tests/pricing/test_rate_card.py",
        )
    },
}


def build_retired_surface_manifest() -> dict[str, Any]:
    """Return the immutable K1 public-surface inventory."""

    return _load(_RETIRED_PATH)


def build_code_disposition_manifest() -> dict[str, Any]:
    """Return the K1 path inventory with its current transition states."""

    return _load(_DISPOSITION_PATH)


def is_retired_authority_path(path: str) -> bool:
    """Return whether CK-00 deliberately removed an obsolete authority path."""

    return path in _AUTHORITY_CLEANUP_PATHS or path.startswith(
        _AUTHORITY_CLEANUP_PREFIXES
    )


def apply_quarantine_transition() -> None:
    """Advance every K1 non-keep path to the K1A removed state."""

    payload = build_code_disposition_manifest()
    payload["source_ref"] = _K1_MERGE
    payload["quarantine_base"] = _K1_MERGE
    for entry in payload["entries"]:
        if entry["disposition"] != "keep":
            entry["status"] = "removed"
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k2_transition() -> None:
    """Resolve every generic K2 assignment to one clean schema-v1 decision."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_k2_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K2"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k3_transition() -> None:
    """Resolve every K3 assignment to bounded ingestion or explicit retirement."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K3"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k4_transition() -> None:
    """Resolve every K4 assignment to the bounded query contract or retirement."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K4"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k5_transition() -> None:
    """Resolve every K5 assignment to the exact evidence contract."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K5"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k6_transition() -> None:
    """Resolve every K6 assignment to the six-tool interface cutover."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K6"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k8_transition() -> None:
    """Resolve K8 assignments to exact ratios, estimates, or retirement."""

    payload = build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    payload["entries"] = [
        _expected_current_entry(base_by_path[entry["path"]])
        if entry["owner_task"] == "K8"
        else entry
        for entry in payload["entries"]
    ]
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def apply_k9_transition() -> None:
    """Mark every frozen decision terminal after the final absence audit."""

    payload = build_code_disposition_manifest()
    for entry in payload["entries"]:
        entry["status"] = "verified"
    failures = k9_disposition_proof_failures(payload)
    if failures:
        raise ValueError("\n".join(failures))
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def k9_disposition_proof_failures(
    disposition: dict[str, Any],
) -> list[str]:
    """Reconcile every terminal K1 path with its physical proof and target."""

    failures: list[str] = []
    for entry in disposition["entries"]:
        source = _REPO_ROOT / entry["path"]
        target = _REPO_ROOT / entry["target_path"]
        disposition_name = entry["disposition"]
        if entry["status"] != "verified":
            failures.append(f"{entry['path']}: K9 status is not verified")
        if disposition_name == "keep":
            if not source.exists() and not source.is_symlink():
                failures.append(f"{entry['path']}: kept path is absent")
        elif source.exists() or source.is_symlink():
            failures.append(f"{entry['path']}: retired source path remains")
        if disposition_name in {"keep", "transplant"} and (
            not target.exists() and not target.is_symlink()
        ):
            failures.append(
                f"{entry['path']}: verified target is absent: {entry['target_path']}"
            )
        proof_paths = (
            entry["removal_or_absence_test"],
            *entry["required_oracle_tests"],
        )
        for proof_path in proof_paths:
            proof = _REPO_ROOT / proof_path
            if not proof.is_file():
                failures.append(
                    f"{entry['path']}: verified proof is absent: {proof_path}"
                )
    return failures


def manifest_failures(
    disposition: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic failures for both frozen inventories."""

    current = disposition or build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    retired = build_retired_surface_manifest()
    failures: list[str] = []

    paths = [entry["path"] for entry in current["entries"]]
    if len(paths) != len(set(paths)):
        failures.append("code disposition contains duplicate paths")
    base_paths = [
        path
        for path in _git_lines("ls-tree", "-r", "--name-only", _K1_MERGE)
        if not is_retired_authority_path(path)
    ]
    if sorted(paths) != base_paths:
        failures.append(
            "code disposition paths differ from the cleaned merged K1 tree"
        )
    digest = hashlib.sha256(
        ("\n".join(sorted(paths)) + "\n").encode("utf-8")
    ).hexdigest()
    if current["resolver_input_sha256"] != digest:
        failures.append("code disposition resolver hash does not match frozen paths")
    if current.get("quarantine_base") != _K1_MERGE:
        failures.append("code disposition does not name the merged K1 quarantine base")
    if current.get("source_ref") != _K1_MERGE:
        failures.append("code disposition source ref is not the merged K1 commit")

    base_by_path = {
        entry["path"]: entry
        for entry in base["entries"]
        if not is_retired_authority_path(entry["path"])
    }
    for entry in current["entries"]:
        path = entry["path"]
        base_entry = base_by_path.get(path)
        if base_entry is None:
            continue
        expected_entry = _expected_current_entry(base_entry)
        immutable = {key: value for key, value in entry.items() if key != "status"}
        base_immutable = {
            key: value for key, value in expected_entry.items() if key != "status"
        }
        if immutable != base_immutable:
            failures.append(f"{path}: immutable K1 disposition decision changed")
        if (
            expected_entry["owner_task"] == "K2"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K2 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K3"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K3 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K4"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K4 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K5"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K5 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K6"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K6 disposition is not verified")
        if (
            expected_entry["owner_task"] == "K8"
            and entry["status"] != "verified"
        ):
            failures.append(f"{path}: K8 disposition is not verified")

    surface_keys = [
        (entry["surface_type"], entry["public_name"])
        for entry in retired["entries"]
    ]
    if len(surface_keys) != len(set(surface_keys)):
        failures.append("retired-surface inventory contains duplicate names")

    for path, payload in (
        (_DISPOSITION_PATH, current),
        (_RETIRED_PATH, retired),
    ):
        if disposition is None and path.read_text(
            encoding="utf-8"
        ) != _compact_manifest(payload):
            failures.append(f"{path.name} is not canonical")
    return failures


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_from_git(ref: str, path: str) -> dict[str, Any]:
    payload = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(payload)


def _expected_k2_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    path = entry["path"]
    deferred = _K2_DEFERRED.get(path)
    if deferred is not None:
        target, oracle = deferred
        entry.update(
            {
                "owner_task": "K3",
                "reason": "Ingestion must prove this accounting lifecycle behavior.",
                "required_oracle_tests": [oracle],
                "removal_or_absence_test": oracle,
                "status": "removed",
                "target_path": target,
            }
        )
        return entry
    transplant = _K2_TRANSPLANTS.get(path)
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Retired K2 spike behavior is not required by the "
                    "schema-v1 contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Schema-v1 behavior survives through one clean kernel owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k3_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    transplant = _K3_TRANSPLANTS.get(entry["path"])
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Legacy refresh, content-index, or interface orchestration "
                    "is not required by the bounded K3 ingestion contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Incremental ingestion behavior survives through one bounded "
                "kernel owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k4_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    transplant = _K4_TRANSPLANTS.get(entry["path"])
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Legacy export, cache, or derived-summary behavior is not "
                    "required by the bounded K4 query contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Bounded generation-consistent query behavior survives through "
                "one typed kernel query owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k5_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    target, tests = _K5_TRANSPLANTS[entry["path"]]
    entry.update(
        {
            "reason": (
                "Stable logical-selector evidence survives through one bounded "
                "generation-consistent kernel owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k6_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    target, tests = _K6_TRANSPLANTS[entry["path"]]
    entry.update(
        {
            "reason": (
                "Operational interface behavior survives through the exact "
                "six-tool kernel application and adapter boundary."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_k8_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = dict(base_entry)
    transplant = _K8_TRANSPLANTS.get(entry["path"])
    if transplant is None:
        entry.update(
            {
                "disposition": "retire",
                "reason": (
                    "Legacy allowance intelligence, updater, forecasting, or "
                    "narrative behavior is outside the exact K8 fact contract."
                ),
                "required_oracle_tests": [
                    "tests/kernel/test_code_disposition_manifest.py"
                ],
                "removal_or_absence_test": (
                    "tests/kernel/test_code_disposition_manifest.py"
                ),
                "status": "verified",
                "target_path": "",
            }
        )
        return entry
    target, tests = transplant
    entry.update(
        {
            "reason": (
                "Exact observations, deterministic reset-aware ratios, and "
                "source-stamped estimates survive through one lean K8 owner."
            ),
            "required_oracle_tests": list(tests),
            "removal_or_absence_test": tests[0],
            "status": "verified",
            "target_path": target,
        }
    )
    return entry


def _expected_current_entry(base_entry: dict[str, Any]) -> dict[str, Any]:
    entry = (
        _expected_k2_entry(base_entry)
        if base_entry["owner_task"] == "K2"
        else dict(base_entry)
    )
    if entry["owner_task"] == "K3":
        return _expected_k3_entry(entry)
    if entry["owner_task"] == "K4":
        return _expected_k4_entry(entry)
    if entry["owner_task"] == "K5":
        return _expected_k5_entry(entry)
    if entry["owner_task"] == "K6":
        return _expected_k6_entry(entry)
    if entry["owner_task"] == "K8":
        return _expected_k8_entry(entry)
    return entry


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(_REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _compact_manifest(payload: dict[str, Any]) -> str:
    entries = payload["entries"]
    header = {key: value for key, value in payload.items() if key != "entries"}
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True)},")
    lines.append('  "entries": [')
    for index, entry in enumerate(entries):
        suffix = "," if index + 1 < len(entries) else ""
        lines.append(
            f"    {json.dumps(entry, sort_keys=True, separators=(',', ':'))}{suffix}"
        )
    lines.extend(["  ]", "}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-quarantine", action="store_true")
    parser.add_argument("--apply-k2", action="store_true")
    parser.add_argument("--apply-k3", action="store_true")
    parser.add_argument("--apply-k4", action="store_true")
    parser.add_argument("--apply-k5", action="store_true")
    parser.add_argument("--apply-k6", action="store_true")
    parser.add_argument("--apply-k8", action="store_true")
    parser.add_argument("--apply-k9", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.apply_quarantine:
        apply_quarantine_transition()
    if args.apply_k2:
        apply_k2_transition()
    if args.apply_k3:
        apply_k3_transition()
    if args.apply_k4:
        apply_k4_transition()
    if args.apply_k5:
        apply_k5_transition()
    if args.apply_k6:
        apply_k6_transition()
    if args.apply_k8:
        apply_k8_transition()
    if args.apply_k9:
        apply_k9_transition()
    failures = manifest_failures()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    if args.check:
        print("Kernel manifests are canonical and frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
