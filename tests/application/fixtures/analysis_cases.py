from codex_usage_tracker.analytics.analysis_models import (
    ANALYSIS_GOALS,
    AnalysisGoal,
    AnalysisReportV2,
)
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.core.contracts import EvidenceV1, FindingV1


def synthetic_analysis_report(goal: AnalysisGoal, context: RequestContext) -> AnalysisReportV2:
    evidence_id = f"evidence-{goal}"
    return AnalysisReportV2(
        f"synthetic:{goal}:{context.source_revision}",
        goal,
        f"Synthetic {goal} result.",
        (
            FindingV1(
                f"finding-{goal}",
                "Synthetic supported finding",
                "observed",
                "low",
                "exact",
                "A synthetic canonical record supports this fixture.",
                {"tokens": 10},
                (evidence_id,),
                (),
            ),
        ),
        (
            EvidenceV1(
                evidence_id,
                "call",
                "Synthetic canonical call",
                {"record_id": f"canonical-{goal}"},
                {"tokens": 10},
                "codex-usage-tracker.query.v2",
                None,
            ),
        ),
        ("Synthetic exact fixture.",),
        (),
        f"synthetic.{goal}",
        "1.0.0",
        context.source_revision,
        context.accounting,
        (),
        (),
        ("overview",),
    )


ANALYSIS_CASES = tuple((goal, f"canonical-{goal}") for goal in ANALYSIS_GOALS)
