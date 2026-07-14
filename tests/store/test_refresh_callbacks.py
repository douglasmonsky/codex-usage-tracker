from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.store.api import refresh_usage_index
from tests.store_dashboard_helpers import _entry, _make_codex_home, _token_event


def test_refresh_derived_fact_callback_receives_full_and_append_targets(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    calls: list[tuple[tuple[str, ...], frozenset[str], bool, bool]] = []

    def sync(
        conn,
        record_ids: tuple[str, ...],
        thread_keys: frozenset[str],
        full_rebuild: bool,
    ) -> None:
        calls.append((record_ids, thread_keys, full_rebuild, conn.in_transaction))

    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )
    source_path = next((codex_home / "sessions").glob("**/*.jsonl"))
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "APPENDED"}],
                    },
                )
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(8_000, 400)) + "\n")
    refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        derived_fact_sync=sync,
    )

    assert len(calls) == 2
    assert calls[0][2:] == (True, True)
    assert calls[1][2:] == (False, True)
    assert len(calls[0][0]) > 0
    assert len(calls[1][0]) == 1
    assert calls[0][1]
    assert calls[1][1]
