"""Transport-independent snapshot and SSE replay semantics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from .journal import MAX_REPLAY, GenerationJournal, JournalEvent


@dataclass(frozen=True)
class StreamBatch:
    events: tuple[JournalEvent, ...]
    generation: int
    next_event_id: int
    snapshot_required: bool
    replay_truncated: bool
    heartbeat: bool
    heartbeat_seconds: int

    def to_sse(self) -> tuple[str, ...]:
        if self.snapshot_required:
            data = json.dumps(
                {"generation": self.generation},
                separators=(",", ":"),
                sort_keys=True,
            )
            return (f"event: snapshot_required\ndata: {data}\n\n",)
        if self.events:
            return tuple(event.to_sse() for event in self.events)
        return (": heartbeat\n\n",)


class LiveStream:
    """Read one bounded replay page without refreshing or taking writer lease."""

    def __init__(
        self,
        journal: GenerationJournal,
        *,
        heartbeat_seconds: int = 15,
    ) -> None:
        if not 5 <= heartbeat_seconds <= 120:
            raise ValueError("heartbeat interval is out of bounds")
        self._journal = journal
        self._heartbeat_seconds = heartbeat_seconds

    def read(
        self,
        *,
        last_event_id: int | None,
        limit: int = 100,
        active_generation: int,
        active_publication_id: str | None = None,
    ) -> StreamBatch:
        if not 1 <= limit <= MAX_REPLAY:
            raise ValueError("stream replay limit is out of bounds")
        replay = self._journal.replay(last_event_id, limit=limit)
        latest_id = replay.latest_event_id or 0
        earliest_id = replay.earliest_event_id
        before_retention = (
            last_event_id is not None
            and earliest_id is not None
            and last_event_id < earliest_id - 1
        )
        generation_gap = (
            active_generation > 0
            and (replay.latest_generation or 0) < active_generation
        )
        future_id = (
            last_event_id is not None
            and last_event_id > (replay.latest_event_id or 0)
        )
        publication_gap = (
            active_publication_id is not None
            and replay.latest_publication_id != active_publication_id
        )
        snapshot_required = (
            before_retention or generation_gap or future_id or publication_gap
        )
        events = () if snapshot_required else replay.events
        next_event_id = events[-1].event_id if events else latest_id
        return StreamBatch(
            events=events,
            generation=active_generation,
            next_event_id=next_event_id,
            snapshot_required=snapshot_required,
            replay_truncated=replay.truncated and not snapshot_required,
            heartbeat=not events and not snapshot_required,
            heartbeat_seconds=self._heartbeat_seconds,
        )


def validate_loopback_origin(origin: str | None) -> str | None:
    if origin is None:
        return None
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("live stream origin must be loopback")
    return origin


def parse_last_event_id(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    if not value.isascii() or not value.isdigit():
        raise ValueError("Last-Event-ID is invalid")
    event_id = int(value)
    if event_id > 9_223_372_036_854_775_807:
        raise ValueError("Last-Event-ID is invalid")
    return event_id
