from __future__ import annotations

import io
import json
import math
import tarfile
from pathlib import Path

import tomllib

from codex_usage_tracker.kernel import __version__
from codex_usage_tracker.kernel.application import KernelApplication
from codex_usage_tracker.kernel.interfaces.mcp.server import McpServer
from scripts.check_release import _sdist_source_byte_failures

from .interfaces.support import active_runtime, synthetic_sources

_ROOT = Path(__file__).resolve().parents[2]
_VERSION = "0.27.0"
_AUDITED_MAIN = "b0857cb6744ffa8f82453eedb07863afb3a6b69f"


def test_release_027_sdist_rejects_stale_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("current\n", encoding="utf-8")
    archive_path = tmp_path / "release.tar.gz"
    stale = b"stale\n"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("package/README.md")
        member.size = len(stale)
        archive.addfile(member, io.BytesIO(stale))

    with tarfile.open(archive_path, "r:gz") as archive:
        failures = _sdist_source_byte_failures(
            archive,
            archive_root="package/",
            relative_paths={"README.md"},
            source_root=source,
        )

    assert failures == [
        "integration sdist contains stale source bytes: README.md"
    ]


def test_release_027_identity_is_coherent_and_anchored_to_merged_main() -> None:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = json.loads((_ROOT / "package.json").read_text(encoding="utf-8"))
    plugin = json.loads(
        (_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    qualification = json.loads(
        (_ROOT / "config" / "kernel-release-qualification-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert project["project"]["version"] == _VERSION
    assert package["version"] == _VERSION
    assert __version__ == _VERSION
    assert plugin["version"] == _VERSION
    assert plugin["bundle"]["runtime_version"] == _VERSION
    assert qualification == {
        "schema": "codex-usage-tracker.kernel-release-qualification.v1",
        "version": _VERSION,
        "audited_main_sha": _AUDITED_MAIN,
        "base_release": {
            "version": "0.26.0",
            "tag": "v0.26.0",
            "merge_sha": "1d6ae5286ecde0201b5c868863df30a783b6aa82",
        },
        "qualified_tasks": {
            "K11": "2efd075b3a3aee7a312f5bd6ea5210b3b72960f0",
            "K12": "45f7a3e20007d18ab769599160ecbf6e7c891911",
            "K13": _AUDITED_MAIN,
        },
        "optional_assets": {
            "context_store": {
                "disposition": "owner_only_unbundled",
                "bundled_bytes": 0,
            },
            "overlay": {"disposition": "absent", "bundled_bytes": 0},
        },
        "golden_prompt": {
            "mcp_calls": 3,
            "measured_response_bytes": [499, 9677, 906],
            "response_byte_ceilings": [513, 9967, 933],
            "measured_total_bytes": 11082,
            "total_byte_ceiling": 11414,
        },
    }


def test_release_027_ci_and_public_install_paths_are_current() -> None:
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    readme = (_ROOT / "README.md").read_text(encoding="utf-8")

    assert "github.head_ref == 'release/0.27.0'" in ci
    assert "config/kernel-release-qualification-v1.json" in ci
    assert "--version 0.27.0" in ci
    assert 'codex-usage-tracking==0.27.0' in readme
    assert "--ref v0.27.0" in readme


def test_release_027_golden_prompt_uses_three_bounded_read_only_mcp_calls(
    tmp_path: Path,
) -> None:
    qualification = json.loads(
        (_ROOT / "config" / "kernel-release-qualification-v1.json").read_text(
            encoding="utf-8"
        )
    )
    budget = qualification["golden_prompt"]
    launches = []
    runtime = active_runtime(tmp_path)
    server = McpServer(
        KernelApplication(
            runtime,
            worker_launcher=launches.append,
            source_provider=lambda _home: synthetic_sources(),
        )
    )
    operational_before = runtime.kernel.operational.read_bytes()
    analytical_before = runtime.kernel.analytical.read_bytes()
    responses = [
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "usage_status", "arguments": {}},
            }
        ),
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "usage_query",
                    "arguments": {
                        "include_guidance": True,
                        "requests": [
                            {
                                "dataset": "calls",
                                "operation": "share",
                                "dimensions": ["thread"],
                                "measures": ["calls", "total_tokens"],
                                "limit": 10,
                            },
                            {
                                "dataset": "calls",
                                "operation": "aggregate",
                                "dimensions": ["model", "effort"],
                                "measures": ["calls", "total_tokens"],
                                "limit": 10,
                            },
                        ],
                    },
                },
            }
        ),
    ]
    query = responses[1]["result"]["structuredContent"]
    selector = query["results"][0]["evidence_selectors"][0]
    responses.append(
        server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "usage_evidence",
                    "arguments": {
                        "selector": selector,
                        "view": "summary",
                        "limit": 10,
                    },
                },
            }
        )
    )
    assert all("error" not in response for response in responses)
    assert all(response["result"].get("isError") is not True for response in responses)
    status = responses[0]["result"]["structuredContent"]
    evidence = responses[2]["result"]["structuredContent"]
    assert status["state"] == "active"
    assert query["results"]
    assert query["guidance"]["datasets"]
    assert all(result["rows"] for result in query["results"])
    assert all(result["generation"] == status["generation"] for result in query["results"])
    assert evidence["generation"] == status["generation"]
    assert evidence["selector"] == selector
    assert evidence["matched_count"] > 0
    assert evidence["rows"]
    response_bytes = [
        len(json.dumps(response, separators=(",", ":"), sort_keys=True).encode())
        for response in responses
    ]

    assert len(responses) == budget["mcp_calls"] == 3
    assert all(
        actual <= ceiling
        for actual, ceiling in zip(
            response_bytes,
            budget["response_byte_ceilings"],
            strict=True,
        )
    )
    assert all(
        measured <= ceiling <= math.floor(measured * 1.03)
        for measured, ceiling in zip(
            budget["measured_response_bytes"],
            budget["response_byte_ceilings"],
            strict=True,
        )
    )
    assert sum(response_bytes) <= budget["total_byte_ceiling"]
    assert (
        budget["measured_total_bytes"]
        <= budget["total_byte_ceiling"]
        <= math.floor(budget["measured_total_bytes"] * 1.03)
    )
    assert launches == []
    assert runtime.kernel.operational.read_bytes() == operational_before
    assert runtime.kernel.analytical.read_bytes() == analytical_before
