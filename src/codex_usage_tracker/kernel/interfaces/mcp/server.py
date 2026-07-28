"""Small stdlib JSON-RPC stdio server for the six kernel MCP tools."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, BinaryIO

from ... import __version__
from ...application import KernelApplication, build_application
from ..schema_catalog import validate_input
from .catalog import TOOL_SPECS

MAX_MESSAGE_BYTES = 1_048_576
MAX_MODEL_CONTENT_BYTES = 65_536
MAX_MODEL_ROWS_PER_RESULT = 25
PROTOCOL_VERSION = "2025-06-18"


class McpServer:
    def __init__(self, application: KernelApplication) -> None:
        self._application = application

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        has_id = "id" in message
        request_id = message.get("id")
        if message.get("jsonrpc") != "2.0" or (
            has_id
            and (
                isinstance(request_id, bool)
                or not isinstance(request_id, (str, int, type(None)))
            )
        ):
            return _error(request_id if has_id else None, -32600, "Invalid Request")
        method = message.get("method")
        if not isinstance(method, str):
            return _error(request_id, -32600, "Invalid Request")
        if not has_id:
            return None
        if method == "initialize":
            parameters = message.get("params")
            if not isinstance(parameters, dict):
                return _error(request_id, -32602, "Invalid params")
            return _result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "codex-usage-tracker",
                        "version": __version__,
                    },
                },
            )
        if method in {"ping", "tools/list"} and not isinstance(
            message.get("params", {}),
            dict,
        ):
            return _error(request_id, -32602, "Invalid params")
        if method == "ping":
            return _result(request_id, {})
        if method == "tools/list":
            return _result(
                request_id,
                {
                    "tools": [
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "inputSchema": spec.input_schema,
                        }
                        for spec in TOOL_SPECS
                    ]
                },
            )
        if method == "tools/call":
            return self._call(request_id, message.get("params"))
        return _error(request_id, -32601, "Method not found")

    def _call(self, request_id: Any, parameters: Any) -> dict[str, Any]:
        if not isinstance(parameters, dict):
            return _error(request_id, -32602, "Invalid params")
        name = parameters.get("name")
        arguments = parameters.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return _error(request_id, -32602, "Invalid params")
        try:
            validate_input(name, arguments)
            structured = self._application.dispatch(name, arguments)
            content = _model_content(name, structured)
        except sqlite3.Error:
            return _tool_error(request_id, "kernel cache is unavailable")
        except (OSError, RuntimeError, ValueError) as exc:
            return _tool_error(request_id, str(exc))
        if name == "usage_query":
            structured = {**structured, "model_summary": content}
        response = _result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": "Kernel result is available in structuredContent.",
                    }
                ],
                "structuredContent": structured,
                "isError": False,
            },
        )
        if len(_compact_json(response).encode()) > MAX_MESSAGE_BYTES:
            return _tool_error(
                request_id,
                "kernel response exceeds byte budget; lower request limits",
            )
        return response


def _tool_error(request_id: Any, message: str) -> dict[str, Any]:
    return _result(
        request_id,
        {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        },
    )


def _model_content(tool_name: str, structured: dict[str, Any]) -> str:
    if tool_name != "usage_query":
        return "Kernel result is available in structuredContent."
    raw_results = structured.get("results", [])
    results = [
        _project_query_result(result)
        for result in raw_results
        if isinstance(result, dict)
    ] if isinstance(raw_results, list) else []
    history = structured.get("history_coverage", {})
    projection = {
        "results": results,
        "history_coverage": _history_projection(history),
        "cache": structured.get("cache"),
    }
    guidance = structured.get("guidance")
    if isinstance(guidance, dict):
        projection["guidance"] = _guidance_projection(guidance)
    return _bounded_projection(projection, results)


def _project_query_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    raw_rows = raw_result.get("rows", [])
    rows = raw_rows if isinstance(raw_rows, list) else []
    raw_selectors = raw_result.get("evidence_selectors", [])
    selectors = raw_selectors if isinstance(raw_selectors, list) else []
    visible_rows = rows[:MAX_MODEL_ROWS_PER_RESULT]
    return {
        "rows": visible_rows,
        "evidence_selectors": selectors[: len(visible_rows)],
        **{
            key: raw_result.get(key)
            for key in (
                "dataset",
                "operation",
                "generation",
                "grade",
                "matched_count",
                "returned_count",
                "truncated",
            )
        },
        "model_rows_returned": len(visible_rows),
        "model_rows_truncated": len(rows) > len(visible_rows),
        "measure_coverage": _measure_coverage(raw_result),
    }


def _measure_coverage(raw_result: dict[str, Any]) -> dict[str, Any]:
    coverage = raw_result.get("coverage", {})
    measures = coverage.get("measures", {}) if isinstance(coverage, dict) else {}
    return {
        name: {
            key: metadata[key]
            for key in (
                "basis",
                "confidence",
                "coverage_percent",
                "limitations",
            )
            if key in metadata
        }
        for name, metadata in measures.items()
        if isinstance(name, str) and isinstance(metadata, dict)
    }


def _history_projection(history: Any) -> dict[str, Any]:
    if not isinstance(history, dict):
        return {}
    return {
        key: history.get(key)
        for key in (
            "preset",
            "complete_history",
            "cutoff_at",
            "coverage_revision",
        )
    }


def _guidance_projection(guidance: dict[str, Any]) -> dict[str, Any]:
    datasets = guidance.get("datasets", {})
    templates = guidance.get("templates", {})
    return {
        "schema": guidance.get("schema"),
        "limits": guidance.get("limits"),
        "filter_grammar": guidance.get("filter_grammar"),
        "datasets": {
            name: {
                key: metadata.get(key)
                for key in ("operations", "dimensions", "measures", "filters")
            }
            for name, metadata in datasets.items()
            if isinstance(name, str) and isinstance(metadata, dict)
        } if isinstance(datasets, dict) else {},
        "templates": {
            name: {
                key: metadata.get(key)
                for key in ("label", "evidence_policy", "parameters")
                if key in metadata
            }
            for name, metadata in templates.items()
            if isinstance(name, str) and isinstance(metadata, dict)
        } if isinstance(templates, dict) else {},
    }


def _bounded_projection(
    projection: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    encoded = _compact_json(projection)
    while len(encoded.encode()) > MAX_MODEL_CONTENT_BYTES:
        candidates = [result for result in results if result["rows"]]
        if not candidates:
            raise ValueError("usage query model projection exceeds byte budget")
        largest = max(candidates, key=lambda item: len(item["rows"]))
        largest["rows"].pop()
        selectors = largest["evidence_selectors"]
        if selectors:
            selectors.pop()
        largest["model_rows_returned"] = len(largest["rows"])
        largest["model_rows_truncated"] = True
        encoded = _compact_json(projection)
    return encoded


def _compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def run_stdio(
    application: KernelApplication | None = None,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: BinaryIO | None = None,
) -> None:
    server = McpServer(application or build_application())
    source = input_stream or sys.stdin.buffer
    destination = output_stream or sys.stdout.buffer
    for line in source:
        response: dict[str, Any] | None
        if len(line) > MAX_MESSAGE_BYTES:
            response = _error(None, -32600, "Message too large")
        else:
            try:
                payload = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                response = _error(None, -32700, "Parse error")
            else:
                response = (
                    server.handle(payload)
                    if isinstance(payload, dict)
                    else _error(None, -32600, "Invalid Request")
                )
        if response is None:
            continue
        destination.write(
            json.dumps(
                response,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            + b"\n"
        )
        destination.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(
    request_id: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
