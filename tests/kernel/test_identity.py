from __future__ import annotations

import pytest

from codex_usage_tracker.kernel.identity import (
    canonical_fingerprint,
    event_id,
    safe_label,
    source_id,
    stable_id,
)


def test_public_ids_are_stable_across_rebuild_and_row_order() -> None:
    inputs = ("thread-123", "turn-4", "call-8")

    assert stable_id("call", *inputs) == stable_id("call", *inputs)
    assert stable_id("call", *inputs) != stable_id("turn", *inputs)
    assert canonical_fingerprint({"model": "gpt-5", "effort": "high"}) == (
        canonical_fingerprint({"effort": "high", "model": "gpt-5"})
    )


def test_source_and_event_ids_use_safe_semantic_identity() -> None:
    source = source_id(
        source_kind="session",
        device_identity="device-1",
        file_identity="inode-2",
    )

    assert source.startswith("src_")
    assert event_id(source, byte_offset=42, event_kind="token_count").startswith("evt_")
    assert "/Users/" not in source


@pytest.mark.parametrize(
    "candidate",
    [
        "/Users/example/private-project",
        r"C:\Users\example\private-project",
        "../private-project",
        "name/with/slash",
        "name\x00with-null",
    ],
)
def test_safe_labels_reject_path_or_control_material(candidate: str) -> None:
    with pytest.raises(ValueError):
        safe_label(candidate)


def test_safe_labels_are_bounded_and_deterministic() -> None:
    assert safe_label("Project Alpha") == "Project Alpha"
    with pytest.raises(ValueError):
        safe_label("x" * 65)
