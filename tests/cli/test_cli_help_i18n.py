from __future__ import annotations

import argparse

from codex_usage_tracker.cli.help_i18n import localize_parser_help, requested_cli_language
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
    compact_help = "".join(help_text.split())

    assert help_text.startswith("用法：codex-usage-tracker serve-dashboard")
    assert "生成并提供仪表盘前刷新SQLite索引" in compact_help
    assert "--no-refresh" in help_text
    assert "--context-api" in help_text


def test_chinese_help_translates_python_310_boolean_default_suffix() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_argument(
        "--refresh",
        help=(
            "Refresh the SQLite index before generating and serving the dashboard. "
            "This is the default; use --no-refresh to serve the cached index only. "
            "(default: %(default)s)"
        ),
    )

    localize_parser_help(parser, "zh-Hans")

    assert action.help == (
        "生成并提供仪表盘前刷新 SQLite 索引（默认行为）；使用 --no-refresh 可只提供缓存索引。"
        "（默认值：%(default)s）"
    )


def test_requested_cli_language_reads_flag_or_environment(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_USAGE_TRACKER_LANG", "zh-CN")
    assert requested_cli_language([]) == "zh-Hans"
    assert requested_cli_language(["--lang", "en", "summary"]) == "en"
    assert requested_cli_language(["--lang=zh", "summary"]) == "zh-Hans"
