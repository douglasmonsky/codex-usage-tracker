"""Context loading constants."""

DEFAULT_CONTEXT_CHARS = 20_000
DEFAULT_CONTEXT_ENTRIES = 80
DEFAULT_CONTEXT_SEEK_BACKWARD_BYTES = 131_072
CONTEXT_MODE_QUICK = "quick"
CONTEXT_MODE_FULL = "full"
CONTEXT_MODES = {CONTEXT_MODE_QUICK, CONTEXT_MODE_FULL}


def normalize_context_mode(mode: str) -> str:
    normalized = str(mode or CONTEXT_MODE_QUICK).strip().lower()
    if normalized not in CONTEXT_MODES:
        raise ValueError(
            f"Unsupported context mode: {mode}. Expected one of: {', '.join(sorted(CONTEXT_MODES))}"
        )
    return normalized
