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
PREDECESSOR_ARTIFACT_MANIFESTS = (
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
EXPECTED_ARTIFACT_MANIFESTS = (
    "da80c04f4f2bf635be2e2bf6944247b679149b1736cae739233a364d788f84fa",
    "6a10a272eeaae7923f442fca3b379bc50b05acd73649c54de70c688c02a7de35",
    "056a717c5f1cb9f329d12e8f2af1c8d06c6aaae650dd73fa98c668324995edc9",
    "bb080ce4e67d95b24360b09c00145453b853c6e22e3baa39a263963f37929ae1",
    "0eae23fdacc49d97fef85a95a0a5d8b3fb36a87424bf52543e28674fbc63d2ce",
    "5e6b85e452aa00faf86c7d7ef6d143ddfd2cb5a25370f9fd1e34c50bcdf06a2d",
    "8c9cd9fba18c1d3019bcbba407e6b443b281ee5b3122d01d94338fef3e22f273",
    "987205ab71d770d207dcff1f85fb0b6bf698558af4a9e99fbae344a4e12839a0",
    "aa5f5fc8be6cc57ff66e10fa6730cb4d895da1f89d78157d7323c976c0ef700a",
    "0516f0afc7c91189469c7c298ba6c24f48010209a3ec03fd85b4e41759f9c9af",
    "2a99b05fe43a9a51ba5e32424e7c0cc17bb563d784e5c56e5e85a8e21138c066",
    "660eae8bacfd91252842884cbf34edc0b9f7ea3b47aa0aa934e1caff0f2807d5",
    "9d4c1f9772712fbd9cc0962129fcd4a5fe3e163d6d372af5ffede844689e5bd3",
    "cddb17e3ab06ac02f9f5e89eb0906b5d135578db9062a49e022b224e256b1c41",
    "4ee6479777723e05ac405435dd7415565dd4e0f653332d79096c48b79dc63127",
    "a665df7688fc7dc95369212119838afa95fadbbedf1458cb66c5a219a439a16b",
    "3b8ae2ad301d06efe1450e934f2cabb1ccedb84baf261fbb29c14ad7b086c8cd",
    "62c034f36f4393bdc830030f22ca27a4705d03ca89c357e0ab2885bf62d306dc",
    "3efc490279e380a00ec950d6bc6a154085c050fae2af856f93e04cafbf223540",
    "3dbda3e0c3920cce17c543e11133b6018dbe434a99c8cbe360890e5387081d08",
    "d65fbe01baeb9ae0d7be33f359934b3f4075844422df341337c2aad7028bbe51",
    "5f725926390ca0368771e7bace97e4df231372354033f0c4c96bb632bc63ec45",
    "0671912727ffee1ef3b669a601cf47d6c5fa422729bfbc5809d0bf7bcf2971e4",
    "2751471bd8503d67ad84d2e3451bd54e9c9cb9a46c335f2e427979de5232e0ea",
    "7e3e5931e9e4d851715994109814cee31f64de522c61251a12a3149fb1ad18fe",
    "35b9a30fd9adc4a0d0e4d80d91831313152a8323ad994d68ba41ea64f993fa35",
    "9c422c77f0f96ceeb5dbd37a2f9b1ffbf9601a0a99da774131052052eb031748",
    "cbf098b493c72d4c1381b5b848cb7d7243768a587ba671c49450504de963ade7",
    "e6566b9299ec36d1058800ab262b705fea727775f97a59b0d5b5a67e96fe82b8",
    "682dc1ff7e14d99a65bdcbfdd33dbab51bc240d6ff7d1ae0df588aacf99b8a92",
    "dd4ee0a1d374883d48cc12584b6f3493586597566d35bc1de5656f838dd18c61",
    "4bab8b9a2c62e5ebc468fcf7e97047d8d477768cef6637026016e672c1cd7f09",
    "102736180a4be2e26335c831b01bf8b389f0f8699b47255e673da69473b9a6c8",
    "66efcc3aad9162ce2fb41d6f7b5b466629fcd3a4da6e04076ed1b98cafd9306b",
    "b13cdbcf96d8661da26cd72c0fb316ca2c441c668e6558134f91b8db96997b66",
    "162d00c240a173943bdd4d53de5eee5cf1fe5f693b473e379b6e6ebcdfb81cde",
    "8a0207e58bb7821b632bab180a3eb941440fa5a78059126c40070e9f550fa739",
    "22db630ce103db655a77a3cbcdc5730bbc699a3000aede6f15503cb55d165ff3",
    "65e5efba5b5894bb27dc2a53adde3df08b734f514d6f567baab5773ddae8fb0d",
    "aa4ea9e238e4c816a3b187e83fbbb94765b6a23aa967526ab97c7397074c9149",
    "593fc1f1b2cc81526fbfa0a4fe54efb9d1822015d2e699a332d55d1bb348c055",
    "4569c91f6372fb8144fc376febed055bcb83d659df8ae7b3a48e1c361d1e07e6",
    "f5c9b72afde032aef8dbb3426187fb2e1770779de7dc4be9f42c11c95616cd9d",
    "f879a098c311b2a1a93856d48780131e1c1abc0bf3a3b004f4e97dc172a61e88",
    "4ad8f60d9d84ee7255087d8b85520b2cdbaec4b64ab69f00273bec10b431200a",
    "3e059e2b0869d4514e53563da33325c9cd426cedfc8016be71cbc4d0d557fdc9",
    "5e891cdf01cbb52ee11bf867f46f30c88fa44c731afbb078191d74f9d48d9835",
    "22dac5640aae8c3feddd899cacde3c3020c8a7a6e4130012a9440eb9f86a5146",
    "d08a33f5ed6d44f1a166d8d6419b8218f9faef5bb6687ede22fc9bd22dbf8cd7",
    "010de431786409e214d8d1d6d5e772ac908ead6f907fadae8402e962ae99d6d9",
    "6b4e22c2d6b59d61104e56db635cf97ee9ccdcf5b103f38a37074e9ee9fcef9c",
    "7bf881349c71fae6f891cb3b5d701f3c9cb7e7d81fe18f42b665774b5b3f2a87",
    "6b54a26e18de291c85731bdef8aace5ac1a2b5a8c9ea0f77837d2dba9434020c",
    "752156d16f5d6b70a7f82e33e2a146bc008f9ebbdc5659db07931eda200f84a4",
    "36a42dc4a86fe167cc19e41143ff6a1c90d2cf6c46addcdb90e1118e87d289ee",
    "1adb40c2dc91b31ac6bc46b98a14d3b3fb59d37cb29c23960df5b32d7e080a4b",
    "daecfd2f4c46b900a5c568eb13d9dbb068bb04beecc033b7c392e151f8f1def0",
    "bbbe67d481a4df63ad9e22a2b989f90d7af434e0b063072107ea7fbe6a385839",
    "30aa589736c3b036b88b8751a178cff2118350a6975a350fcd82cde532966c04",
    "f2918e8e3b70ae185041cec8abac745d567e91577ee9ecab7502beda3b823e34",
    "828ebafcc48ae457c39a29f113f79777a0d6b6daeb27cad58ec932b6302c5472",
    "9932446f3cabece2194b2bc646e5cff7efc952b7c759cad6d9a27debef06885a",
    "bea175c1d0142793cdb5c78a17aa1ab3326ace19a1cd3c7464736065901577c4",
    "da94cc9884ed68ee6187ef5eab55cf088e1c0bda53eef5bfe426b1cb98af9ac7",
    "86946ece36b452fafb93b07822cc722914a9e6e7905be4206e3eb6f1a527be3b",
    "c11844f1a0432aa016eeaadbcbdce8645a6c9204c67cab64da79a255d7e5111e",
    "c4097184e5a32c0bfe5f6dcd6b8182620d855cb18d813cf642d31a4aa1b2d635",
    "570f16c7eff1ced82cae8dfdefa2df2a8a7648e319638a97752d081d074aec2a",
    "8257a739da568a0b97d98ef443dc47e698d22b4209fa8522c8d64e4fa635b2ce",
    "6cd30b6fd44a3b2a57a13ed0b66e2f0e81ae896191919df54e7e5e0af546fb54",
    "ce9ec1a7afcd8c4467377b8bfd18594b69cceb880ad079a5fa95447358d05832",
    "c116e8cb3a6da384e149e519d5bcd7ea1b1cf26dd0a0e041ebf6a0b790989804",
    "c409412a494737309098a84d3341cc59c25906bbc2d7b3cd64b0b50ff922b3b1",
    "6f7d4da72501b3af99bda73dc218cbbe9e9b82d6dbf86bd1735c1fcd8006b2aa",
    "028cdfaebf380ace5a122e12d1a16cbbbc1bd734570d56080f7c0b37900e45a7",
    "8c0a7238b5ab8d410caab884fb531a83c5829fd817bef7c395f45303643bc876",
    "dc5e6797315bfbfe5cc0745fbea48a250e18815386fab1ed1d10b83f7c489bc1",
    "6d69749cceb0c06ec2f4c69b080ddc1f089450fda8fd1eac2d7467e884d6cf17",
    "a399bc575a0b3b77e9dac93a6dbc73ae0f055ef9ef7f7f91f641febee4cb4a8b",
    "31681c5999de1e1ea2fdb800fac5af137cb52c444241fbedb50be84a3261bce2",
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

_MEASUREMENT_BITS = {
    "uncached_input_tokens": 1 << 0,
    "cached_input_tokens": 1 << 1,
    "reasoning_tokens": 1 << 2,
    "output_tokens": 1 << 3,
    "context_window_tokens": 1 << 4,
    "event_at_us": 1 << 5,
}
_TERMINAL_LIFECYCLES = frozenset({"succeeded", "failed", "cancelled", "rolled_back"})
_TOOL_COORDINATE_FIELDS = tuple(
    field
    for prefix in ("start", "terminal")
    for field in (
        f"{prefix}_at_us",
        f"{prefix}_source_rank",
        f"{prefix}_source_order",
        f"{prefix}_event_kind_order",
        f"{prefix}_transition_rank",
    )
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one object")
    return value


def _materialize_r1a_measurements_and_tool_coordinates(
    cases: list[dict[str, Any]],
) -> None:
    """Fold synthetic declarations into the complete R1A fact shape."""

    for case in cases:
        needs_context_capability = case["request"]["plan_id"] == "compare_sessions"
        if needs_context_capability:
            publication_id = "publication:ck07a-structural-v2"
            if not any(fact["relation"] == "publication" for fact in case["declaration"]["facts"]):
                case["declaration"]["facts"].append(
                    {
                        "relation": "publication",
                        "logical_id": publication_id,
                        "values": {
                            "publication_id": publication_id,
                            "capabilities": {"structural_context": True},
                        },
                        "coordinates": {
                            "event_at_us": 600,
                            "source_rank": 0,
                            "source_order": 0,
                            "event_kind_order": 0,
                            "transition_rank": 0,
                        },
                    }
                )
        session_facts = {
            fact["logical_id"]: fact
            for fact in case["declaration"]["facts"]
            if fact["relation"] == "session"
        }

        def hierarchy(
            session_id: str,
            seen: set[str],
            session_facts: dict[str, dict[str, Any]] = session_facts,
        ) -> tuple[str, int] | None:
            if session_id in seen:
                return None
            fact = session_facts.get(session_id)
            if fact is None:
                return None
            parent = fact["values"].get("parent_session_id")
            if parent is None:
                return session_id, 0
            if not isinstance(parent, str):
                return None
            ancestor = hierarchy(parent, seen | {session_id})
            if ancestor is None:
                return None
            return ancestor[0], ancestor[1] + 1

        for fact in case["declaration"]["facts"]:
            values = fact["values"]
            coordinates = fact.get("coordinates")
            if fact["relation"] == "publication" and needs_context_capability:
                capabilities = values.get("capabilities")
                if isinstance(capabilities, dict) and "structural_context" not in capabilities:
                    capabilities["structural_context"] = True
            if fact["relation"] == "session":
                session_id = values.get("session_id")
                if isinstance(session_id, str):
                    resolved = hierarchy(session_id, set())
                    if resolved is not None:
                        root_session_id, delegation_depth = resolved
                        values.setdefault("root_session_id", root_session_id)
                        values.setdefault("delegation_depth", delegation_depth)
                        if values.get("root_session_id") is None:
                            values["root_session_id"] = root_session_id
                        if values.get("delegation_depth") is None:
                            values["delegation_depth"] = delegation_depth
            if fact["relation"] == "canonical_call" and "measurement_mask" not in values:
                mask = 0
                for field, bit in _MEASUREMENT_BITS.items():
                    if field == "event_at_us":
                        available = (
                            isinstance(coordinates, dict) and coordinates.get(field) is not None
                        )
                    else:
                        available = values.get(field) is not None
                    if available:
                        mask |= bit
                values["measurement_mask"] = mask
            if fact["relation"] != "tool_invocation":
                continue
            if any(field in values for field in _TOOL_COORDINATE_FIELDS):
                continue
            if not isinstance(coordinates, dict):
                continue
            start_at_us = coordinates.get("event_at_us")
            source_rank = coordinates.get("source_rank", 0)
            source_order = coordinates.get("source_order")
            event_kind_order = coordinates.get("event_kind_order")
            transition_rank = coordinates.get("transition_rank", 0)
            duration_us = values.get("duration_us")
            lifecycle = values.get("lifecycle")
            if (
                not isinstance(start_at_us, int)
                or isinstance(start_at_us, bool)
                or not isinstance(source_rank, int)
                or isinstance(source_rank, bool)
                or not isinstance(source_order, int)
                or isinstance(source_order, bool)
                or not isinstance(event_kind_order, int)
                or isinstance(event_kind_order, bool)
                or not isinstance(transition_rank, int)
                or isinstance(transition_rank, bool)
                or not isinstance(duration_us, int)
                or isinstance(duration_us, bool)
                or duration_us < 0
                or lifecycle not in _TERMINAL_LIFECYCLES
            ):
                continue
            values.update(
                {
                    "start_at_us": start_at_us,
                    "start_source_rank": source_rank,
                    "start_source_order": source_order,
                    "start_event_kind_order": event_kind_order,
                    "start_transition_rank": transition_rank,
                    "terminal_at_us": start_at_us + duration_us,
                    "terminal_source_rank": source_rank,
                    "terminal_source_order": source_order + 1,
                    "terminal_event_kind_order": 50,
                    "terminal_transition_rank": 1,
                }
            )


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
    _materialize_r1a_measurements_and_tool_coordinates(cases)
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
        frozen_mutation = case.get("semantic_mutation")
        if not isinstance(frozen_mutation, dict):
            raise ValueError(f"{case['oracle_id']} has no frozen semantic mutation")
        mutation["expected_artifact_manifest_sha256"] = frozen_mutation[
            "expected_artifact_manifest_sha256"
        ]
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
