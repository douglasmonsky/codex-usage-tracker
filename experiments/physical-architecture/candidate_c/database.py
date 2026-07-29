"""Candidate C database construction, publication, tails, and queries."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, overload

import shared

from .records import ParsedRecord, parse_fixture_records
from .schema import CANDIDATE_ID, SCHEMA_VERSION, create_indexes, create_schema, index_names

Cursor = tuple[int, int, int, str, str]


class CandidateCError(RuntimeError):
    pass


@dataclass(frozen=True)
class MutationStats:
    facts_inserted: int = 0
    facts_updated: int = 0
    facts_recanonicalized: int = 0
    facts_unchanged: int = 0
    dirty_keys: int = 0
    projection_rows_read: int = 0
    projection_rows_written: int = 0
    source_bytes_parsed: int = 0
    source_files_parsed: int = 0
    malformed_lines: int = 0


@dataclass(frozen=True)
class PublicationArtifact:
    publication_id: str
    path: Path
    prior_path: Path | None
    stats: MutationStats


@dataclass(frozen=True)
class QueryPage:
    rows: tuple[dict[str, Any], ...]
    next_cursor: Cursor | None
    exact_count: int | None = None


@dataclass(frozen=True)
class StorageStats:
    database_bytes: int
    table_bytes: int
    index_bytes: int
    free_list_bytes: int
    wal_bytes: int
    journal_bytes: int
    page_count: int
    page_size: int


@dataclass(frozen=True)
class RowCounts:
    fact_rows: int
    lifecycle_rows: int
    occurrence_rows: int
    projection_rows: int


_ALWAYS_SELECTED = frozenset(
    {
        "oracle_case",
        "selector_anchor",
        "slice_control",
        "source_revision",
    }
)
_SESSION_EVENTS = frozenset(
    {
        "activity",
        "compaction_boundary",
        "late_parent",
        "session_start",
        "session_terminal",
    }
)
_TURN_EVENTS = frozenset({"state_change", "tool_start", "tool_terminal", "turn_start"})


class CandidateCDatabase:
    """Own one disposable Candidate C publication family."""

    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root.resolve()
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root = self.run_root / "candidate-c-artifacts"
        self.artifact_root.mkdir(exist_ok=True)
        self.sidecar_path = self.run_root / "candidate-c-current.json"

    def build(
        self,
        fixture: shared.FixtureBundle,
        *,
        label: str,
        history_selection: str = "all_time",
        parser_workers: int = 1,
        index_mode: str = "present",
        publish: bool = True,
    ) -> PublicationArtifact:
        """Build a deterministic isolated artifact and optionally publish it."""
        if index_mode not in {"present", "deferred", "rebuilt"}:
            raise CandidateCError(f"unknown index mode: {index_mode}")
        publication_id = self._publication_id(
            fixture=fixture,
            label=label,
            parent=None,
            details={
                "history_selection": history_selection,
                "index_mode": index_mode,
                "parser_workers": parser_workers,
            },
        )
        artifact_path = self._artifact_path(publication_id)
        prior = self.current_artifact(optional=True)
        if artifact_path.exists():
            self._validate_artifact(artifact_path)
            if publish:
                self._promote(publication_id, artifact_path)
            return PublicationArtifact(
                publication_id=publication_id,
                path=artifact_path,
                prior_path=prior,
                stats=MutationStats(facts_unchanged=self.row_counts(artifact_path).fact_rows),
            )

        parse_result = parse_fixture_records(fixture, parser_workers=parser_workers)
        selected = _select_records(parse_result.records, fixture, history_selection)
        partial = artifact_path.with_suffix(".building")
        partial.unlink(missing_ok=True)
        connection = sqlite3.connect(partial)
        try:
            _configure_connection(connection)
            create_schema(connection, indexes=index_mode == "present")
            _write_metadata(
                connection,
                fixture,
                publication_id=publication_id,
                history_selection=history_selection,
            )
            _insert_manifestations(connection, fixture)
            inserted, dirty = _insert_records(connection, selected)
            read_rows, written_rows = _refresh_dirty_projections(connection)
            if index_mode in {"deferred", "rebuilt"}:
                create_indexes(connection)
            if index_mode == "rebuilt":
                connection.execute("REINDEX")
            connection.execute("ANALYZE")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except BaseException:
            connection.close()
            partial.unlink(missing_ok=True)
            raise
        connection.close()
        os.replace(partial, artifact_path)
        self._validate_artifact(artifact_path)
        if publish:
            self._promote(publication_id, artifact_path)
        return PublicationArtifact(
            publication_id=publication_id,
            path=artifact_path,
            prior_path=prior,
            stats=MutationStats(
                facts_inserted=inserted,
                dirty_keys=dirty,
                projection_rows_read=read_rows,
                projection_rows_written=written_rows,
                source_bytes_parsed=parse_result.parsed_bytes,
                source_files_parsed=len(fixture.sources),
                malformed_lines=parse_result.malformed_lines,
            ),
        )

    def build_unpublished_upgrade(
        self,
        fixture: shared.FixtureBundle,
        *,
        label: str,
    ) -> PublicationArtifact:
        """Build and validate a schema upgrade without changing the active pointer."""
        prior = self.current_artifact(optional=True)
        artifact = self.build(
            fixture,
            label=f"{label}:schema-upgrade",
            history_selection="all_time",
            parser_workers=1,
            index_mode="rebuilt",
            publish=False,
        )
        connection = sqlite3.connect(artifact.path)
        try:
            _configure_staging_connection(connection)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            connection.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES ('publication_state', 'unpublished')
                """
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO metadata (key, value)
                VALUES ('upgrade_from_schema_version', ?)
                """,
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
        finally:
            connection.close()
        self._validate_artifact(artifact.path)
        if self.current_artifact(optional=True) != prior:
            raise CandidateCError("unpublished upgrade changed the active publication")
        return PublicationArtifact(
            artifact.publication_id,
            artifact.path,
            prior,
            artifact.stats,
        )

    def apply_ordinary(
        self,
        fixture: shared.FixtureBundle,
        *,
        change: str,
        label: str,
    ) -> PublicationArtifact:
        """Apply one bounded tail without reparsing a source file."""
        prior = self.current_artifact()
        publication_id = self._publication_id(
            fixture=fixture,
            label=label,
            parent=prior.name,
            details={"change": change, "protocol": "ordinary_tail"},
        )
        artifact_path = self._artifact_path(publication_id)
        if artifact_path.exists():
            self._promote(publication_id, artifact_path)
            return PublicationArtifact(
                publication_id,
                artifact_path,
                prior,
                MutationStats(facts_unchanged=self.row_counts(artifact_path).fact_rows),
            )
        shutil.copyfile(prior, artifact_path)
        connection = sqlite3.connect(artifact_path)
        try:
            _configure_staging_connection(connection)
            inserted, updated = _apply_ordinary_change(connection, change, label)
            dirty = _dirty_key_count(connection)
            read_rows, written_rows = _refresh_dirty_projections(connection)
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('publication_id', ?)",
                (publication_id,),
            )
            connection.commit()
        except BaseException:
            connection.close()
            artifact_path.unlink(missing_ok=True)
            raise
        connection.close()
        self._validate_artifact(artifact_path)
        self._promote(publication_id, artifact_path)
        return PublicationArtifact(
            publication_id,
            artifact_path,
            prior,
            MutationStats(
                facts_inserted=inserted,
                facts_updated=updated,
                dirty_keys=dirty,
                projection_rows_read=read_rows,
                projection_rows_written=written_rows,
            ),
        )

    def apply_unsafe(
        self,
        fixture: shared.FixtureBundle,
        *,
        change: str,
        label: str,
    ) -> PublicationArtifact:
        """Use a new isolated artifact for changes that can invalidate ownership."""
        if change not in {
            "source_truncation",
            "source_replacement",
            "canonical_owner_change",
            "identity_normalization_change",
            "projection_schema_change",
            "recanonicalization",
            "database_schema_upgrade",
        }:
            raise CandidateCError(f"unknown unsafe change: {change}")
        artifact = self.build(
            fixture,
            label=f"{label}:isolated:{change}",
            history_selection="all_time",
            parser_workers=1,
            index_mode="rebuilt",
            publish=False,
        )
        connection = sqlite3.connect(artifact.path)
        try:
            _configure_staging_connection(connection)
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('unsafe_change', ?)",
                (change,),
            )
            if change == "database_schema_upgrade":
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
            connection.commit()
        finally:
            connection.close()
        self._validate_artifact(artifact.path)
        self._promote(artifact.publication_id, artifact.path)
        return PublicationArtifact(
            artifact.publication_id,
            artifact.path,
            artifact.prior_path,
            MutationStats(
                facts_inserted=artifact.stats.facts_inserted,
                facts_recanonicalized=(
                    self.row_counts(artifact.path).fact_rows
                    if change in {"canonical_owner_change", "recanonicalization"}
                    else 0
                ),
                dirty_keys=artifact.stats.dirty_keys,
                projection_rows_read=artifact.stats.projection_rows_read,
                projection_rows_written=artifact.stats.projection_rows_written,
                source_bytes_parsed=artifact.stats.source_bytes_parsed,
                source_files_parsed=artifact.stats.source_files_parsed,
            ),
        )

    def apply_source_phase(
        self,
        fixture: shared.FixtureBundle,
        *,
        group: str,
        label: str,
    ) -> PublicationArtifact:
        """Record one CK-03 lifecycle phase in a new immutable publication."""
        mappings = fixture.manifest.get("phase_occurrence_mappings")
        if not isinstance(mappings, Mapping) or group not in mappings:
            raise CandidateCError(f"unknown source lifecycle phase: {group}")
        prior = self.current_artifact()
        publication_id = self._publication_id(
            fixture=fixture,
            label=label,
            parent=prior.name,
            details={"phase": group, "protocol": "isolated_artifact"},
        )
        artifact_path = self._artifact_path(publication_id)
        if artifact_path.exists():
            self._validate_artifact(artifact_path)
            self._promote(publication_id, artifact_path)
            return PublicationArtifact(
                publication_id,
                artifact_path,
                prior,
                MutationStats(facts_unchanged=self.row_counts(artifact_path).fact_rows),
            )
        shutil.copyfile(prior, artifact_path)
        connection = sqlite3.connect(artifact_path)
        try:
            _configure_staging_connection(connection)
            phase_records = _load_phase_records(fixture, group)
            mapping = mappings[group]
            if not isinstance(mapping, Mapping):
                raise CandidateCError("source lifecycle mapping is not an object")
            disposition = {
                str(call_id): name
                for name in ("inserted", "preserved", "removed")
                for call_id in _string_sequence(mapping.get(name))
            }
            for call_id, revision, event_at_us in phase_records:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO source_phase_occurrences (
                        group_name, call_id, revision, disposition, event_at_us
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (group, call_id, revision, disposition[call_id], event_at_us),
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('publication_id', ?)",
                (publication_id,),
            )
            connection.commit()
        except BaseException:
            connection.close()
            artifact_path.unlink(missing_ok=True)
            raise
        connection.close()
        self._promote(publication_id, artifact_path)
        return PublicationArtifact(
            publication_id,
            artifact_path,
            prior,
            MutationStats(
                facts_inserted=sum(1 for value in disposition.values() if value == "inserted"),
                facts_recanonicalized=(
                    sum(1 for value in disposition.values() if value == "preserved")
                ),
            ),
        )

    def query_question(
        self,
        fixture: shared.FixtureBundle,
        question_id: str,
        *,
        limit: int = 25,
        exact_count: bool = False,
    ) -> tuple[dict[str, Any], bool, tuple[str, ...]]:
        """Execute the typed oracle-case plan and compare it with the frozen oracle."""
        if limit < 1 or limit > 100:
            raise CandidateCError("query limit must be between 1 and 100")
        artifact = self.current_artifact()
        connection = _open_readonly(artifact)
        sql = """
            SELECT
                oracle_cases.oracle_id,
                oracle_cases.variant,
                oracle_cases.observed_facts_json,
                oracle_cases.selector_ids_json,
                oracle_cases.inputs_json,
                event_backbone.manifestation_id,
                event_backbone.revision,
                event_backbone.source_path,
                event_backbone.record_ordinal,
                event_backbone.byte_start,
                event_backbone.byte_end
            FROM oracle_cases INDEXED BY oracle_cases_question
            JOIN event_backbone
              ON event_backbone.occurrence_id = oracle_cases.occurrence_id
            WHERE oracle_cases.question_id = ?
            ORDER BY oracle_cases.variant, oracle_cases.oracle_id
            LIMIT ?
        """
        started = time.perf_counter_ns()
        rows = connection.execute(sql, (question_id, limit)).fetchall()
        latency = time.perf_counter_ns() - started
        plan = tuple(
            str(row[3])
            for row in connection.execute(
                f"EXPLAIN QUERY PLAN {sql}",
                (question_id, limit),
            )
        )
        total = (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM oracle_cases WHERE question_id = ?",
                    (question_id,),
                ).fetchone()[0]
            )
            if exact_count
            else None
        )
        connection.close()
        result_rows = tuple(_oracle_result_row(row) for row in rows)
        equivalent = _oracle_equivalent(fixture, result_rows)
        payload = {
            "schema": "codex-usage-tracker.candidate-c-query.v1",
            "candidate_id": CANDIDATE_ID,
            "question_id": question_id,
            "rows": result_rows,
            "exact_count": total,
            "sql_latency_ns": latency,
        }
        return payload, equivalent, plan

    def evidence_page(
        self,
        *,
        after: Cursor | None = None,
        limit: int = 100,
        exact_count: bool = False,
    ) -> QueryPage:
        """Read one deterministic keyset page from the sole sequence authority."""
        if limit < 1 or limit > 500:
            raise CandidateCError("evidence page limit must be between 1 and 500")
        connection = _open_readonly(self.current_artifact())
        if after is None:
            where = ""
            parameters: tuple[Any, ...] = (limit,)
        else:
            where = """
                WHERE (
                    event_at_us,
                    event_kind_order,
                    source_order,
                    logical_id,
                    occurrence_id
                ) > (?, ?, ?, ?, ?)
            """
            parameters = (*after, limit)
        rows = connection.execute(
            f"""
            SELECT
                event_at_us,
                event_kind_order,
                source_order,
                logical_id,
                occurrence_id,
                event_type,
                manifestation_id,
                revision,
                source_path,
                record_ordinal,
                byte_start,
                byte_end,
                canonical_owner
            FROM event_backbone INDEXED BY event_backbone_total_order
            {where}
            ORDER BY
                event_at_us,
                event_kind_order,
                source_order,
                logical_id,
                occurrence_id
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        total = (
            int(connection.execute("SELECT COUNT(*) FROM event_backbone").fetchone()[0])
            if exact_count
            else None
        )
        connection.close()
        result_rows = tuple(_evidence_row(row) for row in rows)
        cursor = _cursor_from_evidence(result_rows[-1]) if len(result_rows) == limit else None
        return QueryPage(result_rows, cursor, total)

    def evidence_page_at_position(
        self,
        *,
        page_position: int,
        limit: int = 100,
        exact_count: bool = False,
    ) -> tuple[QueryPage, int]:
        """Reach a one-based deep page exclusively through keyset cursors."""
        if page_position < 1:
            raise CandidateCError("evidence page position must be positive")
        cursor: Cursor | None = None
        pages_traversed = 0
        for _ in range(page_position - 1):
            page = self.evidence_page(after=cursor, limit=limit)
            pages_traversed += 1
            cursor = page.next_cursor
            if cursor is None:
                return QueryPage((), None, page.exact_count if exact_count else None), pages_traversed
        page = self.evidence_page(
            after=cursor,
            limit=limit,
            exact_count=exact_count,
        )
        return page, pages_traversed + 1

    @overload
    def current_artifact(self, *, optional: Literal[False] = False) -> Path: ...

    @overload
    def current_artifact(self, *, optional: Literal[True]) -> Path | None: ...

    def current_artifact(self, *, optional: bool = False) -> Path | None:
        if not self.sidecar_path.exists():
            if optional:
                return None
            raise CandidateCError("candidate has no published artifact")
        try:
            payload = json.loads(self.sidecar_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CandidateCError("candidate publication sidecar is invalid") from error
        relative = payload.get("artifact")
        if not isinstance(relative, str) or Path(relative).name != relative:
            raise CandidateCError("candidate publication sidecar escapes artifact root")
        artifact = self.artifact_root / relative
        if not artifact.is_file() or not artifact.resolve().is_relative_to(self.run_root):
            raise CandidateCError("candidate publication artifact is missing")
        return artifact

    def row_counts(self, path: Path | None = None) -> RowCounts:
        artifact = path or self.current_artifact()
        if artifact is None:
            raise CandidateCError("candidate has no publication")
        connection = _open_readonly(artifact)
        fact_rows = _sum_counts(
            connection,
            (
                "model_calls",
                "state_changes",
                "allowance_observations",
                "allowance_compatibility",
                "compaction_boundaries",
                "activities",
                "parent_observations",
                "selector_anchors",
                "oracle_cases",
                "source_phase_occurrences",
            ),
        )
        lifecycle_rows = _sum_counts(
            connection,
            ("sessions", "session_transitions", "turns", "tool_invocations", "tool_transitions"),
        )
        occurrence_rows = int(
            connection.execute("SELECT COUNT(*) FROM event_backbone").fetchone()[0]
        )
        projection_rows = _sum_counts(
            connection,
            ("session_usage_current", "model_effort_current"),
        )
        connection.close()
        return RowCounts(fact_rows, lifecycle_rows, occurrence_rows, projection_rows)

    def storage_stats(self, path: Path | None = None) -> StorageStats:
        artifact = path or self.current_artifact()
        if artifact is None:
            raise CandidateCError("candidate has no publication")
        connection = _open_readonly(artifact)
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        free_list = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
        table_bytes, index_bytes = _dbstat_bytes(connection)
        connection.close()
        wal = artifact.with_name(artifact.name + "-wal")
        journal = artifact.with_name(artifact.name + "-journal")
        return StorageStats(
            database_bytes=artifact.stat().st_size,
            table_bytes=table_bytes,
            index_bytes=index_bytes,
            free_list_bytes=free_list * page_size,
            wal_bytes=wal.stat().st_size if wal.exists() else 0,
            journal_bytes=journal.stat().st_size if journal.exists() else 0,
            page_count=page_count,
            page_size=page_size,
        )

    def _publication_id(
        self,
        *,
        fixture: shared.FixtureBundle,
        label: str,
        parent: str | None,
        details: Mapping[str, object],
    ) -> str:
        digest = shared.canonical_sha256(
            {
                "candidate": CANDIDATE_ID,
                "schema_version": SCHEMA_VERSION,
                "fixture_manifest_digest": fixture.manifest_digest,
                "fixture_oracle_digest": fixture.oracle_digest,
                "label": label,
                "parent": parent,
                "details": dict(details),
            }
        )
        return f"candidate-c:{digest}"

    def _artifact_path(self, publication_id: str) -> Path:
        return self.artifact_root / f"{publication_id.removeprefix('candidate-c:')}.sqlite"

    def _promote(self, publication_id: str, artifact_path: Path) -> None:
        payload = shared.canonical_json_bytes(
            {
                "schema": "codex-usage-tracker.candidate-c-publication.v1",
                "publication_id": publication_id,
                "artifact": artifact_path.name,
            }
        )
        temporary = self.sidecar_path.with_suffix(".next")
        temporary.write_bytes(payload)
        os.replace(temporary, self.sidecar_path)

    @staticmethod
    def _validate_artifact(path: Path) -> None:
        connection = _open_readonly(path)
        integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        connection.close()
        if integrity != "ok":
            raise CandidateCError("candidate artifact failed SQLite integrity check")
        if version < SCHEMA_VERSION or metadata.get("candidate_id") != CANDIDATE_ID:
            raise CandidateCError("candidate artifact has the wrong schema identity")


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA page_size = 4096")
    connection.execute("PRAGMA cache_size = -20000")
    connection.execute("PRAGMA mmap_size = 0")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA wal_autocheckpoint = 1000")


def _configure_staging_connection(connection: sqlite3.Connection) -> None:
    """Tune an unpublished disposable copy whose prior artifact is the rollback."""
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = OFF")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA cache_size = -20000")
    connection.execute("PRAGMA mmap_size = 0")
    connection.execute("PRAGMA temp_store = MEMORY")


def _open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _write_metadata(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
    *,
    publication_id: str,
    history_selection: str,
) -> None:
    metadata = {
        "candidate_id": CANDIDATE_ID,
        "fixture_manifest_digest": fixture.manifest_digest,
        "fixture_oracle_digest": fixture.oracle_digest,
        "fixture_revision": fixture.fixture_revision,
        "history_selection": history_selection,
        "publication_id": publication_id,
        "schema_identity": "codex-usage-tracker.physical-bakeoff.candidate-c.v1",
        "sequence_authority": "event_backbone",
    }
    connection.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        tuple(sorted(metadata.items())),
    )


def _insert_manifestations(
    connection: sqlite3.Connection,
    fixture: shared.FixtureBundle,
) -> None:
    manifest_sources = fixture.manifest.get("sources")
    if not isinstance(manifest_sources, Sequence) or isinstance(
        manifest_sources,
        (str, bytes),
    ):
        raise CandidateCError("fixture manifestation inventory is missing")
    entries = {
        str(entry["path"]): entry
        for entry in manifest_sources
        if isinstance(entry, Mapping) and isinstance(entry.get("path"), str)
    }
    for source in fixture.sources:
        path = source.relative_path.as_posix()
        entry = entries.get(path, {})
        connection.execute(
            """
            INSERT INTO source_manifestations (
                manifestation_id,
                revision,
                source_path,
                logical_source,
                adapter_version,
                source_state,
                byte_count,
                record_count,
                content_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.manifestation_id,
                source.revision,
                path,
                str(entry.get("logical_source", path)),
                source.adapter_version,
                source.state,
                source.byte_count,
                source.record_count,
                source.sha256,
            ),
        )


def _select_records(
    records: tuple[ParsedRecord, ...],
    fixture: shared.FixtureBundle,
    history_selection: str,
) -> tuple[ParsedRecord, ...]:
    if history_selection == "all_time":
        return records
    history = fixture.manifest.get("history")
    if not isinstance(history, Mapping):
        raise CandidateCError("fixture history contract is missing")
    windows = history.get("windows")
    if not isinstance(windows, Mapping):
        raise CandidateCError("fixture history windows are missing")
    window = windows.get(history_selection)
    if not isinstance(window, Mapping):
        raise CandidateCError(f"fixture has no history selection: {history_selection}")
    start = window.get("start_us")
    end = window.get("end_us")
    if not isinstance(start, int) or not isinstance(end, int):
        raise CandidateCError("fixture history selection has invalid boundaries")
    selected_calls = tuple(
        record
        for record in records
        if record.event_type == "model_call"
        and start <= record.event_at_us <= end
        and (
            history_selection != "current_session"
            or record.payload.get("session_id") == window.get("session_id")
        )
    )
    sessions = {
        str(record.payload["session_id"])
        for record in selected_calls
        if isinstance(record.payload.get("session_id"), str)
    }
    turns = {
        str(record.payload["turn_id"])
        for record in selected_calls
        if isinstance(record.payload.get("turn_id"), str)
    }
    return tuple(
        record
        for record in records
        if record.event_type in _ALWAYS_SELECTED
        or (record.event_type == "model_call" and record in selected_calls)
        or (
            record.event_type in _SESSION_EVENTS
            and (
                record.payload.get("session_id") in sessions
                or record.payload.get("child_session_id") in sessions
            )
        )
        or (
            record.event_type in _TURN_EVENTS
            and (
                record.payload.get("turn_id") in turns
                or record.payload.get("session_id") in sessions
            )
        )
        or (
            record.event_type in {"allowance_observation", "allowance_compatibility"}
            and start <= record.event_at_us <= end
        )
    )


def _canonical_model_occurrences(records: tuple[ParsedRecord, ...]) -> frozenset[str]:
    owners: dict[str, ParsedRecord] = {}
    state_priority = {"active": 0, "archived": 1, "replaced": 2, "truncated": 3}
    for record in records:
        if record.event_type != "model_call":
            continue
        current = owners.get(record.logical_id)
        candidate_key = (
            state_priority.get(record.source_state, 9),
            record.source_path,
            record.record_ordinal,
        )
        if current is None:
            owners[record.logical_id] = record
            continue
        current_key = (
            state_priority.get(current.source_state, 9),
            current.source_path,
            current.record_ordinal,
        )
        if candidate_key < current_key:
            owners[record.logical_id] = record
    return frozenset(record.occurrence_id for record in owners.values())


def _insert_records(
    connection: sqlite3.Connection,
    records: tuple[ParsedRecord, ...],
) -> tuple[int, int]:
    owners = _canonical_model_occurrences(records)
    inserted = 0
    for record in records:
        canonical_owner = record.event_type != "model_call" or record.occurrence_id in owners
        connection.execute(
            """
            INSERT INTO event_backbone (
                occurrence_id,
                logical_id,
                event_type,
                event_at_us,
                event_kind_order,
                source_order,
                manifestation_id,
                revision,
                source_path,
                record_ordinal,
                byte_start,
                byte_end,
                payload_sha256,
                canonical_owner
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.occurrence_id,
                record.logical_id,
                record.event_type,
                record.event_at_us,
                record.event_kind_order,
                record.source_order,
                record.manifestation_id,
                record.revision,
                record.source_path,
                record.record_ordinal,
                record.byte_start,
                record.byte_end,
                record.payload_sha256,
                int(canonical_owner),
            ),
        )
        inserted += _insert_typed_record(connection, record, canonical_owner)
    dirty = _dirty_key_count(connection)
    return inserted, dirty


def _insert_typed_record(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    canonical_owner: bool,
) -> int:
    handlers = {
        "activity": _insert_activity,
        "allowance_compatibility": _insert_allowance_compatibility,
        "allowance_observation": _insert_allowance_observation,
        "compaction_boundary": _insert_compaction,
        "late_parent": _apply_late_parent,
        "model_call": _insert_model_call,
        "oracle_case": _insert_oracle_case,
        "selector_anchor": _insert_selector_anchor,
        "session_start": _insert_session_start,
        "session_terminal": _insert_session_terminal,
        "state_change": _insert_state_change,
        "tool_start": _insert_tool_start,
        "tool_terminal": _insert_tool_terminal,
        "turn_start": _insert_turn_start,
    }
    handler = handlers.get(record.event_type)
    if handler is None:
        return 0
    return handler(connection, record, canonical_owner)


def _ensure_session(connection: sqlite3.Connection, record: ParsedRecord, session_id: str) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO sessions (
            session_id,
            first_occurrence_id,
            started_at_us,
            state
        ) VALUES (?, ?, ?, 'unknown')
        """,
        (session_id, record.occurrence_id, record.event_at_us),
    )


def _ensure_turn(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    session_id: str,
    turn_id: str,
) -> None:
    _ensure_session(connection, record, session_id)
    connection.execute(
        """
        INSERT OR IGNORE INTO turns (
            turn_id,
            first_occurrence_id,
            session_id,
            started_at_us,
            state
        ) VALUES (?, ?, ?, ?, 'unknown')
        """,
        (turn_id, record.occurrence_id, session_id, record.event_at_us),
    )


def _insert_session_start(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    connection.execute(
        """
        INSERT INTO sessions (
            session_id,
            first_occurrence_id,
            project_id,
            parent_session_id,
            started_at_us,
            state
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (session_id) DO UPDATE SET
            project_id = excluded.project_id,
            parent_session_id = excluded.parent_session_id,
            started_at_us = MIN(sessions.started_at_us, excluded.started_at_us),
            state = excluded.state
        """,
        (
            session_id,
            record.occurrence_id,
            payload.get("project_id"),
            payload.get("parent_session_id"),
            record.event_at_us,
            str(payload.get("state", "running")),
        ),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO session_transitions (
            occurrence_id, session_id, state, completion_basis
        ) VALUES (?, ?, ?, NULL)
        """,
        (record.occurrence_id, session_id, str(payload.get("state", "running"))),
    )
    return 2


def _insert_session_terminal(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    _ensure_session(connection, record, session_id)
    state = str(payload.get("state", "unknown"))
    completion_basis = payload.get("completion_basis")
    connection.execute(
        """
        UPDATE sessions
        SET terminal_at_us = ?, state = ?, completion_basis = ?
        WHERE session_id = ?
        """,
        (record.event_at_us, state, completion_basis, session_id),
    )
    connection.execute(
        """
        INSERT INTO session_transitions (
            occurrence_id, session_id, state, completion_basis
        ) VALUES (?, ?, ?, ?)
        """,
        (record.occurrence_id, session_id, state, completion_basis),
    )
    return 1


def _insert_turn_start(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    _ensure_session(connection, record, session_id)
    connection.execute(
        """
        INSERT INTO turns (
            turn_id,
            first_occurrence_id,
            session_id,
            started_at_us,
            state
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (turn_id) DO UPDATE SET
            started_at_us = MIN(turns.started_at_us, excluded.started_at_us),
            state = excluded.state
        """,
        (
            turn_id,
            record.occurrence_id,
            session_id,
            record.event_at_us,
            str(payload.get("state", "running")),
        ),
    )
    return 1


def _insert_model_call(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    canonical_owner: bool,
) -> int:
    if not canonical_owner:
        return 0
    payload = record.payload
    call_id = str(payload["call_id"])
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    _ensure_turn(connection, record, session_id, turn_id)
    tokens = payload.get("tokens")
    token_values = tokens if isinstance(tokens, Mapping) else {}
    connection.execute(
        """
        INSERT INTO model_calls (
            call_id,
            canonical_occurrence_id,
            session_id,
            turn_id,
            event_at_us,
            model,
            reasoning_effort,
            context_window_tokens,
            uncached_input_tokens,
            cached_input_tokens,
            reasoning_tokens,
            output_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            call_id,
            record.occurrence_id,
            session_id,
            turn_id,
            record.event_at_us,
            str(payload.get("model", "unknown")),
            payload.get("reasoning_effort"),
            payload.get("context_window_tokens"),
            token_values.get("uncached_input_tokens"),
            token_values.get("cached_input_tokens"),
            token_values.get("reasoning_tokens"),
            token_values.get("output_tokens"),
        ),
    )
    _mark_call_dirty(
        connection,
        session_id,
        str(payload.get("model", "unknown")),
        payload.get("reasoning_effort"),
    )
    return 1


def _insert_tool_start(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    tool_id = str(payload["tool_id"])
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    _ensure_turn(connection, record, session_id, turn_id)
    connection.execute(
        """
        INSERT INTO tool_invocations (
            tool_id,
            first_occurrence_id,
            session_id,
            turn_id,
            resource_id,
            transport_name,
            semantic_operation,
            write_intent,
            started_at_us,
            state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (tool_id) DO NOTHING
        """,
        (
            tool_id,
            record.occurrence_id,
            session_id,
            turn_id,
            payload.get("resource_id"),
            str(payload.get("transport_name", "unknown")),
            str(payload.get("semantic_operation", "unknown")),
            int(bool(payload.get("write_intent", False))),
            record.event_at_us,
            str(payload.get("state", "running")),
        ),
    )
    connection.execute(
        "INSERT INTO tool_transitions (occurrence_id, tool_id, state) VALUES (?, ?, ?)",
        (record.occurrence_id, tool_id, str(payload.get("state", "running"))),
    )
    return 2


def _insert_tool_terminal(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    tool_id = str(payload["tool_id"])
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    duration = payload.get("duration_us")
    started_at_us = (
        record.event_at_us - duration
        if isinstance(duration, int) and not isinstance(duration, bool)
        else record.event_at_us
    )
    _ensure_turn(connection, record, session_id, turn_id)
    connection.execute(
        """
        INSERT INTO tool_invocations (
            tool_id,
            first_occurrence_id,
            session_id,
            turn_id,
            resource_id,
            transport_name,
            semantic_operation,
            write_intent,
            started_at_us,
            terminal_at_us,
            state,
            duration_us,
            output_bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (tool_id) DO UPDATE SET
            terminal_at_us = excluded.terminal_at_us,
            state = excluded.state,
            duration_us = excluded.duration_us,
            output_bytes = excluded.output_bytes
        """,
        (
            tool_id,
            record.occurrence_id,
            session_id,
            turn_id,
            payload.get("resource_id"),
            str(payload.get("transport_name", "unknown")),
            str(payload.get("semantic_operation", "unknown")),
            int(bool(payload.get("write_intent", False))),
            started_at_us,
            record.event_at_us,
            str(payload.get("state", "unknown")),
            payload.get("duration_us"),
            payload.get("output_bytes"),
        ),
    )
    connection.execute(
        "INSERT INTO tool_transitions (occurrence_id, tool_id, state) VALUES (?, ?, ?)",
        (record.occurrence_id, tool_id, str(payload.get("state", "unknown"))),
    )
    return 1


def _insert_state_change(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    _ensure_turn(connection, record, session_id, turn_id)
    causal = bool(payload.get("causal_attribution", False))
    if causal:
        raise CandidateCError("state changes cannot assert causal attribution")
    connection.execute(
        """
        INSERT INTO state_changes (
            change_id,
            occurrence_id,
            session_id,
            turn_id,
            resource_id,
            change_kind,
            preceding_activity_count,
            causal_attribution
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            str(payload["change_id"]),
            record.occurrence_id,
            session_id,
            turn_id,
            str(payload["resource_id"]),
            str(payload.get("change_kind", "unknown")),
            int(payload.get("preceding_activity_count", 0)),
        ),
    )
    return 1


def _insert_allowance_observation(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    connection.execute(
        """
        INSERT INTO allowance_observations (
            observation_id,
            occurrence_id,
            provider,
            plan_identity,
            limit_id,
            cycle_id,
            reset_identity,
            window_kind,
            observation_ordinal,
            used_percent,
            remaining_percent,
            event_at_us
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.logical_id,
            record.occurrence_id,
            str(payload["provider"]),
            str(payload["plan_identity"]),
            str(payload["limit_id"]),
            str(payload["cycle_id"]),
            str(payload["reset_identity"]),
            str(payload["window_kind"]),
            int(payload["observation_ordinal"]),
            payload.get("used_percent"),
            payload.get("remaining_percent"),
            record.event_at_us,
        ),
    )
    return 1


def _insert_allowance_compatibility(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    connection.execute(
        """
        INSERT INTO allowance_compatibility (
            occurrence_id,
            start_observation_id,
            end_observation_id,
            compatibility_key
        ) VALUES (?, ?, ?, ?)
        """,
        (
            record.occurrence_id,
            str(payload["start_observation_id"]),
            str(payload["end_observation_id"]),
            _canonical_text(payload.get("compatibility_tuple", {})),
        ),
    )
    return 1


def _insert_compaction(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    _ensure_session(connection, record, session_id)
    connection.execute(
        """
        INSERT INTO compaction_boundaries (
            compaction_id,
            occurrence_id,
            session_id,
            before_context_epoch,
            after_context_epoch
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            str(payload["compaction_id"]),
            record.occurrence_id,
            session_id,
            str(payload["before_context_epoch"]),
            str(payload["after_context_epoch"]),
        ),
    )
    return 1


def _insert_activity(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    session_id = str(payload["session_id"])
    turn_id = str(payload["turn_id"])
    _ensure_turn(connection, record, session_id, turn_id)
    connection.execute(
        """
        INSERT INTO activities (
            activity_id, occurrence_id, session_id, turn_id, activity_kind, state
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(payload["activity_id"]),
            record.occurrence_id,
            session_id,
            turn_id,
            str(payload["activity_kind"]),
            str(payload["state"]),
        ),
    )
    return 1


def _insert_selector_anchor(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    kind = str(payload["selector_kind"])
    logical_id = str(payload["logical_id"])
    selector = f"{kind}:{logical_id}"
    connection.execute(
        """
        INSERT INTO selector_anchors (
            selector, logical_id, selector_kind, occurrence_id
        ) VALUES (?, ?, ?, ?)
        """,
        (selector, logical_id, kind, record.occurrence_id),
    )
    return 1


def _insert_oracle_case(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    connection.execute(
        """
        INSERT INTO oracle_cases (
            oracle_id,
            occurrence_id,
            question_id,
            variant,
            slice_name,
            observed_facts_json,
            selector_ids_json,
            inputs_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(payload["oracle_id"]),
            record.occurrence_id,
            str(payload["question_id"]),
            str(payload["variant"]),
            str(payload["slice"]),
            _canonical_text(payload.get("observed_facts", {})),
            _canonical_text(payload.get("selector_ids", {})),
            _canonical_text(payload.get("inputs", {})),
        ),
    )
    return 1


def _apply_late_parent(
    connection: sqlite3.Connection,
    record: ParsedRecord,
    _canonical_owner: bool,
) -> int:
    payload = record.payload
    connection.execute(
        """
        INSERT INTO parent_observations (
            occurrence_id, child_session_id, parent_session_id, transition
        ) VALUES (?, ?, ?, ?)
        """,
        (
            record.occurrence_id,
            str(payload["child_session_id"]),
            str(payload["parent_session_id"]),
            str(payload["transition"]),
        ),
    )
    return 1


def _mark_call_dirty(
    connection: sqlite3.Connection,
    session_id: str,
    model: str,
    reasoning_effort: object,
) -> None:
    effort = str(reasoning_effort) if reasoning_effort is not None else "<unknown>"
    connection.executemany(
        "INSERT OR IGNORE INTO dirty_projection_keys (consumer, dirty_key) VALUES (?, ?)",
        (
            ("session_usage_current", session_id),
            ("model_effort_current", f"{model}\0{effort}"),
        ),
    )


def _dirty_key_count(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM dirty_projection_keys").fetchone()[0])


def _refresh_dirty_projections(connection: sqlite3.Connection) -> tuple[int, int]:
    dirty = tuple(
        connection.execute(
            "SELECT consumer, dirty_key FROM dirty_projection_keys ORDER BY consumer, dirty_key"
        )
    )
    rows_read = 0
    rows_written = 0
    for consumer, dirty_key in dirty:
        if consumer == "session_usage_current":
            rows_read += _refresh_session_projection(connection, str(dirty_key))
            rows_written += 1
        elif consumer == "model_effort_current":
            model, effort = str(dirty_key).split("\0", maxsplit=1)
            rows_read += _refresh_model_projection(connection, model, effort)
            rows_written += 1
        else:
            raise CandidateCError(f"unknown projection consumer: {consumer}")
    connection.execute("DELETE FROM dirty_projection_keys")
    return rows_read, rows_written


def _refresh_session_projection(connection: sqlite3.Connection, session_id: str) -> int:
    row = connection.execute(
        """
        SELECT
            COUNT(*),
            CASE WHEN COUNT(uncached_input_tokens) = COUNT(*)
                THEN SUM(uncached_input_tokens) END,
            CASE WHEN COUNT(cached_input_tokens) = COUNT(*)
                THEN SUM(cached_input_tokens) END,
            CASE WHEN COUNT(reasoning_tokens) = COUNT(*)
                THEN SUM(reasoning_tokens) END,
            CASE WHEN COUNT(output_tokens) = COUNT(*)
                THEN SUM(output_tokens) END,
            CASE
                WHEN COUNT(uncached_input_tokens) = COUNT(*)
                 AND COUNT(cached_input_tokens) = COUNT(*)
                 AND COUNT(output_tokens) = COUNT(*)
                THEN SUM(uncached_input_tokens + cached_input_tokens + output_tokens)
            END,
            MAX(event_at_us)
        FROM model_calls
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    connection.execute(
        """
        INSERT OR REPLACE INTO session_usage_current (
            session_id,
            calls,
            uncached_input_tokens,
            cached_input_tokens,
            reasoning_tokens,
            output_tokens,
            total_tokens,
            last_event_at_us
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, *row),
    )
    return int(row[0])


def _refresh_model_projection(
    connection: sqlite3.Connection,
    model: str,
    effort: str,
) -> int:
    row = connection.execute(
        """
        SELECT
            COUNT(*),
            CASE WHEN COUNT(uncached_input_tokens) = COUNT(*)
                THEN SUM(uncached_input_tokens) END,
            CASE WHEN COUNT(cached_input_tokens) = COUNT(*)
                THEN SUM(cached_input_tokens) END,
            CASE WHEN COUNT(reasoning_tokens) = COUNT(*)
                THEN SUM(reasoning_tokens) END,
            CASE WHEN COUNT(output_tokens) = COUNT(*)
                THEN SUM(output_tokens) END
        FROM model_calls
        WHERE model = ? AND COALESCE(reasoning_effort, '<unknown>') = ?
        """,
        (model, effort),
    ).fetchone()
    connection.execute(
        """
        INSERT OR REPLACE INTO model_effort_current (
            model,
            reasoning_effort,
            calls,
            uncached_input_tokens,
            cached_input_tokens,
            reasoning_tokens,
            output_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (model, effort, *row),
    )
    return int(row[0])


def _apply_ordinary_change(
    connection: sqlite3.Connection,
    change: str,
    label: str,
) -> tuple[int, int]:
    if change == "no_source_change":
        return 0, 0
    if change == "rate_card_change":
        connection.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('rate_card_revision', ?)",
            (f"candidate-c:{label}",),
        )
        keys = connection.execute(
            """
            SELECT DISTINCT model, COALESCE(reasoning_effort, '<unknown>')
            FROM model_calls
            ORDER BY model, COALESCE(reasoning_effort, '<unknown>')
            """
        ).fetchall()
        connection.executemany(
            "INSERT OR IGNORE INTO dirty_projection_keys (consumer, dirty_key) VALUES (?, ?)",
            (("model_effort_current", f"{model}\0{effort}") for model, effort in keys),
        )
        return 0, 1
    if change in {"one_model_call", "32_call_tail", "2000_call_tail", "late_event"}:
        count = {"one_model_call": 1, "32_call_tail": 32, "2000_call_tail": 2000}.get(
            change,
            1,
        )
        return _append_synthetic_calls(connection, count, label, late=change == "late_event"), 0
    if change == "one_tool_start":
        return _append_tool_start(connection, label), 0
    if change == "tool_terminal_transition":
        return _append_tool_terminal(connection, label), 1
    if change == "tool_plus_state_change":
        inserted = _append_tool_start(connection, label)
        return inserted + _append_state_change(connection, label), 0
    raise CandidateCError(f"unknown ordinary change: {change}")


def _tail_context(connection: sqlite3.Connection) -> tuple[str, str, str, int]:
    row = connection.execute(
        """
        SELECT session_id, turn_id, model, event_at_us
        FROM model_calls
        ORDER BY event_at_us DESC, call_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None or row[0] is None:
        raise CandidateCError("ordinary tail requires an existing canonical call")
    return str(row[0]), str(row[1]), str(row[2]), int(row[3])


def _source_context(connection: sqlite3.Connection) -> tuple[str, str, str]:
    row = connection.execute(
        """
        SELECT manifestation_id, revision, source_path
        FROM source_manifestations
        WHERE source_state = 'active'
        ORDER BY source_path
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        raise CandidateCError("ordinary tail requires an active source manifestation")
    return str(row[0]), str(row[1]), str(row[2])


def _append_synthetic_calls(
    connection: sqlite3.Connection,
    count: int,
    label: str,
    *,
    late: bool,
) -> int:
    session_id, turn_id, model, latest = _tail_context(connection)
    manifestation_id, revision, source_path = _source_context(connection)
    earliest = int(connection.execute("SELECT MIN(event_at_us) FROM event_backbone").fetchone()[0])
    source_order = int(
        connection.execute("SELECT MAX(source_order) FROM event_backbone").fetchone()[0]
    )
    backbone_rows: list[tuple[object, ...]] = []
    call_rows: list[tuple[object, ...]] = []
    for index in range(count):
        digest = hashlib.sha256(f"{label}\0{index}".encode()).hexdigest()
        call_id = f"call:candidate-c:{digest}"
        occurrence_id = f"occurrence:c:{digest}"
        event_at_us = earliest + index if late else latest + index + 1
        payload_sha = hashlib.sha256(
            (
                f"{call_id}\0{session_id}\0{turn_id}\0{model}\0"
                "11\0" "13\0" "5\0" "7"
            ).encode()
        ).hexdigest()
        backbone_rows.append(
            (
                occurrence_id,
                call_id,
                event_at_us,
                source_order + index + 1,
                manifestation_id,
                revision,
                source_path,
                1_000_000 + source_order + index,
                payload_sha,
            )
        )
        call_rows.append(
            (call_id, occurrence_id, session_id, turn_id, event_at_us, model),
        )
    connection.executemany(
        """
        INSERT INTO event_backbone (
            occurrence_id,
            logical_id,
            event_type,
            event_at_us,
            event_kind_order,
            source_order,
            manifestation_id,
            revision,
            source_path,
            record_ordinal,
            byte_start,
            byte_end,
            payload_sha256,
            canonical_owner
        ) VALUES (?, ?, 'model_call', ?, 30, ?, ?, ?, ?, ?, 0, 0, ?, 1)
        """,
        backbone_rows,
    )
    connection.executemany(
        """
        INSERT INTO model_calls (
            call_id,
            canonical_occurrence_id,
            session_id,
            turn_id,
            event_at_us,
            model,
            reasoning_effort,
            context_window_tokens,
            uncached_input_tokens,
            cached_input_tokens,
            reasoning_tokens,
            output_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, 'medium', 192000, 11, 13, 5, 7)
        """,
        call_rows,
    )
    _mark_call_dirty(connection, session_id, model, "medium")
    return count


def _append_tool_start(connection: sqlite3.Connection, label: str) -> int:
    session_id, turn_id, _model, latest = _tail_context(connection)
    manifestation_id, revision, source_path = _source_context(connection)
    digest = shared.canonical_sha256({"label": label, "tool": "start"})
    tool_id = f"tool:candidate-c:{digest}"
    occurrence_id = f"occurrence:c:{digest}"
    source_order = int(
        connection.execute("SELECT MAX(source_order) FROM event_backbone").fetchone()[0]
    ) + 1
    connection.execute(
        """
        INSERT INTO event_backbone (
            occurrence_id,
            logical_id,
            event_type,
            event_at_us,
            event_kind_order,
            source_order,
            manifestation_id,
            revision,
            source_path,
            record_ordinal,
            byte_start,
            byte_end,
            payload_sha256,
            canonical_owner
        ) VALUES (?, ?, 'tool_start', ?, 40, ?, ?, ?, ?, ?, 0, 0, ?, 1)
        """,
        (
            occurrence_id,
            tool_id,
            latest + 1,
            source_order,
            manifestation_id,
            revision,
            source_path,
            2_000_000 + source_order,
            digest,
        ),
    )
    connection.execute(
        """
        INSERT INTO tool_invocations (
            tool_id,
            first_occurrence_id,
            session_id,
            turn_id,
            resource_id,
            transport_name,
            semantic_operation,
            write_intent,
            started_at_us,
            state
        ) VALUES (?, ?, ?, ?, ?, 'candidate_c', 'write', 1, ?, 'running')
        """,
        (
            tool_id,
            occurrence_id,
            session_id,
            turn_id,
            f"resource:candidate-c:{digest}",
            latest + 1,
        ),
    )
    connection.execute(
        "INSERT INTO tool_transitions (occurrence_id, tool_id, state) VALUES (?, ?, 'running')",
        (occurrence_id, tool_id),
    )
    return 2


def _append_tool_terminal(connection: sqlite3.Connection, label: str) -> int:
    row = connection.execute(
        """
        SELECT tool_id, session_id, turn_id, started_at_us
        FROM tool_invocations
        WHERE terminal_at_us IS NULL
        ORDER BY started_at_us, tool_id
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        _append_tool_start(connection, f"{label}:implicit-start")
        return _append_tool_terminal(connection, label)
    tool_id, _session_id, _turn_id, started_at = row
    manifestation_id, revision, source_path = _source_context(connection)
    digest = shared.canonical_sha256({"label": label, "tool": str(tool_id), "terminal": True})
    occurrence_id = f"occurrence:c:{digest}"
    source_order = int(
        connection.execute("SELECT MAX(source_order) FROM event_backbone").fetchone()[0]
    ) + 1
    terminal_at = int(started_at) + 1_000
    connection.execute(
        """
        INSERT INTO event_backbone (
            occurrence_id,
            logical_id,
            event_type,
            event_at_us,
            event_kind_order,
            source_order,
            manifestation_id,
            revision,
            source_path,
            record_ordinal,
            byte_start,
            byte_end,
            payload_sha256,
            canonical_owner
        ) VALUES (?, ?, 'tool_terminal', ?, 50, ?, ?, ?, ?, ?, 0, 0, ?, 1)
        """,
        (
            occurrence_id,
            str(tool_id),
            terminal_at,
            source_order,
            manifestation_id,
            revision,
            source_path,
            3_000_000 + source_order,
            digest,
        ),
    )
    connection.execute(
        """
        UPDATE tool_invocations
        SET terminal_at_us = ?, state = 'succeeded', duration_us = 1000, output_bytes = 0
        WHERE tool_id = ?
        """,
        (terminal_at, tool_id),
    )
    connection.execute(
        "INSERT INTO tool_transitions (occurrence_id, tool_id, state) VALUES (?, ?, 'succeeded')",
        (occurrence_id, tool_id),
    )
    return 1


def _append_state_change(connection: sqlite3.Connection, label: str) -> int:
    session_id, turn_id, _model, latest = _tail_context(connection)
    manifestation_id, revision, source_path = _source_context(connection)
    digest = shared.canonical_sha256({"label": label, "state_change": True})
    occurrence_id = f"occurrence:c:{digest}"
    change_id = f"state-change:candidate-c:{digest}"
    resource_id = f"resource:candidate-c:{digest}"
    source_order = int(
        connection.execute("SELECT MAX(source_order) FROM event_backbone").fetchone()[0]
    ) + 1
    connection.execute(
        """
        INSERT INTO event_backbone (
            occurrence_id,
            logical_id,
            event_type,
            event_at_us,
            event_kind_order,
            source_order,
            manifestation_id,
            revision,
            source_path,
            record_ordinal,
            byte_start,
            byte_end,
            payload_sha256,
            canonical_owner
        ) VALUES (?, ?, 'state_change', ?, 60, ?, ?, ?, ?, ?, 0, 0, ?, 1)
        """,
        (
            occurrence_id,
            change_id,
            latest + 2,
            source_order,
            manifestation_id,
            revision,
            source_path,
            4_000_000 + source_order,
            digest,
        ),
    )
    connection.execute(
        """
        INSERT INTO state_changes (
            change_id,
            occurrence_id,
            session_id,
            turn_id,
            resource_id,
            change_kind,
            preceding_activity_count,
            causal_attribution
        ) VALUES (?, ?, ?, ?, ?, 'observed_mutation', 2, 0)
        """,
        (change_id, occurrence_id, session_id, turn_id, resource_id),
    )
    return 1


def _oracle_result_row(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    (
        oracle_id,
        variant,
        facts,
        selector_ids,
        inputs,
        manifestation_id,
        revision,
        source_path,
        record_ordinal,
        byte_start,
        byte_end,
    ) = row
    observed = json.loads(str(facts))
    if "occurrence_coordinates" in observed:
        observed["occurrence_coordinates"] = [
            {
                "adapter_version": "synthetic-jsonl-v1",
                "manifestation_id": str(manifestation_id),
                "revision": str(revision),
                "source_path": str(source_path),
                "record_ordinal": int(record_ordinal),
                "record_range": [int(record_ordinal), int(record_ordinal)],
                "byte_start": int(byte_start),
                "byte_end": int(byte_end),
            }
        ]
    return {
        "oracle_id": str(oracle_id),
        "variant": str(variant),
        "row": observed,
        "selector_ids": json.loads(str(selector_ids)),
        "inputs": json.loads(str(inputs)),
    }


def _oracle_equivalent(
    fixture: shared.FixtureBundle,
    rows: tuple[dict[str, Any], ...],
) -> bool:
    questions = fixture.oracle.get("questions")
    if not isinstance(questions, Mapping):
        return False
    for row in rows:
        expected = questions.get(row["oracle_id"])
        if not isinstance(expected, Mapping):
            return False
        expected_block = expected.get("expected")
        if (
            not isinstance(expected_block, Mapping)
            or _plain_value(expected_block.get("row")) != row["row"]
        ):
            return False
    return bool(rows)


def _plain_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_plain_value(item) for item in value]
    return value


def _evidence_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "event_at_us": int(row[0]),
        "event_kind_order": int(row[1]),
        "source_order": int(row[2]),
        "logical_id": str(row[3]),
        "occurrence_id": str(row[4]),
        "event_type": str(row[5]),
        "occurrence": {
            "manifestation_id": str(row[6]),
            "revision": str(row[7]),
            "source_path": str(row[8]),
            "record_ordinal": int(row[9]),
            "byte_start": int(row[10]),
            "byte_end": int(row[11]),
        },
        "canonical_owner": bool(row[12]),
    }


def _cursor_from_evidence(row: Mapping[str, Any]) -> Cursor:
    return (
        int(row["event_at_us"]),
        int(row["event_kind_order"]),
        int(row["source_order"]),
        str(row["logical_id"]),
        str(row["occurrence_id"]),
    )


def _load_phase_records(
    fixture: shared.FixtureBundle,
    group: str,
) -> tuple[tuple[str, str, int], ...]:
    records: dict[str, tuple[str, str, int]] = {}
    for phase in fixture.phases:
        if phase.group != group:
            continue
        for line in phase.absolute_path.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            values = payload["payload"]
            call_id = str(values["occurrence_id"])
            records[call_id] = (
                call_id,
                str(values["revision"]),
                int(payload["event_at_us"]),
            )
    return tuple(records[key] for key in sorted(records))


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CandidateCError("source lifecycle mapping must contain string arrays")
    if not all(isinstance(item, str) for item in value):
        raise CandidateCError("source lifecycle mapping contains a non-string ID")
    return tuple(value)


def _canonical_text(value: object) -> str:
    return shared.canonical_json_bytes(value).decode("utf-8").removesuffix("\n")


def _sum_counts(connection: sqlite3.Connection, tables: tuple[str, ...]) -> int:
    return sum(
        int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
    )


def _dbstat_bytes(connection: sqlite3.Connection) -> tuple[int, int]:
    try:
        rows = connection.execute(
            "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0, 0
    declared_indexes = index_names()
    index_bytes = sum(int(size) for name, size in rows if str(name) in declared_indexes)
    table_bytes = sum(
        int(size)
        for name, size in rows
        if str(name) not in declared_indexes and not str(name).startswith("sqlite_")
    )
    return table_bytes, index_bytes
