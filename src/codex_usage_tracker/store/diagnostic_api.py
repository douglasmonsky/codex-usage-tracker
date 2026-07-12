"""Database-path adapters for focused diagnostic repositories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.large_low_output import query_large_low_output_calls as _large_calls
from codex_usage_tracker.store.repeated_files import query_repeated_file_rediscovery as _files
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.shell_churn import query_shell_churn as _shell_churn


def query_repeated_file_rediscovery(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Return repeated safe file-identity rediscovery candidates."""
    with connect(db_path) as conn:
        init_db(conn)
        return _files(
            conn,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=min_occurrences,
            limit=limit,
            sample_limit=sample_limit,
        )


def query_shell_churn(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Return repeated shell command family churn candidates."""
    with connect(db_path) as conn:
        init_db(conn)
        return _shell_churn(
            conn,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_occurrences=min_occurrences,
            limit=limit,
            sample_limit=sample_limit,
        )


def query_large_low_output_calls(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
) -> dict[str, Any]:
    """Return large aggregate-token calls that produced little output."""
    with connect(db_path) as conn:
        init_db(conn)
        return _large_calls(
            conn,
            since=since,
            until=until,
            thread=thread,
            include_archived=include_archived,
            min_total_tokens=min_total_tokens,
            max_output_tokens=max_output_tokens,
            limit=limit,
        )
