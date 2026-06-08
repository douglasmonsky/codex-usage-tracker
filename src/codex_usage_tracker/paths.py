"""Shared filesystem defaults for local Codex usage tracking."""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path.home() / ".codex-usage-tracker"
DEFAULT_DB_PATH = APP_DIR / "usage.sqlite3"
DEFAULT_DASHBOARD_PATH = APP_DIR / "dashboard.html"
DEFAULT_SUPPORT_BUNDLE_PATH = APP_DIR / "support-bundle.json"
DEFAULT_PRICING_PATH = APP_DIR / "pricing.json"
DEFAULT_ALLOWANCE_PATH = APP_DIR / "allowance.json"
DEFAULT_RATE_CARD_PATH = APP_DIR / "rate-card.json"
DEFAULT_THRESHOLDS_PATH = APP_DIR / "thresholds.json"
DEFAULT_PROJECTS_PATH = APP_DIR / "projects.json"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CLAUDE_HOME = Path.home() / ".claude"
DEFAULT_PLUGIN_LINK = Path.home() / "plugins" / "codex-usage-tracker"
DEFAULT_MARKETPLACE_PATH = Path.home() / ".agents" / "plugins" / "marketplace.json"
