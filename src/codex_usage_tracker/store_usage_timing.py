"""Shared SQL snippets for usage event timing joins."""

USAGE_TIMING_SELECT_SQL = """
    previous_usage.event_timestamp AS previous_call_event_timestamp,
    previous_usage.session_id AS previous_call_session_id,
    previous_usage.turn_id AS previous_call_turn_id
"""

USAGE_TIMING_JOIN_SQL = """
    LEFT JOIN usage_events previous_usage
        ON previous_usage.record_id = usage_events.previous_record_id
"""
