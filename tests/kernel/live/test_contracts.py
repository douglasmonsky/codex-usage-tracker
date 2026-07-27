from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from codex_usage_tracker.kernel.live.journal import GenerationJournal
from codex_usage_tracker.kernel.live.stream import (
    LiveStream,
    parse_last_event_id,
    validate_loopback_origin,
)
from codex_usage_tracker.kernel.operational import (
    initialize_operational_database,
    kernel_paths,
)


def test_replay_is_monotonic_bounded_and_restart_safe(tmp_path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    journal = GenerationJournal(path, retention=3)
    for generation in range(1, 6):
        journal.publish_generation(
            generation,
            publication_id=f"publication-{generation}",
            changed_sources=1,
            inserted_calls=generation,
            inserted_tools=0,
            deleted_rows=0,
        )

    stream = LiveStream(journal, heartbeat_seconds=15)
    retained = stream.read(last_event_id=3, limit=2, active_generation=5)
    assert [event.event_id for event in retained.events] == [4, 5]
    assert retained.next_event_id == 5
    assert not retained.snapshot_required

    before_retention = stream.read(
        last_event_id=1,
        limit=2,
        active_generation=5,
    )
    assert before_retention.snapshot_required
    assert before_retention.events == ()

    restarted = LiveStream(GenerationJournal(path, retention=3))
    heartbeat = restarted.read(
        last_event_id=5,
        limit=2,
        active_generation=5,
    )
    assert heartbeat.heartbeat
    assert heartbeat.next_event_id == 5
    assert heartbeat.to_sse() == (": heartbeat\n\n",)


def test_stream_payload_and_origin_are_private_and_loopback_only(tmp_path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    journal = GenerationJournal(path)

    with pytest.raises(ValueError, match="private"):
        journal.append(
            generation=1,
            event_kind="generation_committed",
            selector=None,
            payload={"arguments": "PRIVATE_SYNTHETIC_SENTINEL"},
            publication_id="unsafe-publication",
        )
    with pytest.raises(ValueError, match="identity"):
        journal.append(
            generation=1,
            event_kind="generation_committed\nid: injected",
            selector=None,
            payload={"inserted_calls": 1},
            publication_id="publication-1",
        )
    assert validate_loopback_origin(None) is None
    assert validate_loopback_origin("http://127.0.0.1:47821") == (
        "http://127.0.0.1:47821"
    )
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_origin("https://example.com")
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_origin("http://127.0.0.1/private")
    assert parse_last_event_id("42") == 42
    assert parse_last_event_id(None) is None
    with pytest.raises(ValueError, match="Last-Event-ID"):
        parse_last_event_id("-1")


def test_burst_slow_client_disconnect_and_generation_gap_are_bounded(
    tmp_path,
) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    journal = GenerationJournal(path, retention=10)
    for generation in range(1, 21):
        journal.publish_generation(
            generation,
            publication_id=f"publication-{generation}",
            changed_sources=1,
            inserted_calls=1,
            inserted_tools=0,
            deleted_rows=0,
        )
    before = path.read_bytes()

    first = LiveStream(journal).read(
        last_event_id=10,
        limit=3,
        active_generation=20,
    )
    resumed = LiveStream(journal).read(
        last_event_id=first.next_event_id,
        limit=3,
        active_generation=20,
    )
    assert [event.event_id for event in first.events] == [11, 12, 13]
    assert [event.event_id for event in resumed.events] == [14, 15, 16]
    assert first.replay_truncated
    assert path.read_bytes() == before

    gap = LiveStream(journal).read(
        last_event_id=20,
        limit=3,
        active_generation=21,
    )
    assert gap.snapshot_required
    assert not gap.heartbeat
    assert gap.to_sse()[0].startswith("event: snapshot_required\n")
    future = LiveStream(journal).read(
        last_event_id=10_000,
        limit=3,
        active_generation=20,
        active_publication_id="publication-20",
    )
    assert future.snapshot_required


def test_sse_event_is_compact_and_contains_generation_identity(tmp_path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    event = GenerationJournal(path).publish_generation(
        1,
        publication_id="publication-1",
        changed_sources=2,
        inserted_calls=3,
        inserted_tools=4,
        deleted_rows=0,
    )

    payload = event.to_sse()
    assert payload.startswith("id: 1\nevent: generation_committed\n")
    assert '"generation":1' in payload
    assert '"publication_id":"publication-1"' in payload
    assert "PRIVATE_" not in payload


def test_concurrent_publishers_allocate_unique_monotonic_ids(tmp_path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    journal = GenerationJournal(path, retention=100)

    def publish(generation: int):
        return journal.append(
            generation=generation,
            event_kind="generation_committed",
            selector=None,
            payload={"inserted_calls": 1},
            event_key=f"concurrent:{generation}",
            publication_id=f"publication-{generation}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        events = list(executor.map(publish, range(1, 33)))

    assert sorted(event.event_id for event in events) == list(range(1, 33))
    replay = journal.replay(None, limit=100)
    assert [event.event_id for event in replay.events] == list(range(1, 33))


def test_rollback_and_reused_generation_require_new_publication(tmp_path) -> None:
    path = kernel_paths(tmp_path).operational
    initialize_operational_database(path)
    journal = GenerationJournal(path)
    journal.publish_generation(
        1,
        publication_id="artifact-one",
        changed_sources=1,
        inserted_calls=1,
        inserted_tools=0,
        deleted_rows=0,
    )
    journal.publish_generation(
        2,
        publication_id="artifact-two-old",
        changed_sources=1,
        inserted_calls=1,
        inserted_tools=0,
        deleted_rows=0,
    )

    rolled_back = LiveStream(journal).read(
        last_event_id=2,
        active_generation=1,
        active_publication_id="artifact-one",
    )
    assert rolled_back.snapshot_required

    replacement = journal.publish_generation(
        2,
        publication_id="artifact-two-new",
        changed_sources=1,
        inserted_calls=2,
        inserted_tools=0,
        deleted_rows=0,
    )
    assert replacement.event_id == 3
    resumed = LiveStream(journal).read(
        last_event_id=2,
        active_generation=2,
        active_publication_id="artifact-two-new",
    )
    assert [event.event_id for event in resumed.events] == [3]
