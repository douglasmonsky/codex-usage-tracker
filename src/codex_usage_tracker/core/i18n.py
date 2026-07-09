"""Dashboard localization catalog loading and language metadata."""

from __future__ import annotations

import json
import os
from functools import cache
from importlib import resources

DEFAULT_LANGUAGE = "en"
LANGUAGE_ENV_VAR = "CODEX_USAGE_TRACKER_LANG"
SUPPORTED_LANGUAGES = (
    "en",
    "vi",
    "es",
    "fr",
    "de",
    "pt",
    "ja",
    "zh-Hans",
    "ko",
    "ru",
    "it",
    "ar",
)
SUPPORTED_LANGUAGE_METADATA: dict[str, dict[str, str]] = {
    "en": {"english_name": "English", "native_name": "English", "dir": "ltr"},
    "vi": {"english_name": "Vietnamese", "native_name": "Tiếng Việt", "dir": "ltr"},
    "es": {"english_name": "Spanish", "native_name": "Español", "dir": "ltr"},
    "fr": {"english_name": "French", "native_name": "Français", "dir": "ltr"},
    "de": {"english_name": "German", "native_name": "Deutsch", "dir": "ltr"},
    "pt": {"english_name": "Portuguese", "native_name": "Português", "dir": "ltr"},
    "ja": {"english_name": "Japanese", "native_name": "日本語", "dir": "ltr"},
    "zh-Hans": {"english_name": "Chinese, Simplified", "native_name": "简体中文", "dir": "ltr"},
    "ko": {"english_name": "Korean", "native_name": "한국어", "dir": "ltr"},
    "ru": {"english_name": "Russian", "native_name": "Русский", "dir": "ltr"},
    "it": {"english_name": "Italian", "native_name": "Italiano", "dir": "ltr"},
    "ar": {"english_name": "Arabic", "native_name": "العربية", "dir": "rtl"},
}

_ALIASES = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "en-us": "en",
    "en_us": "en",
    "vi": "vi",
    "vn": "vi",
    "vie": "vi",
    "vietnamese": "vi",
    "tieng viet": "vi",
    "tiếng việt": "vi",
    "vi-vn": "vi",
    "vi_vn": "vi",
    "es": "es",
    "spa": "es",
    "spanish": "es",
    "es-es": "es",
    "es_mx": "es",
    "fr": "fr",
    "fre": "fr",
    "fra": "fr",
    "french": "fr",
    "de": "de",
    "ger": "de",
    "deu": "de",
    "german": "de",
    "pt": "pt",
    "por": "pt",
    "portuguese": "pt",
    "pt-br": "pt",
    "pt_br": "pt",
    "ja": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "zh": "zh-Hans",
    "zh-cn": "zh-Hans",
    "zh_cn": "zh-Hans",
    "zh-hans": "zh-Hans",
    "zh_hans": "zh-Hans",
    "chinese": "zh-Hans",
    "simplified chinese": "zh-Hans",
    "ko": "ko",
    "kor": "ko",
    "korean": "ko",
    "ru": "ru",
    "rus": "ru",
    "russian": "ru",
    "it": "it",
    "ita": "it",
    "italian": "it",
    "ar": "ar",
    "ara": "ar",
    "arabic": "ar",
}


def normalize_language(language: str | None = None) -> str:
    """Return a supported dashboard language code, honoring the env var when unset."""

    raw = language if language is not None else os.environ.get(LANGUAGE_ENV_VAR)
    key = str(raw or "").strip().lower()
    if not key:
        return DEFAULT_LANGUAGE
    return _ALIASES.get(key, _ALIASES.get(key.replace("_", "-"), DEFAULT_LANGUAGE))


def raw_catalog(language: str) -> dict[str, str]:
    """Return a copy of one raw locale JSON catalog without English fallback overlay."""

    return dict(_cached_raw_catalog(normalize_language(language)))


def translations_for(language: str | None = None) -> dict[str, str]:
    """Return a copy of English strings overlaid with the selected language."""

    selected = normalize_language(language)
    translations = dict(_cached_raw_catalog(DEFAULT_LANGUAGE))
    if selected != DEFAULT_LANGUAGE:
        translations.update(_cached_raw_catalog(selected))
    return translations


def translation_catalog() -> dict[str, dict[str, str]]:
    """Return merged catalogs for all supported languages for static dashboard switching."""

    return {language: translations_for(language) for language in SUPPORTED_LANGUAGES}


def available_languages() -> list[dict[str, object]]:
    """Return supported dashboard languages with native/English names and text direction."""

    languages: list[dict[str, object]] = []
    for code in SUPPORTED_LANGUAGES:
        metadata = SUPPORTED_LANGUAGE_METADATA[code]
        languages.append({"code": code, **metadata})
    return languages


def language_direction(language: str | None = None) -> str:
    """Return the document direction for a dashboard language."""

    selected = normalize_language(language)
    direction = SUPPORTED_LANGUAGE_METADATA[selected]["dir"]
    return direction if direction in {"ltr", "rtl"} else "ltr"


def dashboard_i18n_payload(language: str | None = None) -> dict[str, object]:
    selected = normalize_language(language)
    return {
        "language": selected,
        "language_direction": language_direction(selected),
        "available_languages": available_languages(),
        "translations": translations_for(selected),
        "translation_catalog": translation_catalog(),
    }


@cache
def _cached_raw_catalog(language: str) -> dict[str, str]:
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    resource = resources.files("codex_usage_tracker.plugin_data").joinpath(
        "dashboard", "locales", f"{language}.json"
    )
    try:
        data = json.loads(resource.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if language == DEFAULT_LANGUAGE:
            raise RuntimeError("missing canonical English dashboard locale catalog") from exc
        return dict(_cached_raw_catalog(DEFAULT_LANGUAGE))
    if not isinstance(data, dict):
        raise ValueError(f"dashboard locale catalog must be an object: {language}")
    catalog: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"dashboard locale catalog contains an invalid key: {language}")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"dashboard locale catalog contains an invalid value for {key!r}: {language}"
            )
        catalog[key] = value
    return catalog
