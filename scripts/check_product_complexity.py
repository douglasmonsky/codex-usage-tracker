#!/usr/bin/env python3
"""Measure and enforce deterministic product-complexity budgets."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter
from fnmatch import fnmatchcase
from importlib import import_module
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parent

METRIC_NAMES = (
    "default_mcp_tools",
    "full_profile_mcp_tools",
    "stable_cli_top_level_commands",
    "primary_dashboard_routes",
    "shell_utility_dashboard_routes",
    "contextual_dashboard_routes",
    "unbudgeted_python_files_over_600",
    "unbudgeted_frontend_source_files_over_500",
    "wheel_bytes",
    "sdist_bytes",
    "main_initial_react_js_gzip_bytes",
    "stable_json_schemas",
    "sqlite_schema_increments",
)

_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SCRIPT_REFERENCE_PATTERN = re.compile(r'(?:src|href)="[^"]*/(assets/[^"?]+)(?:\?[^"\s]*)?"')


class BudgetError(ValueError):
    """Raised when a budget or measurement source is incomplete or ambiguous."""


def load_budget(path: Path) -> dict[str, Any]:
    """Load and validate one versioned product-complexity budget."""
    payload = _read_budget_object(path)
    _validate_budget_header(payload)
    _validate_metrics(payload.get("metrics"))
    _validate_measurement_config(payload)
    return payload


def _read_budget_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BudgetError(f"could not load budget {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BudgetError("budget root must be an object")
    return payload


def _validate_budget_header(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise BudgetError("budget schema_version must equal 1")
    _validate_baseline(payload.get("baseline"))
    if not isinstance(payload.get("increase_policy"), str) or not payload["increase_policy"]:
        raise BudgetError("budget increase_policy must be a non-empty string")


def _validate_metrics(metrics: object) -> None:
    if not isinstance(metrics, dict):
        raise BudgetError("budget metrics must be an object")
    missing = [name for name in METRIC_NAMES if name not in metrics]
    extras = sorted(set(metrics) - set(METRIC_NAMES))
    if missing:
        raise BudgetError(f"budget is missing metric {missing[0]}")
    if extras:
        raise BudgetError(f"budget has unknown metrics: {', '.join(extras)}")
    for name in METRIC_NAMES:
        _validate_metric(name, metrics[name])


def _validate_baseline(value: object) -> None:
    if not isinstance(value, dict):
        raise BudgetError("budget baseline must be an object")
    for key in ("release", "measurement_command", "rationale"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise BudgetError(f"budget baseline {key} must be a non-empty string")
    if not isinstance(value.get("commit"), str) or not _SHA_PATTERN.fullmatch(value["commit"]):
        raise BudgetError("budget baseline commit must be a full lowercase Git SHA")


def _validate_metric(name: str, value: object) -> None:
    if not isinstance(value, dict):
        raise BudgetError(f"{name} budget must be an object")
    for key in ("maximum", "baseline"):
        if not isinstance(value.get(key), int) or value[key] < 0:
            raise BudgetError(f"{name} {key} must be a non-negative integer")
    commit = value.get("baseline_commit")
    if not isinstance(commit, str) or not _SHA_PATTERN.fullmatch(commit):
        raise BudgetError(f"{name} baseline_commit must be a full lowercase Git SHA")
    if not isinstance(value.get("rationale"), str) or not value["rationale"]:
        raise BudgetError(f"{name} rationale must be a non-empty string")


def _validate_measurement_config(payload: dict[str, Any]) -> None:
    _validate_source_files(payload.get("source_files"))
    _validate_dashboard_routes(payload.get("dashboard_routes"))
    _validate_dashboard_bundle(payload.get("dashboard_bundle"))
    _validate_sqlite_schema(payload.get("sqlite_schema"))


def _validate_source_files(value: object) -> None:
    if not isinstance(value, dict):
        raise BudgetError("source_files must be an object")
    for name in ("python", "frontend"):
        config = value.get(name)
        if not isinstance(config, dict):
            raise BudgetError(f"source_files.{name} must be an object")
        _validate_source_file(name, config)


def _validate_source_file(name: str, config: dict[str, Any]) -> None:
    context = f"source_files.{name}"
    _require_string_list(config, "roots", context)
    _require_string_list(config, "extensions", context)
    _require_string_list(config, "exclude_globs", context, allow_empty=True)
    _require_non_negative_integer(
        config.get("maximum_physical_lines"),
        f"{context}.maximum_physical_lines",
    )
    _validate_grandfathered(config.get("grandfathered"), context)


def _require_non_negative_integer(value: object, context: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BudgetError(f"{context} must be a non-negative integer")


def _validate_grandfathered(grandfathered: object, context: str) -> None:
    if not isinstance(grandfathered, dict):
        raise BudgetError(f"{context}.grandfathered must map paths to lines")
    invalid = [
        path
        for path, lines in grandfathered.items()
        if not isinstance(path, str)
        or not isinstance(lines, int)
        or isinstance(lines, bool)
        or lines <= 0
    ]
    if invalid:
        raise BudgetError(f"{context}.grandfathered must map paths to lines")


def _validate_dashboard_routes(value: object) -> None:
    if not isinstance(value, dict) or not all(
        isinstance(value.get(key), str) and value[key] for key in ("catalog", "const")
    ):
        raise BudgetError("dashboard_routes must declare catalog and const")


def _validate_dashboard_bundle(value: object) -> None:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("output_dir"), str)
        or not value["output_dir"]
    ):
        raise BudgetError("dashboard_bundle must declare output_dir")


def _validate_sqlite_schema(value: object) -> None:
    if not isinstance(value, dict) or not all(
        isinstance(value.get(key), int) and not isinstance(value[key], bool) and value[key] >= 0
        for key in ("release_023_version", "budget_adoption_version")
    ):
        raise BudgetError(
            "sqlite_schema must declare non-negative integer release and adoption versions"
        )
    if value["budget_adoption_version"] < value["release_023_version"]:
        raise BudgetError("SQLite budget adoption version predates the release baseline")


def _require_string_list(
    config: dict[str, Any],
    key: str,
    context: str,
    *,
    allow_empty: bool = False,
) -> None:
    value = config.get(key)
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise BudgetError(f"{context}.{key} must be a list of non-empty strings")


def evaluate_budget(
    budget: dict[str, Any],
    measurements: dict[str, int],
) -> list[str]:
    """Return stable failure messages for measurements above their ceilings."""
    metrics = budget["metrics"]
    failures: list[str] = []
    for name in METRIC_NAMES:
        if name not in measurements:
            continue
        value = measurements[name]
        if not isinstance(value, int) or value < 0:
            raise BudgetError(f"{name} measurement must be a non-negative integer")
        maximum = metrics[name]["maximum"]
        if value > maximum:
            failures.append(f"{name}={value} exceeds maximum {maximum}")
    return failures


def parse_route_placements(source: str, const_name: str) -> dict[str, int]:
    """Count placements from one named TypeScript route-catalog array."""
    array_source = _extract_typescript_array(source, const_name)
    objects = _top_level_typescript_objects(array_source, const_name)
    if not objects:
        raise BudgetError(f"{const_name} contains no route objects")
    placements: Counter[str] = Counter()
    route_ids: set[str] = set()
    for route in objects:
        if any(marker in route for marker in ("//", "/*", "*/", "...")):
            raise BudgetError(f"{const_name} route entries must not use comments or spreads")
        route_ids_found = re.findall(
            r"^    id: '([^'\n]+)',$",
            route,
            flags=re.MULTILINE,
        )
        placements_found = re.findall(
            r"^    placement: '(primary|contextual|utility)',$",
            route,
            flags=re.MULTILINE,
        )
        if len(route_ids_found) != 1:
            raise BudgetError(f"{const_name} route must have exactly one literal id")
        if len(placements_found) != 1:
            raise BudgetError(
                f"{const_name} route {route_ids_found[0]} "
                "must have exactly one literal known placement"
            )
        route_id = route_ids_found[0]
        if route_id in route_ids:
            raise BudgetError(f"{const_name} contains duplicate route id {route_id}")
        route_ids.add(route_id)
        placements[placements_found[0]] += 1
    return {
        "primary": placements["primary"],
        "contextual": placements["contextual"],
        "utility": placements["utility"],
    }


def _extract_typescript_array(source: str, const_name: str) -> str:
    declaration_pattern = re.compile(
        rf"^[ \t]*(?:export[ \t]+)?const[ \t]+{re.escape(const_name)}"
        rf"[ \t]*=[ \t]*\[(?P<body>.*?)^[ \t]*\][ \t]+as[ \t]+const"
        rf"(?:[ \t]+satisfies[^\n;]+)?[ \t]*;",
        flags=re.MULTILINE | re.DOTALL,
    )
    declarations = list(declaration_pattern.finditer(source))
    if len(declarations) != 1:
        raise BudgetError(f"expected exactly one literal TypeScript array const {const_name}")
    return declarations[0].group("body")


def _top_level_typescript_objects(
    array_source: str,
    const_name: str,
) -> list[str]:
    objects: list[str] = []
    current: list[str] | None = None
    for line_number, line in enumerate(array_source.splitlines(), start=1):
        if not line.strip():
            continue
        if current is None:
            if line != "  {":
                raise BudgetError(
                    f"{const_name} array entry at line {line_number} is not a literal route object"
                )
            current = []
            continue
        if line in {"  },", "  }"}:
            objects.append("\n".join(current))
            current = None
            continue
        current.append(line)
    if current is not None:
        raise BudgetError(f"{const_name} contains an unterminated route object")
    return objects


def _matches_exclusion(relative: str, pattern: str) -> bool:
    """Match normalized repository paths, including recursive directory globs."""
    if pattern.endswith("/**"):
        prefix = pattern.removesuffix("/**").rstrip("/")
        return relative == prefix or relative.startswith(f"{prefix}/")
    return fnmatchcase(relative, pattern)


def _iter_source_files(
    root: Path,
    configured_roots: list[str],
    extensions: set[str],
) -> list[Path]:
    paths: list[Path] = []
    for item in configured_roots:
        source_root = root / item
        if not source_root.is_dir():
            raise BudgetError(f"source root does not exist: {source_root}")
        paths.extend(
            path for path in source_root.rglob("*") if path.is_file() and path.suffix in extensions
        )
    return sorted(paths)


def _stale_grandfathered_paths(
    seen: dict[str, int],
    grandfathered: dict[str, int],
    maximum: int,
) -> list[str]:
    return sorted(
        path
        for path, frozen_lines in grandfathered.items()
        if path not in seen or seen[path] <= maximum or seen[path] < frozen_lines
    )


def measure_line_budget(root: Path, config: dict[str, Any]) -> list[str]:
    """Return sorted source paths that are new or have grown beyond frozen debt."""
    extensions = set(config["extensions"])
    excludes = tuple(config["exclude_globs"])
    maximum = int(config["maximum_physical_lines"])
    grandfathered = dict(config["grandfathered"])
    seen: dict[str, int] = {}
    violations: list[str] = []
    paths = _iter_source_files(root, config["roots"], extensions)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if any(_matches_exclusion(relative, pattern) for pattern in excludes):
            continue
        lines = len(path.read_bytes().splitlines())
        seen[relative] = lines
        frozen_limit = grandfathered.get(relative)
        if lines > maximum and (frozen_limit is None or lines > frozen_limit):
            violations.append(relative)
    stale = _stale_grandfathered_paths(seen, grandfathered, maximum)
    if stale:
        raise BudgetError("grandfathered source baseline is stale: " + ", ".join(stale))
    return sorted(violations)


def measure_distribution_sizes(dist_dir: Path) -> dict[str, int]:
    """Measure exactly one built wheel and one built source distribution."""
    if not dist_dir.is_dir():
        raise BudgetError(f"distribution directory does not exist: {dist_dir}")
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise BudgetError(f"expected exactly one wheel in {dist_dir}, found {len(wheels)}")
    if len(sdists) != 1:
        raise BudgetError(f"expected exactly one sdist in {dist_dir}, found {len(sdists)}")
    return {
        "wheel_bytes": wheels[0].stat().st_size,
        "sdist_bytes": sdists[0].stat().st_size,
    }


def measure_initial_javascript(output_dir: Path) -> int:
    """Return deterministic gzip bytes for JavaScript loaded by dashboard HTML."""
    try:
        html = (output_dir / "index.html").read_text(encoding="utf-8")
    except OSError as exc:
        raise BudgetError(f"could not read dashboard index: {exc}") from exc
    references = sorted(
        {
            match.group(1)
            for match in _SCRIPT_REFERENCE_PATTERN.finditer(html)
            if match.group(1).endswith(".js")
        }
    )
    if not references:
        raise BudgetError("dashboard index contains no initial JavaScript assets")
    total = 0
    for reference in references:
        path = (output_dir / reference).resolve()
        try:
            path.relative_to(output_dir.resolve())
        except ValueError as exc:
            raise BudgetError(f"dashboard asset escapes output directory: {reference}") from exc
        try:
            total += len(gzip.compress(path.read_bytes(), compresslevel=9, mtime=0))
        except OSError as exc:
            raise BudgetError(f"could not read dashboard asset {reference}: {exc}") from exc
    return total


def measure_product_complexity(
    root: Path,
    budget: dict[str, Any],
    *,
    dist_dir: Path | None = None,
) -> dict[str, int]:
    """Measure authoritative registries, authored source, bundles, and artifacts."""
    source_root = root / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

    # Keep the release checker as its own typed boundary instead of making its
    # focused MyPy target recursively analyze the complete runtime package.
    json_contracts = import_module("codex_usage_tracker.core.json_contracts")
    cli_parser = import_module("codex_usage_tracker.interfaces.cli.parser")
    mcp_profiles = import_module("codex_usage_tracker.interfaces.mcp.profiles")
    store_schema = import_module("codex_usage_tracker.store.schema")

    route_config = budget["dashboard_routes"]
    route_source = (root / route_config["catalog"]).read_text(encoding="utf-8")
    placements = parse_route_placements(route_source, route_config["const"])
    python_debt = measure_line_budget(root, budget["source_files"]["python"])
    frontend_debt = measure_line_budget(root, budget["source_files"]["frontend"])
    adoption_version = budget["sqlite_schema"]["budget_adoption_version"]
    schema_version = store_schema.SCHEMA_VERSION
    increments = schema_version - adoption_version
    if increments < 0:
        raise BudgetError(
            f"SQLite schema version {schema_version} predates budget adoption "
            f"version {adoption_version}"
        )
    measurements = {
        "default_mcp_tools": len(mcp_profiles.tools_for_profile("core")),
        "full_profile_mcp_tools": len(mcp_profiles.tools_for_profile("full")),
        "stable_cli_top_level_commands": len(cli_parser.STABLE_TOP_LEVEL_COMMANDS),
        "primary_dashboard_routes": placements["primary"],
        "shell_utility_dashboard_routes": placements["utility"],
        "contextual_dashboard_routes": placements["contextual"],
        "unbudgeted_python_files_over_600": len(python_debt),
        "unbudgeted_frontend_source_files_over_500": len(frontend_debt),
        "main_initial_react_js_gzip_bytes": measure_initial_javascript(
            root / budget["dashboard_bundle"]["output_dir"]
        ),
        "stable_json_schemas": len(json_contracts.known_json_schemas()),
        "sqlite_schema_increments": increments,
    }
    if dist_dir is not None:
        measurements.update(measure_distribution_sizes(dist_dir))
    return measurements


def check_product_complexity_budget(
    root: Path,
    config_path: Path,
    *,
    dist_dir: Path | None = None,
) -> list[str]:
    """Return release-checker-ready failures without hiding measurement errors."""
    try:
        budget = load_budget(config_path)
        measurements = measure_product_complexity(root, budget, dist_dir=dist_dir)
        return evaluate_budget(budget, measurements)
    except (BudgetError, OSError) as exc:
        return [f"could not be measured: {exc}"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/product-complexity-budget.json"),
    )
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _resolve_repo_path(path: Path | None) -> Path | None:
    if path is None or path.is_absolute():
        return path
    return REPO_ROOT / path


def _print_report(
    measurements: dict[str, int],
    failures: list[str],
    *,
    as_json: bool,
) -> None:
    if as_json:
        print(
            json.dumps(
                {
                    "status": "failed" if failures else "passed",
                    "measurements": measurements,
                    "failures": failures,
                },
                sort_keys=True,
            )
        )
        return
    for name in METRIC_NAMES:
        if name in measurements:
            print(f"{name}: {measurements[name]}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    if not failures:
        print("Product complexity budget passed.")


def main() -> int:
    args = _parse_args()
    try:
        config_path = _resolve_repo_path(args.config)
        if config_path is None:
            raise BudgetError("budget config path is required")
        budget = load_budget(config_path)
        dist_dir = _resolve_repo_path(args.dist)
        measurements = measure_product_complexity(REPO_ROOT, budget, dist_dir=dist_dir)
        failures = evaluate_budget(budget, measurements)
    except (BudgetError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    _print_report(measurements, failures, as_json=args.json)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
