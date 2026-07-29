#!/usr/bin/env python3
"""Prepare and verify one Codex Usage Tracker development worktree.

The entry point intentionally uses only the Python standard library so it can
repair a missing or stale project virtual environment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on Python 3.10
    tomllib = None  # type: ignore[assignment]


_DISTRIBUTION_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXACT_VERSION_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*==\s*([^;,\s]+)\s*$"
)
_SCALENE_DISTRIBUTION = "scalene"
_GITNEXUS_VERSION = "1.6.9"
_GITNEXUS_LOCK_FILENAME = "codex-usage-tracker-gitnexus-analyze.lock"
_GITNEXUS_LOCK_TIMEOUT_SECONDS = 600.0
_GITNEXUS_COMPARE_BASE = "origin/main"
_GITNEXUS_CHANGED_FILES_PATTERN = re.compile(r"^Changes:\s+(\d+)\s+files\b", re.MULTILINE)
_GITNEXUS_FTS_CORRUPTION_PATTERN = re.compile(
    r"FTS index 'file_fts' inconsistent: node offset \d+ missing during delete\. "
    r"Drop and recreate FTS index\."
)


class BootstrapError(RuntimeError):
    """A worktree-readiness failure with an actionable explanation."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class DevToolContract:
    project_distribution: str
    requirements: tuple[str, ...]
    scalene_version: str


@dataclass(frozen=True)
class PythonEnvironmentResult:
    changed: bool
    python: Path
    uv_version: str
    scalene_version: str
    source: str


@dataclass(frozen=True)
class GitNexusResult:
    changed: bool
    state: str
    runner: Path
    node_version: str
    gitnexus_version: str


@dataclass(frozen=True)
class _PythonInspection:
    ready: bool
    versions: dict[str, str | None]
    reason: str


@dataclass(frozen=True)
class _GitNexusInspection:
    state: str
    detail: str
    repository: Path | None = None
    branch: str | None = None


def _which(executable: str) -> str | None:
    return shutil.which(executable)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stream: bool = False,
) -> CommandResult:
    try:
        if stream:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                check=False,
                text=True,
            )
            return CommandResult(completed.returncode, "", "")
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        raise BootstrapError(f"Could not run {command[0]!r}: {exc}") from exc
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _fallback_dev_dependencies(text: str) -> list[str]:
    section_match = re.search(
        r"(?ms)^\[project\.optional-dependencies\]\s*$"
        r"(?P<section>.*?)(?=^\[|\Z)",
        text,
    )
    if section_match is None:
        raise BootstrapError("pyproject.toml has no [project.optional-dependencies] table.")
    dev_match = re.search(
        r"(?ms)^\s*dev\s*=\s*\[(?P<body>.*?)^\s*\]",
        section_match.group("section"),
    )
    if dev_match is None:
        raise BootstrapError("pyproject.toml has no project dev extra.")
    dependencies: list[str] = []
    for encoded in re.findall(r'"(?:[^"\\]|\\.)*"', dev_match.group("body")):
        try:
            dependencies.append(json.loads(encoded))
        except json.JSONDecodeError as exc:
            raise BootstrapError(
                "The project dev extra contains a string Python 3.10 cannot parse."
            ) from exc
    return dependencies


def _read_dev_dependencies(pyproject: Path) -> list[str]:
    if not pyproject.is_file():
        raise BootstrapError(f"Missing project declaration: {pyproject}")
    text = pyproject.read_text(encoding="utf-8")
    if tomllib is None:
        dependencies = _fallback_dev_dependencies(text)
    else:
        try:
            payload = tomllib.loads(text)
            dependencies = payload["project"]["optional-dependencies"]["dev"]
        except (KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
            raise BootstrapError(
                "pyproject.toml must declare [project.optional-dependencies].dev."
            ) from exc
    if not isinstance(dependencies, list) or not all(
        isinstance(dependency, str) for dependency in dependencies
    ):
        raise BootstrapError("The project dev extra must be a list of requirement strings.")
    return dependencies


def _fallback_project_distribution(text: str) -> str:
    project_match = re.search(
        r"(?ms)^\[project\]\s*$"
        r"(?P<section>.*?)(?=^\[|\Z)",
        text,
    )
    if project_match is None:
        raise BootstrapError("pyproject.toml has no [project] table.")
    name_match = re.search(
        r'(?m)^\s*name\s*=\s*(?P<name>"(?:[^"\\]|\\.)*")\s*$',
        project_match.group("section"),
    )
    if name_match is None:
        raise BootstrapError("pyproject.toml has no project name.")
    try:
        name = json.loads(name_match.group("name"))
    except json.JSONDecodeError as exc:
        raise BootstrapError("The project name is not a valid TOML basic string.") from exc
    if not isinstance(name, str) or not name:
        raise BootstrapError("The project name must be a non-empty string.")
    return name


def _read_project_distribution(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    if tomllib is None:
        return _fallback_project_distribution(text)
    try:
        name = tomllib.loads(text)["project"]["name"]
    except (KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise BootstrapError("pyproject.toml must declare [project].name.") from exc
    if not isinstance(name, str) or not name:
        raise BootstrapError("The project name must be a non-empty string.")
    return name


def read_dev_tool_contract(pyproject: Path) -> DevToolContract:
    """Read required dev distributions and exact pins from ``pyproject.toml``."""

    dependencies = _read_dev_dependencies(pyproject)
    scalene_requirements: list[str] = []
    scalene_version: str | None = None

    for requirement in dependencies:
        requirement_without_marker, marker_separator, _marker = requirement.partition(";")
        name_match = _DISTRIBUTION_PATTERN.match(requirement_without_marker.strip())
        if name_match is None:
            raise BootstrapError(f"Unsupported dev requirement: {requirement!r}")
        distribution = _normalize_distribution(name_match.group(1))
        exact_match = _EXACT_VERSION_PATTERN.fullmatch(requirement_without_marker)
        if distribution == _SCALENE_DISTRIBUTION:
            scalene_requirements.append(requirement)
            if exact_match is not None and not marker_separator:
                scalene_version = exact_match.group(2)

    if len(scalene_requirements) != 1:
        raise BootstrapError(
            "The project dev extra must contain exactly one exact scalene==VERSION pin."
        )
    if scalene_version is None:
        raise BootstrapError("The project dev extra must contain an exact scalene==VERSION pin.")
    return DevToolContract(
        _read_project_distribution(pyproject),
        tuple(dependencies),
        scalene_version,
    )


def _command_failure(command: list[str], result: CommandResult) -> str:
    detail = (result.stderr or result.stdout).strip()
    rendered = " ".join(command)
    if detail:
        return f"{rendered} failed ({result.returncode}): {detail}"
    return f"{rendered} failed with exit code {result.returncode}."


def _uv_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("VIRTUAL_ENV", None)
    environment["UV_PROJECT_ENVIRONMENT"] = str(root / ".venv")
    environment["UV_NO_PROGRESS"] = "1"
    return environment


def _venv_python(root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return root / ".venv" / relative


def _venv_executable(root: Path, name: str) -> Path:
    relative = Path("Scripts") / f"{name}.exe" if os.name == "nt" else Path("bin") / name
    return root / ".venv" / relative


def _requirement_problems(
    requirements: tuple[str, ...],
    versions: Mapping[str, str | None],
    *,
    environment: dict[str, str] | None = None,
) -> list[str]:
    try:
        from packaging.markers import default_environment
    except ImportError as exc:
        raise BootstrapError(
            "The dev environment cannot evaluate PEP 508 requirements because "
            "`packaging` is unavailable."
        ) from exc

    marker_environment = {key: str(value) for key, value in default_environment().items()}
    if environment is not None:
        marker_environment.update(environment)
    return [
        problem
        for raw_requirement in requirements
        if (
            problem := _requirement_problem(
                raw_requirement,
                versions,
                marker_environment,
            )
        )
        is not None
    ]


def _requirement_problem(
    raw_requirement: str,
    versions: Mapping[str, str | None],
    marker_environment: Mapping[str, str],
) -> str | None:
    from packaging.requirements import InvalidRequirement, Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import InvalidVersion

    try:
        requirement = Requirement(raw_requirement)
    except InvalidRequirement as exc:
        raise BootstrapError(f"Invalid dev requirement {raw_requirement!r}: {exc}") from exc
    if requirement.marker is not None and not requirement.marker.evaluate(marker_environment):
        return None
    distribution = canonicalize_name(requirement.name)
    installed = versions.get(distribution)
    if installed is None:
        return f"active requirement {raw_requirement!r} is not installed"
    try:
        satisfies = requirement.specifier.contains(installed, prereleases=True)
    except InvalidVersion:
        satisfies = False
    if not satisfies:
        return f"active requirement {raw_requirement!r} is not satisfied by {installed}"
    return None


def _editable_source_problem(source: Path | None, root: Path) -> str | None:
    if source is None:
        return "editable project source is missing"
    if source.expanduser().resolve() != root.resolve():
        return (
            f"editable project source is {source.expanduser().resolve()}, "
            f"expected exact worktree {root.resolve()}"
        )
    return None


def _editable_source_from_metadata(project_distribution: str) -> Path | None:
    import importlib.metadata
    from urllib.parse import unquote, urlparse
    from urllib.request import url2pathname

    try:
        distribution = importlib.metadata.distribution(project_distribution)
    except importlib.metadata.PackageNotFoundError:
        return None
    direct_url_text = distribution.read_text("direct_url.json")
    if direct_url_text is None:
        return None
    try:
        direct_url = json.loads(direct_url_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(direct_url, dict):
        return None
    directory = direct_url.get("dir_info")
    url = direct_url.get("url")
    if not isinstance(directory, dict) or directory.get("editable") is not True:
        return None
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return None
    path = url2pathname(unquote(parsed.path))
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    return Path(path)


def _local_python_contract_report(root: Path) -> dict[str, object]:
    import importlib.metadata

    try:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
    except ImportError as exc:
        raise BootstrapError(
            "The dev environment cannot evaluate PEP 508 requirements because "
            "`packaging` is unavailable."
        ) from exc

    contract = read_dev_tool_contract(root / "pyproject.toml")
    marker_environment = {key: str(value) for key, value in default_environment().items()}
    versions: dict[str, str | None] = {}
    for raw_requirement in contract.requirements:
        requirement = Requirement(raw_requirement)
        if requirement.marker is not None and not requirement.marker.evaluate(marker_environment):
            continue
        distribution = canonicalize_name(requirement.name)
        try:
            versions[distribution] = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    problems = _requirement_problems(contract.requirements, versions)
    editable_source = _editable_source_from_metadata(contract.project_distribution)
    editable_problem = _editable_source_problem(editable_source, root)
    if editable_problem is not None:
        problems.append(editable_problem)
    return {"problems": problems, "versions": versions}


def _probe_python_contract(root: Path, python: Path) -> _PythonInspection:
    command = [
        str(python),
        "-I",
        str(root / "scripts" / "bootstrap_dev_environment.py"),
        "--_verify-python-contract",
        "--root",
        str(root),
    ]
    result = _run(command, cwd=root)
    if result.returncode != 0:
        return _PythonInspection(False, {}, _command_failure(command, result))
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _PythonInspection(False, {}, f"{python} returned invalid verification metadata")
    if not isinstance(payload, dict):
        return _PythonInspection(False, {}, f"{python} returned invalid verification metadata")
    raw_versions = payload.get("versions")
    raw_problems = payload.get("problems")
    if not isinstance(raw_versions, dict) or not isinstance(raw_problems, list):
        return _PythonInspection(False, {}, f"{python} returned invalid verification metadata")
    versions = {
        str(name): str(version) if version is not None else None
        for name, version in raw_versions.items()
    }
    problems = [str(problem) for problem in raw_problems]
    if problems:
        return _PythonInspection(False, versions, "; ".join(problems))
    return _PythonInspection(True, versions, "ready")


def _scalene_entrypoint_problem(
    root: Path,
    contract: DevToolContract,
) -> str | None:
    scalene = _venv_executable(root, _SCALENE_DISTRIBUTION)
    if not scalene.is_file():
        return f"missing Scalene console entry point: {scalene}"
    result = _run([str(scalene), "--version"], cwd=root)
    expected_banner = f"scalene version {contract.scalene_version}"
    output = f"{result.stdout}\n{result.stderr}".lower()
    if result.returncode != 0 or expected_banner not in output:
        return (
            "Scalene console entry point does not report the declared "
            f"{contract.scalene_version} pin"
        )
    return None


def _inspect_python_environment(
    root: Path,
    uv: str,
    contract: DevToolContract,
) -> _PythonInspection:
    python = _venv_python(root)
    if not python.is_file():
        return _PythonInspection(False, {}, f"{python} does not exist")
    version_result = _run([str(python), "--version"], cwd=root)
    if version_result.returncode != 0:
        return _PythonInspection(False, {}, f"{python} is not executable")
    inspection = _probe_python_contract(root, python)
    if not inspection.ready:
        return inspection
    problem = _scalene_entrypoint_problem(root, contract)
    if problem is not None:
        return _PythonInspection(False, inspection.versions, problem)

    check_command = [uv, "pip", "check", "--python", str(python)]
    check_result = _run(
        check_command,
        cwd=root,
        env=_uv_environment(root),
    )
    if check_result.returncode != 0:
        return _PythonInspection(
            False,
            inspection.versions,
            _command_failure(check_command, check_result),
        )
    return _PythonInspection(True, inspection.versions, "ready")


def _assert_safe_venv(root: Path) -> None:
    venv = root / ".venv"
    if venv.is_symlink():
        raise BootstrapError(
            f"Refusing to use or repair a .venv symlink: {venv} -> {venv.resolve(strict=False)}"
        )
    if venv.exists() and not venv.is_dir():
        raise BootstrapError(f"Refusing to use non-directory virtual environment path: {venv}")
    if venv.resolve(strict=False) != root.resolve() / ".venv":
        raise BootstrapError(f"Refusing to use a virtual environment outside {root.resolve()}.")


def _create_or_repair_venv(root: Path, uv: str) -> None:
    _assert_safe_venv(root)
    venv = root / ".venv"
    command = [uv, "venv"]
    if venv.exists():
        command.append("--clear")
    command.extend(("--python", sys.executable, str(venv)))
    result = _run(command, cwd=root, env=_uv_environment(root), stream=True)
    if result.returncode != 0:
        raise BootstrapError(_command_failure(command, result))


def prepare_python_environment(
    root: Path,
    *,
    check_only: bool,
) -> PythonEnvironmentResult:
    """Prepare or verify the repository-local Python dev environment."""

    _assert_safe_venv(root)
    contract = read_dev_tool_contract(root / "pyproject.toml")
    uv = _which("uv")
    if uv is None:
        raise BootstrapError(
            "uv is required to prepare the dev environment. Install uv, then rerun "
            "`python3 scripts/bootstrap_dev_environment.py`."
        )
    uv_result = _run([uv, "--version"], cwd=root)
    if uv_result.returncode != 0:
        raise BootstrapError(_command_failure([uv, "--version"], uv_result))
    uv_version = uv_result.stdout.strip()

    inspection = _inspect_python_environment(root, uv, contract)
    if inspection.ready:
        return PythonEnvironmentResult(
            False,
            _venv_python(root),
            uv_version,
            contract.scalene_version,
            "verified",
        )
    if check_only:
        raise BootstrapError(
            f"Python dev environment is not ready: {inspection.reason}. "
            "Run the bootstrap without --check to repair it from `.[dev]`."
        )

    python = _venv_python(root)
    python_result = (
        _run([str(python), "--version"], cwd=root)
        if python.is_file()
        else CommandResult(1, "", "missing")
    )
    if python_result.returncode != 0:
        _create_or_repair_venv(root, uv)

    _assert_safe_venv(root)
    uv_environment = _uv_environment(root)
    if (root / "uv.lock").is_file():
        install_command = [uv, "sync", "--extra", "dev", "--frozen"]
        source = "uv.lock"
    else:
        install_command = [
            uv,
            "pip",
            "install",
            "--strict",
            "--python",
            str(_venv_python(root)),
            "--editable",
            ".[dev]",
        ]
        source = "pyproject dev extra"
    install_result = _run(
        install_command,
        cwd=root,
        env=uv_environment,
        stream=True,
    )
    if install_result.returncode != 0:
        raise BootstrapError(_command_failure(install_command, install_result))

    _assert_safe_venv(root)
    repaired = _inspect_python_environment(root, uv, contract)
    if not repaired.ready:
        raise BootstrapError(
            f"uv completed, but the Python dev environment is still not ready: {repaired.reason}"
        )
    return PythonEnvironmentResult(
        True,
        _venv_python(root),
        uv_version,
        contract.scalene_version,
        source,
    )


def _gitnexus_runner(root: Path) -> Path:
    return root / "tools" / "gitnexus" / "node_modules" / "gitnexus" / "dist" / "cli" / "index.js"


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise BootstrapError(f"Missing integrity-controlled tool declaration: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"Invalid JSON tool declaration: {path}") from exc
    if not isinstance(payload, dict):
        raise BootstrapError(f"Tool declaration must be a JSON object: {path}")
    return payload


def _validate_gitnexus_tool_contract(root: Path) -> None:
    tool_root = root / "tools" / "gitnexus"
    package = _read_json_object(tool_root / "package.json")
    lock = _read_json_object(tool_root / "package-lock.json")
    expected_dependency = {"gitnexus": _GITNEXUS_VERSION}
    if package.get("private") is not True or package.get("dependencies") != expected_dependency:
        raise BootstrapError(
            "tools/gitnexus/package.json must be private and pin exactly "
            f"gitnexus=={_GITNEXUS_VERSION}."
        )
    packages = lock.get("packages")
    if not isinstance(packages, dict):
        raise BootstrapError("tools/gitnexus/package-lock.json has no packages map.")
    root_package = packages.get("")
    pinned_package = packages.get("node_modules/gitnexus")
    if (
        not isinstance(root_package, dict)
        or root_package.get("dependencies") != expected_dependency
    ):
        raise BootstrapError("GitNexus lock root does not match the exact package pin.")
    if not isinstance(pinned_package, dict):
        raise BootstrapError("GitNexus lock has no pinned gitnexus package entry.")
    integrity = pinned_package.get("integrity")
    if pinned_package.get("version") != _GITNEXUS_VERSION or not (
        isinstance(integrity, str) and integrity.startswith("sha512-")
    ):
        raise BootstrapError(f"GitNexus lock must pin {_GITNEXUS_VERSION} with sha512 integrity.")


def _gitnexus_status_command(root: Path, node: str) -> list[str] | None:
    runner = _gitnexus_runner(root)
    if runner.is_file():
        return [node, str(runner), "status"]
    return None


def _gitnexus_tool_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["npm_config_cache"] = str(root / ".gitnexus" / "npm-cache")
    environment["npm_config_update_notifier"] = "false"
    environment["SCARF_ANALYTICS"] = "false"
    environment["DO_NOT_TRACK"] = "1"
    return environment


def _install_gitnexus_tool(root: Path) -> None:
    npm = _which("npm")
    if npm is None:
        raise BootstrapError(
            "npm is required to install the repository-private pinned GitNexus tool."
        )
    command = [
        npm,
        "ci",
        "--prefix",
        str(root / "tools" / "gitnexus"),
        "--no-audit",
        "--no-fund",
    ]
    result = _run(
        command,
        cwd=root,
        env=_gitnexus_tool_environment(root),
        stream=True,
    )
    if result.returncode != 0:
        raise BootstrapError(_command_failure(command, result))


def _gitnexus_status_field(status: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+?)\s*$", status, re.MULTILINE)
    if match is None:
        raise BootstrapError(f"GitNexus status omitted required {field!r} identity.")
    return match.group(1)


def _run_git(root: Path, *arguments: str) -> CommandResult:
    git = _which("git")
    if git is None:
        raise BootstrapError("Git is required to verify GitNexus worktree identity.")
    command = [git, *arguments]
    result = _run(command, cwd=root)
    if result.returncode != 0:
        raise BootstrapError(_command_failure(command, result))
    return result


def _gitnexus_status_identity(
    root: Path,
    status: str,
    *,
    up_to_date: bool,
) -> tuple[Path, str]:
    reported_root = Path(_gitnexus_status_field(status, "Repository")).expanduser().resolve()
    exact_root = root.resolve()
    if reported_root != exact_root:
        raise BootstrapError(
            "GitNexus status is registered to a different worktree: "
            f"{reported_root}; expected {exact_root}. Re-index this exact worktree; "
            "do not clean or delete another registry entry."
        )

    reported_branch = _gitnexus_status_field(status, "Branch")
    current_branch = _run_git(root, "branch", "--show-current").stdout.strip()
    if not current_branch:
        raise BootstrapError("GitNexus readiness requires an attached worktree branch.")
    if reported_branch != current_branch:
        raise BootstrapError(
            "GitNexus status is registered to branch "
            f"{reported_branch!r}; exact worktree branch is {current_branch!r}."
        )

    current_commit = _gitnexus_status_field(status, "Current commit")
    head_commit = _run_git(root, "rev-parse", "HEAD").stdout.strip()
    if not head_commit.startswith(current_commit):
        raise BootstrapError(
            f"GitNexus reports current commit {current_commit}, but Git HEAD is {head_commit}."
        )
    if up_to_date:
        indexed_commit = _gitnexus_status_field(status, "Indexed commit")
        if indexed_commit != current_commit:
            raise BootstrapError(
                "GitNexus reported up-to-date with different indexed and current commits: "
                f"{indexed_commit} != {current_commit}."
            )
    return reported_root, reported_branch


def _classify_gitnexus_status(status: str) -> str:
    normalized = status.lower()
    if "repository not indexed" in normalized:
        return "missing"
    if "status:" in normalized and "up-to-date" in normalized:
        return "up_to_date"
    if "status:" in normalized and "stale" in normalized:
        return "stale"
    return "error"


def _identified_gitnexus_inspection(
    root: Path,
    status: str,
    state: str,
) -> _GitNexusInspection:
    try:
        repository, branch = _gitnexus_status_identity(
            root,
            status,
            up_to_date=state == "up_to_date",
        )
    except BootstrapError as error:
        return _GitNexusInspection("error", str(error))
    return _GitNexusInspection(state, status.strip(), repository, branch)


def _inspect_gitnexus(
    root: Path,
    node: str,
) -> _GitNexusInspection:
    command = _gitnexus_status_command(root, node)
    if command is None:
        return _GitNexusInspection(
            "missing",
            "repository-private pinned GitNexus tool is not installed",
        )
    result = _run(command, cwd=root)
    if result.returncode != 0:
        return _GitNexusInspection("error", _command_failure(command, result))
    state = _classify_gitnexus_status(f"{result.stdout}\n{result.stderr}")
    if state == "missing":
        return _GitNexusInspection("missing", result.stdout.strip())
    if state != "error":
        return _identified_gitnexus_inspection(root, result.stdout, state)
    return _GitNexusInspection(
        "error",
        "GitNexus status returned an unrecognized result: "
        f"{(result.stdout or result.stderr).strip()}",
    )


def _gitnexus_compare_command(root: Path, node: str, branch: str) -> list[str]:
    status_command = _gitnexus_status_command(root, node)
    if status_command is None:
        raise BootstrapError("GitNexus compare requires an installed or worktree-local runner.")
    return [
        *status_command[:-1],
        "detect_changes",
        "--scope",
        "compare",
        "--base-ref",
        _GITNEXUS_COMPARE_BASE,
        "--repo",
        str(root.resolve()),
        "--branch",
        branch,
        "--limit",
        "1",
    ]


def _git_compare_file_count(root: Path) -> int:
    _run_git(root, "rev-parse", "--verify", _GITNEXUS_COMPARE_BASE)
    result = _run_git(
        root,
        "diff",
        "--name-only",
        "-z",
        _GITNEXUS_COMPARE_BASE,
        "--",
    )
    return len([name for name in result.stdout.split("\0") if name])


def _gitnexus_changed_file_count(output: str) -> int:
    if "No changes detected." in output:
        return 0
    match = _GITNEXUS_CHANGED_FILES_PATTERN.search(output)
    if match is None:
        raise BootstrapError(
            "GitNexus detect_changes returned an unrecognized changed-file summary."
        )
    return int(match.group(1))


def _verify_gitnexus_compare_scope(
    root: Path,
    node: str,
    inspection: _GitNexusInspection,
) -> None:
    expected_count = _git_compare_file_count(root)
    if expected_count == 0:
        return
    if inspection.branch is None:
        raise BootstrapError("GitNexus status did not provide an exact branch for compare.")
    command = _gitnexus_compare_command(root, node, inspection.branch)
    result = _run(command, cwd=root)
    if result.returncode != 0:
        raise BootstrapError(_command_failure(command, result))
    reported_count = _gitnexus_changed_file_count(f"{result.stdout}\n{result.stderr}")
    if reported_count > expected_count:
        raise BootstrapError(
            f"GitNexus compare reported {reported_count} files, but Git diff "
            f"{_GITNEXUS_COMPARE_BASE} contains {expected_count}. The graph, worktree, "
            "or compare base is mismatched; use the exact physical repo path, exact "
            "branch, and origin/main. Do not clean another worktree's registry entry."
        )


def _gitnexus_analyze_command(root: Path, node: str) -> list[str]:
    runner = _gitnexus_runner(root)
    if not runner.is_file():
        raise BootstrapError(
            "Repository-private pinned GitNexus tool is missing after local npm ci."
        )
    return [node, str(runner), "analyze", "--index-only"]


def _is_recognized_gitnexus_fts_corruption(result: CommandResult) -> bool:
    output = f"{result.stdout}\n{result.stderr}"
    return _GITNEXUS_FTS_CORRUPTION_PATTERN.search(output) is not None


def _cache_root() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache"


def _lock_file_nonblocking(handle: object) -> bool:
    if os.name == "nt":  # pragma: no cover - Windows-specific implementation
        import msvcrt

        try:
            handle.seek(0)  # type: ignore[attr-defined]
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
    except BlockingIOError:
        return False
    return True


def _unlock_file(handle: object) -> None:
    if os.name == "nt":  # pragma: no cover - Windows-specific implementation
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


@contextmanager
def _gitnexus_analysis_lock(
    root: Path,
    *,
    timeout_seconds: float,
) -> Iterator[None]:
    lock_path = _cache_root() / _GITNEXUS_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    with lock_path.open("a+", encoding="utf-8") as handle:
        if os.name == "nt" and lock_path.stat().st_size == 0:  # pragma: no cover
            handle.write("0")
            handle.flush()
        while not _lock_file_nonblocking(handle):
            if time.monotonic() >= deadline:
                raise BootstrapError(
                    "Timed out waiting for another GitNexus analysis to release "
                    f"{lock_path}. Let the host-owned analysis finish, then rerun."
                )
            time.sleep(0.1)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            yield
        finally:
            _unlock_file(handle)


def _gitnexus_version(root: Path, node: str) -> str:
    runner = _gitnexus_runner(root)
    if not runner.is_file():
        raise BootstrapError("Repository-private pinned GitNexus entry point is missing.")
    command = [node, str(runner), "--version"]
    result = _run(command, cwd=root)
    if result.returncode != 0:
        raise BootstrapError(_command_failure(command, result))
    version = result.stdout.strip()
    if version != _GITNEXUS_VERSION:
        raise BootstrapError(
            f"Repository-private GitNexus reports {version!r}; expected {_GITNEXUS_VERSION}."
        )
    return version


def _analyze_gitnexus_if_needed(
    root: Path,
    node: str,
    *,
    lock_timeout_seconds: float,
) -> bool:
    with _gitnexus_analysis_lock(root, timeout_seconds=lock_timeout_seconds):
        # Another bootstrap may have completed while this process waited.
        inspection = _inspect_gitnexus(root, node)
        if inspection.state == "up_to_date":
            return False
        if inspection.state == "error":
            raise BootstrapError(inspection.detail)
        analyze_command = _gitnexus_analyze_command(root, node)
        analyze_result = _run(analyze_command, cwd=root)
        if analyze_result.returncode == 0:
            return True
        exact_worktree_identified = (
            inspection.repository == root.resolve() and inspection.branch is not None
        )
        if (
            not exact_worktree_identified
            or not _is_recognized_gitnexus_fts_corruption(analyze_result)
        ):
            raise BootstrapError(_command_failure(analyze_command, analyze_result))

        clean_command = [
            node,
            str(_gitnexus_runner(root)),
            "clean",
            "--force",
        ]
        clean_result = _run(clean_command, cwd=root)
        if clean_result.returncode != 0:
            raise BootstrapError(
                "GitNexus recognized file_fts corruption for the exact worktree, "
                "but automatic clean failed; analysis was not retried. "
                f"{_command_failure(clean_command, clean_result)} "
                f"Original analysis: {_command_failure(analyze_command, analyze_result)}"
            )

        retry_result = _run(analyze_command, cwd=root)
        if retry_result.returncode != 0:
            raise BootstrapError(
                "GitNexus automatic clean succeeded after recognized file_fts "
                "corruption, but the one allowed index-only retry failed; "
                f"{_command_failure(analyze_command, retry_result)}"
            )
        return True


def _repair_gitnexus_tool(root: Path, node: str) -> str:
    _install_gitnexus_tool(root)
    try:
        return _gitnexus_version(root, node)
    except BootstrapError as error:
        raise BootstrapError(
            f"Pinned GitNexus repair did not produce {_GITNEXUS_VERSION}: {error}"
        ) from error


def _ensure_gitnexus_tool(
    root: Path,
    node: str,
    *,
    check_only: bool,
) -> tuple[bool, str, Path]:
    runner = _gitnexus_runner(root)
    if not runner.is_file():
        if check_only:
            raise BootstrapError(
                "Repository-private pinned GitNexus tool is missing. Run the bootstrap "
                "without --check to install the integrity-locked 1.6.9 tool locally."
            )
        return True, _repair_gitnexus_tool(root, node), runner
    try:
        return False, _gitnexus_version(root, node), runner
    except BootstrapError:
        if check_only:
            raise
    return True, _repair_gitnexus_tool(root, node), runner


def prepare_gitnexus(
    root: Path,
    *,
    check_only: bool,
    lock_timeout_seconds: float = _GITNEXUS_LOCK_TIMEOUT_SECONDS,
) -> GitNexusResult:
    """Prepare or verify the pinned local GitNexus tool and exact-worktree index."""

    _validate_gitnexus_tool_contract(root)
    node = _which("node")
    if node is None:
        raise BootstrapError(
            "Node.js is required for the repository-private pinned GitNexus tool. "
            "Install Node.js, then rerun the bootstrap."
        )
    node_result = _run([node, "--version"], cwd=root)
    if node_result.returncode != 0:
        raise BootstrapError(_command_failure([node, "--version"], node_result))
    node_version = node_result.stdout.strip()

    tool_changed, gitnexus_version, runner = _ensure_gitnexus_tool(
        root,
        node,
        check_only=check_only,
    )

    inspection = _inspect_gitnexus(root, node)
    if inspection.state == "up_to_date":
        _verify_gitnexus_compare_scope(root, node, inspection)
        return GitNexusResult(
            tool_changed,
            inspection.state,
            runner,
            node_version,
            gitnexus_version,
        )
    if inspection.state == "error":
        raise BootstrapError(inspection.detail)
    if check_only:
        raise BootstrapError(
            f"GitNexus index is {inspection.state}: {inspection.detail}. "
            "Run the bootstrap without --check; the host will wait for one "
            "serialized index-only analysis."
        )

    changed = _analyze_gitnexus_if_needed(
        root,
        node,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    verified = _inspect_gitnexus(root, node)
    if verified.state != "up_to_date":
        raise BootstrapError(
            f"GitNexus analysis completed, but the exact worktree is not ready: {verified.detail}"
        )
    _verify_gitnexus_compare_scope(root, node, verified)
    return GitNexusResult(
        tool_changed or changed,
        verified.state,
        runner,
        node_version,
        gitnexus_version,
    )


def validate_repository_root(requested_root: Path) -> Path:
    """Resolve and prove that ``requested_root`` is the exact Git worktree root."""

    git = _which("git")
    if git is None:
        raise BootstrapError("Git is required to resolve the exact worktree root.")
    requested = requested_root.expanduser().resolve()
    result = _run([git, "rev-parse", "--show-toplevel"], cwd=requested)
    if result.returncode != 0:
        raise BootstrapError(_command_failure([git, "rev-parse", "--show-toplevel"], result))
    discovered = Path(result.stdout.strip()).resolve()
    if discovered != requested:
        raise BootstrapError(
            f"Requested root {requested} is not the exact Git worktree root; "
            f"Git resolved {discovered}."
        )
    return discovered


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or verify the repository dev environment and exact-worktree GitNexus index."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify readiness without creating, installing, or indexing",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="exact Git worktree root (defaults to the script's repository)",
    )
    parser.add_argument(
        "--component",
        choices=("all", "python", "gitnexus"),
        default="all",
        help="prepare all readiness components or one focused component",
    )
    parser.add_argument(
        "--gitnexus-lock-timeout-seconds",
        type=float,
        default=_GITNEXUS_LOCK_TIMEOUT_SECONDS,
        help="maximum host wait for the shared GitNexus analysis lock",
    )
    parser.add_argument(
        "--_verify-python-contract",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args._verify_python_contract:
            report = _local_python_contract_report(args.root.expanduser().resolve())
            print(json.dumps(report, sort_keys=True, separators=(",", ":")))
            return 0
        root = validate_repository_root(args.root)
        if args.component in {"all", "python"}:
            python_result = prepare_python_environment(root, check_only=args.check)
            action = "repaired" if python_result.changed else "verified"
            print(
                "Python dev environment "
                f"{action}: {python_result.python} "
                f"(Scalene {python_result.scalene_version}; "
                f"{python_result.source}; {python_result.uv_version})"
            )
        if args.component in {"all", "gitnexus"}:
            gitnexus_result = prepare_gitnexus(
                root,
                check_only=args.check,
                lock_timeout_seconds=args.gitnexus_lock_timeout_seconds,
            )
            action = "analyzed" if gitnexus_result.changed else "verified"
            print(
                "GitNexus "
                f"{action}: {gitnexus_result.runner} "
                f"({gitnexus_result.state}; GitNexus "
                f"{gitnexus_result.gitnexus_version}; Node "
                f"{gitnexus_result.node_version})"
            )
    except BootstrapError as exc:
        print(f"Worktree bootstrap failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
