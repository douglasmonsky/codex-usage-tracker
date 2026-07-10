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
    if _snippet_is_unbounded(text, max_chars):
        return text, False
    snippet_chars = max_chars or len(text)
    center = _first_match_position(text, _search_terms(query))
    start, end = _snippet_bounds(len(text), center=center, max_chars=snippet_chars)
    excerpt = text[start:end].strip()
    prefix, suffix = _snippet_markers(start=start, end=end, text_length=len(text))
    return f"{prefix}{excerpt}{suffix}", True


def _snippet_is_unbounded(text: str, max_chars: int | None) -> bool:
    return max_chars is None or max_chars <= 0 or len(text) <= max_chars


def _first_match_position(text: str, terms: list[str]) -> int:
    positions = [text.lower().find(term.lower()) for term in terms]
    matches = [position for position in positions if position >= 0]
    return min(matches) if matches else 0


def _snippet_bounds(text_length: int, *, center: int, max_chars: int) -> tuple[int, int]:
    start = max(0, center - max_chars // 3)
    end = min(text_length, start + max_chars)
    return max(0, end - max_chars), end


def _snippet_markers(*, start: int, end: int, text_length: int) -> tuple[str, str]:
    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < text_length else ""
    return prefix, suffix


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
