from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.i18n import (
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
from codex_usage_tracker.store import refresh_usage_index
from tests.test_store_dashboard_mcp import _make_codex_home

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
EXPECTED_KEY_PREFIXES = (
    "dashboard.",
    "aria.",
    "docs.",
    "badge.",
    "button.",
    "action.",
    "nav.",
    "filter.",
    "option.",
    "metric.",
    "section.",
    "preset.",
    "insight.",
    "recommendation.",
    "severity.",
    "state.",
    "status.",
    "table.",
    "caption.",
    "call.",
    "date.",
    "history.",
    "pricing.",
    "parser.",
    "privacy.",
    "allowance.",
    "credit.",
    "source.",
    "thread.",
    "detail.",
    "context.",
    "live.",
    "language.",
    "effort.",
    "flag.",
)


def placeholders(value: str) -> set[str]:
    return set(_PLACEHOLDER_RE.findall(value))


def discover_locale_file_stems() -> set[str]:
    repo_root = Path(__file__).resolve().parents[1]
    locale_dir = repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "locales"
    return {path.stem for path in locale_dir.glob("*.json")}


def dashboard_template_text() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_template.html"
    ).read_text(encoding="utf-8")


def dashboard_js_text() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard.js"
    ).read_text(encoding="utf-8")


def extract_js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    brace = source.index("{", start)
    depth = 0
    for offset, char in enumerate(source[brace:], start=brace):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : offset + 1]
    raise AssertionError(f"could not extract function {name}")


def test_supported_language_metadata_matches_supported_languages() -> None:
    assert set(SUPPORTED_LANGUAGE_METADATA) == set(SUPPORTED_LANGUAGES)


def test_supported_language_catalog_files_match_supported_languages() -> None:
    assert discover_locale_file_stems() == set(SUPPORTED_LANGUAGES)


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_raw_catalog_is_valid_nonempty_string_mapping(language: str) -> None:
    catalog = raw_catalog(language)

    assert catalog
    assert all(isinstance(key, str) and key for key in catalog)
    assert all(isinstance(value, str) and value.strip() for value in catalog.values())


def test_english_catalog_is_canonical_and_nonempty() -> None:
    english = raw_catalog("en")

    assert english
    assert english["dashboard.title"] == "Usage Dashboard"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_catalog_keys_match_english(language: str) -> None:
    assert set(raw_catalog(language)) == set(raw_catalog("en"))


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_catalog_placeholders_match_english(language: str) -> None:
    english = raw_catalog("en")
    current = raw_catalog(language)

    for key, english_value in english.items():
        assert placeholders(current[key]) == placeholders(english_value), key


def test_catalog_keys_use_expected_namespaces() -> None:
    for key in raw_catalog("en"):
        assert key.startswith(EXPECTED_KEY_PREFIXES), key


def test_no_raw_english_sentence_keys_in_canonical_catalog() -> None:
    for key in raw_catalog("en"):
        assert not key.startswith(("This ", "The ", "Review ")), key


def test_recommendation_and_flag_stable_keys_are_in_canonical_catalog() -> None:
    english = raw_catalog("en")

    for key in [
        "recommendation.pricing_gap.title",
        "recommendation.pricing_gap.why",
        "recommendation.pricing_gap.action",
        "recommendation.context_bloat.title",
        "recommendation.low_cache.action",
        "recommendation.none.action",
        "flag.high_context_use",
        "flag.low_cache_reuse",
        "flag.expensive_low_output_call",
    ]:
        assert english[key]


def test_translations_for_returns_copy() -> None:
    first = translations_for("en")
    first["dashboard.title"] = "mutated"

    assert translations_for("en")["dashboard.title"] == "Usage Dashboard"


def test_unknown_language_falls_back_to_english() -> None:
    assert translations_for("zz")["dashboard.title"] == translations_for("en")["dashboard.title"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("en", "en"),
        ("english", "en"),
        ("en-US", "en"),
        ("en_US", "en"),
        ("vi", "vi"),
        ("vn", "vi"),
        ("vi-VN", "vi"),
        ("vietnamese", "vi"),
        ("es", "es"),
        ("spanish", "es"),
        ("fr", "fr"),
        ("french", "fr"),
        ("de", "de"),
        ("german", "de"),
        ("pt-BR", "pt"),
        ("portuguese", "pt"),
        ("ja", "ja"),
        ("japanese", "ja"),
        ("zh", "zh-Hans"),
        ("zh-CN", "zh-Hans"),
        ("zh_CN", "zh-Hans"),
        ("simplified chinese", "zh-Hans"),
        ("ko", "ko"),
        ("korean", "ko"),
        ("ru", "ru"),
        ("russian", "ru"),
        ("it", "it"),
        ("italian", "it"),
        ("ar", "ar"),
        ("arabic", "ar"),
        ("unknown", "en"),
        ("", "en"),
        (None, "en"),
    ],
)
def test_normalize_language_aliases(raw: str | None, expected: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(LANGUAGE_ENV_VAR, raising=False)

    assert normalize_language(raw) == expected


def test_normalize_language_uses_env_when_argument_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LANGUAGE_ENV_VAR, "es")

    assert normalize_language(None) == "es"


def test_normalize_language_argument_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LANGUAGE_ENV_VAR, "es")

    assert normalize_language("fr") == "fr"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_language_direction_is_valid(language: str) -> None:
    assert language_direction(language) in {"ltr", "rtl"}


def test_arabic_direction_is_rtl() -> None:
    assert language_direction("ar") == "rtl"


@pytest.mark.parametrize("language", [lang for lang in SUPPORTED_LANGUAGES if lang != "ar"])
def test_non_arabic_starter_languages_are_ltr(language: str) -> None:
    assert language_direction(language) == "ltr"


def test_available_languages_are_derived_from_supported_metadata() -> None:
    languages = available_languages()

    assert {entry["code"] for entry in languages} == set(SUPPORTED_LANGUAGES)
    for entry in languages:
        assert entry["native_name"]
        assert entry["english_name"]
        assert entry["dir"] in {"ltr", "rtl"}


def test_dashboard_i18n_payload_shape_for_each_supported_language() -> None:
    for language in SUPPORTED_LANGUAGES:
        payload = dashboard_i18n_payload(language)
        assert payload["language"] == normalize_language(language)
        assert payload["language_direction"] == language_direction(language)
        assert {entry["code"] for entry in payload["available_languages"]} == set(SUPPORTED_LANGUAGES)  # type: ignore[index]
        assert set(payload["translation_catalog"]) == set(SUPPORTED_LANGUAGES)  # type: ignore[arg-type]
        assert payload["translations"]["dashboard.title"]  # type: ignore[index]


def test_dashboard_i18n_payload_unknown_language_falls_back_to_english() -> None:
    assert dashboard_i18n_payload("zz")["language"] == "en"


def test_dashboard_payload_includes_i18n_without_changing_rows(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    english = dashboard_payload(db_path=db_path, language="en")
    spanish = dashboard_payload(db_path=db_path, language="es")

    assert spanish["language"] == "es"
    assert spanish["language_direction"] == "ltr"
    assert spanish["available_languages"]
    assert spanish["translation_catalog"]
    assert english["rows"] == spanish["rows"]


def test_generate_dashboard_sets_language_and_direction(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    output = tmp_path / "dashboard.html"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    generate_dashboard(db_path=db_path, output_path=output, language="ar")
    html = output.read_text(encoding="utf-8")
    payload = _dashboard_payload_from_html(html)

    assert '<html lang="ar" dir="rtl">' in html
    assert raw_catalog("ar")["dashboard.title"] in html
    assert payload["language"] == "ar"
    assert payload["language_direction"] == "rtl"


def test_generate_dashboard_normalizes_simplified_chinese_alias(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    output = tmp_path / "dashboard.html"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    generate_dashboard(db_path=db_path, output_path=output, language="zh-CN")
    html = output.read_text(encoding="utf-8")
    payload = _dashboard_payload_from_html(html)

    assert '<html lang="zh-Hans" dir="ltr">' in html
    assert payload["language"] == "zh-Hans"


def test_dashboard_template_has_dynamic_language_selector_and_runtime_status_owner() -> None:
    template = dashboard_template_text()

    assert '<html lang="__HTML_LANG__" dir="__HTML_DIR__">' in template
    assert 'id="languageSelect"' in template
    assert 'data-i18n-aria-label="language.label"' in template
    assert '<option value="en">English</option>' in template
    assert 'value="vi"' not in template
    live_status_match = re.search(r'<span id="liveStatus"[^>]*>', template)
    assert live_status_match
    assert "data-i18n" not in live_status_match.group(0)


def test_dashboard_js_generates_language_options_and_preserves_runtime_state() -> None:
    js = dashboard_js_text()
    apply_translations = extract_js_function(js, "applyTranslations")
    populate_options = extract_js_function(js, "populateLanguageOptions")
    set_language = extract_js_function(js, "setLanguage")

    assert "availableLanguages.map" in populate_options
    assert "language.native_name" in populate_options
    assert "document.documentElement.lang = currentLanguage" in apply_translations
    assert "document.documentElement.dir = languageDirection(currentLanguage)" in apply_translations
    assert "if (element === detailEl) return" in apply_translations
    assert "renderLiveStatus()" in apply_translations
    assert "rerenderSelectedDetail()" in set_language


def test_dashboard_js_thread_call_rows_include_cache_and_signals_columns() -> None:
    render_thread_calls = extract_js_function(dashboard_js_text(), "renderThreadCalls")

    for label in [
        "table.time",
        "table.initiated",
        "table.model",
        "table.effort",
        "table.tokens",
        "table.cached",
        "table.uncached",
        "table.output",
        "table.cost",
        "table.cache",
        "table.signals",
    ]:
        assert label in render_thread_calls
    assert "row.cache_ratio" in render_thread_calls
    assert "cachedTokenCell(row)" in render_thread_calls
    assert "uncachedTokenCell(row)" in render_thread_calls
    assert "outputTokenCell(row)" in render_thread_calls
    assert "renderSignalPucks(row, flags, 3" in render_thread_calls
    assert "</tr>" in render_thread_calls


def test_dashboard_js_runtime_i18n_uses_stable_keys() -> None:
    js = dashboard_js_text()
    recommendation_summary = extract_js_function(js, "recommendationSummary")
    next_action = extract_js_function(js, "nextActionForRow")
    show_detail = extract_js_function(js, "showDetail")

    assert "'action.run': 'Run'" in js
    assert "'button.run': 'Run'" not in js
    assert "translatedField(recommendation.title_key, recommendation.title)" in recommendation_summary
    assert "translatedField(recommendation.why_key, recommendation.why)" in recommendation_summary
    assert "translatedField(row.recommended_action_key, row.recommended_action)" in next_action
    assert "translatedField(explanationKeys[index], explanation)" in show_detail
    assert "translateEfficiencyFlag(row, flag, index)" in show_detail


def test_dashboard_js_refresh_preserves_selected_language_for_api_payloads() -> None:
    refresh = extract_js_function(dashboard_js_text(), "refreshDashboardData")

    assert "lang: currentLanguage" in refresh


def _dashboard_payload_from_html(html: str) -> dict[str, object]:
    match = re.search(
        r'<script id="usage-data" type="application/json">(?P<payload>.*?)</script>',
        html,
        re.S,
    )
    assert match
    return json.loads(match.group("payload"))
