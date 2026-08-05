"""Pure, outside-lock preparation for bounded CK-07 publications."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import replace
from decimal import Decimal

from ..adapters.codex_jsonl.canonicalize import ProposedChangeSet
from ..adapters.contracts import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    CAPABILITY_MASK,
    IDENTITY_VERSION,
    AdapterObservation,
    SourceCursor,
    SourceInventory,
)
from ..domain.identity import semantic_id
from ..domain.models import LifecycleFold, LifecycleTransition
from ..storage.lifecycle import TERMINAL_STATES, fold_lifecycle
from .writer import (
    _ENTITY_COUNT_NAMES,
    _ENTITY_TABLES,
    _LIFECYCLE_KINDS,
    _MUTABLE_COLUMNS,
    _OBSERVATION_KINDS,
    IdentityMutation,
    ModelCallTailState,
    PreparedRow,
    PriorPublicationSnapshot,
    PublicationRequest,
    PublicationWriteError,
    PublicationWriteSet,
    _canonical_json,
    _occurrence_tuple,
    _source_ids,
    _state,
)

_PUBLICATION_PROVENANCE_COLUMNS = frozenset(
    {"first_seen_publication_id", "last_seen_publication_id"}
)


class _WriteSetPreparer:
    """Build one schema-exact write set without holding the writer lock."""

    def __init__(
        self,
        changes: ProposedChangeSet,
        request: PublicationRequest,
        *,
        configured_producer_key: str,
        prior: PriorPublicationSnapshot,
        inventory_started_at_us: int | None,
        inventory_completed_at_us: int | None,
    ) -> None:
        normalized_observations = tuple(
            self._normalize_source_order(observation) for observation in changes.observations
        )
        self.changes = replace(changes, observations=normalized_observations)
        self.request = request
        self.configured_producer_key = configured_producer_key
        self.prior = prior
        self.publication_id = request.publication_id
        self.inventory_started_at_us = (
            request.committed_at_us if inventory_started_at_us is None else inventory_started_at_us
        )
        self.inventory_completed_at_us = (
            request.committed_at_us
            if inventory_completed_at_us is None
            else inventory_completed_at_us
        )
        self.identities: dict[str, IdentityMutation] = {}
        self.rows: list[PreparedRow] = []
        self.inventories = tuple(changes.selected_sources) + tuple(changes.deferred_sources)
        self.observations_by_id: dict[str, list[AdapterObservation]] = defaultdict(list)
        self.transitions: list[LifecycleTransition] = []
        self.folds: dict[str, LifecycleFold] = {}
        self.tail_ordinal = 0 if prior.tail_state is None else prior.tail_state.row_count

    @staticmethod
    def _normalize_source_order(observation: AdapterObservation) -> AdapterObservation:
        if observation.source_order is not None:
            return observation
        fallback = observation.source_range.record_ordinal
        if fallback is None:
            raise PublicationWriteError("source order provenance is missing")
        return replace(observation, source_order=fallback)

    def prepare(self) -> PublicationWriteSet:
        self._add_adapter()
        coverage_items = self._add_inventories()
        self._add_source_coverage(coverage_items)
        self._collect_observations()
        self._add_projects()
        self._build_lifecycle()
        self._add_observation_rows()
        self._add_allowance_intervals()
        self._add_accounting()
        return PublicationWriteSet(
            changes=self.changes,
            identities=tuple(self.identities[key] for key in sorted(self.identities)),
            rows=tuple(self.rows),
            lifecycle_transitions=tuple(self.transitions),
            tail_state=self._tail_state(),
            expected_source_revisions=self.prior.source_revisions,
            cursor_snapshot=self._cursor_snapshot(),
            existing_occurrence_ids=self.prior.occurrence_ids,
        )

    def _identity(
        self,
        logical_id: str,
        kind: str,
        identity_tuple: object,
        *,
        enforce: bool = True,
    ) -> None:
        candidate = IdentityMutation(logical_id, kind, identity_tuple, enforce)
        existing = self.identities.get(logical_id)
        if existing is not None and existing != candidate:
            raise PublicationWriteError(f"identity proposal conflicts for {logical_id}")
        self.identities[logical_id] = candidate

    def _add_adapter(self) -> None:
        # ``codex-jsonl`` is a frozen external ID, but still receives
        # collision-checked canonical identity bytes.
        self._identity(
            ADAPTER_ID,
            "adapter",
            [ADAPTER_ID, ADAPTER_VERSION],
            enforce=False,
        )
        self.rows.append(
            PreparedRow(
                "adapters",
                {
                    "adapter_id": ADAPTER_ID,
                    "adapter_version": ADAPTER_VERSION,
                    "source_kind": "codex-jsonl",
                    "capability_mask": CAPABILITY_MASK,
                    "identity_version": IDENTITY_VERSION,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                (
                    "adapter_version",
                    "capability_mask",
                    "last_seen_publication_id",
                ),
            )
        )

    def _add_inventories(self) -> dict[str, list[SourceInventory]]:
        coverage_items: dict[str, list[SourceInventory]] = defaultdict(list)
        for item in self.inventories:
            producer_id, source_id = _source_ids(item, self.configured_producer_key)
            coverage_items[source_id].append(item)
            self._identity(producer_id, "producer", [self.configured_producer_key])
            self._identity(
                source_id,
                "source",
                [
                    ADAPTER_ID,
                    producer_id,
                    item.source_kind,
                    item.source_key,
                ],
            )
            self._identity(
                item.manifestation_id,
                "source-manifestation",
                [item.source_kind, item.technical_path_key],
                enforce=False,
            )
            self.rows.extend(
                (
                    PreparedRow(
                        "source_producers",
                        {
                            "producer_id": producer_id,
                            "configured_producer_key": self.configured_producer_key,
                            "display_label": "Local Codex",
                            "first_seen_publication_id": self.publication_id,
                            "last_seen_publication_id": self.publication_id,
                        },
                        ("display_label", "last_seen_publication_id"),
                    ),
                    PreparedRow(
                        "sources",
                        {
                            "source_id": source_id,
                            "adapter_id": ADAPTER_ID,
                            "producer_id": producer_id,
                            "source_kind": item.source_kind,
                            "adapter_native_source_key": item.source_key,
                            "selected_history_preset": self.request.history_preset,
                            "selected_from_us": self.request.indexed_from_us,
                            "selected_through_us": self.request.indexed_through_us,
                            "first_seen_publication_id": self.publication_id,
                            "last_seen_publication_id": self.publication_id,
                        },
                        (
                            "selected_history_preset",
                            "selected_from_us",
                            "selected_through_us",
                            "last_seen_publication_id",
                        ),
                    ),
                    PreparedRow(
                        "source_manifestations",
                        {
                            "manifestation_id": item.manifestation_id,
                            "manifestation_key": item.manifestation_key,
                            "source_id": source_id,
                            "adapter_native_file_key": item.technical_path_key,
                            "technical_path_key": item.technical_path_key,
                            "display_label": item.display_label,
                            "filesystem_identity_json": (
                                None
                                if item.filesystem_identity is None
                                else _canonical_json({"identity": item.filesystem_identity})
                            ),
                            "size_bytes": item.size_bytes,
                            "modified_at_us": item.modified_at_us,
                            "prefix_sha256": item.prefix_fingerprint,
                            "suffix_sha256": item.suffix_fingerprint,
                            "content_revision": item.content_revision,
                            "source_rank": item.source_rank,
                            "state": item.state.value,
                            "time_range_start_us": (
                                None
                                if item.time_range_hint is None
                                else item.time_range_hint.start_us
                            ),
                            "time_range_end_us": (
                                None
                                if item.time_range_hint is None
                                else item.time_range_hint.end_us
                            ),
                            "time_range_confidence": (item.time_range_confidence.value),
                            "selected": int(item.selected),
                            "first_seen_publication_id": self.publication_id,
                            "last_seen_publication_id": self.publication_id,
                            "ended_publication_id": None,
                        },
                        tuple(_MUTABLE_COLUMNS["source_manifestations"]),
                    ),
                )
            )
        return coverage_items

    def _add_source_coverage(self, coverage_items: dict[str, list[SourceInventory]]) -> None:
        prepared_by_source = {
            str(row.values["source_id"]): PreparedRow(
                row.table,
                {
                    **row.values,
                    "publication_id": self.publication_id,
                },
            )
            for row in self.prior.source_coverage
        }
        prior_cursors = {cursor.manifestation_key: cursor for cursor in self.prior.source_cursors}
        current_cursors = {
            cursor.manifestation_key: cursor for cursor in self.changes.cursor_updates
        }
        for source_id, items in sorted(coverage_items.items()):
            keys = {item.manifestation_key for item in items}
            malformed_ranges = [
                diagnostic.source_range
                for diagnostic in self.changes.diagnostics
                if diagnostic.source_range is not None
                and diagnostic.source_range.manifestation_key in keys
                and (
                    diagnostic.source_range.manifestation_key,
                    diagnostic.source_range.source_revision,
                    diagnostic.source_range.byte_start,
                    diagnostic.source_range.byte_end,
                    diagnostic.code,
                )
                not in self.prior.source_diagnostic_keys
            ]
            prior_values = dict(
                prepared_by_source.get(
                    source_id,
                    PreparedRow(
                        "publication_source_coverage",
                        {
                            "selected_manifestation_count": 0,
                            "selected_manifestation_bytes": 0,
                            "deferred_manifestation_count": 0,
                            "deferred_manifestation_bytes": 0,
                            "malformed_manifestation_count": 0,
                            "malformed_manifestation_bytes": 0,
                            "missing_manifestation_count": 0,
                            "missing_manifestation_bytes": 0,
                            "uncertain_manifestation_count": 0,
                            "uncertain_manifestation_bytes": 0,
                            "malformed_range_count": 0,
                            "malformed_range_bytes": 0,
                            "selected_complete_record_count": 0,
                        },
                    ),
                ).values
            )
            inventory_counts = {
                name: int(prior_values[name]) for name in self._inventory_coverage_counts([])
            }
            for item in items:
                prior_manifestation = self.prior.source_manifestations.get(item.manifestation_key)
                if prior_manifestation is not None:
                    for name, value in self._manifestation_coverage_counts(
                        prior_manifestation.values
                    ).items():
                        inventory_counts[name] -= value
                for name, value in self._inventory_coverage_counts([item]).items():
                    inventory_counts[name] += value
            selected_complete_record_count = int(prior_values["selected_complete_record_count"])
            for manifestation_key in keys & current_cursors.keys():
                selected_complete_record_count += current_cursors[
                    manifestation_key
                ].record_ordinal - (
                    prior_cursors[manifestation_key].record_ordinal
                    if manifestation_key in prior_cursors
                    else 0
                )
            prepared_by_source[source_id] = PreparedRow(
                "publication_source_coverage",
                {
                    "publication_id": self.publication_id,
                    "source_id": source_id,
                    **inventory_counts,
                    "malformed_range_count": int(prior_values["malformed_range_count"])
                    + len(malformed_ranges),
                    "malformed_range_bytes": int(prior_values["malformed_range_bytes"])
                    + sum(item.byte_end - item.byte_start for item in malformed_ranges),
                    "selected_complete_record_count": (selected_complete_record_count),
                    "tail_pending": 0,
                    "indexed_from_us": self.request.indexed_from_us,
                    "indexed_through_us": self.request.indexed_through_us,
                    "guaranteed_complete_from_us": (self.request.guaranteed_complete_from_us),
                    "guaranteed_complete_through_us": (
                        self.request.indexed_through_us
                        if self.request.guaranteed_complete_from_us is not None
                        else None
                    ),
                    "clock_quality": "unknown",
                    "clock_uncertainty_us": None,
                    "inventory_started_at_us": self.inventory_started_at_us,
                    "inventory_completed_at_us": (self.inventory_completed_at_us),
                },
            )
        self.rows.extend(prepared_by_source[source_id] for source_id in sorted(prepared_by_source))

    def _cursor_snapshot(self) -> tuple[SourceCursor, ...]:
        cursors = {cursor.manifestation_key: cursor for cursor in self.prior.source_cursors}
        cursors.update({cursor.manifestation_key: cursor for cursor in self.changes.cursor_updates})
        return tuple(cursors[key] for key in sorted(cursors))

    @staticmethod
    def _inventory_coverage_counts(
        items: list[SourceInventory],
    ) -> dict[str, int]:
        return {
            "selected_manifestation_count": sum(item.selected for item in items),
            "selected_manifestation_bytes": sum(item.size_bytes for item in items if item.selected),
            "deferred_manifestation_count": sum(not item.selected for item in items),
            "deferred_manifestation_bytes": sum(
                item.size_bytes for item in items if not item.selected
            ),
            "malformed_manifestation_count": sum(item.state.value == "malformed" for item in items),
            "malformed_manifestation_bytes": sum(
                item.size_bytes for item in items if item.state.value == "malformed"
            ),
            "missing_manifestation_count": sum(item.state.value == "missing" for item in items),
            "missing_manifestation_bytes": sum(
                item.size_bytes for item in items if item.state.value == "missing"
            ),
            "uncertain_manifestation_count": sum(
                item.time_range_confidence.value != "trusted" for item in items
            ),
            "uncertain_manifestation_bytes": sum(
                item.size_bytes for item in items if item.time_range_confidence.value != "trusted"
            ),
        }

    @staticmethod
    def _manifestation_coverage_counts(
        values: Mapping[str, object],
    ) -> dict[str, int]:
        selected = values["selected"]
        size_bytes = values["size_bytes"]
        state = values["state"]
        confidence = values["time_range_confidence"]
        if (
            type(selected) is not int
            or type(size_bytes) is not int
            or not isinstance(state, str)
            or not isinstance(confidence, str)
        ):
            raise PublicationWriteError("prior source manifestation has invalid coverage scalars")
        return {
            "selected_manifestation_count": selected,
            "selected_manifestation_bytes": size_bytes if selected else 0,
            "deferred_manifestation_count": 1 - selected,
            "deferred_manifestation_bytes": size_bytes if not selected else 0,
            "malformed_manifestation_count": int(state == "malformed"),
            "malformed_manifestation_bytes": (size_bytes if state == "malformed" else 0),
            "missing_manifestation_count": int(state == "missing"),
            "missing_manifestation_bytes": (size_bytes if state == "missing" else 0),
            "uncertain_manifestation_count": int(confidence != "trusted"),
            "uncertain_manifestation_bytes": (size_bytes if confidence != "trusted" else 0),
        }

    def _collect_observations(self) -> None:
        for observation in self.changes.observations:
            kind = _OBSERVATION_KINDS.get(observation.observation_type)
            if kind is not None:
                self._identity(
                    observation.logical_id,
                    kind,
                    observation.identity_tuple,
                )
            self._identity(
                observation.occurrence_id,
                "source-occurrence",
                _occurrence_tuple(observation.logical_id, observation),
            )
            self.observations_by_id[observation.logical_id].append(observation)

    def _add_projects(self) -> None:
        native_keys: set[str] = set()
        for observation in self.changes.observations:
            if observation.observation_type == "ProjectObserved":
                native_keys.add(str(observation.payload["project_id"]))
            elif observation.observation_type == "SessionObserved":
                native_keys.add(str(observation.payload.get("project_id") or "unknown-project"))
            elif observation.observation_type == "ResourceObserved":
                native_keys.add(str(observation.identity_tuple[0]))
        for native in sorted(native_keys):
            project_id = semantic_id("project", [native])
            self._identity(project_id, "project", (native,))
            event_times = [
                item.event_at_us
                for item in self.changes.observations
                if item.event_at_us is not None
                and (
                    item.logical_id == project_id
                    or item.payload.get("project_id") == native
                    or (
                        item.observation_type == "ResourceObserved"
                        and item.identity_tuple[0] == native
                    )
                )
            ]
            self.rows.append(
                PreparedRow(
                    "projects",
                    {
                        "project_id": project_id,
                        "workspace_key": native,
                        "label_candidates_json": "[]",
                        "first_event_at_us": min(event_times, default=None),
                        "last_event_at_us": max(event_times, default=None),
                        "provenance_json": "[]",
                        "first_seen_publication_id": self.publication_id,
                        "last_seen_publication_id": self.publication_id,
                    },
                    tuple(_MUTABLE_COLUMNS["projects"]),
                )
            )

    def _build_lifecycle(self) -> None:
        sequence: Counter[str] = Counter(
            {
                logical_id: max(
                    (item.transition_version for item in self.prior.lifecycle.get(logical_id, ())),
                    default=0,
                )
                for logical_id in self.observations_by_id
            }
        )
        for observation in self.changes.observations:
            lifecycle_kind = _LIFECYCLE_KINDS.get(observation.observation_type)
            if lifecycle_kind is None:
                continue
            sequence[observation.logical_id] += 1
            version = sequence[observation.logical_id]
            session_id = (
                observation.logical_id
                if lifecycle_kind == "session"
                else observation.payload.get("session_id")
            )
            if not isinstance(session_id, str) or not session_id:
                raise PublicationWriteError(
                    "lifecycle session provenance is missing"
                )
            transition_identity = [
                observation.logical_id,
                version,
                _state(observation),
                observation.occurrence_id,
            ]
            transition_id = semantic_id("lifecycle-transition", transition_identity)
            self._identity(transition_id, "lifecycle-transition", transition_identity)
            self.transitions.append(
                LifecycleTransition(
                    transition_id=transition_id,
                    entity_logical_id=observation.logical_id,
                    entity_kind=lifecycle_kind,
                    lifecycle_state=_state(observation),
                    state_basis=observation.basis,
                    transition_version=version,
                    transition_at_us=observation.event_at_us,
                    source_rank=observation.source_rank,
                    source_order=observation.source_order,
                    event_kind_order=observation.event_kind_order,
                    transition_rank=observation.transition_rank,
                    occurrence_id=observation.occurrence_id,
                    terminal_error_category=(
                        str(observation.payload["error_category"])
                        if observation.payload.get("error_category") is not None
                        else None
                    ),
                    measurement_mask=observation.measurement_mask,
                    first_seen_publication_id=self.publication_id,
                    session_id=session_id,
                )
            )
        self.folds = {
            logical_id: fold_lifecycle(
                tuple(self.prior.lifecycle.get(logical_id, ()))
                + tuple(item for item in self.transitions if item.entity_logical_id == logical_id)
            )
            for logical_id in {item.entity_logical_id for item in self.transitions}
        }

    def _add_observation_rows(self) -> None:
        handlers: dict[
            str,
            Callable[[str, list[AdapterObservation], AdapterObservation], None],
        ] = {
            "ResourceObserved": self._add_resource,
            "SessionObserved": self._add_session,
            "TurnBoundaryObserved": self._add_turn,
            "ModelCallObserved": self._add_model_call,
            "ToolLifecycleObserved": self._add_tool,
            "ToolResourceLinkObserved": self._add_tool_resource,
            "ActivityLifecycleObserved": self._add_activity,
            "CompactionObserved": self._add_compaction,
            "ContextComponentObserved": self._add_context_component,
            "StateChangeObserved": self._add_state_change,
            "AllowanceLimitObserved": self._add_allowance_limit,
            "AllowanceObservationObserved": self._add_allowance_observation,
        }
        for logical_id, grouped in sorted(self.observations_by_id.items()):
            observation = max(grouped, key=lambda item: item.sort_key)
            handler = handlers.get(observation.observation_type)
            if handler is not None:
                handler(logical_id, grouped, observation)
        for logical_id, grouped in sorted(self.observations_by_id.items()):
            observation = max(grouped, key=lambda item: item.sort_key)
            if observation.observation_type == "SessionRelationshipObserved":
                self._add_session_relationship(logical_id, grouped, observation)

    @staticmethod
    def _common_order(
        observation: AdapterObservation,
    ) -> dict[str, int | None]:
        return {
            "event_at_us": observation.event_at_us,
            "source_rank": observation.source_rank,
            "source_order": observation.source_order,
            "event_kind_order": observation.event_kind_order,
            "transition_rank": observation.transition_rank,
        }

    def _fold(self, logical_id: str) -> LifecycleFold:
        fold = self.folds.get(logical_id)
        assert fold is not None
        return fold

    def _add_resource(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        native_project = str(observation.identity_tuple[0])
        self.rows.append(
            PreparedRow(
                "resources",
                {
                    "resource_id": logical_id,
                    "project_id": semantic_id("project", [native_project]),
                    "resource_kind": str(payload.get("resource_kind", "unknown")),
                    "normalized_key": str(payload.get("normalized_resource_key", logical_id)),
                    "normalization_version": "resource-normalization-v1",
                    "display_label": str(payload.get("normalized_resource_key", logical_id)),
                    "provenance_json": "[]",
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["resources"]),
            )
        )

    def _add_session(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        fold = self._fold(logical_id)
        parent = payload.get("parent_session_id")
        self.rows.append(
            PreparedRow(
                "sessions",
                {
                    "session_id": logical_id,
                    "adapter_native_session_key": str(observation.identity_tuple[0]),
                    "identity_version": IDENTITY_VERSION,
                    "project_id": semantic_id(
                        "project",
                        [str(payload.get("project_id") or "unknown-project")],
                    ),
                    "root_session_id": None,
                    "parent_session_id": (
                        semantic_id("session", [parent, "identity-v1"])
                        if isinstance(parent, str)
                        else None
                    ),
                    "relationship_basis": None,
                    "delegation_depth": None,
                    "lifecycle_state": fold.lifecycle_state,
                    "state_basis": fold.state_basis,
                    "transition_version": fold.transition_version,
                    "start_at_us": fold.start_at_us,
                    "end_at_us": fold.terminal_at_us,
                    "observed_duration_us": fold.observed_duration_us,
                    "completion_basis": payload.get("completion_basis"),
                    "label_candidates_json": "[]",
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["sessions"]),
            )
        )

    def _add_turn(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        fold = self._fold(logical_id)
        start_source_order = observation.source_order
        if start_source_order is None:
            start_source_order = observation.source_range.record_ordinal
        if start_source_order is None:
            raise PublicationWriteError("turn source order provenance is missing")
        self.rows.append(
            PreparedRow(
                "turns",
                {
                    "turn_id": logical_id,
                    "session_id": str(payload["session_id"]),
                    "ordinal": int(observation.identity_tuple[1]) + 1,
                    "lifecycle_state": fold.lifecycle_state,
                    "state_basis": fold.state_basis,
                    "transition_version": fold.transition_version,
                    "start_at_us": fold.start_at_us,
                    "end_at_us": fold.terminal_at_us,
                    "start_source_rank": observation.source_rank,
                    "start_source_order": start_source_order,
                    "end_source_order": (
                        start_source_order if fold.terminal_at_us is not None else None
                    ),
                    "completion_basis": None,
                    "membership_json": "{}",
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["turns"]),
            )
        )

    def _add_session_relationship(
        self,
        _logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        child_id = str(observation.payload["session_id"])
        parent_id = str(observation.payload["parent_session_id"])
        available_sessions = {
            str(row.values["session_id"]) for row in self.rows if row.table == "sessions"
        } | {
            logical_id
            for logical_id, row in self.prior.entity_rows.items()
            if row.table == "sessions"
        }
        if child_id not in available_sessions or parent_id not in available_sessions:
            return
        relationship_key = (
            child_id,
            parent_id,
            str(observation.payload["relationship_basis"]),
        )
        child_edges_by_relationship: dict[tuple[str, str, str], AdapterObservation] = {}
        for grouped in self.observations_by_id.values():
            candidate = max(grouped, key=lambda item: item.sort_key)
            if (
                candidate.observation_type != "SessionRelationshipObserved"
                or candidate.payload.get("session_id") != child_id
            ):
                continue
            key = (
                child_id,
                str(candidate.payload["parent_session_id"]),
                str(candidate.payload["relationship_basis"]),
            )
            existing = child_edges_by_relationship.get(key)
            if existing is None or candidate.sort_key > existing.sort_key:
                child_edges_by_relationship[key] = candidate
        if observation is not child_edges_by_relationship[relationship_key]:
            return
        child_edges = sorted(
            child_edges_by_relationship.values(),
            key=lambda item: item.sort_key,
        )
        prior_edge = self.prior.late_parent_edges.get(relationship_key)
        if prior_edge is not None:
            edge = prior_edge
        else:
            new_edges = [
                item
                for item in child_edges
                if (
                    child_id,
                    str(item.payload["parent_session_id"]),
                    str(item.payload["relationship_basis"]),
                )
                not in self.prior.late_parent_edges
            ]
            relationship_version = (
                self.prior.late_parent_versions.get(child_id, 0) + new_edges.index(observation) + 1
            )
            edge = PreparedRow(
                "late_parent_edges",
                {
                    "child_session_id": child_id,
                    "relationship_version": relationship_version,
                    "parent_session_id": parent_id,
                    "relationship_basis": str(observation.payload["relationship_basis"]),
                    **self._common_order(observation),
                    "occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                },
            )
        self.rows.append(edge)
        if observation is not child_edges[-1]:
            return

        child_index = next(
            (
                index
                for index, row in enumerate(self.rows)
                if row.table == "sessions" and row.values["session_id"] == child_id
            ),
            None,
        )
        child = (
            self.rows[child_index]
            if child_index is not None
            else self.prior.entity_rows.get(child_id)
        )
        if child is None:
            raise PublicationWriteError(
                f"late parent relationship has no observed child session: {child_id}"
            )
        parent = next(
            (
                row
                for row in self.rows
                if row.table == "sessions" and row.values["session_id"] == parent_id
            ),
            self.prior.entity_rows.get(parent_id),
        )
        parent_root = None if parent is None else parent.values.get("root_session_id")
        parent_depth = None if parent is None else parent.values.get("delegation_depth")
        updated = PreparedRow(
            "sessions",
            {
                **child.values,
                "root_session_id": parent_root or parent_id,
                "parent_session_id": parent_id,
                "relationship_basis": str(observation.payload["relationship_basis"]),
                "delegation_depth": (1 if parent_depth is None else int(parent_depth) + 1),
                "last_seen_publication_id": self.publication_id,
            },
            tuple(_MUTABLE_COLUMNS["sessions"]),
        )
        if child_index is None:
            self.rows.append(updated)
        else:
            self.rows[child_index] = updated

    def _add_model_call(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        fold = self._fold(logical_id)
        model = str(payload["model"])
        profile_tuple = (
            model,
            payload.get("reasoning_effort"),
            payload.get("service_tier"),
        )
        profile_id = str(payload["model_profile_id"])
        self._identity(profile_id, "model-profile", profile_tuple)
        self.rows.append(
            PreparedRow(
                "model_profiles",
                {
                    "model_profile_id": profile_id,
                    "model": model,
                    "reasoning_effort": payload.get("reasoning_effort"),
                    "service_tier": payload.get("service_tier"),
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                ("last_seen_publication_id",),
            )
        )
        prior_row = self.prior.entity_rows.get(logical_id)
        if prior_row is None:
            self.tail_ordinal += 1
            tail_ordinal = self.tail_ordinal
        else:
            tail_ordinal = int(prior_row.values["tail_ordinal"])
        self.rows.extend(
            (
                PreparedRow(
                    "model_call_locations",
                    {"call_id": logical_id, "storage_class": "tail"},
                ),
                PreparedRow(
                    "model_call_tail",
                    {
                        "call_id": logical_id,
                        "storage_class": "tail",
                        "tail_ordinal": tail_ordinal,
                        "adapter_native_call_key": str(observation.identity_tuple[0]),
                        "session_id": str(payload["session_id"]),
                        "turn_id": str(payload["turn_id"]),
                        "model_profile_id": profile_id,
                        "lifecycle_state": fold.lifecycle_state,
                        "state_basis": fold.state_basis,
                        "transition_version": fold.transition_version,
                        **self._common_order(observation),
                        "context_window_tokens": payload.get("context_window_tokens"),
                        "uncached_input_tokens": payload.get("uncached_input_tokens"),
                        "cached_input_tokens": payload.get("cached_input_tokens"),
                        "reasoning_tokens": payload.get("reasoning_tokens"),
                        "output_tokens": payload.get("output_tokens"),
                        "token_basis": str(payload["token_basis"]),
                        "finish_category": payload.get("finish_category"),
                        "error_category": payload.get("error_category"),
                        "measurement_mask": observation.measurement_mask,
                        "primary_occurrence_id": observation.occurrence_id,
                        "first_seen_publication_id": self.publication_id,
                        "last_seen_publication_id": self.publication_id,
                    },
                    tuple(_MUTABLE_COLUMNS["model_call_tail"]),
                ),
            )
        )

    def _add_tool(
        self,
        logical_id: str,
        grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        fold = self._fold(logical_id)
        first = min(grouped, key=lambda item: item.sort_key)
        terminal = max(grouped, key=lambda item: item.sort_key)
        self.rows.append(
            PreparedRow(
                "tool_invocations",
                {
                    "tool_id": logical_id,
                    "adapter_native_invocation_key": str(observation.identity_tuple[0]),
                    "session_id": str(payload["session_id"]),
                    "turn_id": str(payload["turn_id"]),
                    "transport_name": str(payload["transport_name"]),
                    "semantic_operation": str(payload["semantic_operation"]),
                    "tool_family": str(payload["transport_name"]),
                    "primary_resource_id": payload.get("resource_id"),
                    "write_intent": int(payload.get("write_intent", 0)),
                    "lifecycle_state": fold.lifecycle_state,
                    "state_basis": fold.state_basis,
                    "transition_version": fold.transition_version,
                    "start_at_us": first.event_at_us,
                    "start_source_rank": first.source_rank,
                    "start_source_order": first.source_order,
                    "start_event_kind_order": first.event_kind_order,
                    "start_transition_rank": first.transition_rank,
                    "start_occurrence_id": first.occurrence_id,
                    "terminal_at_us": fold.terminal_at_us,
                    "terminal_source_rank": (
                        terminal.source_rank if fold.terminal_at_us is not None else None
                    ),
                    "terminal_source_order": (
                        terminal.source_order if fold.terminal_at_us is not None else None
                    ),
                    "terminal_event_kind_order": (
                        terminal.event_kind_order if fold.terminal_at_us is not None else None
                    ),
                    "terminal_transition_rank": (
                        terminal.transition_rank if fold.terminal_at_us is not None else None
                    ),
                    "terminal_occurrence_id": fold.terminal_occurrence_id,
                    "observed_duration_us": fold.observed_duration_us,
                    "output_bytes": payload.get("output_bytes"),
                    "error_category": fold.terminal_error_category,
                    "measurement_mask": observation.measurement_mask,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["tool_invocations"]),
            )
        )

    def _add_tool_resource(
        self,
        _logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        tool = str(payload["tool_id"])
        tool_operation = next(
            (
                str(item.payload.get("semantic_operation", "unknown"))
                for item in self.changes.observations
                if item.logical_id == tool
            ),
            "unknown",
        )
        role = {
            "search": "searched",
            "list": "listed",
            "execute": "executed",
            "write": "written",
            "patch": "patched",
            "test": "tested",
            "navigate": "navigated",
            "delegate": "delegated",
        }.get(
            tool_operation,
            tool_operation if tool_operation == "read" else "unknown",
        )
        self.rows.append(
            PreparedRow(
                "tool_resources",
                {
                    "tool_id": tool,
                    "resource_id": str(payload["resource_id"]),
                    "relationship_role": role,
                    "occurrence_id": observation.occurrence_id,
                },
            )
        )

    def _add_activity(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        fold = self._fold(logical_id)
        self.rows.append(
            PreparedRow(
                "activities",
                {
                    "activity_id": logical_id,
                    "session_id": str(payload["session_id"]),
                    "turn_id": payload.get("turn_id"),
                    "activity_kind": str(payload["activity_kind"]),
                    "lifecycle_state": fold.lifecycle_state,
                    "state_basis": fold.state_basis,
                    "transition_version": fold.transition_version,
                    **self._common_order(observation),
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["activities"]),
            )
        )

    def _add_compaction(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        self.rows.append(
            PreparedRow(
                "compaction_boundaries",
                {
                    "compaction_id": logical_id,
                    "session_id": str(payload["session_id"]),
                    "before_context_epoch": str(payload["before_context_epoch"]),
                    "after_context_epoch": str(payload["after_context_epoch"]),
                    **self._common_order(observation),
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                },
            )
        )

    def _add_state_change(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        self.rows.append(
            PreparedRow(
                "state_changes",
                {
                    "change_id": logical_id,
                    "session_id": str(payload["session_id"]),
                    "turn_id": payload.get("turn_id"),
                    "resource_id": str(payload["resource_id"]),
                    "change_kind": str(payload["change_kind"]),
                    "before_revision": payload.get("before_revision"),
                    "after_revision": payload.get("after_revision"),
                    "causal_attribution": 0,
                    "confidence": observation.confidence,
                    **self._common_order(observation),
                    "measurement_mask": observation.measurement_mask,
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": self.publication_id,
                },
            )
        )

    def _add_context_component(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        prior = self.prior.entity_rows.get(logical_id)
        self.rows.append(
            PreparedRow(
                "context_components",
                {
                    "component_id": logical_id,
                    "session_id": str(payload["session_id"]),
                    "turn_id": payload.get("turn_id"),
                    "call_id": payload.get("call_id"),
                    "category": str(payload["category"]),
                    "observed_utf8_bytes": int(payload["observed_utf8_bytes"]),
                    "observed_event_count": int(payload["observed_event_count"]),
                    "estimator": payload.get("estimator"),
                    "estimated_tokens": payload.get("estimated_tokens"),
                    "total_context_utf8_bytes": payload.get("total_context_utf8_bytes"),
                    "inclusion_basis": str(payload["inclusion_basis"]),
                    "capability_basis": str(payload["capability_basis"]),
                    "measurement_basis": str(payload["measurement_basis"]),
                    **self._common_order(observation),
                    "measurement_mask": observation.measurement_mask,
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": (
                        self.publication_id
                        if prior is None
                        else prior.values["first_seen_publication_id"]
                    ),
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["context_components"]),
            )
        )

    def _add_allowance_limit(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        self.rows.append(
            PreparedRow(
                "allowance_limits",
                {
                    "limit_id": logical_id,
                    "provider": str(payload["provider"]),
                    "account_local_identity": str(payload["account_local_identity"]),
                    "plan_identity": str(payload["plan_identity"]),
                    "window_kind": str(payload["window_kind"]),
                    "configured_duration_us": None,
                    "capability_basis": observation.basis,
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                ("last_seen_publication_id",),
            )
        )

    def _add_allowance_observation(
        self,
        logical_id: str,
        _grouped: list[AdapterObservation],
        observation: AdapterObservation,
    ) -> None:
        payload = observation.payload
        cycle_id = str(payload["cycle_id"])
        self._identity(
            cycle_id,
            "allowance-cycle",
            (
                str(payload["limit_id"]),
                str(payload["reset_identity"]),
                payload.get("cycle_start_us"),
                payload.get("cycle_end_us"),
            ),
        )
        self.rows.append(
            PreparedRow(
                "allowance_cycles",
                {
                    "cycle_id": cycle_id,
                    "limit_id": str(payload["limit_id"]),
                    "reset_identity": str(payload["reset_identity"]),
                    "start_at_us": payload.get("cycle_start_us"),
                    "end_at_us": payload.get("cycle_end_us"),
                    "reset_basis": observation.basis,
                    "completion_status": str(payload["completion_status"]),
                    "first_seen_publication_id": self.publication_id,
                    "last_seen_publication_id": self.publication_id,
                },
                tuple(_MUTABLE_COLUMNS["allowance_cycles"]),
            )
        )
        prior = self.prior.entity_rows.get(logical_id)
        self.rows.append(
            PreparedRow(
                "allowance_observations",
                {
                    "observation_id": logical_id,
                    "limit_id": str(payload["limit_id"]),
                    "cycle_id": cycle_id,
                    "plan_identity": str(payload["plan_identity"]),
                    "window_kind": str(payload["window_kind"]),
                    "reset_identity": str(payload["reset_identity"]),
                    "observation_ordinal": int(payload["observation_ordinal"]),
                    "used_percent": payload.get("used_percent"),
                    "remaining_percent": payload.get("remaining_percent"),
                    "absolute_fields_json": "{}",
                    "reset_time_us": payload.get("reset_time_us"),
                    "observed_at_us": observation.event_at_us,
                    "source_rank": observation.source_rank,
                    "source_order": observation.source_order,
                    "event_kind_order": observation.event_kind_order,
                    "transition_rank": observation.transition_rank,
                    "measurement_mask": observation.measurement_mask,
                    "primary_occurrence_id": observation.occurrence_id,
                    "first_seen_publication_id": (
                        self.publication_id
                        if prior is None
                        else prior.values["first_seen_publication_id"]
                    ),
                },
                tuple(_MUTABLE_COLUMNS["allowance_observations"]),
            )
        )

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        if value == 0:
            return "0"
        text = format(value.normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _add_allowance_intervals(self) -> None:
        compatibility_fields = (
            "provider",
            "limit_id",
            "plan_identity",
            "window_kind",
            "cycle_id",
            "reset_identity",
        )
        grouped_current: dict[tuple[str, ...], list[dict[str, object]]] = defaultdict(list)
        for grouped in self.observations_by_id.values():
            if grouped[0].observation_type != "AllowanceObservationObserved":
                continue
            observation = max(grouped, key=lambda item: item.sort_key)
            key = tuple(str(observation.payload[field]) for field in compatibility_fields)
            grouped_current[key].append(
                {
                    "observation_id": observation.logical_id,
                    **dict(observation.payload),
                    "observed_at_us": observation.event_at_us,
                    **self._common_order(observation),
                }
            )
        for key, current in sorted(grouped_current.items()):
            facts = list(current)
            predecessor = self.prior.allowance_predecessors.get(key)
            if predecessor is not None:
                facts.append(dict(predecessor.values))
            facts.sort(
                key=lambda item: (
                    item.get("observed_at_us") is None,
                    0 if item.get("observed_at_us") is None else item["observed_at_us"],
                    item.get("source_rank", 0),
                    item.get("source_order", 0),
                    item.get("event_kind_order", 0),
                    str(item["observation_id"]),
                    item.get("transition_rank", 0),
                )
            )
            for start, end in zip(facts, facts[1:], strict=False):
                start_id = str(start["observation_id"])
                end_id = str(end["observation_id"])
                if start_id == end_id:
                    continue
                start_at = start.get("observed_at_us")
                end_at = end.get("observed_at_us")
                if type(start_at) is not int or type(end_at) is not int:
                    continue
                if end_at < start_at:
                    raise PublicationWriteError("allowance observation time decreases")
                self._add_allowance_interval_row(start, end, start_id, end_id, start_at, end_at)

    def _add_allowance_interval_row(
        self,
        start: Mapping[str, object],
        end: Mapping[str, object],
        start_id: str,
        end_id: str,
        start_at: int,
        end_at: int,
    ) -> None:
        deltas: list[Decimal] = []
        if start.get("used_percent") is not None and end.get("used_percent") is not None:
            deltas.append(Decimal(str(end["used_percent"])) - Decimal(str(start["used_percent"])))
        if start.get("remaining_percent") is not None and end.get("remaining_percent") is not None:
            deltas.append(
                Decimal(str(start["remaining_percent"])) - Decimal(str(end["remaining_percent"]))
            )
        if deltas and any(delta != deltas[0] for delta in deltas[1:]):
            raise PublicationWriteError("used and remaining percentage deltas disagree")
        percent_delta = None if not deltas else self._decimal_text(deltas[0])
        interval_identity = (start_id, end_id)
        interval_id = semantic_id("allowance-interval", interval_identity)
        self._identity(interval_id, "allowance-interval", interval_identity)
        prior = self.prior.allowance_intervals.get(interval_id)
        if prior is not None:
            self.rows.append(prior)
            return
        self.rows.append(
            PreparedRow(
                "allowance_intervals",
                {
                    "interval_id": interval_id,
                    "limit_id": str(start["limit_id"]),
                    "cycle_id": str(start["cycle_id"]),
                    "start_observation_id": start_id,
                    "end_observation_id": end_id,
                    "start_us": start_at,
                    "end_us": end_at,
                    "percent_delta": percent_delta,
                    "compatibility_basis": "exact_identity_tuple_v1",
                    "ratio_eligible": int(percent_delta is not None and Decimal(percent_delta) > 0),
                    "coverage_json": "{}",
                    "first_seen_publication_id": self.publication_id,
                },
            )
        )

    def _prepared_entity_rows(self) -> dict[str, PreparedRow]:
        id_columns = {table: id_column for table, id_column in _ENTITY_TABLES.values()}
        return {
            str(row.values[id_columns[row.table]]): row
            for row in self.rows
            if row.table in id_columns
        }

    @staticmethod
    def _row_changed(prior: PreparedRow, proposed: PreparedRow) -> bool:
        prior_values = {
            key: value
            for key, value in prior.values.items()
            if key not in _PUBLICATION_PROVENANCE_COLUMNS
        }
        proposed_values = {
            key: value
            for key, value in proposed.values.items()
            if key not in _PUBLICATION_PROVENANCE_COLUMNS
        }
        return prior_values != proposed_values

    def _entity_classifications(self) -> dict[str, str]:
        prepared = self._prepared_entity_rows()
        classifications: dict[str, str] = {}
        for logical_id, proposed_row in prepared.items():
            prior_row = self.prior.entity_rows.get(logical_id)
            if prior_row is None:
                classifications[logical_id] = "inserted"
                continue
            prior_lifecycle = self.prior.lifecycle.get(logical_id, ())
            current_fold = self.folds.get(logical_id)
            if prior_lifecycle and current_fold is not None:
                prior_fold = fold_lifecycle(prior_lifecycle)
                if (
                    prior_fold.lifecycle_state not in TERMINAL_STATES
                    and current_fold.lifecycle_state in TERMINAL_STATES
                ):
                    classifications[logical_id] = "terminalized"
                    continue
            classifications[logical_id] = (
                "corrected" if self._row_changed(prior_row, proposed_row) else "unchanged"
            )
        return classifications

    def _token_deltas(self, classifications: dict[str, str]) -> dict[str, int | None]:
        fields = (
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
        )
        model_rows = {
            str(row.values["call_id"]): row for row in self.rows if row.table == "model_call_tail"
        }
        result: dict[str, int | None] = {}
        for field in fields:
            total = 0
            unavailable = False
            for logical_id, row in model_rows.items():
                classification = classifications[logical_id]
                proposed = row.values[field]
                prior_row = self.prior.entity_rows.get(logical_id)
                if classification == "inserted":
                    if type(proposed) is not int:
                        unavailable = True
                    else:
                        total += proposed
                    continue
                prior = None if prior_row is None else prior_row.values[field]
                if prior == proposed:
                    continue
                if type(prior) is int and type(proposed) is int:
                    total += proposed - prior
                else:
                    unavailable = True
            result[field] = None if unavailable else total
        return result

    def _add_accounting(self) -> None:
        classifications = self._entity_classifications()
        counts = dict(self.prior.entity_counts)
        inserted_by_kind: Counter[str] = Counter()
        corrected_by_kind: Counter[str] = Counter()
        terminalized_by_kind: Counter[str] = Counter()
        count_name_by_table = {
            _ENTITY_TABLES[observation_type][0]: count_name
            for observation_type, count_name in _ENTITY_COUNT_NAMES.items()
        }
        for logical_id, row in self._prepared_entity_rows().items():
            count_name = count_name_by_table[row.table]
            classification = classifications[logical_id]
            inserted_by_kind[count_name] += classification == "inserted"
            corrected_by_kind[count_name] += classification == "corrected"
            terminalized_by_kind[count_name] += classification == "terminalized"
        for count_name in count_name_by_table.values():
            if count_name in counts or inserted_by_kind[count_name]:
                counts[count_name] = counts.get(count_name, 0) + inserted_by_kind[count_name]
        inserted_occurrences = sum(
            occurrence.occurrence_id not in self.prior.occurrence_ids
            for occurrence in self.changes.occurrences
        )
        inserted_manifestations = len(
            {
                item.manifestation_key
                for item in self.inventories
                if item.manifestation_key not in self.prior.source_revisions
            }
        )
        counts["source_occurrences"] = counts.get("source_occurrences", 0) + inserted_occurrences
        counts["source_manifestations"] = (
            counts.get("source_manifestations", 0) + inserted_manifestations
        )
        for name, count in sorted(counts.items()):
            self.rows.append(
                PreparedRow(
                    "publication_entity_counts",
                    {
                        "publication_id": self.publication_id,
                        "entity_kind": name,
                        "entity_count": count,
                    },
                )
            )
        token_delta = self._token_deltas(classifications)
        changed_ids = {
            logical_id
            for logical_id, classification in classifications.items()
            if classification != "unchanged"
        }
        changed_observations = tuple(
            item for item in self.changes.observations if item.logical_id in changed_ids
        )
        self.rows.append(
            PreparedRow(
                "publication_deltas",
                {
                    "publication_id": self.publication_id,
                    "parent_publication_id": self.request.parent_publication_id,
                    "inserted_count": sum(inserted_by_kind.values()),
                    "corrected_count": sum(corrected_by_kind.values()),
                    "terminalized_count": sum(terminalized_by_kind.values()),
                    "recanonicalized_count": 0,
                    "removed_count": 0,
                    "uncached_input_token_delta": token_delta["uncached_input_tokens"],
                    "cached_input_token_delta": token_delta["cached_input_tokens"],
                    "reasoning_token_delta": token_delta["reasoning_tokens"],
                    "output_token_delta": token_delta["output_tokens"],
                    "affected_session_count": len(
                        {
                            str(item.payload["session_id"])
                            for item in changed_observations
                            if isinstance(item.payload.get("session_id"), str)
                        }
                    ),
                    "affected_turn_count": len(
                        {
                            str(item.payload["turn_id"])
                            for item in changed_observations
                            if isinstance(item.payload.get("turn_id"), str)
                        }
                    ),
                    "affected_tool_count": (
                        inserted_by_kind["tool_invocations"]
                        + corrected_by_kind["tool_invocations"]
                        + terminalized_by_kind["tool_invocations"]
                    ),
                    "affected_resource_count": (
                        inserted_by_kind["resources"]
                        + corrected_by_kind["resources"]
                        + terminalized_by_kind["resources"]
                    ),
                    "affected_state_change_count": (
                        inserted_by_kind["state_changes"]
                        + corrected_by_kind["state_changes"]
                        + terminalized_by_kind["state_changes"]
                    ),
                    "affected_allowance_observation_count": (
                        inserted_by_kind["allowance_observations"]
                        + corrected_by_kind["allowance_observations"]
                        + terminalized_by_kind["allowance_observations"]
                    ),
                    "source_coverage_changed": int(bool(self.inventories)),
                    "sample_truncated": 0,
                },
            )
        )
        affected_kinds = set(inserted_by_kind) | set(corrected_by_kind) | set(terminalized_by_kind)
        for entity_kind in sorted(affected_kinds):
            values = (
                inserted_by_kind[entity_kind],
                corrected_by_kind[entity_kind],
                terminalized_by_kind[entity_kind],
            )
            if not any(values):
                continue
            self.rows.append(
                PreparedRow(
                    "publication_delta_entities",
                    {
                        "publication_id": self.publication_id,
                        "entity_kind": entity_kind,
                        "inserted_count": values[0],
                        "corrected_count": values[1],
                        "terminalized_count": values[2],
                        "recanonicalized_count": 0,
                        "removed_count": 0,
                    },
                )
            )

    def _tail_state(self) -> ModelCallTailState | None:
        model_rows = tuple(row for row in self.rows if row.table == "model_call_tail")
        if not model_rows:
            state = self.prior.tail_state
            if state is None:
                return None
            return ModelCallTailState(
                row_count=state.row_count,
                minimum_event_at_us=state.minimum_event_at_us,
                maximum_event_at_us=state.maximum_event_at_us,
                maximum_source_order=state.maximum_source_order,
                base_publication_id=state.base_publication_id,
                last_fold_publication_id=self.publication_id,
            )
        unaffected = self.prior.unaffected_tail_state
        event_times = [
            int(row.values["event_at_us"])
            for row in model_rows
            if row.values["event_at_us"] is not None
        ]
        source_orders = [int(row.values["source_order"]) for row in model_rows]
        prior_minimum = (
            []
            if unaffected is None or unaffected.minimum_event_at_us is None
            else [unaffected.minimum_event_at_us]
        )
        prior_maximum = (
            []
            if unaffected is None or unaffected.maximum_event_at_us is None
            else [unaffected.maximum_event_at_us]
        )
        prior_source_order = (
            []
            if unaffected is None or unaffected.maximum_source_order is None
            else [unaffected.maximum_source_order]
        )
        return ModelCallTailState(
            row_count=(0 if unaffected is None else unaffected.row_count) + len(model_rows),
            minimum_event_at_us=min([*prior_minimum, *event_times], default=None),
            maximum_event_at_us=max([*prior_maximum, *event_times], default=None),
            maximum_source_order=max([*prior_source_order, *source_orders], default=None),
            base_publication_id=(
                self.publication_id
                if self.prior.tail_state is None
                else self.prior.tail_state.base_publication_id
            ),
            last_fold_publication_id=self.publication_id,
        )


def prepare_write_set(
    changes: ProposedChangeSet,
    request: PublicationRequest,
    *,
    configured_producer_key: str,
    prior: PriorPublicationSnapshot,
    inventory_started_at_us: int | None,
    inventory_completed_at_us: int | None,
) -> PublicationWriteSet:
    """Prepare CK-06 observations for a bounded CK-07 writer transaction."""

    return _WriteSetPreparer(
        changes,
        request,
        configured_producer_key=configured_producer_key,
        prior=prior,
        inventory_started_at_us=inventory_started_at_us,
        inventory_completed_at_us=inventory_completed_at_us,
    ).prepare()
