"""Storage-independent domain primitives for the agent kernel."""

from .identity import (
    IdentityCollisionError,
    IdentityContractError,
    canonical_cbor,
    semantic_id,
)
from .measurements import (
    MeasurementValueError,
    validate_nonnegative_int64,
    validate_nonnegative_measurement,
)
from .models import (
    AccountingSummary,
    ConfiguredProducer,
    ConfiguredSource,
    LifecycleFold,
    LifecycleTransition,
    MeasurementAggregate,
    ModelCallTokens,
    SourceManifestation,
    SourceOccurrence,
)
from .time import (
    INT64_MAX,
    INT64_MIN,
    TimeValueError,
    validate_utc_microseconds,
)

__all__ = [
    "INT64_MAX",
    "INT64_MIN",
    "AccountingSummary",
    "ConfiguredProducer",
    "ConfiguredSource",
    "IdentityCollisionError",
    "IdentityContractError",
    "LifecycleFold",
    "LifecycleTransition",
    "MeasurementAggregate",
    "MeasurementValueError",
    "ModelCallTokens",
    "SourceManifestation",
    "SourceOccurrence",
    "TimeValueError",
    "canonical_cbor",
    "semantic_id",
    "validate_nonnegative_int64",
    "validate_nonnegative_measurement",
    "validate_utc_microseconds",
]
