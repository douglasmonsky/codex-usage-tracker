"""Executable recursive-closure checks for the CK-08R1C test lane."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


class ClosureError(ValueError):
    """The declared evaluator closure cannot be trusted."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _manifest_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_import(module: str, imported: str | None, level: int, source: Path, root: Path) -> Path | None:
    if level:
        package = _module_name(source, root).split(".")
        if source.name != "__init__.py":
            package.pop()
        if level > len(package):
            return None
        package = package[: len(package) - level + 1]
        parts = package + ([module] if module else [])
    else:
        parts = module.split(".") if module else []
    if not parts or parts[0] not in {"tests", "codex_usage_tracker"}:
        return None
    candidate = root.joinpath(*parts)
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if candidate.is_dir() and (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _local_imports(path: Path, root: Path) -> tuple[set[Path], set[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ClosureError(f"cannot inspect {path}") from exc
    paths: set[Path] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                resolved = _resolve_import(alias.name, None, 0, path, root)
                if resolved is not None:
                    paths.add(resolved)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            dotted = "." * node.level + module
            modules.add(dotted)
            resolved = _resolve_import(module, None, node.level, path, root)
            if resolved is not None:
                paths.add(resolved)
            if resolved is not None:
                for alias in node.names:
                    child = resolved.parent / alias.name
                    if child.with_suffix(".py").is_file():
                        paths.add(child.with_suffix(".py"))
                    elif child.is_dir() and (child / "__init__.py").is_file():
                        paths.add(child / "__init__.py")
    return paths, modules


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def compute_closure(
    *,
    harness: Path,
    consumer: Path,
    root: Path,
    harness_role: str = "harness",
    consumer_role: str = "consumer",
) -> dict[str, Any]:
    """Recompute roots, recursive local imports, exact digests, and digest."""

    roots = [(harness, harness_role), (consumer, consumer_role)]
    visited: set[Path] = set()
    pending = [path.resolve() for path, _ in roots]
    modules: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        if not path.is_file():
            raise ClosureError(f"closure file is inaccessible: {path}")
        visited.add(path)
        imports, imported_modules = _local_imports(path, root.resolve())
        modules.update(imported_modules)
        pending.extend(imports - visited)

    root_paths = {path.resolve() for path, _ in roots}
    import_paths = sorted(visited - root_paths, key=lambda item: _relative(item, root.resolve()))
    root_records = [
        {"path": _relative(path.resolve(), root.resolve()), "role": role, "sha256": _digest(path.resolve())}
        for path, role in sorted(roots, key=lambda item: _relative(item[0].resolve(), root.resolve()))
    ]
    import_records = [
        {"path": _relative(path, root.resolve()), "sha256": _digest(path)} for path in import_paths
    ]
    payload = {
        "consumer": _relative(consumer.resolve(), root.resolve()),
        "harness": _relative(harness.resolve(), root.resolve()),
        "imports": import_records,
        "roots": root_records,
    }
    return {**payload, "closure_digest": _manifest_digest(payload), "imported_modules": sorted(modules)}


def verify_closure(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    forbidden_modules: Iterable[str] = (),
    forbidden_roles: Iterable[str] = (),
) -> dict[str, Any]:
    """Fail closed on missing files, drift, unlisted imports, or forbidden roles."""

    required = {"consumer", "harness", "imports", "roots", "closure_digest"}
    if not required.issubset(manifest):
        raise ClosureError("closure manifest is incomplete")
    root_path = root.resolve()
    roots = manifest["roots"]
    if not isinstance(roots, list) or len(roots) != 2:
        raise ClosureError("closure requires exactly two roots")
    root_by_role: dict[str, Path] = {}
    for record in roots:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise ClosureError("closure root is malformed")
        role = record.get("role")
        if role in set(forbidden_roles):
            raise ClosureError("forbidden closure role")
        path = root_path / record["path"]
        if not path.is_file():
            raise ClosureError(f"closure root is inaccessible: {record['path']}")
        if record.get("sha256") != _digest(path):
            raise ClosureError(f"closure root drift: {record['path']}")
        root_by_role[str(role)] = path
    if "harness" not in root_by_role or "consumer" not in root_by_role:
        raise ClosureError("closure root roles are incomplete")

    imports = manifest["imports"]
    if not isinstance(imports, list):
        raise ClosureError("closure imports are malformed")
    listed_paths: dict[str, Mapping[str, Any]] = {}
    for record in imports:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise ClosureError("closure import is malformed")
        path = root_path / record["path"]
        if not path.is_file():
            raise ClosureError(f"closure import is inaccessible: {record['path']}")
        if record.get("sha256") != _digest(path):
            raise ClosureError(f"closure import drift: {record['path']}")
        listed_paths[record["path"]] = record

    actual = compute_closure(harness=root_by_role["harness"], consumer=root_by_role["consumer"], root=root_path)
    actual_paths = {record["path"] for record in actual["roots"] + actual["imports"]}
    listed_paths_all = {record["path"] for record in roots} | set(listed_paths)
    if actual_paths != listed_paths_all:
        raise ClosureError("closure membership drift or unlisted local import")
    modules = set(actual.get("imported_modules", []))
    for forbidden in forbidden_modules:
        if any(module == forbidden or module.startswith(f"{forbidden}.") for module in modules):
            raise ClosureError(f"forbidden dependency in closure: {forbidden}")
    expected_payload = {key: actual[key] for key in ("consumer", "harness", "imports", "roots")}
    if manifest.get("closure_digest") != _manifest_digest(expected_payload):
        raise ClosureError("closure digest drift")
    return {
        "membership_recomputed": True,
        "digests_recomputed": True,
        "all_files_accessible": True,
        "forbidden_dependencies_absent": True,
        "passed_before_grading": True,
        "closure_digest": actual["closure_digest"],
    }
