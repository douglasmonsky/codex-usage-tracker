"""Human-facing CLI help localization without changing command contracts."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from codex_usage_tracker.core.i18n import normalize_language

_ZH_HANS = "zh-Hans"
_ARGPARSE_DEFAULT_SUFFIX = " (default: %(default)s)"
_ZH_HANS_DEFAULT_SUFFIX = "（默认值：%(default)s）"

_ZH_HANS_HELP: dict[str, str] = {
    "show this help message and exit": "显示此帮助信息并退出",
    "show program's version number and exit": "显示程序版本并退出",
    "Initial dashboard language. Accepts supported language codes and common aliases; defaults to CODEX_USAGE_TRACKER_LANG or en.": "仪表盘初始语言。可使用受支持的语言代码和常见别名；默认读取 CODEX_USAGE_TRACKER_LANG，未设置时使用英语。",
    "Project metadata display mode: normal keeps local labels, redacted hides raw paths and hashes unnamed projects, strict also hides branch, relative cwd, and tags.": "项目元数据展示模式：normal 保留本地标签；redacted 隐藏原始路径并哈希未命名项目；strict 还会隐藏分支、相对工作目录和标签。",
    "Python executable Codex should use for the MCP server.": "Codex 启动 MCP 服务器时使用的 Python 可执行文件。",
    "Replace an existing generated plugin wrapper or source-checkout symlink.": "替换现有的插件包装目录或源码检出符号链接。",
    "Fetch current pricing during setup instead of writing a local template.": "设置时获取当前定价，而不是写入本地模板。",
    "Include read-only repair suggestions for warning and failure checks.": "为警告和失败检查提供只读修复建议。",
    "Replace an existing generated plugin directory or source-checkout symlink.": "替换现有的插件目录或源码检出符号链接。",
    "Skip local content indexing and store aggregate usage rows only.": "跳过本地内容索引，只保存聚合用量记录。",
    "Rebuild aggregate usage rows without local content indexing.": "重建聚合用量记录，但不建立本地内容索引。",
    "Only include calls at or after this ISO date/time": "只包含此 ISO 日期/时间之后（含）的调用",
    "Only include calls at or before this ISO date/time": "只包含此 ISO 日期/时间之前（含）的调用",
    "Run slower full hypothesis evidence scans instead of quick routing checks.": "运行较慢的完整假设证据扫描，而不是快速路由检查。",
    "Also run the slower full usage_investigate dogfood paths instead of reusing action brief findings.": "同时运行较慢的完整 usage_investigate 自测流程，不复用行动摘要结论。",
    "Refresh active local usage before running the dogfood report.": "运行自测报告前刷新活动的本地用量。",
    "Write a compact Markdown summary next to summary.json.": "在 summary.json 旁写入精简的 Markdown 摘要。",
    "Confirm clearing local aggregate usage rows. Raw Codex logs are not touched.": "确认清除本地聚合用量记录；不会改动 Codex 原始日志。",
    "Convenience preset for common summaries": "常用摘要的快捷预设",
    "Maximum rows to return; use 0 for all": "最多返回的记录数；0 表示全部",
    "Accepted for consistency; query always returns JSON.": "为保持接口一致而接受；query 始终返回 JSON。",
    "Accepted for consistency; action-brief always returns JSON.": "为保持接口一致而接受；action-brief 始终返回 JSON。",
    "Maximum rows; use 0 for all": "最大记录数；0 表示全部",
    "Recompute and persist the overview snapshot before reading it.": "读取前重新计算并保存概览快照。",
    "Recompute and persist the tool-output snapshot before reading it.": "读取前重新计算并保存工具输出快照。",
    "Recompute and persist the command snapshot before reading it.": "读取前重新计算并保存命令快照。",
    "Recompute and persist the Git interaction snapshot before reading it.": "读取前重新计算并保存 Git 交互快照。",
    "Recompute and persist the file-read snapshot before reading it.": "读取前重新计算并保存文件读取快照。",
    "Recompute and persist the file-modification snapshot before reading it.": "读取前重新计算并保存文件修改快照。",
    "Recompute and persist the read-productivity snapshot before reading it.": "读取前重新计算并保存读取成效快照。",
    "Recompute and persist the concentration snapshot before reading it.": "读取前重新计算并保存集中度快照。",
    "Recompute and persist guided summary snapshot before reading it.": "读取前重新计算并保存引导式摘要快照。",
    "Recompute and persist the usage-drain snapshot before reading it.": "读取前重新计算并保存用量消耗快照。",
    "Maximum redacted context characters to return; use 0 for no character limit.": "最多返回的脱敏上下文字符数；0 表示不限制字符数。",
    "Maximum context entries to return; use 0 for all matching entries.": "最多返回的上下文条目数；0 表示返回全部匹配条目。",
    "Include redacted, size-limited tool output in the on-demand context.": "在按需上下文中包含经过脱敏和大小限制的工具输出。",
    "Include redacted compaction replacement history when a compaction event is present.": "存在压缩事件时，包含经过脱敏的压缩替换历史。",
    "Maximum calls to load; use 0 for all": "最多加载的调用数；0 表示全部",
    "Include archived session rows already present in the SQLite index.": "包含 SQLite 索引中已有的归档会话记录。",
    "Include archived sessions when refreshing and in the generated dashboard.": "刷新和生成仪表盘时包含归档会话。",
    "Refresh the SQLite index before generating the dashboard. This is the default; use --no-refresh to open the cached index only.": "生成仪表盘前刷新 SQLite 索引（默认行为）；使用 --no-refresh 可只打开缓存索引。",
    "Initial maximum calls to load; use 0 for all": "初始最多加载的调用数；0 表示全部",
    "Enable explicit per-row context loading or disable the context API.": "启用显式的逐记录上下文加载，或禁用上下文 API。",
    "Start with dashboard context loading off; it can be enabled from the local dashboard.": "启动时关闭仪表盘上下文加载；之后可在本地仪表盘中启用。",
    "Refresh the SQLite index before generating and serving the dashboard. This is the default; use --no-refresh to serve the cached index only.": "生成并提供仪表盘前刷新 SQLite 索引（默认行为）；使用 --no-refresh 可只提供缓存索引。",
    "Accepted for API consistency; serve-dashboard still runs as a long-lived server.": "为保持 API 一致而接受；serve-dashboard 仍会作为常驻服务器运行。",
    "Convenience date window": "快捷日期范围",
    "Return the coverage report as JSON": "以 JSON 返回覆盖率报告",
    "Return source coverage report as JSON": "以 JSON 返回来源覆盖率报告",
    "Skip estimated prices for internal Codex model labels.": "跳过内部 Codex 模型标签的估算价格。",
    "Pasted usage text. Reads stdin when omitted.": "粘贴的用量文本；省略时从标准输入读取。",
    "Overwrite an invalid existing allowance config.": "覆盖现有的无效使用限额配置。",
    "Limit analysis to one observed allowance window kind.": "仅分析一种已观测的额度窗口。",
    "Maximum normalized observations to inspect. Use 0 for all.": "最多检查的标准化观测数；0 表示全部。",
    "Include archived Codex sessions.": "包含已归档的 Codex 会话。",
    "Validate and copy this JSON rate-card snapshot instead of the bundled one.": "验证并复制此 JSON 费率表快照，而不使用内置快照。",
    "Run first-time setup: plugin install, pricing init, refresh, and doctor": "执行首次设置：安装插件、初始化定价、刷新索引并运行环境检查",
    "Check local setup without writing files": "检查本地设置，不写入文件",
    "Register this installed package as a local Codex plugin": "将已安装的软件包注册为本地 Codex 插件",
    "Refresh the generated local Codex plugin wrapper for this installed package": "刷新此软件包生成的本地 Codex 插件包装目录",
    "Remove the generated local Codex plugin wrapper and marketplace entry": "移除生成的本地 Codex 插件包装目录和市场条目",
    "Scan Codex logs into SQLite": "扫描 Codex 日志并写入 SQLite",
    "Inspect one Codex JSONL log through the parser without writing to SQLite": "使用解析器检查一个 Codex JSONL 日志，不写入 SQLite",
    "Clear aggregate rows and rescan local Codex logs": "清除聚合记录并重新扫描本地 Codex 日志",
    "Run repeatable local dogfood checks for agentic MCP investigation reports": "针对智能体 MCP 调查报告运行可重复的本地自测",
    "Clear tracker-owned aggregate rows and refresh metadata": "清除跟踪器管理的聚合记录并刷新元数据",
    "Show aggregate usage summary": "显示聚合用量摘要",
    "Return stable JSON aggregate usage rows with filters": "按筛选条件返回稳定格式的 JSON 聚合用量记录",
    "Rank aggregate usage rows and threads by action recommendation severity": "按行动建议严重程度排列聚合用量记录和线程",
    "Build compact aggregate remediation brief for usage-waste investigations": "为用量浪费调查生成精简的聚合改进摘要",
    "Inspect aggregate diagnostic facts and their associated token costs": "检查聚合诊断事实及其关联token成本",
    "Show one session's usage": "显示一个会话的用量",
    "Load raw logged context for one usage record on demand": "按需加载一条用量记录的原始日志上下文",
    "Generate static dashboard": "生成静态仪表盘",
    "Generate the default dashboard and open it": "生成并打开默认仪表盘",
    "Serve dashboard with lazy localhost context loading": "启动仪表盘服务，并按需从本机加载上下文",
    "Manage the local dashboard service": "管理本地仪表盘服务",
    "Manage the persistent dashboard service": "管理常驻仪表盘服务",
    "Install and start the dashboard service": "安装并启动常驻仪表盘服务",
    "Show dashboard service health": "显示常驻仪表盘服务状态",
    "Stop and remove the dashboard service": "停止并移除常驻仪表盘服务",
    "Persistent dashboard port": "常驻仪表盘端口",
    "Show copied clone usage rows excluded from billable totals": "显示已从计费汇总中排除的克隆复制记录",
    "Show largest last-call usage rows": "显示末次调用用量最大的记录",
    "Show priced, estimated, and unpriced token coverage": "显示已定价、估算和未定价token的覆盖情况",
    "Show source provenance and parser coverage": "显示数据来源和解析器覆盖情况",
    "Export aggregate usage CSV": "导出聚合用量 CSV",
    "Write a local pricing template": "写入本地定价模板",
    "Fetch OpenAI text-token pricing into the local config": "获取 OpenAI 文本token定价并写入本地配置",
    "Copy the current local pricing config to a reproducible report snapshot": "将当前本地定价配置复制为可复现的报告快照",
    "Write a local template for optional Codex allowance windows": "写入可选 Codex 额度窗口的本地模板",
    "Update allowance windows from pasted Codex /status or usage text": "根据粘贴的 Codex /status 或用量文本更新额度窗口",
    "Return normalized observed Codex allowance history": "返回标准化的 Codex 额度观测历史",
    "Diagnose observed allowance movement against local credit estimates": "结合本地点数估算诊断已观测的额度变化",
    "Build strict-privacy allowance evidence bundle for manual sharing": "生成可手动分享的严格隐私额度证据包",
    "Write the bundled or supplied Codex credit rate-card snapshot locally": "在本地写入内置或指定的 Codex 点数费率表快照",
    "Write a local template for dashboard recommendation thresholds": "写入仪表盘建议阈值的本地模板",
    "Write a local template for project aliases, ignored paths, and tags": "写入项目别名、忽略路径和标签的本地模板",
    "Write a privacy-preserving diagnostic bundle for support": "写入保护隐私的支持诊断包",
}


class ChineseArgumentParser(argparse.ArgumentParser):
    """Argument parser with Simplified Chinese argparse section labels."""

    def format_help(self) -> str:
        return _translate_argparse_sections(super().format_help())

    def format_usage(self) -> str:
        return _translate_argparse_sections(super().format_usage())


def requested_cli_language(argv: Sequence[str]) -> str:
    """Read the global language before argparse renders help or errors."""

    for index, argument in enumerate(argv):
        if argument.startswith("--lang="):
            return normalize_language(argument.partition("=")[2])
        if argument == "--lang" and index + 1 < len(argv):
            return normalize_language(argv[index + 1])
    return normalize_language()


def argument_parser_class(language: str | None) -> type[argparse.ArgumentParser]:
    return ChineseArgumentParser if normalize_language(language) == _ZH_HANS else argparse.ArgumentParser


def localize_parser_help(parser: argparse.ArgumentParser, language: str | None) -> None:
    """Translate parser descriptions and help strings in place for human output."""

    if normalize_language(language) != _ZH_HANS:
        return
    parser.description = _translate(parser.description)
    parser.epilog = _translate(parser.epilog)
    for action in parser._actions:
        if isinstance(action.help, str):
            action.help = _translate(action.help)
        if isinstance(action, argparse._SubParsersAction):
            for choice_action in action._choices_actions:
                if isinstance(choice_action.help, str):
                    choice_action.help = _translate(choice_action.help)
            for child in action.choices.values():
                localize_parser_help(child, language)


def localized_cli_error_prefix(language: str | None) -> str:
    return "错误" if normalize_language(language) == _ZH_HANS else "Error"


def _translate(value: str | None) -> str | None:
    if value is None:
        return None
    if value.endswith(_ARGPARSE_DEFAULT_SUFFIX):
        base_value = value[: -len(_ARGPARSE_DEFAULT_SUFFIX)]
        translated = _ZH_HANS_HELP.get(base_value)
        if translated is not None:
            return translated + _ZH_HANS_DEFAULT_SUFFIX
    return _ZH_HANS_HELP.get(value, value)


def _translate_argparse_sections(value: str) -> str:
    replacements = {
        "usage: ": "用法：",
        "positional arguments:\n": "位置参数：\n",
        "options:\n": "选项：\n",
    }
    for source, translated in replacements.items():
        value = value.replace(source, translated)
    return value
