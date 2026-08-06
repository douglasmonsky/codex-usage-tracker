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


def _finding(identity, score, count):
    return {"id": identity, "score": score, "count": count}


def normalized_findings(source_root):
    findings, total, count = [], 0, 0
    for path in sorted(source_root.rglob("*.py")):
        blocks = cc_visit(path.read_text())
        name = path.relative_to(source_root).as_posix()
        subtotal = sum(block.complexity for block in blocks)
        for block in blocks:
            if block.complexity > 20:
                owner = getattr(block, "classname", None)
                identity = f"{name}:{owner}.{block.name}" if owner else f"{name}:{block.name}"
                findings.append(_finding(identity, block.complexity, 1))
        if blocks and subtotal > 10 * len(blocks):
            findings.append(_finding(name, subtotal, len(blocks)))
        total, count = total + subtotal, count + len(blocks)
    if count and total > 10 * count:
        findings.append(_finding(".", total, count))
    return sorted(findings, key=lambda item: item["id"])


def _previous_findings(baseline_path):
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


def _regressed(recorded, previous):
    if previous is None:
        return False
    prior = {item["id"]: item for item in previous}
    return any(
        item["id"] not in prior
        or item["score"] / item["count"] > prior[item["id"]]["score"] / prior[item["id"]]["count"]
        for item in recorded
    )


def maintainability_failures(source_root=DEFAULT_SOURCE_ROOT, *, baseline_path=DEFAULT_BASELINE):
    try:
        baseline = json.loads(baseline_path.read_text())
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
        return [] if recorded == normalized_findings(source_root) else ["mismatch"]
    except Exception:
        return ["error"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args()
    failures = maintainability_failures(args.source_root)
    if failures:
        raise SystemExit(failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
