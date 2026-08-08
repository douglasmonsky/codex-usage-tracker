#!/usr/bin/env python3
"""Enforce a deterministic maintainability baseline for the replacement kernel."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from radon.complexity import cc_visit  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
_ = "C", "B", "B"
DEFAULT_SOURCE_ROOT = ROOT / "src/codex_usage_tracker/agent_kernel"
DEFAULT_BASELINE = ROOT / "config/agent-kernel/maintainability-baseline-v1.json"
SPIKE_ROOT = ROOT / "src/codex_usage_tracker/kernel"
_METADATA_SHA = "a86abfe8565347950964245a11698aae587086e36f4cf3a48e5df6853ddd1c2d"
_EXPECTED_BASELINE_SHA256 = "fda777e28db7a0696f29b55c9d694f99d987413b206d8e323f217b4fa6a73ad5"


def _finding(identity: str, score: int, count: int) -> dict[str, object]:
    return {"id": identity, "score": score, "count": count}


def normalized_findings(source_root: Path) -> list[dict[str, object]]:
    """Return stable, path-relative findings from Radon complexity output."""

    findings: list[dict[str, object]] = []
    total = 0
    count = 0
    for path in sorted(source_root.rglob("*.py")):
        blocks = cc_visit(path.read_text(encoding="utf-8"))
        name = path.relative_to(source_root).as_posix()
        subtotal = sum(block.complexity for block in blocks)
        for block in blocks:
            if block.complexity > 20:
                owner = getattr(block, "classname", None)
                identity = f"{name}:{owner}.{block.name}" if owner else f"{name}:{block.name}"
                findings.append(_finding(identity, block.complexity, 1))
        if blocks and subtotal > 10 * len(blocks):
            findings.append(_finding(name, subtotal, len(blocks)))
        total += subtotal
        count += len(blocks)
    if count and total > 10 * count:
        findings.append(_finding(".", total, count))
    return sorted(findings, key=lambda item: str(item["id"]))


def _previous_findings(baseline_path: Path) -> list[dict[str, object]] | None:
    try:
        relative = baseline_path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return None
    listed = subprocess.run(
        ["git", "ls-tree", "--name-only", "origin/main", "--", relative],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if not listed.stdout.strip():
        return None
    shown = subprocess.run(
        ["git", "show", f"origin/main:{relative}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(shown.stdout)["baseline_findings"]


def _has_duplicate_ids(findings: list[dict[str, object]]) -> bool:
    identities = [str(item["id"]) for item in findings]
    return len(identities) != len(set(identities))


def _regressed(
    recorded: list[dict[str, object]],
    previous: list[dict[str, object]] | None,
) -> bool:
    if previous is None:
        return False
    if _has_duplicate_ids(recorded) or _has_duplicate_ids(previous):
        return True
    prior = {str(item["id"]): item for item in previous}
    return any(
        str(item["id"]) not in prior
        or float(str(item["score"])) / float(str(item["count"]))
        > float(str(prior[str(item["id"])]["score"]))
        / float(str(prior[str(item["id"])]["count"]))
        for item in recorded
    )


def maintainability_failures(
    source_root: Path = DEFAULT_SOURCE_ROOT,
    *,
    baseline_path: Path = DEFAULT_BASELINE,
) -> list[str]:
    """Return fail-closed baseline, spike, or normalized-finding failures."""

    try:
        baseline_bytes = baseline_path.read_bytes()
        if (
            baseline_path.resolve() == DEFAULT_BASELINE.resolve()
            and hashlib.sha256(baseline_bytes).hexdigest() != _EXPECTED_BASELINE_SHA256
        ):
            return ["baseline"]
        baseline = json.loads(baseline_bytes)
        metadata = {**baseline, "baseline_findings": []}
        digest = hashlib.sha256(
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        recorded = baseline["baseline_findings"]
        if digest != _METADATA_SHA or _regressed(
            recorded, _previous_findings(baseline_path)
        ):
            return ["baseline"]
        if normalized_findings(SPIKE_ROOT):
            return ["spike"]
        actual = normalized_findings(source_root)
        if _has_duplicate_ids(actual):
            return ["mismatch"]
        return [] if recorded == actual else ["mismatch"]
    except Exception:
        return ["error"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()
    failures = maintainability_failures(args.source_root)
    if failures:
        raise SystemExit(failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
