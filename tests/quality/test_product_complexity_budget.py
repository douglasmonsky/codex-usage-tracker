from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from scripts.check_product_complexity import (
    METRIC_NAMES,
    BudgetError,
    evaluate_budget,
    load_budget,
    measure_distribution_sizes,
    measure_line_budget,
    measure_product_complexity,
    parse_route_placements,
)


def _budget_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "baseline": {
            "release": "0.23.0",
            "commit": "a" * 40,
            "measurement_command": "python scripts/check_product_complexity.py",
            "rationale": "Synthetic focused-test baseline.",
        },
        "increase_policy": "Architecture decision and changed test fixture required.",
        "metrics": {
            name: {
                "maximum": 1,
                "baseline": 1,
                "baseline_commit": "a" * 40,
                "rationale": f"Synthetic {name} ceiling.",
            }
            for name in METRIC_NAMES
        },
        "source_files": {
            "python": {
                "roots": ["src"],
                "extensions": [".py"],
                "exclude_globs": [],
                "maximum_physical_lines": 600,
                "grandfathered": {},
            },
            "frontend": {
                "roots": ["frontend"],
                "extensions": [".ts", ".tsx", ".css"],
                "exclude_globs": ["**/*.test.ts", "**/*.test.tsx"],
                "maximum_physical_lines": 500,
                "grandfathered": {},
            },
        },
        "dashboard_routes": {
            "catalog": "frontend/routes.ts",
            "const": "evidenceConsoleRoutes",
        },
        "dashboard_bundle": {
            "output_dir": "built-dashboard",
        },
        "sqlite_schema": {
            "release_023_version": 34,
            "budget_adoption_version": 37,
        },
    }


@pytest.mark.parametrize("metric", METRIC_NAMES)
def test_every_product_complexity_metric_blocks_above_its_ceiling(metric: str) -> None:
    payload = _budget_payload()
    measurements = dict.fromkeys(METRIC_NAMES, 1)
    measurements[metric] = 2

    failures = evaluate_budget(payload, measurements)

    assert failures == [f"{metric}=2 exceeds maximum 1"]


def test_budget_loader_requires_provenance_and_every_metric(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    payload = _budget_payload()
    del payload["baseline"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BudgetError, match="baseline"):
        load_budget(path)

    payload = _budget_payload()
    del payload["metrics"][METRIC_NAMES[0]]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BudgetError, match=METRIC_NAMES[0]):
        load_budget(path)


@pytest.mark.parametrize(
    ("source_kind", "key"),
    [
        ("python", "roots"),
        ("python", "extensions"),
        ("frontend", "roots"),
        ("frontend", "extensions"),
    ],
)
def test_budget_loader_rejects_empty_required_source_lists(
    tmp_path: Path,
    source_kind: str,
    key: str,
) -> None:
    payload = _budget_payload()
    payload["source_files"][source_kind][key] = []
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BudgetError, match=key):
        load_budget(path)


def test_route_catalog_parser_counts_only_the_named_structured_catalog() -> None:
    source = """
export const evidenceConsoleRoutes = [
  {
    id: 'home',
    placement: 'primary',
  },
  {
    id: 'evidence',
    placement: 'contextual',
  },
  {
    id: 'settings',
    placement: 'utility',
  },
] as const;
const unrelated = { placement: 'primary' };
"""

    assert parse_route_placements(source, "evidenceConsoleRoutes") == {
        "primary": 1,
        "contextual": 1,
        "utility": 1,
    }


def test_route_catalog_parser_fails_closed_on_missing_placement() -> None:
    source = """
export const evidenceConsoleRoutes = [
  {
    id: 'home',
  },
] as const;
"""

    with pytest.raises(BudgetError, match="placement"):
        parse_route_placements(source, "evidenceConsoleRoutes")


@pytest.mark.parametrize(
    "entry",
    [
        """  {
    id: 'home',
    // placement: 'primary',
  },""",
        """  {
    id: 'home',
    metadata: {
      placement: 'primary',
    },
  },""",
        """  {
    id: 'home',
    ...routeDefaults,
    placement: 'primary',
  },""",
        """  createRoute({
    id: 'home',
    placement: 'primary',
  }),""",
        """  {
    ['id']: 'home',
    placement: 'primary',
  },""",
    ],
)
def test_route_catalog_parser_rejects_nonliteral_or_decoy_entries(entry: str) -> None:
    source = f"""
export const evidenceConsoleRoutes = [
{entry}
] as const;
"""

    with pytest.raises(BudgetError, match="literal|comments|spreads"):
        parse_route_placements(source, "evidenceConsoleRoutes")


def test_line_budget_allows_frozen_debt_but_blocks_growth_and_new_debt(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    root.mkdir()
    frozen = root / "frozen.py"
    frozen.write_text("x = 1\n" * 4, encoding="utf-8")
    fresh = root / "fresh.py"
    fresh.write_text("x = 1\n" * 3, encoding="utf-8")
    config = {
        "roots": ["src"],
        "extensions": [".py"],
        "exclude_globs": [],
        "maximum_physical_lines": 3,
        "grandfathered": {"src/frozen.py": 4},
    }

    assert measure_line_budget(tmp_path, config) == []

    frozen.write_text("x = 1\n" * 5, encoding="utf-8")
    fresh.write_text("x = 1\n" * 4, encoding="utf-8")

    assert measure_line_budget(tmp_path, config) == [
        "src/fresh.py",
        "src/frozen.py",
    ]


def test_line_budget_excludes_nested_files_with_recursive_glob(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "plugin_data" / "nested" / "deeper"
    nested.mkdir(parents=True)
    (nested / "generated.py").write_text("x = 1\n" * 4, encoding="utf-8")
    config = {
        "roots": ["src"],
        "extensions": [".py"],
        "exclude_globs": ["src/plugin_data/**"],
        "maximum_physical_lines": 3,
        "grandfathered": {},
    }

    assert measure_line_budget(tmp_path, config) == []


def test_line_budget_requires_a_downward_ratchet_after_debt_shrinks(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    root.mkdir()
    frozen = root / "frozen.py"
    frozen.write_text("x = 1\n" * 4, encoding="utf-8")
    config = {
        "roots": ["src"],
        "extensions": [".py"],
        "exclude_globs": [],
        "maximum_physical_lines": 3,
        "grandfathered": {"src/frozen.py": 5},
    }

    with pytest.raises(BudgetError, match="baseline is stale"):
        measure_line_budget(tmp_path, config)


def test_distribution_measurement_requires_exactly_one_wheel_and_sdist(
    tmp_path: Path,
) -> None:
    (tmp_path / "package-0.24.0-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "package-0.24.0.tar.gz").write_bytes(b"source")

    assert measure_distribution_sizes(tmp_path) == {
        "wheel_bytes": 5,
        "sdist_bytes": 6,
    }

    (tmp_path / "duplicate-0.24.0-py3-none-any.whl").write_bytes(b"other")
    with pytest.raises(BudgetError, match="exactly one wheel"):
        measure_distribution_sizes(tmp_path)


def test_committed_product_complexity_budget_passes_source_measurement() -> None:
    root = Path(__file__).resolve().parents[2]
    budget = load_budget(root / "config/product-complexity-budget.json")
    measurements = measure_product_complexity(root, budget)

    assert set(measurements) == set(METRIC_NAMES) - {"wheel_bytes", "sdist_bytes"}
    assert evaluate_budget(budget, measurements) == []


def test_committed_budget_preserves_reviewed_baselines_and_exact_headroom() -> None:
    root = Path(__file__).resolve().parents[2]
    budget = load_budget(root / "config/product-complexity-budget.json")
    metrics = budget["metrics"]

    assert metrics["default_mcp_tools"]["maximum"] == 7
    assert metrics["full_profile_mcp_tools"]["maximum"] == 59
    assert metrics["stable_cli_top_level_commands"]["maximum"] == 11
    assert metrics["primary_dashboard_routes"]["maximum"] == 3
    assert metrics["shell_utility_dashboard_routes"]["maximum"] == 1
    assert metrics["contextual_dashboard_routes"]["maximum"] == 1
    assert metrics["unbudgeted_python_files_over_600"]["maximum"] == 0
    assert metrics["unbudgeted_frontend_source_files_over_500"]["maximum"] == 0
    assert metrics["wheel_bytes"]["baseline"] == 7_017_243
    assert metrics["wheel_bytes"]["maximum"] == math.ceil(7_017_243 * 1.05)
    assert metrics["sdist_bytes"]["baseline"] == 32_021_790
    assert metrics["sdist_bytes"]["maximum"] == math.ceil(32_021_790 * 1.05)
    assert metrics["main_initial_react_js_gzip_bytes"]["baseline"] == 61_457
    assert metrics["main_initial_react_js_gzip_bytes"]["maximum"] == math.ceil(61_457 * 1.10)
    assert metrics["stable_json_schemas"]["maximum"] == 114
    assert metrics["sqlite_schema_increments"]["maximum"] == 1
    assert budget["source_files"]["python"]["roots"] == ["src/codex_usage_tracker"]
    assert budget["source_files"]["python"]["extensions"] == [".py"]
    assert budget["source_files"]["python"]["exclude_globs"] == [
        "src/codex_usage_tracker/plugin_data/**"
    ]
    assert budget["source_files"]["python"]["maximum_physical_lines"] == 600
    assert budget["source_files"]["frontend"]["roots"] == ["frontend/dashboard/src"]
    assert budget["source_files"]["frontend"]["extensions"] == [".ts", ".tsx", ".css"]
    assert budget["source_files"]["frontend"]["exclude_globs"] == [
        "**/*.test.ts",
        "**/*.test.tsx",
    ]
    assert budget["source_files"]["frontend"]["maximum_physical_lines"] == 500
    assert budget["dashboard_routes"] == {
        "catalog": "frontend/dashboard/src/routes/evidenceConsoleRoutes.ts",
        "const": "evidenceConsoleRoutes",
    }
    assert budget["dashboard_bundle"] == {
        "output_dir": "src/codex_usage_tracker/plugin_data/dashboard/react"
    }
    assert budget["sqlite_schema"] == {
        "release_023_version": 34,
        "budget_adoption_version": 37,
    }
