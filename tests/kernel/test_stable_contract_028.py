from __future__ import annotations

import hashlib
import json
from pathlib import Path

from codex_usage_tracker.kernel.application.runtime import default_runtime_paths
from codex_usage_tracker.kernel.content import CONTENT_SCHEMA_VERSION
from codex_usage_tracker.kernel.evidence.contracts import (
    _SELECTOR_KINDS,
    EvidenceView,
)
from codex_usage_tracker.kernel.interfaces.cli.main import COMMANDS
from codex_usage_tracker.kernel.interfaces.http.app import API_PREFIX, ROUTES
from codex_usage_tracker.kernel.interfaces.mcp.catalog import TOOL_SPECS
from codex_usage_tracker.kernel.live.journal import (
    _EVENT_KINDS,
    _SAFE_PAYLOAD_KEYS,
)
from codex_usage_tracker.kernel.operational import (
    OPERATIONAL_SCHEMA_VERSION,
    kernel_paths,
)
from codex_usage_tracker.kernel.schema import SCHEMA_VERSION

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT_PATH = _ROOT / "config/kernel-stable-contract-v1.json"
_REFERENCE_PATH = (
    _ROOT / "docs/archive/spike/KERNEL_STABLE_CONTRACT_0_28.md"
)
_VERSION = "0.28.0"


def test_028_stable_contract_freezes_exact_public_surface() -> None:
    contract = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    runtime = default_runtime_paths(
        {"CODEX_HOME": "/synthetic/codex-home"}
    )
    paths = kernel_paths(Path("/synthetic/cache"))

    assert contract["schema"] == "codex-usage-tracker.kernel-stable-contract.v1"
    assert contract["version"] == _VERSION
    assert contract["stability"] == "frozen_pre_1_0"
    assert contract["breaking_change_policy"] == "approved_roadmap_amendment"
    assert [item["name"] for item in contract["mcp_tools"]] == [
        spec.name for spec in TOOL_SPECS
    ]
    assert {
        item["name"]: item["input_schema_sha256"]
        for item in contract["mcp_tools"]
    } == {
        spec.name: hashlib.sha256(
            json.dumps(
                spec.input_schema,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for spec in TOOL_SPECS
    }
    assert contract["http"]["api_prefix"] == API_PREFIX
    assert {
        (item["method"], item["route"]) for item in contract["http"]["routes"]
    } == set(ROUTES)
    assert contract["http"]["sse"] == {
        "event_kinds": sorted(_EVENT_KINDS),
        "generation_payload_keys": sorted(_SAFE_PAYLOAD_KEYS),
        "snapshot_event": "snapshot_required",
        "heartbeat": "comment",
    }
    assert contract["cli"] == {
        "commands": list(COMMANDS),
        "machine_output": "json",
        "export_formats": ["json"],
        "unsupported_export_formats": ["csv"],
    }
    assert contract["evidence"] == {
        "selector_kinds": sorted(_SELECTOR_KINDS),
        "views": [view.value for view in EvidenceView],
        "destination": "/evidence/{url_encoded_selector}?view={view}",
        "identity": "logical_not_row_id",
    }
    assert contract["storage"] == {
        "default_cache_root_suffix": str(
            runtime.cache_root.relative_to(runtime.codex_home)
        ),
        "analytical_filename": paths.analytical.name,
        "operational_filename": paths.operational.name,
        "content_filename": "codex-usage-content-v1.sqlite3",
        "analytical_schema_version": SCHEMA_VERSION,
        "operational_schema_version": OPERATIONAL_SCHEMA_VERSION,
        "content_schema_version": CONTENT_SCHEMA_VERSION,
        "upgrade_behavior": "side_by_side_atomic_promotion",
        "rollback_behavior": "preserve_prior_published_generation",
    }
    assert contract["calculations"] == {
        "grades": ["exact", "deterministic", "estimated"],
        "model_inference_location": "consumer_only",
        "token_classes": [
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        ],
    }


def test_028_contract_freezes_privacy_installation_and_experiments() -> None:
    contract = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["privacy"] == {
        "local_only": True,
        "raw_content_default": "disabled",
        "content_store": "owner_only_separable_deletable",
        "operational_registry_exportable": False,
        "synthetic_release_fixtures_only": True,
    }
    assert contract["installation"] == {
        "distribution": "codex-usage-tracking",
        "cli": "codex-usage-tracker",
        "plugin": "codex-usage-tracker",
        "mcp_server": "codex-usage-tracker",
        "same_version_bundle_install": "atomic_replace",
        "supported_upgrade_from": ["0.26.0", "0.27.0"],
    }
    assert contract["experimental_capabilities"] == {
        "context_composition": "optional_not_stable",
        "overlay_adapter": "contract_only_not_runtime",
    }
    assert contract["one_point_zero_readiness"] == {
        "decision": "defer_until_post_freeze_dogfood",
        "stable_surface_ready": True,
        "feature_work_in_0_28": False,
    }


def test_028_reference_publishes_every_required_operational_contract() -> None:
    reference = _REFERENCE_PATH.read_text(encoding="utf-8")

    for heading in (
        "## Stable Surface",
        "## Operations",
        "## Recovery",
        "## Privacy",
        "## Query",
        "## Evidence",
        "## Installation and Upgrade",
        "## Export",
        "## Experimental Capabilities",
        "## 1.0 Readiness Decision",
    ):
        assert heading in reference
    assert "config/kernel-stable-contract-v1.json" in reference
    assert "approved roadmap amendment" in reference.lower()
