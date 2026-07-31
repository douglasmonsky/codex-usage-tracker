"""Build the frozen 80-case structural-v2 CK-07A declaration set."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from tests.agent_kernel.fact_adapters.support import (
    plan_contract,
)
from tests.agent_kernel.fixtures.oracles.exact import normalize_exact

SCENARIO_SCHEMA = "codex-usage-tracker.synthetic-question-scenarios.v1"
FIXTURE_REVISION = "agent-kernel-structural-v2"
ROOT = Path(__file__).resolve().parents[4]
CATALOG_PATH = ROOT / "config/agent-kernel/question-catalog-v1.json"
FROZEN_AUTHORITY_PATH = ROOT / "tests/agent_kernel/fixtures/tiny-v2/question-scenarios.json"

# This is deliberately explicit.  The ordinal assigns one distinct native turn
# key to every named oracle without deriving the catalog from CK-06/CK-07.  The
# adapter must canonicalize that source-level identity onto the declared turn
# ordinal, so the mutation is semantic input rather than an ignored body field.
ORACLE_AUTHORITY_ORDER = (
    "oracle:q-acc-01:boundaries",
    "oracle:q-acc-01:missing_measurement",
    "oracle:q-acc-02:ties",
    "oracle:q-acc-02:duplicate_source",
    "oracle:q-acc-03:nonoverlap",
    "oracle:q-acc-03:reconciliation",
    "oracle:q-acc-04:unknown_effort",
    "oracle:q-acc-04:profile_transition",
    "oracle:q-acc-05:multilevel_hierarchy",
    "oracle:q-acc-05:late_parent",
    "oracle:q-acc-06:mixed_pricing",
    "oracle:q-acc-06:zero_coverage",
    "oracle:q-acc-07:missing_rate_card",
    "oracle:q-acc-07:unmatched_alias",
    "oracle:q-ctx-01:missing_cached_input",
    "oracle:q-ctx-01:percentile_ties",
    "oracle:q-ctx-02:compaction_epoch",
    "oracle:q-ctx-02:missing_window",
    "oracle:q-ctx-03:constant_sequence",
    "oracle:q-ctx-03:outlier_policy",
    "oracle:q-ctx-04:compaction_boundary",
    "oracle:q-ctx-04:equal_time",
    "oracle:q-ctx-05:multiple_tools",
    "oracle:q-ctx-05:no_following_call",
    "oracle:q-ctx-06:zero_output",
    "oracle:q-ctx-06:tool_heavy_turn",
    "oracle:q-ctx-07:capability_absent",
    "oracle:q-ctx-07:unattributed_bytes",
    "oracle:q-ctx-08:missing_side",
    "oracle:q-ctx-08:multiple_compactions",
    "oracle:q-ctx-09:delayed_mutation",
    "oracle:q-ctx-09:missing_capability",
    "oracle:q-ctx-10:explicit_cohort",
    "oracle:q-ctx-10:unrelated_labels",
    "oracle:q-wf-01:open_tail",
    "oracle:q-wf-01:terminal_basis",
    "oracle:q-wf-02:failed_then_success",
    "oracle:q-wf-02:delayed_mutation",
    "oracle:q-wf-03:path_aliases",
    "oracle:q-wf-03:read_write_mix",
    "oracle:q-wf-04:unrelated_interleave",
    "oracle:q-wf-04:success_first_try",
    "oracle:q-wf-05:unknown_operation",
    "oracle:q-wf-05:missing_duration",
    "oracle:q-wf-06:long_gap",
    "oracle:q-wf-06:no_following_call",
    "oracle:q-wf-07:resource_alias",
    "oracle:q-wf-07:write_without_change",
    "oracle:q-wf-08:unknown_effort",
    "oracle:q-wf-08:repeated_profile",
    "oracle:q-wf-09:one_off_pattern",
    "oracle:q-wf-09:conflicting_outcomes",
    "oracle:q-wf-10:incomplete_tool",
    "oracle:q-wf-10:user_gap",
    "oracle:q-del-01:multilevel_family",
    "oracle:q-del-01:orphan_parent",
    "oracle:q-del-02:model_mix_confounder",
    "oracle:q-del-02:unequal_cohorts",
    "oracle:q-alw-01:compatible_interval",
    "oracle:q-alw-01:reset_boundary",
    "oracle:q-alw-02:empty_interval",
    "oracle:q-alw-02:same_time_boundary",
    "oracle:q-alw-03:negative_delta",
    "oracle:q-alw-03:unpriced_interval",
    "oracle:q-alw-04:incomplete_cycle",
    "oracle:q-alw-04:plan_change",
    "oracle:q-ops-01:no_change",
    "oracle:q-ops-01:recanonicalized_owner",
    "oracle:q-ops-02:deferred_history",
    "oracle:q-ops-02:missing_capability",
    "oracle:q-ops-03:exact_copy",
    "oracle:q-ops-03:owner_change",
    "oracle:q-ops-04:equal_time_event",
    "oracle:q-ops-04:stable_rebuild_selector",
    "oracle:q-rev-01:partial_history",
    "oracle:q-rev-01:unpriced_model",
    "oracle:q-rev-02:conflicting_signals",
    "oracle:q-rev-02:no_candidate",
    "oracle:q-rev-03:differing_coverage",
    "oracle:q-rev-03:open_session",
)
EXPECTED_ARTIFACT_MANIFESTS = (
    "23c044b20e1b578b191af79f298f6eb4a1352be56e6db6c3ce98c22c2adb5df9",
    "aa05c3e602e85c6e660b4bd064ae4d750d36155d38ad5228cd5c09a48135d786",
    "b9ea7e810612ad9d258bfc88f5dd9c0ced7b509658af46b8e4d412065b033157",
    "04b39068bf828630c0369446b2044b44b55a57cdb2aef7b975399dd5edc15113",
    "f65ea9b57f74c42787fa81064e8ded559203009bc42504a612a0537907b734f3",
    "1520a16c9501465810a4ae78b60f322ff6c017cf0084c17ed25e8561d929c029",
    "0d8351f005ef15a09390eab3cf195e756a26a13396a13b4a52d7e7508e75ffaf",
    "489a833a0000d9fb4e770fe581233b115a9612daf3aa34f24d3def1d2456b57c",
    "a8a2033f1fbb6ac744edd08b13da1695a178ab0eaa94a6fff22e773007a55eca",
    "0bf814e63714ebde6a4ce16eca06940bb5f214e5b3a8179c8c5339d9946cfc4f",
    "0623a563c6a1c52d3475f40e78e5ce2d887a06bc2fbe6486f291d3b4d397a476",
    "2e032c480a0aa55206d5ab86712d4828834a6d50dd7bb9909104e3845dd99b3e",
    "451cb1272dee3adb6a7de4e1fc5ad72c62fc0389025f3066bbb954cefb5dc2ea",
    "e34f15be80d9c9153fdd816376bc71cc078881cc6d256d0e5a408b23a42c30e6",
    "a3dcca8fcd59ceb886f1a32d15948e69a50514836d0a8424e4bf34cf11fb3241",
    "5673eba4f031ea730bbfc2a8bbeba15defaa23e16c7e11611bb49f7e8348261a",
    "d041281f7974292088fe09809a853d4923577e557b3049fb27768faf221e2758",
    "574d1a87238b44729be0b43cb7f838cb537d7f8dd35eaa637d2cd45bd7bba37e",
    "d7cd9ec573ebb6a0180572d6c0e2a1f21b1407f409a7d95e6e7412c64f6145f6",
    "30bb0394f34250b81d76f554588c5c5b9c93afd22f73c588a1c5df6f35f22bb6",
    "e0162a571dde2f4985cd91ea857a55d20197a0c67385512724e3da758321ce33",
    "d0736538eec949b862529f84063f28371dc6468ada8176325ab99df447c0b4dc",
    "fb2cba04f9f2700bcf9fb8fad44c4e191e886ff955d053583a64b3ebd8fa3af7",
    "9713d09ccd5914b2b39a9a9f32c4a914f40ed47aa0970ae3af5e4ab8b2f54fbf",
    "ea987260c2a628b155c7f4c441bb8d6fc13b76360da4acaa4be9e1b6b39d681d",
    "f177c7224547f1bea4ff47d2ff05aa0d5f45e8ae28ebbf826824840a63c9d154",
    "08eb699cead344b2a8dc83e37fe0264df8710f04d2a0792c781764bbb6541dc0",
    "27f2d13b41826c9227efd228b6878df1e862daf8ed9a1204da7f5aa6799e1223",
    "48a22787ea5f020a223798b50969496c29fc79af4aee6d47a74c6e8355a9f87a",
    "10bc85edf5afdd59e69daf3d87810d44c2d09bd73cbb9a426e838db25d7a09b5",
    "ef218f934dacffb7d17628c22d1203bcd3c54e4019f6db69974021d9ee491a70",
    "f5fe2be20840af9608277abb1d6779506289fb83c8a3c0c788f1a87cb091bcbc",
    "980cb6e1e803d2b3b02f037557b7e18c532b3874173ffa89c429e2911cb08316",
    "94902b2ae74ad184d0264272d600a51198fb67d089a5959ed1d55f6af7d3f08b",
    "1b40c64961b64038fe8441bc711b3c04ead65a8bedc1e2fae65ca53b7e1acea8",
    "76d0cd0c947d04266d6802b34d199db27df4c23da48cd64ad4b162a8ca7883af",
    "035a772cc52a032bb552c805ec5a6ed3c430d4c7dea58c5bcacfbebe6cccdd59",
    "2fce748d7aaabadeca6131fe9dcda7eb556eb7f486dd201658feeecc58aecb6c",
    "dacaeab13afc9c058fe1193b5c8c332b5111904cf91b986127db2a9442da96f5",
    "a994b125de025fb913f887fa11fa4289895c24256b6bee35ebacc35829b327b7",
    "a13b30a13a65c254594dfaea04690acda2028f8cfa229dfb4ea5c1610d752e31",
    "242ad23b0ed9b66c48c5a6e11a58f1c294f518752f6ce4a67847c05bf1c8a56b",
    "702af92d6aeadc2ba3882f3e8ff13403805cb403c37fd8dbc04188c1dfd99abb",
    "2e9240a48df3fc8059313c1293f6622e9cac306ef7492f27646d991068efe982",
    "fc608181fdc41a962e4ec227d2993ef66af794af14c1ae0667ce97e3344e0014",
    "b33d49bd29db76ab6709cb3c491485fc640fb3f05ebf89b6273a0054e6ab8d82",
    "1fd80efcbc09e4016ffd895e4792d9b98b0b42e78b0088dea252d9d7c892655b",
    "fe166cfbf33a43e1ce5696f6e1654956e25c4135b84e68253bb07d3cd0a07efb",
    "18eba67d97d242ea36edc822fa3be0821638d1588835d3f6a3613b3afaed6514",
    "42a9011d986775ede73d029cc3f5e50e5c1de4f90e37e98d4c3880191bd247de",
    "d7ffe1f195393427cddba8e10e9df694dd7b67c9c8de2a0820e349903782885a",
    "9142f83f713fb849a737e48bb6d0db21b97966ded1b092978f1ee1cdc7ef0905",
    "d99d8a1e7f0dc4a366276e74d6928372e3b2ccac775f4470f74ee18f71377c99",
    "34517f0f34262eede4c2e3ece236a838f61fed8137c48041e34717afb68f68be",
    "ea39c713a9dfa1570c6bf5196a3b814b4bb7bcdb1ef01b71bfe3292741ad1f6a",
    "140262e49844c0f67df304a230dea4760969bfc7105dcc70f92d2ad3bd827154",
    "2a4fb7db22e35d3e208aaf423a3141bfdaecf618ef05ea1b69285e56a57bc364",
    "afc0a8d7dc2e97fea6755a7ac4da6d84e937efae8a2054ef3b920b4900eae5cb",
    "1c19ae5ff5897680a90749a298489af60015cce1d12650405353cdb82bad0198",
    "544bdd3631ac6b31afcb0da3988ceb0fa62cb90047ad15085257e413109d62bf",
    "4a28a028475d2863794cae3183b8867bedef84f5d3d145135ed12e88e58a329d",
    "853251cfbe17f1c5d7821bc2d63059b53c7daea9f02db8ba20ce4f029d27b004",
    "a8b160a2dfebc79ec1fae7807103a8a82b3874a2b8ccde610ed39cf5bebb0574",
    "3510339a9a515326687dedbf10a2f8496efa71deafd79acf02b3133ad51a7bdb",
    "b81fd349b93c9c2cb0eb2a4f73b388adde6003f001bc18f387bd3e608812d201",
    "1ff82be40c96723db5c4b4fe41bb94a442195290ad8739ff7d7a0c4eee0ad029",
    "046c897d5345519df214a864512d82d12c9cf7b558a2b0a07aa8482d4b50cbb2",
    "7fb8a54c5d8e0a0e06ddd0d2956a09015162142ac317d29c8fdda7f3674793ee",
    "86ea56a0b18eb06ac8a1e4bb4fa8dee429a02a4aae4a3a2be05fd179bacd4919",
    "488319f9836fcd171361c496e7dac274fd9ea4c0e38a8873592062066c70ea43",
    "ece9463925cf20cfe8aeb9d0e7c3cce925878d4a7d383c80029381d501d98217",
    "894f71d17d172c730233708f67a9d7bfb7a899c4ccf4609583d52e0858b4eeb5",
    "d8af796ddcba91e08ebf7f0cc5ca5102ad187695ff9715b1119ad860ab130303",
    "3f130a505eb383dd7122d8b4b3e9c69b2211d03e18ad586fa7bcaf2a67bda8e9",
    "1122a7ec8eb617742f737cd595703bb19562cb781752497f184d405d5fedfcaa",
    "a52420cf54d9f1cfff3911021d2469f3e3cc0392aed8b6ceef88ef199d7c77e9",
    "46a92bea1464da429e3c77f6997158dfce37f40780b5ea1952060b0399f02f87",
    "b29e49796246d5d7c440ed0b528302831e859cc4e98d99e6e674839ca5e37d4c",
    "e681a4829c50184527824725d76f45b0e1e342ccc899dc87812c035552feb374",
    "8c3ea8c3a2c7a152cfd058c9f12e0621f8854338ec7ae30a009e05ac6445e88a",
)
VARIANT_MUTATIONS = {
    oracle_id: {
        "kind": "set_native_turn_key",
        "record_type": "model_call",
        "native_call_id": "before",
        "native_turn_id": f"v{variant_ordinal:08d}",
        "expected_artifact_manifest_sha256": EXPECTED_ARTIFACT_MANIFESTS[variant_ordinal],
    }
    for variant_ordinal, oracle_id in enumerate(ORACLE_AUTHORITY_ORDER)
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one object")
    return value


def build_question_scenarios() -> dict[str, Any]:
    """Load the frozen, independently declared truth before any database replay."""

    catalog = _load(CATALOG_PATH)
    authority = _load(FROZEN_AUTHORITY_PATH)
    catalog_ids = {
        oracle_id for question in catalog["questions"] for oracle_id in question["oracle_ids"]
    }
    if catalog_ids != set(ORACLE_AUTHORITY_ORDER):
        raise ValueError("explicit CK-07A oracle authority does not match the catalog")
    if len(ORACLE_AUTHORITY_ORDER) != 80 or len(VARIANT_MUTATIONS) != 80:
        raise ValueError("CK-07A requires exactly 80 explicit variant mutations")
    if len({item["native_turn_id"] for item in VARIANT_MUTATIONS.values()}) != 80:
        raise ValueError("CK-07A variant mutations must produce 80 distinct source shapes")

    cases = copy.deepcopy(authority["cases"])
    if {case["oracle_id"] for case in cases} != catalog_ids:
        raise ValueError("frozen CK-07A authority does not match the catalog")
    plans = {plan["plan_id"]: plan for plan in plan_contract()["plans"]}
    for case in cases:
        permitted_relations = {
            source["relation"] for source in plans[case["request"]["plan_id"]]["permitted_sources"]
        }
        if "source_occurrence" in permitted_relations:
            selected_entity_ids = {
                fact["logical_id"]
                for fact in case["declaration"]["facts"]
                if fact["relation"] in permitted_relations
                and fact["relation"] != "source_occurrence"
            }
            case["declaration"]["facts"] = [
                fact
                for fact in case["declaration"]["facts"]
                if fact["relation"] != "source_occurrence"
                or fact["values"]["semantic_logical_id"] in selected_entity_ids
            ]
        mutation = copy.deepcopy(VARIANT_MUTATIONS[case["oracle_id"]])
        source_profile = case.get("source_profile")
        if not isinstance(source_profile, dict):
            prior_name = Path(str(case["source_path"])).stem
            source_profile = {
                "late_event": prior_name in {"late", "late-missing"},
                "missing_cached_input": prior_name in {"missing", "late-missing"},
            }
        case["source_profile"] = source_profile
        case["semantic_mutation"] = mutation
        publication_facts = [
            fact for fact in case["declaration"]["facts"] if fact["relation"] == "publication"
        ]
        if len(publication_facts) > 1:
            raise ValueError(f"{case['oracle_id']} declares duplicate publication facts")
        if publication_facts:
            publication_facts[0]["values"]["artifact_manifest_sha256"] = mutation[
                "expected_artifact_manifest_sha256"
            ]
        case["variant_predicates"] = [
            {
                "predicate": "source_record_native_turn_key",
                "record_type": mutation["record_type"],
                "native_call_id": mutation["native_call_id"],
                "asserted_value": mutation["native_turn_id"],
            },
            {
                "predicate": "published_call_canonical_identity",
                "native_call_id": mutation["native_call_id"],
                "asserted_value": semantic_id(
                    "call",
                    [
                        "before",
                        semantic_id("session", ["root", "identity-v1"]),
                        semantic_id(
                            "turn",
                            [semantic_id("session", ["root", "identity-v1"]), 1],
                        ),
                    ],
                ),
            },
        ]
    return {
        "schema": SCENARIO_SCHEMA,
        "fixture_revision": FIXTURE_REVISION,
        "authority": {
            "basis": "frozen_pre_ck06_ck07_structural_declaration",
            "database_export_prohibited": True,
            "variant_mutations": 80,
            "variant_predicates": 160,
        },
        "cases": normalize_exact(cases),
    }
