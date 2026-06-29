from __future__ import annotations

from urllib.parse import quote

import pytest

from codex_usage_tracker.server.open_investigator import (
    OPEN_INVESTIGATOR_SCHEMA,
    OpenInvestigatorRequestError,
    open_investigator_payload,
)


def test_open_investigator_payload_opens_safe_relative_dashboard_url() -> None:
    opened_urls: list[str] = []
    target = quote("/dashboard.html?view=call&record=abc", safe="")

    payload = open_investigator_payload(
        f"url={target}",
        request_host="127.0.0.1:8898",
        server_port=8898,
        dashboard_name="dashboard.html",
        open_new_tab=lambda url: opened_urls.append(url) or True,
    )

    assert payload == {
        "schema": OPEN_INVESTIGATOR_SCHEMA,
        "opened": True,
        "url": "http://127.0.0.1:8898/dashboard.html?view=call&record=abc",
    }
    assert opened_urls == ["http://127.0.0.1:8898/dashboard.html?view=call&record=abc"]


def test_open_investigator_payload_preserves_fragment() -> None:
    opened_urls: list[str] = []
    target = quote(
        "http://127.0.0.1:8898/dashboard.html?view=call&record=abc#section",
        safe="",
    )

    payload = open_investigator_payload(
        f"url={target}",
        request_host="localhost:8898",
        server_port=8898,
        dashboard_name="dashboard.html",
        open_new_tab=lambda url: opened_urls.append(url) or False,
    )

    assert payload["opened"] is False
    assert payload["url"] == "http://localhost:8898/dashboard.html?view=call&record=abc#section"
    assert opened_urls == ["http://localhost:8898/dashboard.html?view=call&record=abc#section"]


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("", "url is required"),
        ("url=ftp://127.0.0.1/dashboard.html?view=call&record=abc", "Only dashboard URLs can be opened"),
        (
            "url=http://example.com/dashboard.html?view=call&record=abc",
            "Only loopback dashboard URLs can be opened",
        ),
        (
            "url=http://127.0.0.1:8899/dashboard.html?view=call&record=abc",
            "Dashboard URL port is not allowed",
        ),
        (
            "url=http://127.0.0.1:8898/other.html?view=call&record=abc",
            "Only dashboard investigator URLs can be opened",
        ),
        (
            "url=http://127.0.0.1:8898/dashboard.html?view=thread&record=abc",
            "Investigator URL must include view=call and record",
        ),
    ],
)
def test_open_investigator_payload_rejects_unsafe_targets(query: str, message: str) -> None:
    with pytest.raises(OpenInvestigatorRequestError, match=message):
        open_investigator_payload(
            query,
            request_host="127.0.0.1:8898",
            server_port=8898,
            dashboard_name="dashboard.html",
            open_new_tab=lambda _: True,
        )
