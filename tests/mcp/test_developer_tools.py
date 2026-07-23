from __future__ import annotations

from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile

_DEVELOPER_ONLY_NAMES = {
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_visualization_suggest",
    "usage_visualization_render",
}


def test_developer_is_full_plus_only_explicit_developer_tools() -> None:
    full = {spec.name for spec in tools_for_profile("full")}
    developer = {spec.name for spec in tools_for_profile("developer")}

    assert developer == full | _DEVELOPER_ONLY_NAMES
    assert developer - full == _DEVELOPER_ONLY_NAMES


def test_developer_only_tools_are_explicitly_classified() -> None:
    specs = {spec.name: spec for spec in tools_for_profile("developer")}

    assert all(specs[name].minimum_profile == "developer" for name in _DEVELOPER_ONLY_NAMES)
