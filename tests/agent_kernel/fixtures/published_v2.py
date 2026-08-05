"""Synthetic structural-v2 source records and real CK-06/CK-07 publication."""

from __future__ import annotations

import copy
import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, TypedDict

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
)
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.rate_cards import (
    attach_rate_card_frontier,
    prepare_rate_card_frontier,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_analytical
from tests.agent_kernel.fixtures.oracles.cases_v2 import (
    EXPECTED_ARTIFACT_MANIFESTS as REVOKED_ARTIFACT_MANIFESTS,
)
from tests.agent_kernel.fixtures.oracles.cases_v2 import (
    ORACLE_AUTHORITY_ORDER,
    PREDECESSOR_ARTIFACT_MANIFESTS,
)

PUBLICATION_ID = "publication:ck07a-structural-v2"
OLD_DIGEST = "1" * 64
HEAD_DIGEST = "2" * 64
PREDECESSOR_SCHEMA_CONTRACT_SHA256 = (
    "1a2dcffe778633457bbeb60dd3a41c233a78c15af2a3393bf9cacc1d9e645bb5"
)
REVOKED_SCHEMA_CONTRACT_SHA256 = (
    "e3b8509774987fb4fd9cd09aeee1ab9ee32642932ea6a07726315154409b1e35"
)
SELECTED_SCHEMA_CONTRACT_SHA256 = (
    "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295"
)

# This tuple is candidate-owned publication truth for the current schema.  It
# is kept beside the generator so the frozen CK-07A oracle-order source and its
# authority digest remain unchanged until the authority owner selects these
# bytes.  Values were independently recomputed by replaying every declared
# synthetic variant through this current-schema writer.
CURRENT_SCHEMA_ARTIFACT_MANIFESTS = (
    "31ad1ec4a73ce22f702260782048d7f13ef3fb169bb9e09fdc25f1a277941732",
    "a50ec90d01c35da25cc18c51cc1cfa097b6ae05f0bf7417dfaa573923e0bd5a8",
    "756aab1522f6e6f8cc05b8a1bdaab88671ae4fd6bfa2580951cf03c38ba1dd37",
    "b445a1b3479c82b8dd1f116dc920136aeaedad510696f4037f89abfdd432e234",
    "cc9367872862a18a3382e962f45424230fe0411c3699cda93358e20e53f53421",
    "a1634d27d4c361283b213eb6a169adb16d24a4b12469821b8c25210894d1e0ad",
    "a627c9525c39780224d797ecc10e5ac1faa1fd9aa4066b12d60b618e09f0624f",
    "4bf297ca684182141042650adb0f6783a094c5075ff5d20be9d4b6ad3d7df9f5",
    "5ea511bca5c24303a08dc0484ae860fccf2fe2fce22ae14ef3dae2310cc67efe",
    "886be062068b57db8cd1b31d9dae8998684f3013a877884c5c70dcb30123c98c",
    "96fb2da76715ea016d738f4830e6d4038f298a9810f2f70e25efb21e7aadf14c",
    "418579cb04e86ac055a8cebc0998b5b5a68c81f936104a7f01286167f1c5726a",
    "c8db77a4bcc903fc8d73bf8b3573bbf7e93bc69e21992a14f6d47b2dcb469d53",
    "baefdeeba31c0182f1d690b98810197e8b117ae6029142da1481011698a1f049",
    "17148b759ffb69dbb78b3584d6cf2f967d9490b5712652ff4c8bb8e594ee52dd",
    "07e5f47ac4e2fb988643150d605df58cda7119b9dd6fe6dfa59c99da5140e430",
    "842bce1c7c24e4bd1f9efc9574378e72959d1465910929930e5f4f6550b66fc2",
    "0a5d555e2f696cbf2cf09b4221e6669ec468e2dfad76e26f875628ced60f2e39",
    "7f69c32b845dc77b4513c9996200032de3b7ce20ec171b44879ce1afb1ea818a",
    "45cd758fdb1aea655b55f4473232f375ebe1fb18e4eee9d2c0c9dfa4241dd75a",
    "f424f8ab9a773ec09e6d4329769377c9100c667178ae236bbdde0ac8543e1a12",
    "305e22629adc3c20bc570f9073d4d712614240a053a882f9888c91095297ddaa",
    "ad379c6daa8c0103ea47cce3a22f209e055164e02ed19321e8edbe1b2880f84a",
    "58a9eca5b37c08119188becba6a827b9e134d56d73bf4b400a1fc57c6c592914",
    "8f2894d9e91af8bc733547fcd2e3286eb7187bc486c492b28cb3524c46bc4b7b",
    "cfb7296c7890bee60f1f55b27fbfe2927738f82e34d6375b9d016c17847e0a19",
    "f3b0628c72fc8aa938f00bbc8281b0c1902bbb4ac05d8f846c88384f5cb2cd25",
    "4adf07e4a831b015b0d2f89da877c6e7e78f8c0cea520ea1e5b97ab995121692",
    "0ca244c17aff61cec5f5ab2d0828a60ea9a4a91fea3776f99ad11beda502b3b1",
    "933364ddaa320e03044254cac29a4c2b4cdf6109cf6058b138ee0699efa6c6df",
    "209d71fbd1b9020818c01e12c41a1a7c89ee1b81f82ef6f711f26728c93a0de8",
    "6a73e58f10b51cf8302f3b0694ce8c39c92fb70d40610e72106818c066c3cc23",
    "fb2c007690d715fa8cd71731ece1d9dc30409e38d5bafcd5a35fbcb1edf385e8",
    "efaea7dd3b5185e7809d8f0f156f8a292db39112cd33c67ee7cc07e2d49b6fc7",
    "c62b84558c3296483d27af0cebf544921f662283536a67205ca842f8646a28ec",
    "43e5eb6904bcdce960f97d9d37efb73184cac3b7b28c1ef37829fed658939af7",
    "e65573aae0524aba6714c100c867c9ed19788bbdc6f9a8dcfa8cd2057ad8fa07",
    "7d619f78546fd3906122113c56e2b94ee213cb9ddda4e7510f413f3efc60a28f",
    "282cef2fee27967e3014fe945bab9e37807488c55b4b58961cea8a57699168c7",
    "ee514b36c07db22e4245ce0e7207acec56043c485184d5f1040b30dce8e6150c",
    "88a919f3c855fdbae864ffcf98cc0b3f3ffd561d3c5e38dca060b3f7508f82ef",
    "7c309b9cc204cc5132f5e3d8840615d38f4d44a2f99e2d9c788c9abc60554917",
    "3450225e76d1ef551d5e13e410e8738c78d9b1e0cbf42ec0ebb53d688db80b24",
    "c4c1abc0762e5ad7b2561ad4bdebf8955d0bb3f89282e61dd74acf8038ac84f1",
    "79f6763656ad4449813ca589c0fb0c5aba210455dd439fd939e4a8e6d1ff8f66",
    "1095bd8a735cf021b3cd9c3a8d9569277fc184aeded2c65c849c811a37db6e23",
    "edc78a50c7f87c32d9e22b2527cb99961aa14844759c22ae85ebb59345d24218",
    "f7bc61551c870aaa9100562ae9f8ffcdc01f8443413f5c2e76a08e55b2810424",
    "2eb9ba8dee996c7bb3228a61838f51a154302e425da48d7a3b2079a0b3898793",
    "3d9413c9010d94c89b160b01cf71935c14267f213dc053c31d2ac66b81e98f9b",
    "44e4c7c84648d7eb6352cf1ce354ce5b82416097b7a94dc803075f9955c93820",
    "2353224a9336ba936ff562b8f7919ce9b45a7c9f48be737ee880d25e378995b6",
    "9545d75254d083479cf5ffff06c2dc9684cb107907e221b8a77521dfb9ea7fae",
    "a1ddece9a806c9aaa92bc6b09a23fe1fb3ebfba4a1a7525f0643853c3bfc5549",
    "9db2c2e34c45839d06e80e6ba73a36664b47ccb6e49c41f74d1e55a0bdeb7c9f",
    "996146cf127a4f81b9361ba13f6dd26a1ebe40a8706e3e175fd9ea6075585c56",
    "9715b5d55413e62e7457d04a05cda9d4e9e97ce52d20fdcf619f0381674022c4",
    "dab4133ad976210b13600f946d22ae9f2740063825b84bd88dba42ef6a7609de",
    "5169dd5fdb0b464c3856ad0e37256ead295e2e438ee3318fdd17471079124786",
    "0899548a130d04b58d46829feec7482e888aed35d723ea030d993ce1a43903ac",
    "5dc25cdae7a817becd02edd868938eefe86cbbb6e55defa30e9e8239773beaa4",
    "b9dadc7cb8b1349d22a0ed2b05158599f361f2f519eff47ddd4ac70fd53c1115",
    "c89897c0ffad64497c51dae90fddc98d88288203cbd830c8f69be4d853d3a971",
    "b40fa5faab9363d1682dada026da7d38495feafbd2cf63b95f234ca3dd054b02",
    "7581ec5f45ec40caa1784b3e3c2262d5c066ef42c47fbf6d9478e9d10829e4fe",
    "5763f5dd8a0880b50fcda7058d01076498d0184cbc23ced276e5baec53cfaf00",
    "8b23c011decb4c16700ca7484ff391af788ec7d612b4c0549e4f5e50c5140c99",
    "3df07cef9ff9d2dd0db8d8c17ae24724a1fff6bef94af573c0a269567beea91c",
    "8a1e943d1cedf9c0ef8ff21dff37ee6bd9ee767bad670dec1c83cea29210e2cc",
    "e9e0ef9a675b51929e222b16f9e7c0f1d2ea0a1ee57857537f9b506f054ea853",
    "c5a0be766803f41087f54f1d738e05994417d94a5e7a52cf9bc348fea4dbce55",
    "57836752a5d8be2cc6802d05fe90a52acd35083d25009eef06a5ecbc6bf7835b",
    "cd78272e6bcf959b6cf9c16bcda3d96d38a37110586f4e7afb3719758611e78f",
    "543c463247588f760733802451c9e27ea82d2bbd64162e88a9c665386affcbe1",
    "82fe694cf22b9fb800f78d7a8a12e72321e911cf8b7dfb53e0b743900ec0ba8f",
    "dfdda5fb205b435f1c7aa1c9e1a066ce3c33e2084c28661de7219230ff6cecf4",
    "5964a77d55cd6ef844d2878e57e3a13588201a5093b2c68a9cba4d7e65c7c575",
    "124c028cd5ede635d8a34036690cb436cf910b047ed16c353ded944933f8a9ea",
    "91536778311a827a091d2008d8e1cccee07f65e6d56ff9aa8a0b781d641ce7d5",
    "e51a0f955f76d34a208c2fd6ef4f6aed00609252c1d9bf3404ad5abf277e2618",
)

_EVENT_KIND_ORDER = {
    "session_start": 10,
    "turn_start": 20,
    "model_call": 30,
    "compaction_boundary": 35,
    "context_component": 37,
    "tool_start": 40,
    "tool_terminal": 50,
    "state_change": 60,
    "allowance_observation": 70,
    "session_terminal": 80,
}


class StructuralPublication(TypedDict):
    artifact_manifest_sha256: str
    source_bytes: int
    source_records: int
    observations: int
    occurrences: int
    inserted_occurrences: int
    ingestion_ns: int
    publication_ns: int


def _record(
    record_type: str,
    event_at_us: int,
    source_order: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": record_type,
        "event_at_us": event_at_us,
        "event_kind_order": _EVENT_KIND_ORDER[record_type],
        "source_order": source_order,
        "payload": payload,
    }


def structural_records(
    *,
    include_late_call: bool = False,
    null_cached_tokens: bool = False,
    variant_native_turn_id: str = "root-turn",
) -> list[dict[str, Any]]:
    """Return body-free adapter-ingestible records spanning every fact family."""

    records = [
        _record(
            "session_start",
            50,
            1,
            {
                "session_id": "root",
                "project_id": "alpha",
                "parent_session_id": None,
                "state": "running",
            },
        ),
        _record(
            "session_start",
            150,
            2,
            {
                "session_id": "child",
                "project_id": "alpha",
                "parent_session_id": "root",
                "relationship_basis": "structural",
                "state": "running",
            },
        ),
        _record(
            "turn_start",
            75,
            20,
            {
                "session_id": "root",
                "turn_id": "root-turn",
                "turn_ordinal": 1,
                "state": "running",
            },
        ),
        _record(
            "turn_start",
            175,
            40,
            {
                "session_id": "child",
                "turn_id": "child-turn",
                "turn_ordinal": 1,
                "state": "running",
            },
        ),
    ]
    calls = [
        ("before", "root", "root-turn", 100, 21, "synthetic-model", "high", 100, 20, 5, 10),
        ("boundary", "child", "child-turn", 250, 41, "synthetic-model", "high", 200, 40, 10, 20),
        ("other", "child", "child-turn", 300, 42, "synthetic-other", "medium", 300, 60, 15, 30),
    ]
    for (
        call_id,
        session_id,
        turn_id,
        event_at_us,
        source_order,
        model,
        effort,
        uncached,
        cached,
        reasoning,
        output,
    ) in calls:
        records.append(
            _record(
                "model_call",
                event_at_us,
                source_order,
                {
                    "call_id": call_id,
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "turn_ordinal": 1,
                    "model": model,
                    "reasoning_effort": effort,
                    "service_tier": "priority" if effort == "high" else "standard",
                    "context_window_tokens": 128_000,
                    "tokens": {
                        "uncached_input_tokens": uncached,
                        "cached_input_tokens": (
                            None if null_cached_tokens and call_id == "before" else cached
                        ),
                        "reasoning_tokens": reasoning,
                        "output_tokens": output,
                    },
                },
            )
        )
    tools = (
        ("inspect", "read", "file", "file", False, "succeeded", 180, 60),
        ("attempt", "execute", "file", "file", True, "failed", 200, 62),
        ("retry", "test", "test", "test_target", True, "succeeded", 220, 64),
    )
    for tool_id, operation, resource_id, resource_kind, write_intent, state, at, order in tools:
        common = {
            "tool_id": tool_id,
            "session_id": "root",
            "turn_id": "root-turn",
            "turn_ordinal": 1,
            "transport_name": "synthetic",
            "semantic_operation": operation,
            "resource_id": resource_id,
            "resource_kind": resource_kind,
            "project_id": "alpha",
            "write_intent": write_intent,
        }
        records.append(_record("tool_start", at, order, {**common, "state": "running"}))
        records.append(
            _record(
                "tool_terminal",
                at + 25,
                order + 1,
                {**common, "state": state, "duration_us": 25, "output_bytes": 64},
            )
        )
    records.extend(
        [
            _record(
                "state_change",
                210,
                70,
                {
                    "change_id": "file-change",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "resource_id": "file",
                    "resource_kind": "file",
                    "project_id": "alpha",
                    "change_kind": "modified",
                    "preceding_activity_count": 1,
                    "causal_attribution": None,
                },
            ),
            _record(
                "compaction_boundary",
                230,
                71,
                {
                    "compaction_id": "one",
                    "session_id": "root",
                    "before_context_epoch": "before",
                    "after_context_epoch": "after",
                },
            ),
        ]
    )
    for index, category in enumerate(("tool_output", "workspace_context"), start=1):
        records.append(
            _record(
                "context_component",
                235 + index,
                72 + index,
                {
                    "component_id": f"component-{index}",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "call_id": "before",
                    "category": category,
                    "observed_utf8_bytes": 1000 * index,
                    "observed_event_count": 1,
                    "estimator": "synthetic",
                    "estimated_tokens": 250 * index,
                    "total_context_utf8_bytes": 5000,
                    "inclusion_basis": "observed_in_source",
                    "capability_basis": "structural",
                    "measurement_basis": "synthetic",
                },
            )
        )
    for index, (observed_at_us, remaining_percent) in enumerate(
        ((90, "90"), (190, "80"), (190, "80"), (290, "70"))
    ):
        records.append(
            _record(
                "allowance_observation",
                observed_at_us,
                80 + index,
                {
                    "provider": "synthetic-provider",
                    "account_local_identity": "synthetic-account",
                    "limit_id": "weekly",
                    "cycle_id": "one",
                    "plan_identity": "synthetic-plan",
                    "window_kind": "rolling_week",
                    "reset_identity": "reset:one",
                    "cycle_start_us": 0,
                    "cycle_end_us": 1000,
                    "completion_status": "completed",
                    "observation_ordinal": index,
                    "used_percent": str(100 - int(remaining_percent)),
                    "remaining_percent": remaining_percent,
                    "observed_at_us": observed_at_us,
                },
            )
        )
    records.extend(
        [
            _record(
                "session_terminal",
                450,
                90,
                {
                    "session_id": "child",
                    "project_id": "alpha",
                    "parent_session_id": "root",
                    "relationship_basis": "structural",
                    "state": "succeeded",
                    "completion_basis": "terminal_event",
                },
            ),
            _record(
                "session_terminal",
                500,
                91,
                {
                    "session_id": "root",
                    "project_id": "alpha",
                    "parent_session_id": None,
                    "state": "succeeded",
                    "completion_basis": "terminal_event",
                },
            ),
        ]
    )
    if include_late_call:
        records.append(
            _record(
                "model_call",
                125,
                92,
                {
                    "call_id": "late",
                    "session_id": "root",
                    "turn_id": "root-turn",
                    "turn_ordinal": 1,
                    "model": "synthetic-model",
                    "reasoning_effort": "high",
                    "service_tier": "priority",
                    "context_window_tokens": 128_000,
                    "tokens": {
                        "uncached_input_tokens": 80,
                        "cached_input_tokens": 10,
                        "reasoning_tokens": 2,
                        "output_tokens": 8,
                    },
                },
            )
        )
    matching_variant_records = [
        record
        for record in records
        if record["type"] == "model_call" and record["payload"].get("call_id") == "before"
    ]
    if len(matching_variant_records) != 1:
        raise ValueError("structural source must contain exactly one variant call")
    matching_variant_records[0]["payload"]["turn_id"] = variant_native_turn_id
    return records


def rate_card_frontier() -> RateCardFrontier:
    rates = {
        "uncached_input_tokens": "1",
        "cached_input_tokens": "1",
        "reasoning_tokens": "1",
        "output_tokens": "1",
    }
    revisions = (
        RateCardRevision(
            rate_card_id=semantic_id("rate-card", [OLD_DIGEST]),
            digest=OLD_DIGEST,
            predecessor_digest=None,
            effective_at_us=0,
            fetched_at_us=900,
            source_name="synthetic-old",
            source_url=None,
            currency="USD",
            model_match_rules=(
                {"match_basis": "model_alias", "model_alias": "synthetic-model"},
                {"match_basis": "model_alias", "model_alias": "synthetic-other"},
            ),
            four_class_rates=rates,
            credit_rates=rates,
            reasoning_in_output=False,
            confidence="synthetic",
            validation_status="valid",
        ),
        RateCardRevision(
            rate_card_id=semantic_id("rate-card", [HEAD_DIGEST]),
            digest=HEAD_DIGEST,
            predecessor_digest=OLD_DIGEST,
            effective_at_us=250,
            fetched_at_us=100,
            source_name="synthetic-new",
            source_url=None,
            currency="USD",
            model_match_rules=(
                {"match_basis": "model_alias", "model_alias": "synthetic-model"},
                {"match_basis": "model_alias", "model_alias": "synthetic-other"},
            ),
            four_class_rates={key: "2" for key in rates},
            credit_rates={key: "2" for key in rates},
            reasoning_in_output=False,
            confidence="synthetic",
            validation_status="valid",
        ),
    )
    return RateCardFrontier(HEAD_DIGEST, revisions)


def publish_structural_snapshot(
    fixture_root: Path,
    database_path: Path,
    *,
    include_late_call: bool = False,
    null_cached_tokens: bool = False,
    variant_native_turn_id: str = "root-turn",
) -> StructuralPublication:
    """Run real CK-06 ingestion and CK-07 publication into database-v1."""

    fixture_root.mkdir(parents=True, exist_ok=True)
    payload = b"".join(
        json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for record in structural_records(
            include_late_call=include_late_call,
            null_cached_tokens=null_cached_tokens,
            variant_native_turn_id=variant_native_turn_id,
        )
    )
    (fixture_root / "source.jsonl").write_bytes(payload)
    ingestion_started_ns = time.perf_counter_ns()
    ingested = ingest(fixture_root, workers=2, batch_size=32)
    ingestion_ns = time.perf_counter_ns() - ingestion_started_ns
    frontier = rate_card_frontier()
    request = PublicationRequest(
        publication_id=PUBLICATION_ID,
        operation_id="operation:ck07a-structural-v2",
        committed_at_us=600,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        observed_through_us=500,
        indexed_from_us=50,
        indexed_through_us=500,
        guaranteed_complete_from_us=50,
        rate_card_digest=frontier.head_digest,
    )
    prepared = prepare_rate_card_frontier(
        frontier,
        publication_id=request.publication_id,
    )
    write_set = attach_rate_card_frontier(
        prepare_write_set_from_changes(ingested.changes, request),
        request,
        prepared,
    )
    plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(
            ingested.changes,
            dirty_keys=len(prepared.dirty_intervals),
        ),
        ("ck07a_structural_v2",),
        True,
        prepared.dirty_intervals,
    )
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            plan,
            request,
            write_set,
        ),
    )
    publication_started_ns = time.perf_counter_ns()
    connection = initialize_analytical(database_path)
    try:
        published = PublicationWriter(connection).publish(plan, request, write_set)
    finally:
        connection.close()
    publication_ns = time.perf_counter_ns() - publication_started_ns
    return {
        "artifact_manifest_sha256": request.artifact_manifest_sha256,
        "source_bytes": len(payload),
        "source_records": len(
            structural_records(
                include_late_call=include_late_call,
                null_cached_tokens=null_cached_tokens,
                variant_native_turn_id=variant_native_turn_id,
            )
        ),
        "observations": len(ingested.changes.observations),
        "occurrences": len(ingested.changes.occurrences),
        "inserted_occurrences": published.inserted_occurrences,
        "ingestion_ns": ingestion_ns,
        "publication_ns": publication_ns,
    }


def case_for_schema_contract(
    connection: sqlite3.Connection,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Bind expected synthetic publication facts to one exact schema state."""

    result = copy.deepcopy(case)
    row = connection.execute(
        """
        SELECT schema_contract_sha256
        FROM publications
        WHERE publication_id = ?
        """,
        (PUBLICATION_ID,),
    ).fetchone()
    actual_schema = None if row is None else str(row[0])
    try:
        ordinal = ORACLE_AUTHORITY_ORDER.index(str(result["oracle_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("published variant is outside frozen CK-07A authority") from exc
    if actual_schema == PREDECESSOR_SCHEMA_CONTRACT_SHA256:
        expected_artifact = PREDECESSOR_ARTIFACT_MANIFESTS[ordinal]
        result["semantic_mutation"]["expected_artifact_manifest_sha256"] = expected_artifact
        for fact in result["declaration"]["facts"]:
            if fact.get("relation") == "publication":
                fact["values"]["artifact_manifest_sha256"] = expected_artifact
    elif actual_schema == SELECTED_SCHEMA_CONTRACT_SHA256:
        expected_artifact = CURRENT_SCHEMA_ARTIFACT_MANIFESTS[ordinal]
        result["semantic_mutation"]["expected_artifact_manifest_sha256"] = expected_artifact
        for fact in result["declaration"]["facts"]:
            if fact.get("relation") == "publication":
                fact["values"]["artifact_manifest_sha256"] = expected_artifact
    else:
        raise ValueError("publication uses an unauthorized schema-contract digest")
    return result


def published_question_case(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    *,
    preserve_frozen_authority: bool = False,
) -> dict[str, Any]:
    """Verify a publication against, but never derive, frozen structural truth."""

    result = copy.deepcopy(case)
    publication = connection.execute(
        """
        SELECT publication_id
        FROM publication_head
        WHERE singleton = 1
        """
    ).fetchone()
    if publication is None or str(publication[0]) != PUBLICATION_ID:
        raise ValueError("published CK-07A snapshot is missing")
    artifact = connection.execute(
        """
        SELECT artifact_manifest_sha256, schema_contract_sha256
        FROM publications
        WHERE publication_id = ?
        """,
        (PUBLICATION_ID,),
    ).fetchone()
    try:
        ordinal = ORACLE_AUTHORITY_ORDER.index(str(result["oracle_id"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("published variant is outside frozen CK-07A authority") from exc
    if artifact is None:
        raise ValueError("publication is missing its schema-contract digest")
    actual_schema = str(artifact[1])
    expected_by_schema = {
        PREDECESSOR_SCHEMA_CONTRACT_SHA256: PREDECESSOR_ARTIFACT_MANIFESTS,
        SELECTED_SCHEMA_CONTRACT_SHA256: CURRENT_SCHEMA_ARTIFACT_MANIFESTS,
    }
    expected_manifests = expected_by_schema.get(actual_schema)
    if expected_manifests is None:
        raise ValueError("publication uses an unauthorized schema-contract digest")
    result["semantic_mutation"]["expected_artifact_manifest_sha256"] = expected_manifests[ordinal]
    for fact in result["declaration"]["facts"]:
        if fact.get("relation") == "publication":
            fact["values"]["artifact_manifest_sha256"] = expected_manifests[ordinal]
    expected_artifact = result["semantic_mutation"]["expected_artifact_manifest_sha256"]
    if expected_artifact != expected_manifests[ordinal]:
        raise ValueError("candidate publication artifact transition is not selected")
    expected_by_schema = {
        PREDECESSOR_SCHEMA_CONTRACT_SHA256: PREDECESSOR_ARTIFACT_MANIFESTS,
        SELECTED_SCHEMA_CONTRACT_SHA256: CURRENT_SCHEMA_ARTIFACT_MANIFESTS,
    }
    expected_by_variant = (
        expected_by_schema.get(actual_schema) if actual_schema is not None else None
    )
    if (
        artifact is None
        or expected_by_variant is None
        or str(artifact[0]) != expected_by_variant[ordinal]
    ):
        raise ValueError("published artifact manifest differs from frozen authority")
    for predicate in result.get("variant_predicates", ()):
        if predicate.get("predicate") != "published_call_canonical_identity":
            continue
        row = connection.execute(
            """
            SELECT call_id
            FROM model_calls_visible
            WHERE adapter_native_call_key = ?
            """,
            (predicate["native_call_id"],),
        ).fetchone()
        if row is None or str(row[0]) != str(predicate["asserted_value"]):
            raise ValueError("published variant predicate failed")
    if preserve_frozen_authority:
        return result
    return case_for_schema_contract(connection, result)


__all__ = [
    "HEAD_DIGEST",
    "OLD_DIGEST",
    "case_for_schema_contract",
    "CURRENT_SCHEMA_ARTIFACT_MANIFESTS",
    "PREDECESSOR_SCHEMA_CONTRACT_SHA256",
    "PUBLICATION_ID",
    "REVOKED_ARTIFACT_MANIFESTS",
    "REVOKED_SCHEMA_CONTRACT_SHA256",
    "SELECTED_SCHEMA_CONTRACT_SHA256",
    "publish_structural_snapshot",
    "published_question_case",
    "rate_card_frontier",
    "structural_records",
]
