from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .canonical import canonical_sha256

AGENT_PERF_WORKLOAD_SCHEMA = "codex-usage-tracker.agent-perf-workload.v1"
_ALLOWED_PLACEHOLDERS = frozenset({"{python}", "{fixture_root}", "{output_root}"})
_ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_SHELL_PROGRAMS = frozenset({"bash", "dash", "fish", "sh", "zsh"})
_SECRET_KEY_PARTS = ("CREDENTIAL", "KEY", "PASSWORD", "SECRET", "TOKEN")
_CONTRACT_FIELDS = frozenset(
    {
        "schema",
        "version",
        "candidate_id",
        "fixture_profile",
        "fixture_revision",
        "fixture_manifest_digest",
        "fixture_oracle_digest",
        "workload_matrix_digest",
        "synthetic_only",
        "workload_id",
        "command_argv",
        "environment",
        "minimum_unprofiled_runs",
        "profile_is_attribution_only",
    }
)


class AgentPerfContractError(ValueError):
    pass


@dataclass(frozen=True)
class AgentPerfWorkload:
    candidate_id: str
    fixture_profile: str
    fixture_revision: str
    fixture_manifest_digest: str
    fixture_oracle_digest: str
    workload_matrix_digest: str
    workload_id: str
    command_argv: tuple[str, ...]
    environment: Mapping[str, str]
    minimum_unprofiled_runs: int
    profile_is_attribution_only: bool
    source_path: Path

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "schema": AGENT_PERF_WORKLOAD_SCHEMA,
                "version": 1,
                "candidate_id": self.candidate_id,
                "fixture_profile": self.fixture_profile,
                "fixture_revision": self.fixture_revision,
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "fixture_oracle_digest": self.fixture_oracle_digest,
                "workload_matrix_digest": self.workload_matrix_digest,
                "synthetic_only": True,
                "workload_id": self.workload_id,
                "command_argv": self.command_argv,
                "environment": dict(self.environment),
                "minimum_unprofiled_runs": self.minimum_unprofiled_runs,
                "profile_is_attribution_only": self.profile_is_attribution_only,
            }
        )

    def command(
        self,
        *,
        python: Path,
        fixture_root: Path,
        output_root: Path,
    ) -> tuple[str, ...]:
        replacements = {
            "{python}": str(python),
            "{fixture_root}": str(fixture_root),
            "{output_root}": str(output_root),
        }
        return tuple(replacements.get(argument, argument) for argument in self.command_argv)


def _validate_command(arguments: object) -> tuple[str, ...]:
    if (
        not isinstance(arguments, list)
        or not arguments
        or not all(isinstance(argument, str) and argument for argument in arguments)
    ):
        raise AgentPerfContractError("agent-perf command_argv must be a non-empty string list")
    command = tuple(arguments)
    if Path(command[0]).name in _SHELL_PROGRAMS or "-c" in command:
        raise AgentPerfContractError("agent-perf workload cannot invoke a shell")
    if any(
        argument.startswith(("/", "~"))
        or any(operator in argument for operator in ("&&", "||", "$(", "`", "\n"))
        for argument in command
    ):
        raise AgentPerfContractError("agent-perf workload contains an unsafe path or shell token")
    placeholders = {argument for argument in command if argument.startswith("{")}
    if placeholders != _ALLOWED_PLACEHOLDERS:
        raise AgentPerfContractError(
            "agent-perf command must use python, fixture_root, and output_root placeholders"
        )
    return command


def _validate_environment(value: object) -> Mapping[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise AgentPerfContractError("agent-perf environment must map strings to strings")
    for key in value:
        if not _ENVIRONMENT_NAME.fullmatch(key):
            raise AgentPerfContractError(f"invalid agent-perf environment key: {key!r}")
        if any(part in key for part in _SECRET_KEY_PARTS):
            raise AgentPerfContractError("agent-perf environment cannot contain secret-like keys")
    return MappingProxyType(dict(sorted(value.items())))


def load_agent_perf_workload(path: Path) -> AgentPerfWorkload:
    """Load the exact unprofiled workload that agent-perf may wrap for attribution."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentPerfContractError("agent-perf workload file is not readable JSON") from error
    if not isinstance(payload, dict):
        raise AgentPerfContractError("agent-perf workload file must contain one object")
    if set(payload) != _CONTRACT_FIELDS:
        raise AgentPerfContractError("agent-perf workload fields differ from frozen v1")
    if payload.get("schema") != AGENT_PERF_WORKLOAD_SCHEMA or payload.get("version") != 1:
        raise AgentPerfContractError("agent-perf workload schema/version is not frozen v1")
    if payload.get("candidate_id") not in {"A", "C", "D"}:
        raise AgentPerfContractError("agent-perf candidate must be A, C, or D")
    if payload.get("fixture_profile") != "standard":
        raise AgentPerfContractError("agent-perf attribution must use the standard fixture")
    if payload.get("fixture_revision") != "agent-kernel-structural-v1":
        raise AgentPerfContractError("agent-perf fixture revision is not CK-03 v1")
    for field_name in (
        "fixture_manifest_digest",
        "fixture_oracle_digest",
        "workload_matrix_digest",
    ):
        digest = payload.get(field_name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise AgentPerfContractError(f"agent-perf {field_name} must be SHA-256")
    if payload.get("synthetic_only") is not True:
        raise AgentPerfContractError("agent-perf workload must be synthetic only")
    if payload.get("workload_id") != "build.scale.standard":
        raise AgentPerfContractError("agent-perf workload must use build.scale.standard")
    if payload.get("profile_is_attribution_only") is not True:
        raise AgentPerfContractError("agent-perf profile cannot be used as a speed claim")
    minimum_runs = payload.get("minimum_unprofiled_runs")
    if not isinstance(minimum_runs, int) or isinstance(minimum_runs, bool) or minimum_runs < 5:
        raise AgentPerfContractError("agent-perf workload requires five unprofiled runs")
    return AgentPerfWorkload(
        candidate_id=str(payload["candidate_id"]),
        fixture_profile=str(payload["fixture_profile"]),
        fixture_revision=str(payload["fixture_revision"]),
        fixture_manifest_digest=str(payload["fixture_manifest_digest"]),
        fixture_oracle_digest=str(payload["fixture_oracle_digest"]),
        workload_matrix_digest=str(payload["workload_matrix_digest"]),
        workload_id=str(payload["workload_id"]),
        command_argv=_validate_command(payload.get("command_argv")),
        environment=_validate_environment(payload.get("environment", {})),
        minimum_unprofiled_runs=minimum_runs,
        profile_is_attribution_only=True,
        source_path=path.resolve(),
    )
