from __future__ import annotations

from codex_usage_tracker.server_context_settings import (
    CONTEXT_SETTINGS_SCHEMA,
    ContextApiState,
    context_settings_payload,
)


def test_context_settings_payload_defaults_to_enabled() -> None:
    state = ContextApiState(False)

    payload = context_settings_payload("", context_api_state=state)

    assert payload == {
        "schema": CONTEXT_SETTINGS_SCHEMA,
        "context_api_enabled": True,
        "raw_context_persisted": False,
    }
    assert state.enabled is True


def test_context_settings_payload_disables_context_api() -> None:
    state = ContextApiState(True)

    payload = context_settings_payload("enabled=false", context_api_state=state)

    assert payload["context_api_enabled"] is False
    assert payload["raw_context_persisted"] is False
    assert state.enabled is False


def test_context_settings_payload_accepts_truthy_values() -> None:
    state = ContextApiState(False)

    payload = context_settings_payload("enabled=on", context_api_state=state)

    assert payload["context_api_enabled"] is True
    assert state.enabled is True
