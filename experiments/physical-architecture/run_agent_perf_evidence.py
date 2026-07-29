"""Thin command-line entry point for the CK-04 Agent Perf evidence collector."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from shared.agent_perf_runner import AgentPerfEvidenceError, collect_agent_perf_evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect canonical Candidate A Agent Perf evidence for CK-04.",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--agent-perf", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repository_root = Path(__file__).resolve().parents[2]
    agent_perf = args.agent_perf
    if agent_perf is None:
        discovered = shutil.which("agent-perf")
        if discovered is None:
            raise SystemExit("agent-perf is unavailable on PATH")
        agent_perf = Path(discovered)
    try:
        collect_agent_perf_evidence(
            repository_root=repository_root,
            workload_path=Path(__file__).with_name("candidate_a") / "agent-perf-workload.json",
            fixture_root=args.fixture,
            destination=args.output,
            python_executable=args.python,
            agent_perf_executable=agent_perf,
            scratch_root=args.scratch,
        )
    except AgentPerfEvidenceError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
