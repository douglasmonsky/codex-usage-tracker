from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DBHUB_PACKAGE = "@bytebase/dbhub"
DBHUB_VERSION = "0.24.0"
DBHUB_NPM_INTEGRITY = (
    "sha512-R+S7FQXwHyr99Klei+sHG8ijLdk8Ob/B3KN2zAjKptQZGoyTe6hHtN3S74wG0dx3"
    "BxvEPShb3iv4nNgcHStz5w=="
)
DBHUB_MAX_ROW_CAP = 100
_SQLITE_HEADER = b"SQLite format 3\x00"
_NAME_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_FORBIDDEN_SQL = re.compile(
    r"\b(?:ALTER|ATTACH|CREATE|DELETE|DETACH|DROP|INSERT|REINDEX|REPLACE|"
    r"UPDATE|VACUUM)\b",
    re.IGNORECASE,
)


class DbhubContractError(ValueError):
    pass


@dataclass(frozen=True)
class DbhubParameter:
    name: str
    parameter_type: str
    description: str

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name):
            raise DbhubContractError(f"invalid DBHub parameter name: {self.name!r}")
        if self.parameter_type not in {"string", "integer", "number", "boolean"}:
            raise DbhubContractError("DBHub parameter type is not admitted")
        if not self.description.strip():
            raise DbhubContractError("DBHub parameter description is required")


@dataclass(frozen=True)
class DbhubCustomTool:
    name: str
    description: str
    statement: str
    parameters: tuple[DbhubParameter, ...] = ()

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name) or self.name in {
            "execute_sql",
            "search_objects",
        }:
            raise DbhubContractError(f"invalid DBHub custom tool name: {self.name!r}")
        if not self.description.strip():
            raise DbhubContractError("DBHub custom tool description is required")
        _validate_read_statement(self.statement)
        if self.statement.count("?") != len(self.parameters):
            raise DbhubContractError("DBHub custom tool parameters do not match placeholders")
        if len({parameter.name for parameter in self.parameters}) != len(self.parameters):
            raise DbhubContractError("DBHub custom tool parameter names must be unique")


@dataclass(frozen=True)
class DbhubRun:
    package: str
    version: str
    package_integrity: str
    snapshot_path: Path
    snapshot_sha256: str
    config_path: Path
    argv: tuple[str, ...]
    max_rows: int

    def verify_unchanged(self) -> None:
        try:
            mode = self.snapshot_path.stat().st_mode
        except OSError as error:
            raise DbhubContractError("disposable DBHub snapshot is missing") from error
        if _sha256_file(self.snapshot_path) != self.snapshot_sha256:
            raise DbhubContractError("disposable DBHub snapshot changed during research run")
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            raise DbhubContractError("disposable DBHub snapshot is no longer read-only")

    @contextmanager
    def runtime_access(self) -> Iterator[None]:
        """Permit DBHub 0.24 to open its disposable copy, then fail closed."""

        self.verify_unchanged()
        try:
            os.chmod(
                self.snapshot_path,
                stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH,
            )
        except OSError as error:
            raise DbhubContractError(
                "disposable DBHub snapshot cannot enter runtime mode"
            ) from error
        try:
            yield
        finally:
            try:
                os.chmod(
                    self.snapshot_path,
                    stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
                )
            except OSError as error:
                raise DbhubContractError(
                    "disposable DBHub snapshot cannot restore read-only mode"
                ) from error
            self.verify_unchanged()


def _validate_read_statement(statement: str) -> None:
    normalized = statement.strip()
    if not normalized or ";" in normalized or "--" in normalized or "/*" in normalized:
        raise DbhubContractError("DBHub custom tool must be one comment-free statement")
    first_word = normalized.split(maxsplit=1)[0].upper()
    if first_word not in {"SELECT", "WITH", "EXPLAIN"} or _FORBIDDEN_SQL.search(normalized):
        raise DbhubContractError("DBHub custom tool must be a read-only SELECT")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise DbhubContractError("DBHub snapshot cannot be hashed") from error
    return digest.hexdigest()


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_config(
    snapshot_path: Path,
    tools: tuple[DbhubCustomTool, ...],
    max_rows: int,
) -> str:
    lines = [
        "# Generated CK-04 disposable DBHub research configuration.",
        "[[sources]]",
        'id = "ck04_synthetic_snapshot"',
        f"dsn = {_toml_string(f'sqlite://{snapshot_path}')}",
        "",
        "[[tools]]",
        'name = "search_objects"',
        'source = "ck04_synthetic_snapshot"',
        "",
        "[[tools]]",
        'name = "execute_sql"',
        'source = "ck04_synthetic_snapshot"',
        "readonly = true",
        f"max_rows = {max_rows}",
    ]
    for tool in tools:
        lines.extend(
            [
                "",
                "[[tools]]",
                f"name = {_toml_string(tool.name)}",
                f"description = {_toml_string(tool.description)}",
                'source = "ck04_synthetic_snapshot"',
                f"statement = {_toml_string(tool.statement)}",
                "readonly = true",
                f"max_rows = {max_rows}",
            ]
        )
        for parameter in tool.parameters:
            lines.extend(
                [
                    "",
                    "[[tools.parameters]]",
                    f"name = {_toml_string(parameter.name)}",
                    f"type = {_toml_string(parameter.parameter_type)}",
                    f"description = {_toml_string(parameter.description)}",
                ]
            )
    return "\n".join(lines) + "\n"


def build_dbhub_run(
    *,
    source_snapshot: Path,
    run_root: Path,
    custom_tools: tuple[DbhubCustomTool, ...],
    max_rows: int = DBHUB_MAX_ROW_CAP,
    synthetic_only: bool = True,
) -> DbhubRun:
    """Create a no-overwrite disposable snapshot and pinned stdio launch contract."""
    if not synthetic_only:
        raise DbhubContractError("DBHub bake-off accepts synthetic snapshots only")
    if not 1 <= max_rows <= DBHUB_MAX_ROW_CAP:
        raise DbhubContractError(f"DBHub row cap must be between 1 and {DBHUB_MAX_ROW_CAP}")
    if not 1 <= len(custom_tools) <= 4:
        raise DbhubContractError("DBHub research requires one to four named custom tools")
    if len({tool.name for tool in custom_tools}) != len(custom_tools):
        raise DbhubContractError("DBHub custom tool names must be unique")
    try:
        with source_snapshot.open("rb") as source:
            header = source.read(len(_SQLITE_HEADER))
    except OSError as error:
        raise DbhubContractError("DBHub source snapshot cannot be read") from error
    if header != _SQLITE_HEADER:
        raise DbhubContractError("DBHub source snapshot is not a SQLite database")
    try:
        run_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise DbhubContractError("DBHub run root already exists") from error
    snapshot_path = (run_root / "synthetic-snapshot.sqlite").resolve()
    shutil.copyfile(source_snapshot, snapshot_path)
    os.chmod(snapshot_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    snapshot_digest = _sha256_file(snapshot_path)
    config_path = run_root / "dbhub-v0.24.0.toml"
    config_path.write_text(
        _render_config(snapshot_path, custom_tools, max_rows),
        encoding="utf-8",
    )
    argv = (
        "npx",
        "--yes",
        f"{DBHUB_PACKAGE}@{DBHUB_VERSION}",
        "--transport",
        "stdio",
        "--config",
        str(config_path),
    )
    run = DbhubRun(
        package=DBHUB_PACKAGE,
        version=DBHUB_VERSION,
        package_integrity=DBHUB_NPM_INTEGRITY,
        snapshot_path=snapshot_path,
        snapshot_sha256=snapshot_digest,
        config_path=config_path,
        argv=argv,
        max_rows=max_rows,
    )
    run.verify_unchanged()
    return run
