"""Static command and package-resource catalogs for installed-package smoke tests."""

from __future__ import annotations

CLI_HELP_SUBCOMMANDS = [
    "setup",
    "status",
    "doctor",
    "refresh",
    "analyze",
    "query",
    "open",
    "export",
    "config",
    "service",
    "admin",
]

RESOURCE_PATHS = [
    "assets/icon.svg",
    "dashboard/react/index.html",
    "dashboard/react/assets/dashboard-react.js",
    "dashboard/react/assets/index.css",
    "dashboard/react/assets/HomePage.js",
    "dashboard/react/assets/ExplorePage.js",
    "dashboard/react/assets/EvidencePage.js",
    "dashboard/react/assets/UsageDrainPage.js",
    "dashboard/locales/en.json",
    "dashboard/locales/vi.json",
    "dashboard/locales/es.json",
    "dashboard/locales/fr.json",
    "dashboard/locales/de.json",
    "dashboard/locales/pt.json",
    "dashboard/locales/ja.json",
    "dashboard/locales/zh-Hans.json",
    "dashboard/locales/ko.json",
    "dashboard/locales/ru.json",
    "dashboard/locales/it.json",
    "dashboard/locales/ar.json",
    "docs/dashboard-guide.html",
    "docs/examples/token-waste-conversation.md",
    "docs/examples/remediation-conversation.md",
    "docs/assets/plugin-prompts.png",
    "docs/assets/plugin-thread-leaderboard.png",
    "rate_cards/codex-credit-rates.json",
    "skills/codex-usage-api/SKILL.md",
    "skills/codex-usage-tracker/SKILL.md",
    "skills/codex-usage-tracker/scripts/run_mcp.py",
]
