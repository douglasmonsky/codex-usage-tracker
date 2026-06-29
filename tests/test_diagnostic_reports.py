from __future__ import annotations

from codex_usage_tracker.diagnostic_reports import _action_hint


def test_action_hint_prioritizes_compaction_type_and_name() -> None:
    by_type = _action_hint(fact_type="compaction", fact_name="anything")
    by_name = _action_hint(fact_type="other", fact_name="post_compaction")

    assert by_type == by_name
    assert "fresh handoff" in by_type


def test_action_hint_distinguishes_unknown_command_family() -> None:
    unknown = _action_hint(fact_type="command_family", fact_name="unknown_command")
    repeated = _action_hint(fact_type="command_family", fact_name="pytest")

    assert "command text is intentionally not stored" in unknown
    assert "validation or command loops" in repeated


def test_action_hint_uses_specific_fact_name_before_default() -> None:
    patch = _action_hint(fact_type="event", fact_name="patch_applied")
    fallback = _action_hint(fact_type="event", fact_name="something_else")

    assert "Likely productive work" in patch
    assert "Open associated high-cost calls" in fallback
