"""Shared paging and snippet helpers for content-index queries."""

from __future__ import annotations

import re

DEFAULT_SEARCH_SNIPPET_CHARS = 800


def _snippet(
    text: str,
    *,
    query: str,
    max_chars: int | None,
) -> tuple[str, bool]:
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text, False
    terms = _search_terms(query)
    lower_text = text.lower()
    positions = [lower_text.find(term.lower()) for term in terms]
    match_positions = [position for position in positions if position >= 0]
    center = min(match_positions) if match_positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    excerpt = text[start:end].strip()
    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}", True


def _search_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[\w-]+", query) if term]


def _fts_match_query(query: str) -> str:
    terms = _search_terms(query)
    if not terms:
        return _fts_quote(query)
    return " ".join(_fts_quote(term) for term in terms)


def _fts_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _normalize_search_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _normalize_search_offset(offset: int) -> int:
    return max(0, offset)


def _limit_clause(limit: int | None) -> str:
    if limit is None:
        return ""
    return "LIMIT ? OFFSET ?"


def _limit_params(limit: int | None, offset: int) -> list[int]:
    if limit is None:
        return []
    return [limit, offset]
