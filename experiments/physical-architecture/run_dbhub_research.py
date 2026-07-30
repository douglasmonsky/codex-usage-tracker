from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

_EXPERIMENT_ROOT = Path(__file__).resolve().parent
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
dbhub_runner = importlib.import_module("shared.dbhub_runner")
publication = importlib.import_module("candidate_a.publication")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the deterministic CK-04 DBHub research matrix.",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--qualification-run-id",
        default="dbhub.standard.synthetic",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    fixture = shared.load_fixture_bundle(arguments.fixture)
    if fixture.profile != "standard":
        raise ValueError("DBHub research requires the CK-03 standard synthetic fixture")
    output = arguments.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"DBHub output root already exists: {output}")
    with tempfile.TemporaryDirectory(
        prefix="ck04-dbhub-candidate-a-",
        dir=output.parent,
    ) as temporary:
        artifact = publication.publish_artifact(fixture, Path(temporary))
        dbhub_runner.collect_dbhub_research(
            source_snapshot=artifact.path,
            run_root=output,
            qualification_run_id=arguments.qualification_run_id,
        )
    print(output / dbhub_runner.DBHUB_MEASUREMENTS_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
