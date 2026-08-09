"""Exact executable transitive-closure verification for CK-08R1 lanes."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


class ClosureError(ValueError):
    """A requalification lane closure is incomplete or untrustworthy."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _manifest_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _module_path(parts: Sequence[str], root: Path) -> Path | None:
    if not parts:
        return None
    if parts[0] == "codex_usage_tracker":
        candidate = root.joinpath("src", *parts)
    elif parts[0] in {"scripts", "tests"} or (
        parts[0] == "src" and len(parts) > 1 and parts[1] == "codex_usage_tracker"
    ):
        candidate = root.joinpath(*parts)
    else:
        return None
    module = candidate.with_suffix(".py")
    if module.is_file():
        return module
    package = candidate / "__init__.py"
    return package if package.is_file() else None


def _resolve_import(
    module: str,
    *,
    level: int,
    source: Path,
    root: Path,
) -> Path | None:
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
    return _module_path(parts, root)


def _local_imports(path: Path, root: Path) -> tuple[set[Path], set[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ClosureError(f"cannot inspect closure file: {path}") from exc

    paths: set[Path] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
                resolved = _resolve_import(
                    alias.name,
                    level=0,
                    source=path,
                    root=root,
                )
                if resolved is not None:
                    paths.add(resolved)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            modules.add("." * node.level + module)
            resolved = _resolve_import(
                module,
                level=node.level,
                source=path,
                root=root,
            )
            if resolved is not None:
                paths.add(resolved)
                for alias in node.names:
                    child = _module_path(
                        (*resolved.parent.relative_to(root).parts, alias.name),
                        root,
                    )
                    if child is not None:
                        paths.add(child)
    return paths, modules


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def compute_closure(
    *,
    roots: Sequence[tuple[Path, str]],
    root: Path,
) -> dict[str, Any]:
    """Recompute all roots, recursive local imports, and exact identities."""

    if len(roots) < 2:
        raise ClosureError("closure requires at least two roots")
    root_path = root.resolve()
    resolved_roots = [(path.resolve(), role) for path, role in roots]
    if len({role for _, role in resolved_roots}) != len(resolved_roots):
        raise ClosureError("closure root roles must be unique")
    root_by_role = {role: path for path, role in resolved_roots}
    if "consumer" not in root_by_role or "harness" not in root_by_role:
        raise ClosureError("closure requires consumer and harness roots")

    visited: set[Path] = set()
    pending = [path for path, _ in resolved_roots]
    modules: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate in visited:
            continue
        if not candidate.is_file():
            raise ClosureError(f"closure file is inaccessible: {candidate}")
        try:
            candidate.relative_to(root_path)
        except ValueError as exc:
            raise ClosureError("closure file is outside repository root") from exc
        visited.add(candidate)
        imports, imported_modules = _local_imports(candidate, root_path)
        modules.update(imported_modules)
        pending.extend(imports - visited)

    root_paths = {path for path, _ in resolved_roots}
    root_records = [
        {
            "path": _relative(path, root_path),
            "role": role,
            "sha256": _sha256(path),
        }
        for path, role in sorted(
            resolved_roots,
            key=lambda item: _relative(item[0], root_path),
        )
    ]
    import_records = [
        {"path": _relative(path, root_path), "sha256": _sha256(path)}
        for path in sorted(
            visited - root_paths,
            key=lambda item: _relative(item, root_path),
        )
    ]
    payload = {
        "consumer": _relative(root_by_role["consumer"], root_path),
        "harness": _relative(root_by_role["harness"], root_path),
        "imports": import_records,
        "roots": root_records,
    }
    return {
        **payload,
        "closure_digest": _manifest_digest(payload),
        "imported_modules": sorted(modules),
    }


def verify_closure(
    manifest: Mapping[str, Any],
    *,
    root: Path,
    required_roles: Iterable[str],
    forbidden_modules: Iterable[str] = (),
    forbidden_roles: Iterable[str] = (),
) -> dict[str, bool]:
    """Fail before grading on drift, inaccessibility, or membership mismatch."""

    required = {"consumer", "harness", "imports", "roots", "closure_digest"}
    if not required.issubset(manifest):
        raise ClosureError("closure manifest is incomplete")
    roots = manifest["roots"]
    imports = manifest["imports"]
    if not isinstance(roots, list) or len(roots) < 2:
        raise ClosureError("closure roots are malformed")
    if not isinstance(imports, list):
        raise ClosureError("closure imports are malformed")

    root_path = root.resolve()
    forbidden_role_set = set(forbidden_roles)
    resolved_roots: list[tuple[Path, str]] = []
    seen_roles: set[str] = set()
    for record in roots:
        if not isinstance(record, Mapping):
            raise ClosureError("closure root is malformed")
        relative = record.get("path")
        role = record.get("role")
        if not isinstance(relative, str) or not isinstance(role, str):
            raise ClosureError("closure root is malformed")
        if role in forbidden_role_set:
            raise ClosureError(f"forbidden closure role: {role}")
        if role in seen_roles:
            raise ClosureError("closure root roles must be unique")
        seen_roles.add(role)
        candidate = root_path / relative
        if not candidate.is_file():
            raise ClosureError(f"closure root is inaccessible: {relative}")
        if record.get("sha256") != _sha256(candidate):
            raise ClosureError(f"closure root drift: {relative}")
        resolved_roots.append((candidate, role))

    if not set(required_roles).issubset(seen_roles):
        raise ClosureError("closure root roles are incomplete")
    root_by_role = {role: _relative(path.resolve(), root_path) for path, role in resolved_roots}
    if manifest["consumer"] != root_by_role.get("consumer"):
        raise ClosureError("closure consumer root mismatch")
    if manifest["harness"] != root_by_role.get("harness"):
        raise ClosureError("closure harness root mismatch")

    for record in imports:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise ClosureError("closure import is malformed")
        relative = record["path"]
        candidate = root_path / relative
        if not candidate.is_file():
            raise ClosureError(f"closure import is inaccessible: {relative}")
        if record.get("sha256") != _sha256(candidate):
            raise ClosureError(f"closure import drift: {relative}")

    actual = compute_closure(roots=resolved_roots, root=root_path)
    expected_membership = {str(record["path"]) for record in (*roots, *imports)}
    actual_membership = {str(record["path"]) for record in (*actual["roots"], *actual["imports"])}
    if actual_membership != expected_membership:
        raise ClosureError("closure membership drift or unlisted local import")
    if manifest.get("closure_digest") != actual["closure_digest"]:
        raise ClosureError("closure digest drift")

    modules = set(actual["imported_modules"])
    for forbidden in forbidden_modules:
        if any(module == forbidden or module.startswith(f"{forbidden}.") for module in modules):
            raise ClosureError(f"forbidden dependency in closure: {forbidden}")

    return {
        "membership_recomputed": True,
        "digests_recomputed": True,
        "all_files_accessible": True,
        "forbidden_dependencies_absent": True,
        "passed_before_grading": True,
    }
