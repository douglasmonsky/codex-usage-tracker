"""Serve and verify dashboard entry points for the installed-package smoke."""

from __future__ import annotations

import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def smoke_served_dashboard(
    command: Path,
    global_args: list[str],
    codex_home: Path,
    env: dict[str, str],
    *,
    repo_root: Path,
) -> None:
    """Start the installed server and verify its React and rollback surfaces."""
    port = _unused_loopback_port()
    root_url = f"http://127.0.0.1:{port}"
    react_url = f"{root_url}/react-dashboard.html"
    removed_url = f"{root_url}/dashboard.html"
    process_env = dict(env)
    process_env["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        [
            str(command),
            *global_args,
            "serve-dashboard",
            "--codex-home",
            str(codex_home),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-refresh",
            "--context-api",
            "explicit",
        ],
        cwd=repo_root,
        env=process_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        react_html = _read_url_when_ready(react_url, process)
        root_status, root_headers, root_html = _read_url_without_redirect(f"{root_url}/")
        removed_status, removed_headers, removed_html = _read_url_without_redirect(removed_url)
        react_js = _read_url(
            f"{root_url}/codex-usage-tracker-assets/react/assets/dashboard-react.js"
        )
        react_css = _read_url(f"{root_url}/codex-usage-tracker-assets/react/assets/index.css")
    finally:
        process_output = _stop_process(process)

    _assert_dashboard_responses(
        react_url=react_url,
        process_output=process_output,
        react_html=react_html,
        root_status=root_status,
        root_headers=root_headers,
        root_html=root_html,
        removed_status=removed_status,
        removed_headers=removed_headers,
        removed_html=removed_html,
        react_js=react_js,
        react_css=react_css,
    )


def _assert_dashboard_responses(
    *,
    react_url: str,
    process_output: str,
    react_html: str,
    root_status: int,
    root_headers: object,
    root_html: str,
    removed_status: int,
    removed_headers: object,
    removed_html: str,
    react_js: str,
    react_css: str,
) -> None:
    if react_url not in process_output:
        raise SystemExit("serve-dashboard output did not include React dashboard URL")
    if 'id="usage-data"' not in react_html or '"api_token"' not in react_html:
        raise SystemExit("served React dashboard did not include live boot payload")
    if '"rows": []' not in react_html and '"rows":[]' not in react_html:
        raise SystemExit("served React dashboard boot payload should not embed aggregate rows")
    if '"limit_label": "All"' in react_html:
        raise SystemExit("served React dashboard should not default to an uncapped row request")
    if root_status != 302:
        raise SystemExit("served root route did not return the 0.25 migration redirect")
    if root_headers.get("Location") != "/react-dashboard.html":
        raise SystemExit("served root route did not redirect to the Evidence Console")
    if root_html:
        raise SystemExit("served root redirect unexpectedly included a response body")
    if removed_status != 410:
        raise SystemExit("removed static dashboard route did not return 410")
    if removed_headers.get("Location"):
        raise SystemExit("removed static dashboard route unexpectedly redirected")
    if "/react-dashboard.html" not in removed_html:
        raise SystemExit("removed static dashboard route omitted Evidence Console guidance")
    if '"rows"' in removed_html or "usage-data" in removed_html:
        raise SystemExit("removed static dashboard route leaked embedded usage data")
    if len(react_js) < 1000:
        raise SystemExit("served React JavaScript asset looked unexpectedly small")
    if "app-shell" not in react_css:
        raise SystemExit("served React CSS asset did not include dashboard shell styles")


def _read_url_when_ready(
    url: str, process: subprocess.Popen[str], timeout_seconds: float = 15.0
) -> str:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f"serve-dashboard exited before {url} became available")
        try:
            return _read_url(url)
        except Exception as exc:  # noqa: BLE001 - retry startup connection failures.
            last_error = exc
            time.sleep(0.2)
    raise SystemExit(f"timed out waiting for {url}: {last_error}")


def _read_url(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2) as response:
        return response.read().decode("utf-8")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _read_url_without_redirect(url: str) -> tuple[int, object, str]:
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(url, timeout=2)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode("utf-8")
    with response:
        return response.status, response.headers, response.read().decode("utf-8")


def _stop_process(process: subprocess.Popen[str]) -> str:
    if process.poll() is None:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
    else:
        output, _ = process.communicate(timeout=5)
    return output or ""


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
