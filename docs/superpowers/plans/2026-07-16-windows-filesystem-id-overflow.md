# Windows Filesystem Identity Overflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Prevent Windows filesystem identifiers wider than signed 64 bits from overflowing SQLite while preserving existing source checkpoints.

**Architecture:** Normalize source device and inode values through one versioned filesystem-ID boundary in store/sources.py. Existing integer rows and new prefixed text rows compare through the same canonical key, while new persistence writes lossless text without changing the SQLite schema.

**Tech Stack:** Python 3.10+, pathlib, sqlite3, pytest, Ruff, mypy

## Global Constraints

- Preserve complete filesystem identifiers without truncation or hashing.
- Keep setup, full refresh, unchanged-source detection, and append-only parsing working on Windows, macOS, and Linux.
- Continue recognizing source identities stored by earlier releases as SQLite integers.
- Do not add a schema migration or force an otherwise unnecessary one-time full reparse.
- Do not change public JSON, CLI, MCP, plugin, or privacy contracts.
- Keep all fixtures synthetic.

---

### Task 1: Fail safely on malformed stored filesystem identities

**Files:**
- Modify: src/codex_usage_tracker/store/sources.py:19-118
- Test: tests/store/test_store_sources.py:35-140

**Interfaces:**
- Consumes: sqlite3.Row values from source_files.source_device and source_files.source_inode.
- Produces: _filesystem_id_key(value: object) -> str | None and canonical fsid-v1 identity comparisons.

- [ ] **Step 1: Write the failing malformed-identity regression test**

Add this test after test_source_logs_requiring_parse_rejects_larger_replacement:

~~~python
def test_source_logs_requiring_parse_reparses_malformed_filesystem_identity(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    conn.execute(
        "UPDATE source_files SET source_inode = ? WHERE source_file = ?",
        ("not-a-filesystem-id", str(source_path)),
    )

    plans = source_logs_requiring_parse(conn.connection, [source_path])

    assert len(plans) == 1
    assert plans[0].replace_existing is True
    assert plans[0].start_byte == 0
    assert plans[0].start_line == 0
~~~

- [ ] **Step 2: Run the test and verify the current integer coercion fails**

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py::test_source_logs_requiring_parse_reparses_malformed_filesystem_identity -q
~~~

Expected: FAIL with ValueError from int(row["source_inode"]).

- [ ] **Step 3: Add canonical filesystem-ID normalization and use it in both comparison paths**

Add the constant and helpers below _PREFIX_TAIL_BYTES:

~~~python
_FILESYSTEM_ID_PREFIX = "fsid-v1:"


def _serialize_filesystem_id(value: int) -> str:
    return f"{_FILESYSTEM_ID_PREFIX}{value}"


def _filesystem_id_key(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _serialize_filesystem_id(value)
    if not isinstance(value, str):
        return None
    payload = value.removeprefix(_FILESYSTEM_ID_PREFIX)
    try:
        identifier = int(payload)
    except ValueError:
        return None
    return _serialize_filesystem_id(identifier)
~~~

Replace _source_metadata_matches with:

~~~python
def _source_metadata_matches(row: sqlite3.Row, metadata: dict[str, int]) -> bool:
    return (
        int(row["size_bytes"]) == metadata["size_bytes"]
        and int(row["mtime_ns"]) == metadata["mtime_ns"]
        and _filesystem_id_key(row["source_device"])
        == _filesystem_id_key(metadata["source_device"])
        and _filesystem_id_key(row["source_inode"])
        == _filesystem_id_key(metadata["source_inode"])
    )
~~~

Replace the two filesystem identity conditions in _can_incrementally_parse_source with:

~~~python
        and _filesystem_id_key(row["source_device"])
        == _filesystem_id_key(metadata["source_device"])
        and _filesystem_id_key(row["source_inode"])
        == _filesystem_id_key(metadata["source_inode"])
~~~

- [ ] **Step 4: Verify the regression and existing source planning tests pass**

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py -q
~~~

Expected: PASS for the complete test module.

- [ ] **Step 5: Commit the safe comparison behavior**

~~~text
git add -- src/codex_usage_tracker/store/sources.py tests/store/test_store_sources.py
git commit -m "fix: normalize stored source filesystem IDs"
~~~

### Task 2: Persist full-width filesystem identities as versioned text

**Files:**
- Modify: src/codex_usage_tracker/store/sources.py:7-277
- Test: tests/store/test_store_sources.py:1-205

**Interfaces:**
- Consumes: arbitrary-precision integer values from Path.stat().st_dev and Path.stat().st_ino.
- Produces: SourceFileMetadata with source_device and source_inode serialized as fsid-v1 text.

- [ ] **Step 1: Add a passing characterization test for legacy integer checkpoints**

Add this test after the malformed-identity test:

~~~python
def test_source_logs_requiring_parse_preserves_legacy_integer_identity(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    stat = source_path.stat()
    conn.execute(
        """
        UPDATE source_files
        SET source_device = ?, source_inode = ?
        WHERE source_file = ?
        """,
        (stat.st_dev, stat.st_ino, str(source_path)),
    )

    assert source_logs_requiring_parse(conn.connection, [source_path]) == []

    with source_path.open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    plans = source_logs_requiring_parse(conn.connection, [source_path])

    assert len(plans) == 1
    assert plans[0].replace_existing is False
    assert plans[0].start_byte == len("{}\n")
    assert plans[0].start_line == 1
~~~

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py::test_source_logs_requiring_parse_preserves_legacy_integer_identity -q
~~~

Expected: PASS before serialization changes; this locks in upgrade compatibility.

- [ ] **Step 2: Write the failing large-identifier persistence regression test**

Add from types import SimpleNamespace near the test imports, then add:

~~~python
def test_upsert_source_file_metadata_persists_large_filesystem_ids_as_text(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    actual_stat = source_path.stat()
    original_stat = Path.stat
    large_device = (1 << 127) + 123
    large_inode = (1 << 127) + 456

    def large_stat(path: Path, *, follow_symlinks: bool = True) -> Any:
        if path == source_path:
            return SimpleNamespace(
                st_size=actual_stat.st_size,
                st_mtime_ns=actual_stat.st_mtime_ns,
                st_dev=large_device,
                st_ino=large_inode,
            )
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", large_stat)

    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )

    row = conn.execute(
        """
        SELECT source_device, source_inode,
               typeof(source_device) AS source_device_type,
               typeof(source_inode) AS source_inode_type
        FROM source_files
        WHERE source_file = ?
        """,
        (str(source_path),),
    ).fetchone()
    assert dict(row) == {
        "source_device": f"fsid-v1:{large_device}",
        "source_inode": f"fsid-v1:{large_inode}",
        "source_device_type": "text",
        "source_inode_type": "text",
    }
~~~

- [ ] **Step 3: Run the large-identifier test and verify SQLite binding overflows**

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py::test_upsert_source_file_metadata_persists_large_filesystem_ids_as_text -q
~~~

Expected: FAIL with OverflowError: Python int too large to convert to SQLite INTEGER.

- [ ] **Step 4: Add the typed metadata boundary and serialize identifiers before persistence**

Change the typing import to:

~~~python
from typing import Any, TypeAlias, TypedDict
~~~

Add this type after SourceParsePlan:

~~~python
class SourceFileMetadata(TypedDict):
    size_bytes: int
    mtime_ns: int
    source_device: str
    source_inode: str
    is_archived: int
~~~

Change _source_parse_plan_from_row to:

~~~python
def _source_parse_plan_from_row(
    path: Path, metadata: SourceFileMetadata, row: sqlite3.Row
) -> SourceParsePlan | None:
~~~

In _source_file_metadata_row, persist the serialized values directly:

~~~python
        "source_device": metadata["source_device"],
        "source_inode": metadata["source_inode"],
~~~

Replace _source_file_metadata with:

~~~python
def _source_file_metadata(path: Path) -> SourceFileMetadata | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "source_device": _serialize_filesystem_id(int(stat.st_dev)),
        "source_inode": _serialize_filesystem_id(int(stat.st_ino)),
        "is_archived": _is_archived_source_file(path),
    }
~~~

Replace _source_metadata_matches with:

~~~python
def _source_metadata_matches(row: sqlite3.Row, metadata: SourceFileMetadata) -> bool:
    return (
        int(row["size_bytes"]) == metadata["size_bytes"]
        and int(row["mtime_ns"]) == metadata["mtime_ns"]
        and _filesystem_id_key(row["source_device"]) == metadata["source_device"]
        and _filesystem_id_key(row["source_inode"]) == metadata["source_inode"]
    )
~~~

Replace _can_incrementally_parse_source with:

~~~python
def _can_incrementally_parse_source(
    path: Path, metadata: SourceFileMetadata, row: sqlite3.Row
) -> bool:
    previous_size = int(row["size_bytes"])
    previous_byte = int(row["parsed_until_byte"])
    expected_tail = str(row["parsed_prefix_tail_hash"] or "")
    return (
        0 < previous_byte <= previous_size < metadata["size_bytes"]
        and _filesystem_id_key(row["source_device"]) == metadata["source_device"]
        and _filesystem_id_key(row["source_inode"]) == metadata["source_inode"]
        and bool(expected_tail)
        and _parsed_prefix_tail_hash(path, previous_byte) == expected_tail
    )
~~~

- [ ] **Step 5: Update the existing persistence assertions**

In test_upsert_source_file_metadata_records_latest_event_and_parser_state, replace the two integer assertions with:

~~~python
    assert row["source_device"] == f"fsid-v1:{source_path.stat().st_dev}"
    assert row["source_inode"] == f"fsid-v1:{source_path.stat().st_ino}"
~~~

- [ ] **Step 6: Verify the red-green cycle and the complete source-store module**

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py::test_upsert_source_file_metadata_persists_large_filesystem_ids_as_text -q
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/pytest tests/store/test_store_sources.py -q
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m mypy src/codex_usage_tracker/store/sources.py
~~~

Expected: all commands PASS with no warnings or type errors.

- [ ] **Step 7: Commit the full-width persistence fix**

~~~text
git add -- src/codex_usage_tracker/store/sources.py tests/store/test_store_sources.py
git commit -m "fix: persist full-width filesystem IDs"
~~~

### Task 3: Validate the packaged fix and prepare the issue PR

**Files:**
- Verify: all changed files
- Build: dist artifacts generated from the isolated worktree

**Interfaces:**
- Consumes: the completed source-store implementation and regression suite.
- Produces: release-ready validation evidence and a focused PR closing issue #278.

- [ ] **Step 1: Run static analysis, tests, coverage, and compilation**

Run each command separately:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m ruff check .
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m mypy
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m compileall src
~~~

Expected: every command exits 0.

- [ ] **Step 2: Validate dashboard JavaScript and release metadata**

Run node --check once for every file returned by:

~~~text
rg --files src/codex_usage_tracker/plugin_data/dashboard -g "dashboard*.js"
~~~

Then run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/check_release.py
git diff --check
~~~

Expected: all commands exit 0.

- [ ] **Step 3: Build and validate distributions**

Run:

~~~text
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m build
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python -m twine check dist/*
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/check_release.py --dist
/Users/Monsky/Developer/Codex/codex-usage-tracker/.venv/bin/python scripts/smoke_installed_package.py
~~~

Expected: build, Twine validation, distribution checks, and installed-package smoke tests all exit 0.

- [ ] **Step 4: Review the final branch**

Run:

~~~text
git status --short --branch
git diff --stat main...HEAD
git diff main...HEAD
git log --oneline main..HEAD
~~~

Confirm only the approved spec, plan, source implementation, and synthetic regression tests are committed; .idea remains untracked and excluded from every commit.

- [ ] **Step 5: Obtain independent code review, address material findings, rerun affected checks, then push and open a PR**

The PR title is:

~~~text
fix: preserve full-width Windows filesystem IDs
~~~

The PR body must summarize the lossless fsid-v1 representation, legacy integer compatibility, lack of schema migration, red-green regression tests, and full validation. Include Closes #278.
