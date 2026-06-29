"""Allowance status text parsing helpers."""

from __future__ import annotations

import re


def allowance_line_matches(text: str) -> list[tuple[str, str, str, str | None]]:
    matches = _explicit_allowance_line_matches(text)
    if matches:
        return _dedupe_allowance_matches(matches)
    return _flat_allowance_line_matches(text)


def _explicit_allowance_line_matches(text: str) -> list[tuple[str, str, str, str | None]]:
    matches: list[tuple[str, str, str, str | None]] = []
    for line in _normalized_allowance_lines(text):
        match = _ALLOWANCE_LINE_RE.match(line)
        if match is None:
            continue
        parsed = _allowance_match_tuple(match)
        if parsed is not None:
            matches.append(parsed)
    return matches


def _normalized_allowance_lines(text: str) -> list[str]:
    return [line.strip() for line in text.replace("\u00a0", " ").splitlines() if line.strip()]


def _allowance_match_tuple(match: re.Match[str]) -> tuple[str, str, str, str | None] | None:
    key = _allowance_window_key(match.group("label"))
    if key is None:
        return None
    reset_at = _clean_allowance_reset(match.group("reset"))
    if reset_at and _ALLOWANCE_LABEL_RE.search(reset_at):
        return None
    return key, _allowance_window_label(key), match.group("percent"), reset_at


def _allowance_window_label(key: str) -> str:
    return "5h" if key == "five_hour" else "Weekly"


def _clean_allowance_reset(reset_at: str | None) -> str | None:
    if reset_at is None:
        return None
    cleaned = reset_at.strip()
    return cleaned or None


def _flat_allowance_line_matches(text: str) -> list[tuple[str, str, str, str | None]]:
    flat = " ".join(text.replace("\u00a0", " ").split())
    label_matches = list(_ALLOWANCE_LABEL_RE.finditer(flat))
    matches = [
        match
        for index, label_match in enumerate(label_matches)
        if (match := _flat_allowance_segment_match(flat, label_matches, index, label_match))
        is not None
    ]
    return _dedupe_allowance_matches(matches)


def _flat_allowance_segment_match(
    flat: str,
    label_matches: list[re.Match[str]],
    index: int,
    label_match: re.Match[str],
) -> tuple[str, str, str, str | None] | None:
    key = _allowance_window_key(label_match.group(0))
    if key is None:
        return None
    next_start = label_matches[index + 1].start() if index + 1 < len(label_matches) else len(flat)
    segment = flat[label_match.end() : next_start].strip()
    percent_match = _ALLOWANCE_PERCENT_RE.search(segment)
    if percent_match is None:
        return None
    reset_at = _clean_allowance_reset(segment[percent_match.end() :])
    return key, _allowance_window_label(key), percent_match.group("percent"), reset_at


def _dedupe_allowance_matches(
    matches: list[tuple[str, str, str, str | None]],
) -> list[tuple[str, str, str, str | None]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str, str, str | None]] = []
    for match in matches:
        key = match[0]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped


def _allowance_window_key(label: str) -> str | None:
    normalized = label.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"5h", "5_hour", "five_hour"}:
        return "five_hour"
    if normalized in {"weekly", "week"}:
        return "weekly"
    return None


_ALLOWANCE_LINE_RE = re.compile(
    r"^(?P<label>5h|5-hour|five-hour|weekly|week)\s+"
    r"(?P<percent>\d+(?:\.\d+)?)\s*%"
    r"(?:\s+(?P<reset>.+?))?\s*$",
    re.IGNORECASE,
)


_ALLOWANCE_LABEL_RE = re.compile(r"\b(?:5h|5-hour|five-hour|weekly|week)\b", re.IGNORECASE)


_ALLOWANCE_PERCENT_RE = re.compile(r"(?P<percent>\d+(?:\.\d+)?)\s*%")
