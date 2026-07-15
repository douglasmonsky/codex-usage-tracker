from __future__ import annotations

import argparse

from codex_usage_tracker.cli.help_i18n import requested_cli_language
from codex_usage_tracker.cli.parser import build_parser


def test_chinese_help_localizes_sections_commands_and_options() -> None:
    help_text = build_parser("zh-Hans").format_help()

    assert help_text.startswith("用法：codex-usage-tracker")
    assert "位置参数：" in help_text
    assert "选项：" in help_text
    assert "执行首次设置：安装插件、初始化定价、刷新索引并运行环境检查" in help_text
    assert "仪表盘初始语言" in help_text
    assert "setup" in help_text
    assert "--lang" in help_text


def test_chinese_subcommand_help_keeps_command_contracts() -> None:
    parser = build_parser("zh-Hans")
    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    help_text = subparsers_action.choices["serve-dashboard"].format_help()

    assert help_text.startswith("用法：codex-usage-tracker serve-dashboard")
    assert "生成并提供仪表盘前刷新 SQLite 索引" in help_text
    assert "--no-refresh" in help_text
    assert "--context-api" in help_text


def test_requested_cli_language_reads_flag_or_environment(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_USAGE_TRACKER_LANG", "zh-CN")
    assert requested_cli_language([]) == "zh-Hans"
    assert requested_cli_language(["--lang", "en", "summary"]) == "en"
    assert requested_cli_language(["--lang=zh", "summary"]) == "zh-Hans"
