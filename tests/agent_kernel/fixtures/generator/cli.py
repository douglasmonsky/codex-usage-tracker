from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from tests.agent_kernel.fixtures.generator.generate import (
    generate_fixture,
    tree_digest,
)
from tests.agent_kernel.fixtures.generator.profile import load_profile


def _check_committed(profile_name: str) -> dict[str, object]:
    if profile_name != "tiny":
        raise ValueError("only the tiny fixture is committed")
    committed = Path(__file__).resolve().parents[1] / "tiny-v1"
    with tempfile.TemporaryDirectory(prefix="ck03-fixture-check-") as raw_temp:
        candidate = Path(raw_temp) / "tiny-v1"
        result = generate_fixture(load_profile(profile_name), candidate)
        if tree_digest(candidate) != tree_digest(committed):
            raise ValueError("committed tiny fixture is not the canonical generation")
    return {
        "manifest_digest": result.manifest_digest,
        "oracle_digest": result.oracle_digest,
        "profile": profile_name,
        "source_bytes": result.source_bytes,
        "source_records": result.source_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic agent-kernel structural fixtures.",
    )
    parser.add_argument(
        "--profile",
        choices=("tiny", "small", "standard", "production", "growth"),
        required=True,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="Compute exact bytes/digests without materializing source files.",
    )
    parser.add_argument(
        "--check-committed",
        action="store_true",
        help="Regenerate and verify the checked-in tiny fixture.",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    if args.check_committed:
        if args.output is not None or args.manifest_only:
            parser.error("--check-committed cannot be combined with output options")
        payload = _check_committed(args.profile)
    else:
        if args.output is None:
            parser.error("--output is required unless --check-committed is used")
        result = generate_fixture(
            load_profile(args.profile),
            args.output,
            manifest_only=args.manifest_only,
        )
        payload = {
            "manifest_digest": result.manifest_digest,
            "oracle_digest": result.oracle_digest,
            "profile": args.profile,
            "source_bytes": result.source_bytes,
            "source_records": result.source_records,
        }
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    payload["elapsed_ms"] = elapsed_ms
    print(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
