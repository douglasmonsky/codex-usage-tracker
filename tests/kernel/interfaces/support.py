from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.kernel.application import RuntimePaths
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.live import GenerationJournal

ORACLE_ROOT = (
    Path(__file__).parents[1] / "fixtures" / "accounting-oracle-v1"
)


def synthetic_sources() -> tuple[Path, ...]:
    return tuple(sorted((ORACLE_ROOT / "logs").glob("**/*.jsonl")))


def active_runtime(root: Path) -> RuntimePaths:
    runtime = RuntimePaths(
        codex_home=root / "codex-home",
        cache_root=root / "cache",
    )
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
        journal=GenerationJournal(runtime.kernel.operational),
    ).refresh(
        list(synthetic_sources()),
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="interface-fixture",
    )
    return runtime


def logical_split_runtime(root: Path) -> RuntimePaths:
    """Build one logical thread from active, archived, and copied sources."""

    runtime = RuntimePaths(
        codex_home=root / "codex-home",
        cache_root=root / "cache",
    )
    shared_session = "00000000-0000-4000-8000-000000000101"
    sources = (
        _logical_source(
            runtime.codex_home / "sessions" / "active-shared.jsonl",
            session_id=shared_session,
            nickname="Current logical thread",
            event_id="shared-active",
            timestamp="2026-01-02T00:00:03Z",
            input_tokens=200,
        ),
        _logical_source(
            runtime.codex_home / "archived_sessions" / "archived-shared.jsonl",
            session_id=shared_session,
            nickname="Archived physical thread",
            event_id="shared-archived",
            timestamp="2026-01-01T00:00:01Z",
            input_tokens=100,
        ),
        _logical_source(
            runtime.codex_home / "archived_sessions" / "copied-shared.jsonl",
            session_id=shared_session,
            nickname="Copied physical thread",
            event_id="shared-archived",
            timestamp="2026-01-01T00:00:01Z",
            input_tokens=100,
        ),
        _logical_source(
            runtime.codex_home / "sessions" / "other.jsonl",
            session_id="00000000-0000-4000-8000-000000000102",
            nickname="Other logical thread",
            event_id="other-active",
            timestamp="2026-01-02T00:00:02Z",
            input_tokens=50,
        ),
    )
    KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
        journal=GenerationJournal(runtime.kernel.operational),
    ).refresh(
        list(sources),
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="logical-split-fixture",
    )
    return runtime


def _logical_source(
    path: Path,
    *,
    session_id: str,
    nickname: str,
    event_id: str,
    timestamp: str,
    input_tokens: int,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    envelopes = (
        {
            "timestamp": timestamp,
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "thread_source": "subagent",
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "agent_nickname": nickname,
                            "agent_role": "worker",
                        }
                    }
                },
            },
        },
        {
            "timestamp": timestamp,
            "type": "turn_context",
            "payload": {
                "turn_id": f"turn-{event_id}",
                "model": "gpt-synthetic",
                "effort": "low",
            },
        },
        {
            "event_id": event_id,
            "timestamp": timestamp,
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": 1,
                        "output_tokens": 2,
                        "reasoning_output_tokens": 1,
                        "total_tokens": input_tokens + 2,
                    },
                    "model_context_window": 200_000,
                },
            },
        },
    )
    path.write_text(
        "".join(f"{json.dumps(envelope, separators=(',', ':'))}\n" for envelope in envelopes),
        encoding="utf-8",
    )
    return path
