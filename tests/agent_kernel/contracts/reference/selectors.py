from __future__ import annotations

import re
from typing import Any

_LOGICAL_ID = re.compile(r"^[a-z][a-z0-9-]*:v1:[a-z2-7]{52}$")


class SelectorContractError(ValueError):
    """Raised when a selector, alias, or publication snapshot is inconsistent."""


def format_selector(
    kind: str,
    logical_id: str,
    prefixes: dict[str, str],
    identity_kinds: dict[str, str],
) -> str:
    """Format a stable public selector from a logical identity."""

    if kind not in prefixes or kind not in identity_kinds:
        raise SelectorContractError(f"unknown selector kind {kind}")
    if _LOGICAL_ID.fullmatch(logical_id) is None:
        raise SelectorContractError("selector contains an invalid logical ID")
    if not logical_id.startswith(f"{identity_kinds[kind]}:v1:"):
        raise SelectorContractError("selector kind does not match logical ID kind")
    return f"{prefixes[kind]}:{logical_id}"


def parse_selector(
    selector: str,
    prefixes: dict[str, str],
    identity_kinds: dict[str, str],
) -> tuple[str, str]:
    """Parse a selector and validate the logical-ID kind contract."""

    prefix, separator, logical_id = selector.partition(":")
    if not separator:
        raise SelectorContractError("selector has no kind prefix")
    inverse = {value: key for key, value in prefixes.items()}
    if prefix not in inverse:
        raise SelectorContractError(f"unknown selector prefix {prefix}")
    kind = inverse[prefix]
    expected_kind = identity_kinds[kind]
    if _LOGICAL_ID.fullmatch(logical_id) is None:
        raise SelectorContractError("selector contains an invalid logical ID")
    if not logical_id.startswith(f"{expected_kind}:v1:"):
        raise SelectorContractError("selector kind does not match logical ID kind")
    return kind, logical_id


def resolve_alias(
    selector: str,
    aliases: dict[str, str],
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve an identity correction only when both selectors name one entity."""

    target = aliases.get(selector, selector)
    if selector not in entities or target not in entities:
        raise SelectorContractError("selector alias names an unknown entity")
    if entities[selector]["entity_key"] != entities[target]["entity_key"]:
        raise SelectorContractError("selector alias would join distinct entities")
    return {
        "requested_selector": selector,
        "resolved_selector": target,
        "alias_applied": target != selector,
        "entity_key": entities[target]["entity_key"],
    }


def validate_publication_snapshot(
    publication: dict[str, Any],
    rows: list[dict[str, Any]],
) -> str:
    """Ensure facts, coverage, and selectors come from one committed truth unit."""

    if publication.get("status") != "committed":
        raise SelectorContractError("publication is not committed")
    publication_id = publication["publication_id"]
    mismatches = [
        row for row in rows if row.get("publication_id") != publication_id
    ]
    if mismatches:
        raise SelectorContractError("snapshot mixes publication identities")
    return publication_id
