from __future__ import annotations

import argparse
import json
from io import StringIO
from pathlib import Path

from codex_usage_tracker.analytics.analysis_models import AnalysisRequest
from codex_usage_tracker.application.query_models import QueryRequest
from codex_usage_tracker.application.requests import StatusRequest
from codex_usage_tracker.interfaces.cli import commands as commands_module
from codex_usage_tracker.interfaces.cli.commands import (
    run_analyze,
    run_open,
    run_query,
    run_status,
    warn_legacy_alias,
)
from codex_usage_tracker.interfaces.cli.parser import build_parser


class _Services:
    def __init__(self) -> None:
        self.request: object | None = None

    def status(self, request: object) -> object:
        self.request = request
        return {"schema": "codex-usage-tracker.status.v2", "state": "ready"}

    def analyze(self, request: object) -> object:
        self.request = request
        return {"schema": "codex-usage-tracker.analysis.v2", "summary": "bounded"}

    def query(self, request: object) -> object:
        self.request = request
        return {"schema": "codex-usage-tracker.query.v2", "rows": []}


def test_status_prints_the_application_contract_as_json() -> None:
    services = _Services()
    stdout = StringIO()
    args = build_parser().parse_args(["--db", "usage.db", "status", "--json"])

    assert run_status(args, services=services, stdout=stdout) == 0
    assert json.loads(stdout.getvalue())["schema"] == "codex-usage-tracker.status.v2"
    assert isinstance(services.request, StatusRequest)
    assert services.request.db_path == Path("usage.db")


def test_default_services_preserve_the_configured_projects_path(tmp_path: Path) -> None:
    projects_path = tmp_path / "custom-projects.json"
    args = build_parser().parse_args(
        ["--projects", str(projects_path), "status", "--json"]
    )

    services = commands_module._default_services(args)

    assert services.application.paths.projects_path == projects_path


def test_query_builds_the_typed_v2_request() -> None:
    services = _Services()
    stdout = StringIO()
    args = build_parser().parse_args(
        [
            "query",
            "--entity",
            "model",
            "--measure",
            "tokens,call_count",
            "--group-by",
            "effort",
            "--history",
            "all",
            "--limit",
            "10",
            "--json",
        ]
    )

    assert run_query(args, services=services, stdout=stdout) == 0
    request = services.request
    assert isinstance(request, QueryRequest)
    assert request.entity == "model"
    assert request.measures == ("tokens", "call_count")
    assert request.group_by == ("effort",)
    assert request.history == "all"
    assert json.loads(stdout.getvalue())["schema"] == "codex-usage-tracker.query.v2"


def test_analyze_builds_the_typed_v2_request_from_bounded_flags() -> None:
    services = _Services()
    stdout = StringIO()
    args = build_parser().parse_args(
        [
            "analyze",
            "--goal",
            "usage_spike",
            "--since",
            "2026-07-01T00:00:00Z",
            "--history-scope",
            "all",
            "--evidence-limit",
            "4",
            "--json",
        ]
    )

    assert run_analyze(args, services=services, stdout=stdout) == 0
    request = services.request
    assert isinstance(request, AnalysisRequest)
    assert request.goal == "usage_spike"
    assert request.history == "all"
    assert request.evidence_limit == 4
    assert request.filters.since == "2026-07-01T00:00:00Z"
    assert json.loads(stdout.getvalue())["schema"] == "codex-usage-tracker.analysis.v2"


def test_open_resolves_an_exact_call_target_without_touching_stdout() -> None:
    stdout = StringIO()
    opened: list[str] = []
    args = build_parser().parse_args(["open", "--call-id", "record-12"])

    assert (
        run_open(
            args,
            stdout=stdout,
            service_origin="http://127.0.0.1:47821",
            open_url=lambda url: opened.append(url) or True,
        )
        == 0
    )
    assert opened == [
        "http://127.0.0.1:47821/react-dashboard.html?kind=call&record=record-12&view=evidence"
    ]
    assert stdout.getvalue() == ""


def test_open_rejects_a_supplied_loopback_url_that_does_not_match_its_target() -> None:
    args = build_parser().parse_args(
        [
            "open",
            "--target-json",
            json.dumps(
                {
                    "schema": "codex-usage-tracker-dashboard-target-v2",
                    "relative_url": "/react-dashboard.html?view=home",
                    "absolute_url": "http://127.0.0.1:47821/admin?delete=true",
                }
            ),
        ]
    )

    try:
        run_open(args, service_origin="", open_url=lambda _url: True)
    except RuntimeError as exc:
        assert "Evidence Console is unavailable" in str(exc)
    else:
        raise AssertionError("mismatched loopback target was accepted")


def test_legacy_warning_is_interactive_only_and_never_uses_stdout() -> None:
    stdout = StringIO()
    stderr = StringIO()
    args = argparse.Namespace(compatibility_alias="summary")

    warn_legacy_alias(args, stderr=stderr, interactive=False)
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == ""

    warn_legacy_alias(args, stderr=stderr, interactive=True)
    assert stderr.getvalue() == (
        "Deprecated: 'summary' is a compatibility alias; use 'analyze' or 'query'.\n"
    )
