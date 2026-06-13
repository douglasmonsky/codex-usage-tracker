from codex_usage_tracker.redaction import redact_secrets


def test_redaction_preserves_token_accounting_labels() -> None:
    text = "\n".join(
        [
            "Budget:",
            "- Tokens used=12345",
            "- Token budget=50000",
            "- Tokens remaining=37655",
            "input_tokens=1200",
            "cached_input_tokens=900",
            "uncached_input_tokens=300",
            "output_tokens=75",
            "reasoning_output_tokens=25",
            "total_tokens=1275",
        ]
    )

    assert redact_secrets(text) == text


def test_redaction_still_redacts_secret_token_labels() -> None:
    text = "\n".join(
        [
            "token=plain-secret-value",
            "access_token=access-secret-value",
            "github token=github-secret-value",
            "token_secret=token-secret-value",
            "api_key=api-key-secret-value",
            "client_secret=client-secret-value",
        ]
    )

    redacted = redact_secrets(text)

    assert "plain-secret-value" not in redacted
    assert "access-secret-value" not in redacted
    assert "github-secret-value" not in redacted
    assert "token-secret-value" not in redacted
    assert "api-key-secret-value" not in redacted
    assert "client-secret-value" not in redacted
    assert redacted.count("[REDACTED_SECRET]") == 6
