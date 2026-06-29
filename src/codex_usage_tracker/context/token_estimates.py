"""Token-estimation helpers for on-demand context evidence."""

from __future__ import annotations

from functools import lru_cache
from math import ceil
from typing import Any


def estimate_visible_tokens(entries: list[dict[str, Any]], model: str | None) -> dict[str, Any]:
    """Estimate visible text tokens for returned context entries."""
    text = visible_entry_text(entries)
    visible_chars = len(text)
    encoding, estimator = context_encoding(model or "")
    visible_tokens = visible_token_count(text, encoding)
    return {
        "visible_char_count": visible_chars,
        "visible_token_estimate": visible_tokens,
        "visible_token_estimator": estimator,
    }


def visible_entry_text(entries: list[dict[str, Any]]) -> str:
    """Join visible context entry text the same way the dashboard displays it."""
    return "\n\n".join(str(entry.get("text") or "") for entry in entries if entry.get("text"))


def visible_token_count(text: str, encoding: Any | None) -> int:
    """Estimate visible tokens, preserving empty visible text as zero tokens."""
    if encoding is None:
        return ceil(len(text) / 4) if text else 0
    return token_estimate(text, encoding)


def token_estimate(text: str, encoding: Any | None) -> int:
    """Estimate tokens with tiktoken when available, otherwise chars/4."""
    if not text:
        return 0
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:
            pass
    return max(1, ceil(len(text) / 4))


@lru_cache(maxsize=32)
def context_encoding(model: str) -> tuple[Any | None, str]:
    """Return a best-effort tiktoken encoding plus estimator label."""
    tiktoken = _tiktoken_module()
    if tiktoken is None:
        return None, "chars_per_4_fallback"
    encoding = _encoding_for_model(tiktoken, model) or _fallback_encoding(tiktoken)
    if encoding is None:
        return None, "chars_per_4_fallback"
    return encoding, f"tiktoken:{getattr(encoding, 'name', 'unknown')}"


def _tiktoken_module() -> Any | None:
    try:
        import tiktoken  # type: ignore[import-not-found]
    except Exception:
        return None
    return tiktoken


def _encoding_for_model(tiktoken: Any, model: str) -> Any | None:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return None
    except Exception:
        return None


def _fallback_encoding(tiktoken: Any) -> Any | None:
    for name in ("o200k_base", "cl100k_base"):
        try:
            return tiktoken.get_encoding(name)
        except Exception:
            continue
    return None
