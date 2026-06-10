from __future__ import annotations

from codex_usage_tracker.i18n import normalize_language, translations_for


def test_normalize_language_supports_vietnamese_alias(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_USAGE_TRACKER_LANG", raising=False)

    assert normalize_language("vi") == "vi"
    assert normalize_language("vn") == "vi"


def test_normalize_language_falls_back_to_english_without_env(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_USAGE_TRACKER_LANG", raising=False)

    assert normalize_language(None) == "en"


def test_translations_for_vietnamese_includes_dashboard_title() -> None:
    translations = translations_for("vi")

    assert translations["dashboard.title"]
