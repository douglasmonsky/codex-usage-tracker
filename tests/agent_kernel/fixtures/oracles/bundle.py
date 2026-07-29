from __future__ import annotations

from typing import Any

from tests.agent_kernel.fixtures.generator.cases import VERTICAL_SLICES
from tests.agent_kernel.fixtures.generator.profile import FixtureProfile
from tests.agent_kernel.fixtures.oracles.accounting import build_accounting_oracle
from tests.agent_kernel.fixtures.oracles.crash import crash_state_oracle
from tests.agent_kernel.fixtures.oracles.evidence import build_evidence_oracle
from tests.agent_kernel.fixtures.oracles.lifecycle import build_lifecycle_oracle
from tests.agent_kernel.fixtures.oracles.questions import (
    question_formula_failures,
    question_oracle_records,
)
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger
from tests.agent_kernel.fixtures.oracles.source_lifecycle import (
    build_source_lifecycle_oracle,
)


def build_oracle_bundle(
    profile: FixtureProfile,
    catalog: dict[str, Any],
    *,
    ledger: SourceLedger,
) -> dict[str, Any]:
    """Build shared truth only after exact source records are ledgered."""

    questions = question_oracle_records(catalog, profile, ledger=ledger)
    return {
        "accounting": build_accounting_oracle(profile, ledger=ledger),
        "crash_states": crash_state_oracle(),
        "digest_policy": {
            "algorithm": "sha256",
            "manifest": "canonical_manifest_without_manifest_digest",
            "oracle": "canonical_complete_oracle_bundle",
            "tree": "sha256(relative_posix_path_nul_file_bytes_nul)",
        },
        "evidence": build_evidence_oracle(profile, ledger=ledger),
        "fixture_revision": "agent-kernel-structural-v1",
        "format_policy": {
            "absolute_paths": "forbidden",
            "content_bodies": "forbidden",
            "encoding": "canonical_json_utf8_lf",
            "json_keys": "lexicographic",
            "source_record_format": "one_compact_json_object_per_lf",
        },
        "lifecycle": build_lifecycle_oracle(),
        "profile": profile.name,
        "questions": questions,
        "schema": "codex-usage-tracker.synthetic-oracle-bundle.v1",
        "seed": profile.seed,
        "source_lifecycle": build_source_lifecycle_oracle(
            profile,
            ledger=ledger,
        ),
        "source_to_oracle_reconciliation": {
            "formula_failures": {
                oracle_id: question_formula_failures(record)
                for oracle_id, record in questions.items()
                if question_formula_failures(record)
            },
            "question_cases": len(ledger.question_cases),
            "selector_coordinates": len(ledger.selector_coordinates),
            "stream_aggregates": ledger.stream_aggregates,
        },
        "version": 1,
        "vertical_slices": VERTICAL_SLICES,
    }


def oracle_bundle_failures(
    bundle: dict[str, Any],
    catalog: dict[str, Any],
) -> list[str]:
    """Return closed reconciliation failures without querying a candidate."""

    failures: list[str] = []
    expected_ids = {
        oracle_id
        for question in catalog["questions"]
        for oracle_id in question["oracle_ids"]
    }
    actual_questions = bundle.get("questions")
    if not isinstance(actual_questions, dict):
        return ["question oracle registry is absent"]
    if set(actual_questions) != expected_ids:
        failures.append("question oracle IDs do not reconcile with CK-01")
    if bundle.get("vertical_slices") != VERTICAL_SLICES:
        failures.append("five bake-off slices are incomplete")
    accounting = bundle.get("accounting", {})
    if accounting.get("token_formula", {}).get("reasoning_in_default_total") is not False:
        failures.append("reasoning tokens entered default total")
    source = bundle.get("source_lifecycle", {})
    if source.get("canonical_model_calls") != accounting.get("canonical_counts", {}).get(
        "model_calls"
    ):
        failures.append("source lifecycle and accounting call counts differ")
    if bundle.get("format_policy", {}).get("content_bodies") != "forbidden":
        failures.append("oracle format does not forbid raw content")
    if len(bundle.get("crash_states", [])) != 9:
        failures.append("crash boundary matrix is incomplete")
    reconciliation = bundle.get("source_to_oracle_reconciliation", {})
    if reconciliation.get("question_cases") != len(expected_ids):
        failures.append("source question cases are incomplete")
    if reconciliation.get("formula_failures"):
        failures.append("question formula reconciliation failed")
    return failures
