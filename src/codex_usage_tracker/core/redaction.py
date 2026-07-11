"""Shared redaction helpers for local diagnostic text."""

from __future__ import annotations

import re

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bA(?:KI|SI)A[0-9A-Z]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (
        re.compile(r"(?i)\baws_secret_access_key\s*[:=]\s*(['\"]?)[A-Za-z0-9/+=]{30,}\1"),
        "aws_secret_access_key=[REDACTED_AWS_SECRET]",
    ),
    (
        re.compile(r"(?i)\bAuthorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._~+/-]+=*"),
        "Authorization: Bearer [REDACTED_BEARER_TOKEN]",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"), "Bearer [REDACTED_BEARER_TOKEN]"),
    (
        re.compile(r"\bxox(?:a|b|p|r|s)-[A-Za-z0-9-]{10,}\b"),
        "[REDACTED_SLACK_TOKEN]",
    ),
    (re.compile(r"\bxapp-[A-Za-z0-9-]{10,}\b"), "[REDACTED_SLACK_TOKEN]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.S,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"(?ix)\b("
            r"[A-Z0-9_ -]*(?:password|api[_-]?key|secret|credential|private[_-]?key)[A-Z0-9_ -]*"
            r"|(?:access|auth|bearer|refresh|session|api|github|gitlab|slack|openai|client|id)[ _-]*token"
            r"|token[ _-]*(?:id|key|secret|value)"
            r"|token"
            r")\s*[:=]\s*(['\"]?)[^'\"\s,;}]+\2"
        ),
        r"\1=[REDACTED_SECRET]",
    ),
)


def redact_secrets(text: str) -> str:
    """Redact common credential patterns from one text value."""

    redacted = text
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
