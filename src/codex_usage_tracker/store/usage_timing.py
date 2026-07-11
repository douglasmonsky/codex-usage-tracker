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


USAGE_PARENT_SELECT_ALL_SQL = """
    CASE
        WHEN usage_events.parent_session_id IS NULL THEN usage_events.parent_thread_name
        ELSE coalesce(usage_events.parent_thread_name, (
            SELECT max(parent_usage.thread_name)
            FROM usage_events parent_usage
            WHERE parent_usage.session_id = usage_events.parent_session_id
                AND parent_usage.thread_name IS NOT NULL
        ))
    END AS resolved_parent_thread_name,
    CASE
        WHEN usage_events.parent_session_id IS NULL THEN usage_events.parent_session_updated_at
        ELSE coalesce(usage_events.parent_session_updated_at, (
            SELECT max(parent_usage.session_updated_at)
            FROM usage_events parent_usage
            WHERE parent_usage.session_id = usage_events.parent_session_id
        ))
    END AS resolved_parent_session_updated_at
"""

USAGE_PARENT_SELECT_ACTIVE_SQL = """
    CASE
        WHEN usage_events.parent_session_id IS NULL THEN usage_events.parent_thread_name
        ELSE coalesce(usage_events.parent_thread_name, (
            SELECT max(parent_usage.thread_name)
            FROM usage_events parent_usage
            WHERE parent_usage.session_id = usage_events.parent_session_id
                AND parent_usage.thread_name IS NOT NULL
                AND parent_usage.is_archived = 0
                AND parent_usage.source_file NOT LIKE '%/archived_sessions/%'
                AND parent_usage.source_file NOT LIKE 'archived_sessions/%'
                AND parent_usage.source_file NOT LIKE '%\\archived_sessions\\%'
                AND parent_usage.source_file NOT LIKE 'archived_sessions\\%'
        ))
    END AS resolved_parent_thread_name,
    CASE
        WHEN usage_events.parent_session_id IS NULL THEN usage_events.parent_session_updated_at
        ELSE coalesce(usage_events.parent_session_updated_at, (
            SELECT max(parent_usage.session_updated_at)
            FROM usage_events parent_usage
            WHERE parent_usage.session_id = usage_events.parent_session_id
                AND parent_usage.is_archived = 0
                AND parent_usage.source_file NOT LIKE '%/archived_sessions/%'
                AND parent_usage.source_file NOT LIKE 'archived_sessions/%'
                AND parent_usage.source_file NOT LIKE '%\\archived_sessions\\%'
                AND parent_usage.source_file NOT LIKE 'archived_sessions\\%'
        ))
    END AS resolved_parent_session_updated_at
"""


def usage_parent_select_sql(*, include_archived: bool) -> str:
    """Resolve parent labels without materializing every session for each page."""

    return USAGE_PARENT_SELECT_ALL_SQL if include_archived else USAGE_PARENT_SELECT_ACTIVE_SQL
