from __future__ import annotations

import csv
import json
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

from codex_usage_tracker.api_payloads import session_payload
from codex_usage_tracker.context import load_call_context
from codex_usage_tracker.dashboard import dashboard_payload, generate_dashboard
from codex_usage_tracker.projects import (
    apply_project_privacy_to_rows,
    project_identity_for_cwd,
)
from codex_usage_tracker.reports import build_query_report
from codex_usage_tracker.store import (
    export_usage_csv,
    query_dashboard_events,
    query_session_usage,
    refresh_usage_index,
)
from codex_usage_tracker.support import build_support_bundle

SESSION_ID = "019e383a-2a4d-7a1e-bf9d-b8775626f6a4"
PROMPT_SENTINEL = "RAW_PROMPT_SENTINEL_DO_NOT_PERSIST"
ASSISTANT_SENTINEL = "RAW_ASSISTANT_SENTINEL_DO_NOT_PERSIST"
TOOL_OUTPUT_SENTINEL = "RAW_TOOL_OUTPUT_SENTINEL_DO_NOT_PERSIST"
OPENAI_SECRET = "sk" + "-proj-abcdefghijklmnopqrstuvwxyz123456"
AWS_SECRET = "AKIA" + "IOSFODNN7EXAMPLE"
BEARER_SECRET = "Authorization: " + "Bearer abc.def.ghi123456789"
PRIVATE_BRANCH = "private-client-branch"
PRIVATE_TAG = "private-client-tag"
RAW_SENTINELS = (
    PROMPT_SENTINEL,
    ASSISTANT_SENTINEL,
    TOOL_OUTPUT_SENTINEL,
    OPENAI_SECRET,
    AWS_SECRET,
    BEARER_SECRET,
)


def test_aggregate_outputs_exclude_raw_transcript_content(tmp_path: Path) -> None:
    fixture = _make_privacy_fixture(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage.csv"
    dashboard_path = tmp_path / "dashboard.html"
    support_path = tmp_path / "support.json"

    refresh_usage_index(codex_home=fixture.codex_home, db_path=db_path)
    raw_rows = query_dashboard_events(db_path=db_path, limit=0)
    strict_payload = dashboard_payload(
        db_path=db_path,
        limit=0,
        projects_path=fixture.projects_path,
        privacy_mode="strict",
    )
    generate_dashboard(
        db_path=db_path,
        output_path=dashboard_path,
        limit=0,
        projects_path=fixture.projects_path,
        privacy_mode="strict",
    )
    export_usage_csv(csv_path, db_path=db_path, privacy_mode="strict")
    build_support_bundle(
        output_path=support_path,
        codex_home=fixture.codex_home,
        db_path=db_path,
        projects_path=fixture.projects_path,
        privacy_mode="strict",
    )

    aggregate_outputs = [
        db_path.read_bytes().decode("utf-8", errors="ignore"),
        json.dumps(raw_rows),
        json.dumps(strict_payload),
        dashboard_path.read_text(encoding="utf-8"),
        csv_path.read_text(encoding="utf-8"),
        support_path.read_text(encoding="utf-8"),
    ]
    for sentinel in RAW_SENTINELS:
        for output in aggregate_outputs:
            assert sentinel not in output

    strict_row = strict_payload["rows"][0]
    csv_rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    assert strict_payload["privacy_mode"] == "strict"
    assert strict_row["cwd"].startswith("[redacted cwd:")
    assert strict_row["source_file"].startswith("[redacted source:")
    assert strict_row["project_name"].startswith("Project ")
    assert strict_row["project_relative_cwd"] is None
    assert strict_row["git_branch"] is None
    assert strict_row["git_remote_label"] is None
    assert strict_row["project_tags"] == []
    assert csv_rows[0]["cwd"].startswith("[redacted cwd:")
    assert PRIVATE_BRANCH not in json.dumps(strict_payload)
    assert PRIVATE_TAG not in json.dumps(strict_payload)
    assert PRIVATE_BRANCH not in csv_path.read_text(encoding="utf-8")
    assert PRIVATE_TAG not in csv_path.read_text(encoding="utf-8")


def test_privacy_modes_cover_dashboard_query_session_and_csv(tmp_path: Path) -> None:
    fixture = _make_privacy_fixture(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=fixture.codex_home, db_path=db_path)

    dashboard_by_mode = {
        mode: dashboard_payload(
            db_path=db_path,
            limit=0,
            projects_path=fixture.projects_path,
            privacy_mode=mode,
        )
        for mode in ("normal", "redacted", "strict")
    }
    query_by_mode = {
        mode: build_query_report(
            db_path=db_path,
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            projects_path=fixture.projects_path,
            limit=0,
            privacy_mode=mode,
        ).payload
        for mode in ("normal", "redacted", "strict")
    }
    session_rows = query_session_usage(db_path=db_path, session_id=SESSION_ID)
    session_by_mode = {
        mode: session_payload(
            apply_project_privacy_to_rows(session_rows, privacy_mode=mode),
            requested_session_id=SESSION_ID,
            limit=200,
            privacy_mode=mode,
        )
        for mode in ("normal", "redacted", "strict")
    }
    redacted_csv = tmp_path / "usage-redacted.csv"
    strict_csv = tmp_path / "usage-strict.csv"
    export_usage_csv(redacted_csv, db_path=db_path, privacy_mode="redacted")
    export_usage_csv(strict_csv, db_path=db_path, privacy_mode="strict")

    assert str(fixture.cwd) in json.dumps(dashboard_by_mode["normal"])
    assert str(fixture.cwd) in json.dumps(query_by_mode["normal"])
    assert str(fixture.cwd) in json.dumps(session_by_mode["normal"])
    for payload in (
        dashboard_by_mode["redacted"],
        dashboard_by_mode["strict"],
        query_by_mode["redacted"],
        query_by_mode["strict"],
        session_by_mode["redacted"],
        session_by_mode["strict"],
    ):
        text = json.dumps(payload)
        assert str(fixture.cwd) not in text
        assert "[redacted cwd:" in text
    assert query_by_mode["redacted"]["rows"][0]["project_relative_cwd"] == "private/workflow"
    assert query_by_mode["redacted"]["rows"][0]["git_branch"] == PRIVATE_BRANCH
    assert query_by_mode["redacted"]["rows"][0]["project_tags"] == [PRIVATE_TAG]
    assert query_by_mode["strict"]["rows"][0]["project_relative_cwd"] is None
    assert query_by_mode["strict"]["rows"][0]["git_branch"] is None
    assert query_by_mode["strict"]["rows"][0]["git_remote_label"] is None
    assert query_by_mode["strict"]["rows"][0]["project_tags"] == []
    assert str(fixture.cwd) not in redacted_csv.read_text(encoding="utf-8")
    assert str(fixture.cwd) not in strict_csv.read_text(encoding="utf-8")


def test_context_loading_is_explicit_redacted_and_not_static_html(tmp_path: Path) -> None:
    fixture = _make_privacy_fixture(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    dashboard_path = tmp_path / "dashboard.html"
    refresh_usage_index(codex_home=fixture.codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]

    generate_dashboard(
        db_path=db_path,
        output_path=dashboard_path,
        context_api_enabled=True,
        api_token="test-token",
    )
    static_html = dashboard_path.read_text(encoding="utf-8")
    default_context = load_call_context(record_id, db_path=db_path)
    default_context_text = json.dumps(default_context)
    tool_context = load_call_context(record_id, db_path=db_path, include_tool_output=True)
    tool_context_text = json.dumps(tool_context)

    for sentinel in RAW_SENTINELS:
        assert sentinel not in static_html
    assert default_context["loaded_on_demand"] is True
    assert default_context["raw_context_persisted"] is False
    assert PROMPT_SENTINEL in default_context_text
    assert ASSISTANT_SENTINEL in default_context_text
    assert TOOL_OUTPUT_SENTINEL not in default_context_text
    assert "Tool output omitted by default" in default_context_text
    assert TOOL_OUTPUT_SENTINEL in tool_context_text
    for secret in (OPENAI_SECRET, AWS_SECRET, BEARER_SECRET):
        assert secret not in default_context_text
        assert secret not in tool_context_text
    assert "[REDACTED_OPENAI_KEY]" in default_context_text
    assert "[REDACTED_AWS_ACCESS_KEY]" in default_context_text
    assert "Authorization: Bearer [REDACTED_BEARER_TOKEN]" in tool_context_text


def test_context_server_requires_loopback_origin_token_and_enablement(tmp_path: Path) -> None:
    from codex_usage_tracker.server import _ContextApiState, _UsageDashboardHandler

    fixture = _make_privacy_fixture(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=fixture.codex_home, db_path=db_path)
    record_id = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]["record_id"]
    context_api_state = _ContextApiState(False)
    handler = partial(
        _UsageDashboardHandler,
        directory=str(tmp_path),
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=fixture.projects_path,
        limit=5000,
        since=None,
        codex_home=fixture.codex_home,
        include_archived=False,
        dashboard_name="dashboard.html",
        context_chars=2000,
        api_token="test-token",
        context_api_state=context_api_state,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        disabled_error = _http_error_json(
            f"{base_url}/api/context?record_id={record_id}",
            headers={"X-Codex-Usage-Token": "test-token"},
        )
        foreign_origin_error = _http_error_json(
            f"{base_url}/api/context-settings?enabled=1",
            headers={
                "Origin": "http://example.test",
                "X-Codex-Usage-Token": "test-token",
            },
        )
        missing_token_error = _http_error_json(f"{base_url}/api/context-settings?enabled=1")
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context-settings?enabled=1",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            settings_payload = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(  # noqa: S310 - local test server only
            urllib.request.Request(
                f"{base_url}/api/context?record_id={record_id}",
                headers={"X-Codex-Usage-Token": "test-token"},
            ),
            timeout=5,
        ) as response:
            context_payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert disabled_error["status"] == 403
    assert disabled_error["payload"]["context_api_enabled"] is False
    assert foreign_origin_error["status"] == 403
    assert missing_token_error["status"] == 403
    assert settings_payload["schema"] == "codex-usage-tracker-context-settings-v1"
    assert settings_payload["context_api_enabled"] is True
    assert settings_payload["raw_context_persisted"] is False
    assert context_payload["loaded_on_demand"] is True
    assert context_payload["raw_context_persisted"] is False


class _PrivacyFixture:
    def __init__(self, *, codex_home: Path, projects_path: Path, cwd: Path) -> None:
        self.codex_home = codex_home
        self.projects_path = projects_path
        self.cwd = cwd


def _make_privacy_fixture(tmp_path: Path) -> _PrivacyFixture:
    codex_home = tmp_path / ".codex"
    project_root = tmp_path / "private-client-project"
    cwd = project_root / "private" / "workflow"
    git_dir = project_root / ".git"
    cwd.mkdir(parents=True)
    git_dir.mkdir()
    (git_dir / "HEAD").write_text(f"ref: refs/heads/{PRIVATE_BRANCH}\n", encoding="utf-8")
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = git@github.com:secret-owner/secret-repo.git\n',
        encoding="utf-8",
    )
    project_key = project_identity_for_cwd(str(cwd))["project_key"]
    projects_path = tmp_path / "projects.json"
    projects_path.write_text(
        json.dumps({"tags": {project_key: [PRIVATE_TAG]}}),
        encoding="utf-8",
    )
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T18-58-27-{SESSION_ID}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": SESSION_ID,
                "thread_name": "Synthetic privacy thread",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": SESSION_ID}),
            _entry(
                "turn_context",
                {
                    "turn_id": "turn-a",
                    "model": "gpt-5.5",
                    "effort": "high",
                    "cwd": str(cwd),
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{PROMPT_SENTINEL} {OPENAI_SECRET} {AWS_SECRET}",
                        }
                    ],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": ASSISTANT_SENTINEL}],
                },
            ),
            _entry(
                "response_item",
                {
                    "type": "function_call_output",
                    "name": "shell",
                    "output": f"{TOOL_OUTPUT_SENTINEL} {BEARER_SECRET}",
                },
            ),
            _token_event(250, 250),
        ],
    )
    return _PrivacyFixture(codex_home=codex_home, projects_path=projects_path, cwd=cwd)


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 30,
                    "cached_input_tokens": 80,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 10,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 30,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 10,
                    "total_tokens": last_total,
                },
                "model_context_window": 258400,
            },
        },
    )


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _http_error_json(url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        urllib.request.urlopen(request, timeout=5)  # noqa: S310 - local test server only
    except urllib.error.HTTPError as exc:
        return {
            "status": exc.code,
            "payload": json.loads(exc.read().decode("utf-8")),
        }
    raise AssertionError("expected HTTPError")
