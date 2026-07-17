from __future__ import annotations

from codex_usage_tracker.core.api_payloads import refresh_result_payload
from codex_usage_tracker.core.models import RefreshResult


def test_refresh_payload_preserves_nonzero_otel_diagnostics() -> None:
    result = RefreshResult(
        scanned_files=1,
        parsed_events=1,
        inserted_or_updated_events=1,
        db_path="/synthetic/usage.sqlite3",
        parser_diagnostics={"otel_matched": 1},
    )

    payload = refresh_result_payload(result, schema="synthetic-refresh-v1")

    assert payload["parser_diagnostics"] == {"otel_matched": 1}
