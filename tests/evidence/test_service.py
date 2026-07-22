from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.contracts import EvidenceV1, payload_mapping
from codex_usage_tracker.core.dashboard_targets import is_canonical_record_id
from codex_usage_tracker.evidence.models import (
    EvidenceAmbiguityError,
    EvidenceHistoryMismatchError,
    EvidenceNotFoundError,
    EvidenceRequest,
)
from codex_usage_tracker.evidence.service import resolve_evidence
from codex_usage_tracker.jobs.adapters import AnalysisJobAdapter, request_hash
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.api import connect, upsert_usage_events
from tests.application.fixtures.analysis_cases import ANALYSIS_CASES, synthetic_analysis_report
from tests.application.test_query import _seed
from tests.store_dashboard_helpers import _usage_event


def seed_evidence(db_path: Path) -> None:
    _seed(db_path)
    with connect(db_path) as connection:
        connection.execute("UPDATE usage_events SET record_id='record-1' WHERE record_id='call-0'")
        connection.execute(
            "UPDATE usage_events SET canonical_record_id='record-1' "
            "WHERE canonical_record_id='call-0'"
        )
        connection.execute("UPDATE usage_events SET record_id='record-4' WHERE record_id='call-1'")
        connection.execute("UPDATE usage_events SET record_id='record-2' WHERE record_id='call-2'")
        connection.execute("UPDATE usage_events SET record_id='record-3' WHERE record_id='call-3'")
        connection.execute(
            "UPDATE usage_events SET thread_key='thread:alpha' WHERE record_id='record-3'"
        )


def test_call_resolution_is_canonical_and_history_scoped(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    result = get_evidence(EvidenceRequest("call", "record-1"), db_path=db_path)
    assert result.schema == "codex-usage-tracker.evidence-result.v1"
    assert result.records[0].selectors == {"record_id": "record-1"}
    assert "raw" not in str(result.records[0].metrics).lower()
    with pytest.raises(EvidenceHistoryMismatchError):
        get_evidence(EvidenceRequest("call", "record-2"), db_path=db_path)
    archived = get_evidence(
        EvidenceRequest("call", "record-2", history="all"),
        db_path=db_path,
    )
    assert archived.records[0].selectors["record_id"] == "record-2"


def test_thread_summary_and_calls_are_aggregate_only(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    summary = get_evidence(EvidenceRequest("thread", "thread:alpha"), db_path=db_path)
    calls = get_evidence(
        EvidenceRequest("thread", "thread:alpha", section="calls", limit=1),
        db_path=db_path,
    )
    assert summary.records[0].kind == "thread"
    assert summary.records[0].source_schema == "thread_summaries.v1"
    assert len(calls.records) == 1
    assert calls.next_cursor is not None
    assert "transcript" not in str(summary.records + calls.records).lower()

    with pytest.raises(ValueError, match="cursor"):
        get_evidence(
            EvidenceRequest("thread", "thread:alpha", section="calls", cursor="bad"),
            db_path=db_path,
        )
    with pytest.raises(ValueError, match="scope"):
        get_evidence(
            EvidenceRequest(
                "thread",
                "thread:alpha",
                section="calls",
                cursor=calls.next_cursor,
                history="all",
                limit=1,
            ),
            db_path=db_path,
        )
    upsert_usage_events(
        [
            _usage_event(
                record_id="record-5",
                session_id="session-5",
                thread_key="thread:alpha",
                event_timestamp="2026-07-26T12:00:00Z",
                cumulative_total_tokens=500,
            )
        ],
        db_path,
    )
    with pytest.raises(ValueError, match="stale"):
        get_evidence(
            EvidenceRequest(
                "thread",
                "thread:alpha",
                section="calls",
                cursor=calls.next_cursor,
                limit=1,
            ),
            db_path=db_path,
        )


def test_missing_selector_is_typed_not_empty(tmp_path: Path) -> None:
    with pytest.raises(EvidenceNotFoundError, match="not found"):
        get_evidence(EvidenceRequest("call", "record-999"), db_path=tmp_path / "missing.sqlite3")


def _analysis_service(revision: str = "generation:1") -> JobService:
    evidence = EvidenceV1(
        evidence_id="evidence-1",
        kind="call",
        label="Canonical call",
        selectors={"record_id": "record-1"},
        metrics={"tokens": 10},
        source_schema="canonical_usage.v2",
        dashboard_target=None,
    )
    report = {
        "schema": "codex-usage-tracker.analysis.v2",
        "analysis_id": "compatibility.token_waste:generation:1",
        "findings": [{"finding_id": "finding-1", "evidence_ids": ["evidence-1"]}],
        "evidence": [payload_mapping(evidence)],
    }
    raw = {
        "job_id": "analysis-evidence",
        "status": "completed",
        "stage": "complete",
        "source_revision": revision,
        "created_at": "2026-07-22T12:00:00Z",
        "updated_at": "2026-07-22T12:01:00Z",
        "progress": {"percent": 100},
        "result": report,
    }
    service = JobService()
    service.register(
        kind="analysis",
        job_id="analysis-evidence",
        adapter=AnalysisJobAdapter(
            lambda _job_id, include_result=False: raw,
            kind="analysis",
            request_hash=request_hash("analysis-evidence"),
            result_schema="codex-usage-tracker.analysis.v2",
        ),
    )
    return service


def test_completed_analysis_and_finding_resolve_exact_embedded_evidence(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    service = _analysis_service()
    analysis = get_evidence(
        EvidenceRequest("analysis", "compatibility.token_waste:generation:1"),
        db_path=db_path,
        job_service=service,
    )
    finding = get_evidence(
        EvidenceRequest("finding", "finding-1"),
        db_path=db_path,
        job_service=service,
    )
    assert analysis.records == finding.records
    assert finding.records[0].selectors == {"record_id": "record-1"}
    assert finding.dashboard_target["analysis_id"] == analysis.selector["id"]
    with pytest.raises(EvidenceNotFoundError):
        get_evidence(
            EvidenceRequest("finding", "finding-1"),
            db_path=db_path,
            job_service=_analysis_service("generation:stale"),
        )


def test_allowance_resolves_one_exact_persisted_interval(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO allowance_source_state VALUES "
            "(1, 1, 'allowance:1', 1, '2026-07-22T00:00:00Z', 'v1', '2026-07-22T00:00:00Z')"
        )
        connection.execute(
            "INSERT INTO allowance_intervals "
            "(interval_id, cycle_id, window_kind, window_key, cohort_key, is_archived, "
            "end_observed_at, point_kind, source_revision) VALUES "
            "('interval-1', 'cycle-1', 'weekly', 'primary', 'team-a', 0, "
            "'2026-07-22T00:00:00Z', 'observed', 'allowance:1')"
        )
    result = get_evidence(EvidenceRequest("allowance", "interval-1"), db_path=db_path)
    assert result.records[0].selectors == {"interval_id": "interval-1"}
    assert result.records[0].source_schema == "allowance_intervals.v1"


class _FixtureRepository:
    def __init__(
        self,
        report: dict[str, object] | tuple[dict[str, object], ...],
        revision: str | None = "generation:1",
    ) -> None:
        self.reports = report if isinstance(report, tuple) else (report,)
        self.revision = revision

    def source_revision(self):
        return self.revision

    def call(self, selector_id: str, history: str):
        return None

    def thread_summary(self, selector_id: str, history: str):
        return None

    def thread_calls(self, selector_id: str, history: str, limit: int, cursor: str | None):
        return (), None

    def allowance(self, selector_id: str, history: str):
        return None

    def completed_analyses(self):
        return self.reports


@pytest.mark.parametrize(("goal", "_record_id"), ANALYSIS_CASES)
def test_every_synthetic_finding_resolves_its_exact_embedded_evidence(
    goal: str, _record_id: str
) -> None:
    context = build_request_context(
        db_path=Path("/nonexistent/synthetic.sqlite3"),
        pricing_path=Path("/nonexistent/pricing.json"),
        scope=RequestScope(),
    )
    fixture = synthetic_analysis_report(goal, context)  # type: ignore[arg-type]
    evidence = fixture.evidence[0]
    report = {
        "analysis_id": fixture.analysis_id,
        "findings": tuple(payload_mapping(item) for item in fixture.findings),
        "evidence": fixture.evidence,
    }
    result = resolve_evidence(
        EvidenceRequest("finding", f"finding-{goal}"), _FixtureRepository(report)
    )
    assert result.records == (evidence,)
    assert evidence.selectors["record_id"] == _record_id
    assert is_canonical_record_id(_record_id)


def test_embedded_analysis_uses_revision_bound_keyset_pagination() -> None:
    evidence = tuple(
        EvidenceV1(
            evidence_id=f"evidence-{index}",
            kind="call",
            label=f"Call {index}",
            selectors={"record_id": f"record-{index}"},
            metrics={"tokens": index},
            source_schema="codex-usage-tracker.query.v2",
            dashboard_target=None,
        )
        for index in range(1, 4)
    )
    repository = _FixtureRepository(
        {"analysis_id": "analysis-1", "findings": (), "evidence": evidence}
    )
    first = resolve_evidence(EvidenceRequest("analysis", "analysis-1", limit=1), repository)
    second = resolve_evidence(
        EvidenceRequest("analysis", "analysis-1", limit=1, cursor=first.next_cursor),
        repository,
    )
    assert [first.records[0].evidence_id, second.records[0].evidence_id] == [
        "evidence-1",
        "evidence-2",
    ]
    with pytest.raises(ValueError, match="malformed"):
        resolve_evidence(EvidenceRequest("analysis", "analysis-1", cursor="bad"), repository)
    with pytest.raises(ValueError, match="scope"):
        resolve_evidence(
            EvidenceRequest("analysis", "analysis-1", limit=2, cursor=first.next_cursor),
            repository,
        )
    repository.revision = "generation:2"
    with pytest.raises(ValueError, match="stale"):
        resolve_evidence(
            EvidenceRequest("analysis", "analysis-1", limit=1, cursor=first.next_cursor),
            repository,
        )


def test_finding_requires_qualifier_when_same_revision_reports_share_id() -> None:
    def report(analysis_id: str, *evidence_ids: str) -> dict[str, object]:
        evidence = tuple(
            EvidenceV1(
                evidence_id=evidence_id,
                kind="call",
                label=evidence_id,
                selectors={"record_id": "record-1"},
                metrics={"tokens": 1},
                source_schema="codex-usage-tracker.query.v2",
                dashboard_target=None,
            )
            for evidence_id in evidence_ids
        )
        return {
            "analysis_id": analysis_id,
            "findings": ({"finding_id": "finding-shared", "evidence_ids": evidence_ids},),
            "evidence": evidence,
        }

    repository = _FixtureRepository(
        (
            report("analysis-1", "evidence-1a", "evidence-1b"),
            report("analysis-2", "evidence-2a", "evidence-2b"),
        )
    )
    with pytest.raises(EvidenceAmbiguityError, match="analysis_id"):
        resolve_evidence(EvidenceRequest("finding", "finding-shared"), repository)
    qualified = resolve_evidence(
        EvidenceRequest("finding", "finding-shared", limit=1, analysis_id="analysis-2"),
        repository,
    )
    assert qualified.records[0].evidence_id == "evidence-2a"
    assert qualified.selector["analysis_id"] == "analysis-2"
    assert qualified.dashboard_target["selectors"]["analysis_id"] == "analysis-2"
    assert qualified.next_cursor is not None
    with pytest.raises(ValueError, match="scope"):
        resolve_evidence(
            EvidenceRequest(
                "finding",
                "finding-shared",
                limit=1,
                cursor=qualified.next_cursor,
                analysis_id="analysis-1",
            ),
            repository,
        )
