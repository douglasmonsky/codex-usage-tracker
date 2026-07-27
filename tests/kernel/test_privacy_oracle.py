from __future__ import annotations

import json
import re
from pathlib import Path

_FIXTURE_ROOT = Path(__file__).with_name("fixtures") / "accounting-oracle-v1"
_FORBIDDEN_OUTPUT = (
    "PRIVATE_FIXTURE_SENTINEL",
    "SYNTHETIC_TOOL_ARGUMENT_SENTINEL",
    "SYNTHETIC_PROMPT_SENTINEL",
)
_SECRET_PATTERN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


def test_kernel_fixtures_are_synthetic_and_portable() -> None:
    assert _FIXTURE_ROOT.is_dir(), "K1 fixture directory is missing"

    for path in _FIXTURE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert "/Users/" not in text
        assert "\\Users\\" not in text
        assert not _SECRET_PATTERN.search(text)


def test_oracle_output_excludes_raw_private_sentinels(tmp_path: Path) -> None:
    from tests.kernel.test_ingest_oracle import export_accounting_oracle

    observed = export_accounting_oracle(
        fixture_root=_FIXTURE_ROOT,
        workspace=tmp_path,
    )
    encoded = json.dumps(observed, sort_keys=True)

    for sentinel in _FORBIDDEN_OUTPUT:
        assert sentinel not in encoded
    assert observed["privacy"] == {
        "raw_content_included": False,
        "source_paths": "repository_relative",
        "unknown_events": "parsed_counted_not_copied",
    }
    assert observed["parser_diagnostics"]["invalid_json"] == 1
    assert observed["parser_diagnostics"]["unknown_event_shape"] == 1
