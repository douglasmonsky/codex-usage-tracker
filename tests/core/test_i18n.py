from __future__ import annotations

import re
from pathlib import Path

import pytest

from codex_usage_tracker.core.i18n import (
    LANGUAGE_ENV_VAR,
    SUPPORTED_LANGUAGE_METADATA,
    SUPPORTED_LANGUAGES,
    available_languages,
    dashboard_i18n_payload,
    language_direction,
    normalize_language,
    raw_catalog,
    translations_for,
)
from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.store.api import refresh_usage_index
from tests.store_dashboard_helpers import _make_codex_home

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def test_supported_language_metadata_and_files_match() -> None:
    locale_dir = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "locales"
    )
    assert set(SUPPORTED_LANGUAGE_METADATA) == set(SUPPORTED_LANGUAGES)
    assert {entry["code"] for entry in available_languages()} == set(SUPPORTED_LANGUAGES)
    assert {path.stem for path in locale_dir.glob("*.json")} == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_catalogs_match_canonical_keys_and_placeholders(language: str) -> None:
    english = raw_catalog("en")
    current = raw_catalog(language)

    assert current
    assert set(current) == set(english)
    assert all(isinstance(value, str) and value.strip() for value in current.values())
    for key, value in english.items():
        assert set(_PLACEHOLDER_RE.findall(current[key])) == set(_PLACEHOLDER_RE.findall(value))


def test_translations_are_copied_and_unknown_language_falls_back() -> None:
    first = translations_for("en")
    first["dashboard.title"] = "changed"
    assert translations_for("en")["dashboard.title"] != "changed"
    assert translations_for("zz")["dashboard.title"] == translations_for("en")["dashboard.title"]


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ("en-US", "en"),
        ("vi-VN", "vi"),
        ("pt-BR", "pt"),
        ("zh-CN", "zh-Hans"),
        ("zh_CN", "zh-Hans"),
    ],
)
def test_normalize_language_aliases(requested: str, expected: str) -> None:
    assert normalize_language(requested) == expected


def test_normalize_language_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LANGUAGE_ENV_VAR, "ar")
    assert normalize_language(None) == "ar"
    assert language_direction("ar") == "rtl"
    assert language_direction("en") == "ltr"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_dashboard_i18n_payload_shape(language: str) -> None:
    payload = dashboard_i18n_payload(language)
    assert payload["language"] == normalize_language(language)
    assert payload["language_direction"] == language_direction(language)
    assert {entry["code"] for entry in payload["available_languages"]} == set(SUPPORTED_LANGUAGES)
    assert set(payload["translation_catalog"]) == set(SUPPORTED_LANGUAGES)
    assert payload["translations"]["dashboard.title"]


def test_shared_dashboard_payload_localization_does_not_change_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    english = dashboard_payload(db_path=db_path, language="en")
    spanish = dashboard_payload(db_path=db_path, language="es")

    assert spanish["language"] == "es"
    assert spanish["language_direction"] == "ltr"
    assert english["rows"] == spanish["rows"]
