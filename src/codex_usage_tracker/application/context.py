"""Shared source freshness and accounting context for application services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from codex_usage_tracker.application.errors import RequestContextError
from codex_usage_tracker.application.protocols import Clock, PricingProvider, UsageRepository
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.contracts import AccountingContextV1, FreshnessV1, ScopeV1
from codex_usage_tracker.pricing.allowance_rate_card import (
    load_bundled_rate_card,
    parse_credit_rates,
)
from codex_usage_tracker.pricing.allowance_rate_card import (
    parse_aliases as parse_credit_aliases,
)
from codex_usage_tracker.pricing.config import PricingConfig, load_pricing_config
from codex_usage_tracker.store.api import (
    InvalidDatabasePathError,
    query_request_context_facts,
    query_status_context_facts,
)

_FRESHNESS_THRESHOLD_SECONDS = 300

if TYPE_CHECKING:
    from codex_usage_tracker.application.analyze import AnalysisRuntime
    from codex_usage_tracker.application.paths import ApplicationPaths


@dataclass(frozen=True)
class RequestContext:
    """Read-only facts shared by status, query, evidence, and analysis services."""

    source_revision: str | None
    freshness: FreshnessV1
    scope: ScopeV1
    physical_rows: int
    canonical_rows: int
    copied_rows_excluded: int
    pricing_coverage: float | None
    credit_coverage: float | None
    service_tier_coverage: float | None
    analysis_runtime: AnalysisRuntime | None = field(default=None, repr=False, compare=False)
    application_paths: ApplicationPaths | None = field(default=None, repr=False, compare=False)

    @property
    def accounting(self) -> AccountingContextV1:
        return AccountingContextV1(
            physical_rows=self.physical_rows,
            canonical_rows=self.canonical_rows,
            copied_rows_excluded=self.copied_rows_excluded,
            pricing_coverage=self.pricing_coverage,
            credit_coverage=self.credit_coverage,
            service_tier_coverage=self.service_tier_coverage,
            history_scope=self.scope.history,
            privacy_mode=self.scope.privacy_mode,
        )


def build_request_context(
    *,
    db_path: Path,
    pricing_path: Path,
    scope: RequestScope,
    prefer_materialized_active: bool = False,
    usage_repository: UsageRepository | None = None,
    pricing_provider: PricingProvider | None = None,
    clock: Clock | None = None,
    application_paths: ApplicationPaths | None = None,
) -> RequestContext:
    """Build bounded context without reports, database creation, or migrations."""
    scope_contract = scope.to_contract()
    if not db_path.exists() and not db_path.is_symlink():
        return _empty_context(scope_contract, application_paths=application_paths)
    if not db_path.is_file():
        raise RequestContextError(f"database path must be a regular file: {db_path}")

    pricing = (
        load_pricing_config(pricing_path)
        if pricing_provider is None
        else pricing_provider.load(pricing_path)
    )
    credit_card = (
        load_bundled_rate_card()
        if pricing_provider is None
        else pricing_provider.credit_rate_card()
    )
    try:
        if usage_repository is None:
            query_facts = (
                query_status_context_facts
                if prefer_materialized_active
                else query_request_context_facts
            )
            facts = query_facts(
                db_path=db_path,
                scope=scope.to_payload(),
                priced_models=_priced_model_names(pricing),
                credit_models=_credit_model_names(credit_card),
            )
        else:
            facts = usage_repository.request_context_facts(
                scope=scope.to_payload(),
                priced_models=_priced_model_names(pricing),
                credit_models=_credit_model_names(credit_card),
                prefer_materialized_active=prefer_materialized_active,
            )
    except InvalidDatabasePathError as exc:
        raise RequestContextError(str(exc)) from exc
    source_revision = _optional_string(facts.get("source_revision"))
    return RequestContext(
        source_revision=source_revision,
        freshness=_freshness(
            facts,
            source_revision,
            now=clock.now() if clock is not None else datetime.now(timezone.utc),
        ),
        scope=scope_contract,
        physical_rows=_int_value(facts["physical_rows"]),
        canonical_rows=_int_value(facts["canonical_rows"]),
        copied_rows_excluded=_int_value(facts["copied_rows_excluded"]),
        pricing_coverage=_optional_float(facts.get("pricing_coverage")),
        credit_coverage=_optional_float(facts.get("credit_coverage")),
        service_tier_coverage=_optional_float(facts.get("service_tier_coverage")),
        application_paths=application_paths,
    )


def _empty_context(
    scope: ScopeV1,
    *,
    application_paths: ApplicationPaths | None = None,
) -> RequestContext:
    freshness = FreshnessV1(
        latest_indexed_event_at=None,
        source_revision=None,
        refresh_completed_at=None,
        state="empty",
        reason="Usage database does not exist.",
        threshold_seconds=_FRESHNESS_THRESHOLD_SECONDS,
        recommended_refresh_action="usage_refresh",
    )
    return RequestContext(
        source_revision=None,
        freshness=freshness,
        scope=scope,
        physical_rows=0,
        canonical_rows=0,
        copied_rows_excluded=0,
        pricing_coverage=None,
        credit_coverage=None,
        service_tier_coverage=None,
        application_paths=application_paths,
    )


def _freshness(
    facts: dict[str, object],
    source_revision: str | None,
    *,
    now: datetime,
) -> FreshnessV1:
    latest = _optional_string(facts.get("latest_indexed_event_at"))
    refreshed = _optional_string(facts.get("refresh_completed_at"))
    if _int_value(facts["canonical_rows"]) == 0:
        state = "empty"
        reason = "The selected scope contains no canonical usage rows."
    else:
        age = _age_seconds(refreshed or latest, now=now)
        if age is None:
            state = "unknown"
            reason = "The index has no parseable freshness timestamp."
        elif age <= _FRESHNESS_THRESHOLD_SECONDS:
            state = "fresh"
            reason = "The usage index is within the freshness threshold."
        else:
            state = "stale"
            reason = "The usage index is older than the freshness threshold."
    return FreshnessV1(
        latest_indexed_event_at=latest,
        source_revision=source_revision,
        refresh_completed_at=refreshed,
        state=state,
        reason=reason,
        threshold_seconds=_FRESHNESS_THRESHOLD_SECONDS,
        recommended_refresh_action=None if state == "fresh" else "usage_refresh",
    )


def _age_seconds(value: str | None, *, now: datetime) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (now - parsed).total_seconds())


def _priced_model_names(pricing: PricingConfig) -> set[str]:
    models = set(pricing.models)
    for tier_models in (pricing.api_service_tiers or {}).values():
        models.update(tier_models)
    aliases = pricing.aliases or {}
    models.update(alias for alias, target in aliases.items() if target in models)
    return models


def _credit_model_names(card: dict[str, object]) -> set[str]:
    rates = parse_credit_rates(card.get("credit_rates", {}))
    aliases = parse_credit_aliases(card.get("aliases", {}))
    models = set(rates)
    models.update(alias for alias, target in aliases.items() if target.get("model") in rates)
    return models


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _int_value(value: object) -> int:
    return int(value) if isinstance(value, int | float | str) else 0
