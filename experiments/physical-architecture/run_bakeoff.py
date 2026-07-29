from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

_EXPERIMENT_ROOT = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _EXPERIMENT_ROOT.parents[1]
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

qualification = importlib.import_module("qualification")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one isolated CK-04 physical-architecture qualification invocation.",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--candidate",
        action="append",
        choices=qualification.CANDIDATE_IDS,
        dest="candidates",
    )
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument(
        "--group",
        action="append",
        choices=tuple(group.value for group in qualification.shared.WorkloadGroup),
        dest="group_ids",
    )
    parser.add_argument("--all-compatible-cases", action="store_true")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--speed-claim", action="store_true")
    parser.add_argument("--profiled", action="store_true")
    parser.add_argument("--allow-large-fixture", action="store_true")
    parser.add_argument("--include-research", action="store_true")
    parser.add_argument("--qualification-model")
    parser.add_argument(
        "--retain-run-artifacts",
        action="store_true",
        help="retain generated candidate databases after measurements are recorded",
    )
    parser.add_argument(
        "--filesystem-cache-state",
        choices=("cold", "warm", "uncontrolled"),
        default="uncontrolled",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        config = qualification.QualificationConfig(
            fixture_root=arguments.fixture,
            output_root=arguments.output,
            run_id=arguments.run_id or qualification.make_run_id(),
            code_commit=qualification.discover_code_commit(_REPOSITORY_ROOT),
            candidates=tuple(arguments.candidates or qualification.CANDIDATE_IDS),
            case_ids=tuple(arguments.case_ids or ()),
            group_ids=tuple(
                qualification.shared.WorkloadGroup(group) for group in (arguments.group_ids or ())
            ),
            repetitions=arguments.repetitions,
            speed_claim=arguments.speed_claim,
            profiled=arguments.profiled,
            allow_large_fixture=arguments.allow_large_fixture,
            all_compatible_cases=arguments.all_compatible_cases,
            include_research=arguments.include_research,
            qualification_model=arguments.qualification_model,
            filesystem_cache_state=arguments.filesystem_cache_state,
            retain_run_artifacts=arguments.retain_run_artifacts,
        )
        artifact = qualification.run_qualification(config)
    except qualification.QualificationRunFailed as error:
        print(error.artifact.summary_path)
        return 1
    except qualification.QualificationContractError as error:
        parser.error(str(error))
    print(artifact.summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
