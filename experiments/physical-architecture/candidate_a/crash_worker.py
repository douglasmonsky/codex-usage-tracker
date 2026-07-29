from __future__ import annotations

import argparse
import os
from pathlib import Path

import shared

from .publication import publish_artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--parent-publication-id", required=True)
    parser.add_argument("--stop-at", choices=shared.CRASH_BOUNDARIES, required=True)
    args = parser.parse_args()
    fixture = shared.load_fixture_bundle(args.fixture)

    def stop(boundary: str) -> None:
        if boundary == args.stop_at:
            os._exit(86)

    publish_artifact(
        fixture,
        args.run_root,
        parent_publication_id=args.parent_publication_id,
        hook=stop,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
