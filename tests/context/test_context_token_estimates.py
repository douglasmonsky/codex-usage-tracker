from __future__ import annotations

from typing import Any

from codex_usage_tracker.context import token_estimates as context_token_estimates


class _FakeEncoding:
    name = "fake"

    def encode(self, text: str) -> list[str]:
        return text.split()


class _BrokenEncoding:
    def encode(self, _text: str) -> list[str]:
        raise RuntimeError("encoding unavailable")


class _FallbackEncodings:
    def get_encoding(self, name: str) -> _FakeEncoding:
        if name == "o200k_base":
            raise ValueError("encoding unavailable")
        return _FakeEncoding()


def test_token_estimate_uses_encoding_when_available() -> None:
    assert context_token_estimates.token_estimate("one two three", _FakeEncoding()) == 3


def test_token_estimate_falls_back_to_chars_per_four() -> None:
    assert context_token_estimates.token_estimate("abcdefgh", _BrokenEncoding()) == 2
    assert context_token_estimates.token_estimate("", None) == 0


def test_fallback_encoding_uses_next_available_encoding() -> None:
    assert isinstance(
        context_token_estimates._fallback_encoding(_FallbackEncodings()),
        _FakeEncoding,
    )


def test_estimate_visible_tokens_uses_joined_entry_text(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        context_token_estimates,
        "context_encoding",
        lambda _model: (_FakeEncoding(), "fake-estimator"),
    )

    estimate = context_token_estimates.estimate_visible_tokens(
        [{"text": "one two"}, {"text": ""}, {"text": "three"}],
        "gpt-test",
    )

    assert estimate == {
        "visible_char_count": len("one two\n\nthree"),
        "visible_token_estimate": 3,
        "visible_token_estimator": "fake-estimator",
    }
