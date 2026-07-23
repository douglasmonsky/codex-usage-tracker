from __future__ import annotations

import pytest

from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.application.errors import RequestValidationError


def test_request_rejects_unbounded_and_conflicting_interactive_fields() -> None:
    with pytest.raises(RequestValidationError, match="finite"):
        AllowanceRequest("series", range="all")
    with pytest.raises(RequestValidationError, match="cursor.*evidence"):
        AllowanceRequest("status", cursor="opaque")
    with pytest.raises(RequestValidationError, match="analysis_id.*analysis"):
        AllowanceRequest("evidence", analysis_id="snapshot-1")
    with pytest.raises(RequestValidationError, match="execution.*analysis"):
        AllowanceRequest("series", execution="sync")
    with pytest.raises(RequestValidationError, match="weekly"):
        AllowanceRequest("analysis", window="five_hour")
