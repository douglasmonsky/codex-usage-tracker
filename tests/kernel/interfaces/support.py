from __future__ import annotations

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
