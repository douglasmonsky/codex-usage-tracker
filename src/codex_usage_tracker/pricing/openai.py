"""OpenAI pricing source fetching, parsing, and cache updates."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from codex_usage_tracker import __version__
from codex_usage_tracker.core.paths import DEFAULT_PRICING_PATH
from codex_usage_tracker.pricing.config import (
    PRICING_SCHEMA,
    load_existing_aliases,
    load_existing_billing_basis,
)
from codex_usage_tracker.pricing.estimates import ESTIMATED_MODEL_PRICES, estimated_model_prices

OPENAI_PRICING_MD_URL = "https://developers.openai.com/api/docs/pricing.md"
OPENAI_LATEST_MODEL_MD_URL = "https://developers.openai.com/api/docs/guides/latest-model.md"
VALID_PRICING_TIERS = ("standard", "batch", "flex", "priority")

_LONG_CONTEXT_THRESHOLD_TOKENS = 272_000
_LONG_CONTEXT_INPUT_MULTIPLIER = 2.0
_LONG_CONTEXT_OUTPUT_MULTIPLIER = 1.5

_OFFICIAL_PRICING_ALIASES = {
    "gpt-5.6": "gpt-5.6-sol",
}


class PricingParseError(ValueError):
    """Raised when the OpenAI pricing Markdown structure cannot be parsed."""


@dataclass(frozen=True)
class PricingUpdateResult:
    """Result from refreshing the local pricing cache."""

    path: Path
    source_url: str
    tier: str
    fetched_at: str
    model_count: int
    estimated_model_count: int = 0
    backup_path: Path | None = None


def update_pricing_from_openai_docs(
    path: Path = DEFAULT_PRICING_PATH,
    *,
    tier: str = "standard",
    source_url: str = OPENAI_PRICING_MD_URL,
    fetch_text: Callable[[str], str] | None = None,
    include_estimates: bool = True,
) -> PricingUpdateResult:
    """Fetch OpenAI-published pricing rows and cache them in the local config."""

    if tier not in VALID_PRICING_TIERS:
        raise ValueError(
            f"unknown pricing tier {tier!r}; expected one of {', '.join(VALID_PRICING_TIERS)}"
        )
    fetcher = fetch_text or _fetch_text
    text = fetcher(source_url)
    parsed_tiers = parse_all_openai_pricing_tiers(text)
    parsed_models = parsed_tiers[tier]
    if not parsed_models:
        raise PricingParseError(
            f"pricing source schema changed: no text-token pricing rows were parsed "
            f"from {source_url} for tier {tier!r}"
        )
    models: dict[str, dict[str, Any]] = {
        model: dict(rates) for model, rates in parsed_models.items()
    }
    available_official_models = {
        model for tier_models in parsed_tiers.values() for model in tier_models
    }
    aliases = {
        **{
            alias: target
            for alias, target in _OFFICIAL_PRICING_ALIASES.items()
            if target in available_official_models
        },
        **load_existing_aliases(path),
    }
    billing_basis = load_existing_billing_basis(path)
    estimated_model_count = 0
    if include_estimates:
        models.update(estimated_model_prices())
        estimated_model_count = len(ESTIMATED_MODEL_PRICES)

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "_schema": PRICING_SCHEMA,
        "_source": {
            "name": "OpenAI Developers pricing docs",
            "url": source_url,
            "tier": tier,
            "tiers": list(VALID_PRICING_TIERS),
            "tier_model_counts": {
                name: len(tier_models) for name, tier_models in parsed_tiers.items()
            },
            "fetched_at": fetched_at,
            "model_count": len(models),
            "official_model_count": len(models) - estimated_model_count,
            "estimated_model_count": estimated_model_count,
        },
        "billing_basis": billing_basis,
        "models": models,
        "api_service_tiers": parsed_tiers,
    }
    if aliases:
        payload["aliases"] = aliases
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _backup_existing_pricing(path)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
    return PricingUpdateResult(
        path=path,
        source_url=source_url,
        tier=tier,
        fetched_at=fetched_at,
        model_count=len(models),
        estimated_model_count=estimated_model_count,
        backup_path=backup_path,
    )


def parse_openai_pricing_markdown(
    markdown: str, *, tier: str = "standard"
) -> dict[str, dict[str, float]]:
    """Parse text-token rows from OpenAI's pricing markdown for one service tier."""

    if tier not in VALID_PRICING_TIERS:
        raise ValueError(
            f"unknown pricing tier {tier!r}; expected one of {', '.join(VALID_PRICING_TIERS)}"
        )
    rows_block = _extract_text_token_rows_block(markdown, tier)
    models: dict[str, dict[str, float]] = {}
    for match in _OPENAI_PRICE_ROW_RE.finditer(rows_block):
        model = _normalize_model_name(match.group("model"))
        input_rate = _parse_openai_price_value(match.group("input"))
        cached_rate = _parse_openai_price_value(match.group("cached"))
        output_rate = _parse_openai_price_value(match.group("output"))
        if not model or input_rate is None or output_rate is None:
            continue
        if cached_rate is None:
            cached_rate = input_rate
        rates = {
            "input_per_million": input_rate,
            "cached_input_per_million": cached_rate,
            "output_per_million": output_rate,
        }
        if _uses_long_context_pricing(tier, match.group("model"), model):
            rates.update(
                {
                    "long_context_threshold_tokens": _LONG_CONTEXT_THRESHOLD_TOKENS,
                    "long_context_input_multiplier": _LONG_CONTEXT_INPUT_MULTIPLIER,
                    "long_context_output_multiplier": _LONG_CONTEXT_OUTPUT_MULTIPLIER,
                }
            )
        models[model] = rates
    if not models:
        raise PricingParseError(
            f"pricing source schema changed: tier {tier!r} rows block contained no "
            "parseable text-token pricing rows"
        )
    return models


def parse_all_openai_pricing_tiers(
    markdown: str,
) -> dict[str, dict[str, dict[str, float]]]:
    """Parse every published API service-tier table from one source document."""

    return {
        tier: parse_openai_pricing_markdown(markdown, tier=tier)
        for tier in VALID_PRICING_TIERS
    }


def parse_openai_latest_model_id(markdown: str) -> str:
    """Return the canonical latest model ID from OpenAI's model guide front matter."""

    match = _OPENAI_LATEST_MODEL_RE.search(markdown)
    if match is None:
        raise PricingParseError(
            "latest-model source schema changed: could not find latestModelInfo.model"
        )
    return match.group("model")


_OPENAI_PRICE_ROW_RE = re.compile(
    r"""\[
        \s*"(?P<model>[^"]+)"\s*,
        \s*(?P<input>[^,\]\n]+)\s*,
        \s*(?P<cached>[^,\]\n]+)\s*,
        (?:\s*(?P<cache_write>[^,\]\n]+)\s*,)?
        \s*(?P<output>[^,\]\n]+)\s*
    \]""",
    re.VERBOSE,
)

_OPENAI_LATEST_MODEL_RE = re.compile(
    r"^latestModelInfo:\s*$.*?^[ \t]+model:\s*(?P<model>[A-Za-z0-9._-]+)\s*$",
    re.MULTILINE | re.DOTALL,
)


def _fetch_text(url: str) -> str:
    if urlsplit(url).scheme != "https":
        raise ValueError("pricing sources must use HTTPS")
    request = Request(
        url,
        headers={
            "Accept": "text/markdown,text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": f"codex-usage-tracker/{__version__}",
        },
    )
    try:
        # The source scheme is restricted to HTTPS above.
        with urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"could not fetch pricing source {url}: {exc}") from exc


def _backup_existing_pricing(path: Path) -> Path | None:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, backup_path)
    return backup_path


def _extract_text_token_rows_block(markdown: str, tier: str) -> str:
    tier_marker = f'tier="{tier}"'
    tier_index = markdown.find(tier_marker)
    if tier_index == -1:
        raise PricingParseError(
            f"pricing source schema changed: could not find text-token tier marker {tier_marker!r}"
        )
    search_end = _pricing_component_end(markdown, tier_index)
    rows_marker_index = markdown.find("rows={[", tier_index, search_end)
    if rows_marker_index == -1:
        raise PricingParseError(
            f"pricing source schema changed: tier {tier!r} does not contain a rows={{[ block"
        )
    bracket_index = markdown.find("[", rows_marker_index, search_end)
    if bracket_index == -1:
        raise PricingParseError(
            f"pricing source schema changed: tier {tier!r} has a malformed rows block"
        )
    end_index = _find_matching_bracket(markdown, bracket_index)
    if end_index > search_end:
        raise PricingParseError(
            f"pricing source schema changed: tier {tier!r} rows block extends past its component"
        )
    return markdown[bracket_index + 1 : end_index]


def _pricing_component_end(markdown: str, tier_index: int) -> int:
    candidates = [
        index
        for index in (
            markdown.find("/>", tier_index),
            markdown.find("</TextTokenPricingTables>", tier_index),
            markdown.find("<TextTokenPricingTables", tier_index + 1),
        )
        if index != -1
    ]
    return min(candidates) if candidates else len(markdown)


def _find_matching_bracket(text: str, start_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start_index, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
    raise PricingParseError("pricing source schema changed: rows block is unterminated")


def _normalize_model_name(model: str) -> str:
    return re.sub(r"\s+\([^)]*context length[^)]*\)\s*$", "", model.strip(), flags=re.I)


def _uses_long_context_pricing(tier: str, source_label: str, normalized_model: str) -> bool:
    return tier in {"standard", "batch", "flex"} and (
        "context length" in source_label.lower() or normalized_model.startswith("gpt-5.6-")
    )


def _parse_openai_price_value(value: str) -> float | None:
    normalized = value.strip()
    if normalized in {"", "null", "undefined", "-", '""', "''", '"-"', "'-'"}:
        return None
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {'"', "'"}:
        normalized = normalized[1:-1].strip()
    if normalized in {"", "-", "Free"}:
        return None
    return float(normalized.replace("_", ""))
