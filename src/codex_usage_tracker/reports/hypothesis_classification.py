"""Normalize and classify user-supplied usage hypotheses."""

from __future__ import annotations

import re


def normalize_hypothesis_inputs(hypotheses: list[str] | str | None) -> list[str]:
    """Return non-empty hypothesis strings in caller order."""
    if hypotheses is None:
        return []
    if isinstance(hypotheses, str):
        return [hypotheses.strip()] if hypotheses.strip() else []
    return [str(hypothesis).strip() for hypothesis in hypotheses if str(hypothesis).strip()]


def classify_hypothesis_family(hypothesis: str, question: str) -> str:
    """Classify a hypothesis, falling back to its question and token waste."""
    hypothesis_family = _classify_hypothesis_text(hypothesis.lower())
    if hypothesis_family is not None:
        return hypothesis_family
    question_family = _classify_hypothesis_text(question.lower())
    if question_family is not None:
        return question_family
    return "token_waste"


def _classify_hypothesis_text(text: str) -> str | None:
    if _has_any_phrase(
        text,
        (
            "allowance",
            "usage allowance",
            "allowance change",
            "limit change",
            "limit changed",
            "codex limit",
            "usage limit",
            "weekly allowance",
            "weekly limit",
            "5-hour",
            "5 hour",
            "throttle",
            "throttled",
        ),
    ):
        return "allowance_change"
    if _has_any_phrase(text, ("cache", "cold resume", "cold resumes", "cold", "resume")):
        return "cache_failure"
    if _has_any_phrase(
        text,
        (
            "file",
            "rediscover",
            "rediscovery",
            "reread",
            "rereads",
            "re-read",
            "re-reads",
            "repeated read",
            "repeated reads",
            "path",
            "content-index",
            "content index",
            "thread-trace",
            "thread trace",
        ),
    ):
        return "repeated_file_rediscovery"
    if _has_shell_hypothesis_signal(text):
        return "shell_churn"
    if _has_any_word(text, ("effort", "model", "xhigh", "high", "medium", "gpt")):
        return "effort_model_choice"
    if _has_any_phrase(
        text,
        (
            "token waste",
            "wasting tokens",
            "waste",
            "expensive",
            "cost",
            "large low-output",
            "large low output",
            "low-output",
            "low output",
            "output length",
            "context pressure",
            "large call",
            "large calls",
            "cleanup target",
        ),
    ):
        return "token_waste"
    return None


def _has_any_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def _has_any_word(text: str, words: tuple[str, ...]) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9_-]){re.escape(word)}(?![a-z0-9_-])", text) for word in words
    )


def _has_shell_hypothesis_signal(text: str) -> bool:
    if "shell" in text or "command" in text:
        return True
    tokens = {token for token in re.split(r"[^a-z0-9]+", text) if token}
    return bool(tokens & {"sed", "rg", "git", "nl", "npm", "python", "pytest"})
