# Persistent Dashboard Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a macOS LaunchAgent workflow that keeps the localhost dashboard available at `http://127.0.0.1:47821` across Codex tasks, crashes, and user logins.

**Architecture:** A focused `dashboard_service` module owns deterministic plist generation, local port checks, atomic managed-file updates, launchctl lifecycle calls, and health status. A thin CLI adapter exposes `dashboard-service install|status|uninstall`; the existing dashboard HTTP server remains unchanged and continues to enforce localhost/privacy controls.

**Tech Stack:** Python 3.10+, standard-library `argparse`, `plistlib`, `socket`, `subprocess`, `urllib.request`, macOS `launchctl`, pytest.

## Global Constraints

- Keep `serve-dashboard` backward-compatible, including its existing default port `8765`.
- The persistent service defaults to `127.0.0.1:47821` and offers no non-loopback host option.
- Use LaunchAgent label `com.codex-usage-tracker.dashboard` and plist path `~/Library/LaunchAgents/com.codex-usage-tracker.dashboard.plist`.
- Start with `--context-api explicit --no-refresh`, never `--open`, and never put credentials or raw usage content in the plist or service logs.
- Use the absolute install-time Python interpreter and separate `ProgramArguments`; never invoke launchctl through a shell string.
- Refuse unknown port owners and never silently select another port or kill an unknown process.
- Automated tests use temporary homes and fakes/disposable sockets; they never load the developer's real LaunchAgent.
- Keep existing untracked `.idea/` and `.playwright-cli/` paths untouched.

---

## File Structure

- Create `src/codex_usage_tracker/dashboard_service.py`: constants, status model, paths, plist construction, port/HTTP probes, and macOS lifecycle functions.
- Create `src/codex_usage_tracker/cli/dashboard_service.py`: argparse namespace adapter and concise human-readable output.
- Modify `src/codex_usage_tracker/cli/parser_data.py`: nested `dashboard-service` parser.
- Modify `src/codex_usage_tracker/cli/parser.py`: register the new parser builder.
- Modify `src/codex_usage_tracker/cli/main.py`: dispatch the new command.
- Modify `src/codex_usage_tracker/cli/help_i18n.py`: localize new help strings consistently with existing CLI behavior.
- Create `tests/cli/test_dashboard_service.py`: pure configuration, collision, lifecycle, parser, dispatch, and privacy tests.
- Modify `docs/install.md`, `docs/dashboard-guide.md`, and `docs/cli-reference.md`: document the stable service URL and lifecycle.
- Modify both `skills/codex-usage-tracker/SKILL.md` and `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`: prefer a healthy persistent service for dashboard-open requests while retaining the foreground fallback.

---

### Task 1: Deterministic LaunchAgent Configuration and Local Probes

**Files:**
- Create: `src/codex_usage_tracker/dashboard_service.py`
- Create: `tests/cli/test_dashboard_service.py`

**Interfaces:**
- Produces: `DEFAULT_SERVICE_PORT: int`, `SERVICE_LABEL: str`, `DashboardServicePaths`, `DashboardServiceStatus`, `service_paths(home: Path)`, `validate_service_port(port: int)`, `build_launch_agent(python: Path, home: Path, port: int)`, `port_is_available(port: int)`, and `dashboard_is_reachable(port: int)`.
- Consumes: standard-library types only.

- [ ] **Step 1: Write failing tests for paths, plist privacy, port validation, collision detection, and HTTP probing**

```python
from __future__ import annotations

import contextlib
import plistlib
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from codex_usage_tracker.dashboard_service import (
    DEFAULT_SERVICE_PORT,
    SERVICE_LABEL,
    build_launch_agent,
    dashboard_is_reachable,
    port_is_available,
    service_paths,
    validate_service_port,
)


def test_service_paths_stay_in_user_owned_locations(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)
    assert paths.plist == tmp_path / "Library/LaunchAgents/com.codex-usage-tracker.dashboard.plist"
    assert paths.stdout_log == tmp_path / ".codex-usage-tracker/logs/dashboard-service.stdout.log"
    assert paths.stderr_log == tmp_path / ".codex-usage-tracker/logs/dashboard-service.stderr.log"


def test_launch_agent_is_loopback_only_and_contains_no_content(tmp_path: Path) -> None:
    payload = build_launch_agent(
        python=Path("/opt/tracker/bin/python"),
        home=tmp_path,
        port=DEFAULT_SERVICE_PORT,
    )
    encoded = plistlib.dumps(payload).decode("utf-8")
    assert payload["Label"] == SERVICE_LABEL
    assert payload["ProgramArguments"] == [
        "/opt/tracker/bin/python", "-m", "codex_usage_tracker",
        "serve-dashboard", "--host", "127.0.0.1", "--port", "47821",
        "--context-api", "explicit", "--no-refresh",
    ]
    assert payload["RunAtLoad"] is True
    assert payload["KeepAlive"] is True
    assert "--open" not in encoded
    assert "prompt" not in encoded.lower()
    assert "assistant" not in encoded.lower()


@pytest.mark.parametrize("port", [0, 1, 1023, 65536])
def test_service_port_rejects_privileged_or_invalid_values(port: int) -> None:
    with pytest.raises(ValueError, match="1024 through 65535"):
        validate_service_port(port)


def test_port_check_detects_an_existing_listener() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        assert port_is_available(port) is False
    finally:
        listener.close()
    assert port_is_available(port) is True


def test_dashboard_probe_distinguishes_reachable_http_server() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Codex Usage Tracker")

        def log_message(self, *_: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert dashboard_is_reachable(server.server_port) is True
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py -q`

Expected: collection fails because `codex_usage_tracker.dashboard_service` does not exist.

- [ ] **Step 3: Implement the minimal deterministic configuration and probe API**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import socket
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

DEFAULT_SERVICE_PORT = 47821
SERVICE_HOST = "127.0.0.1"
SERVICE_LABEL = "com.codex-usage-tracker.dashboard"


@dataclass(frozen=True)
class DashboardServicePaths:
    plist: Path
    stdout_log: Path
    stderr_log: Path


@dataclass(frozen=True)
class DashboardServiceStatus:
    installed: bool
    loaded: bool
    reachable: bool
    port: int
    detail: str

    @property
    def url(self) -> str:
        return f"http://{SERVICE_HOST}:{self.port}"


def service_paths(home: Path) -> DashboardServicePaths:
    logs = home / ".codex-usage-tracker" / "logs"
    return DashboardServicePaths(
        plist=home / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist",
        stdout_log=logs / "dashboard-service.stdout.log",
        stderr_log=logs / "dashboard-service.stderr.log",
    )


def validate_service_port(port: int) -> int:
    if not 1024 <= port <= 65535:
        raise ValueError("dashboard service port must be 1024 through 65535")
    return port


def build_launch_agent(*, python: Path, home: Path, port: int) -> dict[str, Any]:
    paths = service_paths(home)
    return {
        "Label": SERVICE_LABEL,
        "ProgramArguments": [
            str(python), "-m", "codex_usage_tracker", "serve-dashboard",
            "--host", SERVICE_HOST, "--port", str(validate_service_port(port)),
            "--context-api", "explicit", "--no-refresh",
        ],
        "EnvironmentVariables": {"HOME": str(home)},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(paths.stdout_log),
        "StandardErrorPath": str(paths.stderr_log),
    }


def port_is_available(port: int) -> bool:
    validate_service_port(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        try:
            candidate.bind((SERVICE_HOST, port))
        except OSError:
            return False
    return True


def dashboard_is_reachable(port: int, *, timeout: float = 1.0) -> bool:
    try:
        with urlopen(f"http://{SERVICE_HOST}:{port}/", timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except (OSError, URLError):
        return False
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py -q`

Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add -- src/codex_usage_tracker/dashboard_service.py tests/cli/test_dashboard_service.py
git commit -m "feat: define persistent dashboard service"
```

---

### Task 2: Safe launchctl Lifecycle

**Files:**
- Modify: `src/codex_usage_tracker/dashboard_service.py`
- Modify: `tests/cli/test_dashboard_service.py`

**Interfaces:**
- Consumes: Task 1 constants, paths, plist builder, port check, and health probe.
- Produces: `install_dashboard_service`, `dashboard_service_status`, and `uninstall_dashboard_service`, each returning `DashboardServiceStatus` and using the exact keyword-only signatures in Step 3.

- [ ] **Step 1: Add failing lifecycle tests using a fake launchctl runner and temporary home**

Add tests that define a `FakeRunner` recording `list[str]` commands and returning `subprocess.CompletedProcess`. Assert these exact behaviors:

```python
import subprocess


class FakeRunner:
    def __init__(self, *, print_returncode: int = 1, bootstrap_returncode: int = 0) -> None:
        self.print_returncode = print_returncode
        self.bootstrap_returncode = bootstrap_returncode
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[1] == "print":
            return subprocess.CompletedProcess(command, self.print_returncode, "", "not loaded")
        if command[1] == "bootstrap":
            return subprocess.CompletedProcess(command, self.bootstrap_returncode, "", "bootstrap failed")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_install_writes_valid_plist_and_bootstraps_user_domain(tmp_path: Path) -> None:
    runner = FakeRunner()
    python = tmp_path / "python"
    python.touch()
    status = install_dashboard_service(
        home=tmp_path,
        python=python,
        port=47821,
        platform="darwin",
        uid=501,
        runner=runner,
        port_available=lambda _: True,
        reachable=lambda _: True,
    )
    payload = plistlib.loads(service_paths(tmp_path).plist.read_bytes())
    assert payload["Label"] == SERVICE_LABEL
    assert runner.commands[-2:] == [
        ["launchctl", "bootstrap", "gui/501", str(service_paths(tmp_path).plist)],
        ["launchctl", "kickstart", "-k", f"gui/501/{SERVICE_LABEL}"],
    ]
    assert status.installed and status.loaded and status.reachable


def test_install_refuses_unknown_port_owner_without_writing(tmp_path: Path) -> None:
    python = tmp_path / "python"
    python.touch()
    with pytest.raises(RuntimeError, match="47821 is already in use"):
        install_dashboard_service(
            home=tmp_path,
            python=python,
            port=47821,
            platform="darwin",
            uid=501,
            runner=FakeRunner(),
            port_available=lambda _: False,
            reachable=lambda _: False,
        )
    assert not service_paths(tmp_path).plist.exists()


def test_status_is_read_only_and_reports_loaded_but_unreachable(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_bytes(plistlib.dumps(build_launch_agent(
        python=Path("/opt/tracker/bin/python"), home=tmp_path, port=47821,
    )))
    runner = FakeRunner(print_returncode=0)
    status = dashboard_service_status(
        home=tmp_path, platform="darwin", uid=501, runner=runner,
        reachable=lambda _: False,
    )
    assert status == DashboardServiceStatus(True, True, False, 47821, "loaded but unreachable")
    assert runner.commands == [["launchctl", "print", f"gui/501/{SERVICE_LABEL}"]]


def test_uninstall_is_idempotent_and_removes_only_managed_plist(tmp_path: Path) -> None:
    paths = service_paths(tmp_path)
    paths.plist.parent.mkdir(parents=True)
    paths.plist.write_text("managed")
    unrelated = paths.plist.parent / "other.plist"
    unrelated.write_text("keep")
    runner = FakeRunner()
    status = uninstall_dashboard_service(
        home=tmp_path, platform="darwin", uid=501, runner=runner,
    )
    assert not paths.plist.exists()
    assert unrelated.read_text() == "keep"
    assert status.installed is False
```

Also cover non-darwin refusal, a missing interpreter, repeated install with an identical healthy plist returning without a restart, a changed managed plist being booted out before replacement, atomic restoration after bootstrap failure, and port extraction from an existing plist.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py -q`

Expected: failures report missing lifecycle functions.

- [ ] **Step 3: Implement the lifecycle with explicit injectable boundaries**

Use these exact keyword-only signatures and command shapes. The implementation body follows the helper algorithm immediately below rather than leaving stub bodies in source:

```python
Runner = Callable[..., subprocess.CompletedProcess[str]]

INSTALL_SIGNATURE = "install_dashboard_service(*, home: Path, python: Path, port: int = DEFAULT_SERVICE_PORT, platform: str = sys.platform, uid: int | None = None, runner: Runner = subprocess.run, port_available: Callable[[int], bool] = port_is_available, reachable: Callable[[int], bool] = dashboard_is_reachable) -> DashboardServiceStatus"
STATUS_SIGNATURE = "dashboard_service_status(*, home: Path, platform: str = sys.platform, uid: int | None = None, runner: Runner = subprocess.run, reachable: Callable[[int], bool] = dashboard_is_reachable) -> DashboardServiceStatus"
UNINSTALL_SIGNATURE = "uninstall_dashboard_service(*, home: Path, platform: str = sys.platform, uid: int | None = None, runner: Runner = subprocess.run) -> DashboardServiceStatus"
```

Implement small private helpers `_require_macos`, `_domain(uid)`, `_target(uid)`, `_run_launchctl`, `_read_installed_port`, and `_atomic_write_plist`. `runner` receives argument arrays, `check=False`, `capture_output=True`, and `text=True`. Treat `launchctl print gui/<uid>/<label>` return code zero as loaded. For a changed managed config, boot out `gui/<uid>/<label>`, verify the new target port is free, atomically replace the plist, bootstrap it, then kickstart it. Preserve previous bytes and restore/re-bootstrap them if bootstrap fails. Never call `kill`, `pkill`, or inspect raw session logs.

- [ ] **Step 4: Run lifecycle tests and verify GREEN**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py -q`

Expected: all Task 1 and Task 2 tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add -- src/codex_usage_tracker/dashboard_service.py tests/cli/test_dashboard_service.py
git commit -m "feat: manage dashboard launch agent lifecycle"
```

---

### Task 3: CLI Integration and Messages

**Files:**
- Create: `src/codex_usage_tracker/cli/dashboard_service.py`
- Modify: `src/codex_usage_tracker/cli/parser_data.py`
- Modify: `src/codex_usage_tracker/cli/parser.py`
- Modify: `src/codex_usage_tracker/cli/main.py`
- Modify: `src/codex_usage_tracker/cli/help_i18n.py`
- Modify: `tests/cli/test_dashboard_service.py`

**Interfaces:**
- Consumes: Task 2 lifecycle functions and `DashboardServiceStatus`.
- Produces: `_add_dashboard_service_parser` and `run_dashboard_service(args: argparse.Namespace) -> int` registered under top-level command `dashboard-service`.

- [ ] **Step 1: Add failing parser and dispatch tests**

```python
def test_dashboard_service_parser_defaults_install_port() -> None:
    args = build_parser("en").parse_args(["dashboard-service", "install"])
    assert args.command == "dashboard-service"
    assert args.service_action == "install"
    assert args.port == 47821


def test_dashboard_service_status_prints_stable_url(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli_dashboard_service,
        "dashboard_service_status",
        lambda **_: DashboardServiceStatus(True, True, True, 47821, "healthy"),
    )
    args = argparse.Namespace(service_action="status", port=47821)
    assert cli_dashboard_service.run_dashboard_service(args) == 0
    assert capsys.readouterr().out == (
        "Dashboard service is healthy at http://127.0.0.1:47821\n"
    )


def test_main_dispatches_dashboard_service(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(cli_main, "run_dashboard_service", lambda args: called.append(args) or 0)
    monkeypatch.setitem(cli_main._COMMAND_HANDLERS, "dashboard-service", cli_main.run_dashboard_service)
    monkeypatch.setattr(sys, "argv", ["codex-usage-tracker", "dashboard-service", "status"])
    assert cli_main._main() == 0
    assert called[0].service_action == "status"
```

Also assert `install --port 48123` forwards the override, `uninstall` does not accept `--port`, unhealthy status returns exit code 1, and help contains install/status/uninstall descriptions in English and localized CLI output remains valid.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py tests/cli/test_cli_help_i18n.py -q`

Expected: parser rejects `dashboard-service` and the CLI adapter import is missing.

- [ ] **Step 3: Implement parser registration, dispatch, and concise output**

Parser shape:

```python
def _add_dashboard_service_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    service = subparsers.add_parser("dashboard-service", help="Manage the persistent dashboard service")
    actions = service.add_subparsers(dest="service_action", required=True)
    install = actions.add_parser("install", help="Install and start the dashboard service")
    install.add_argument("--port", type=int, default=DEFAULT_SERVICE_PORT)
    actions.add_parser("status", help="Show dashboard service health")
    actions.add_parser("uninstall", help="Stop and remove the dashboard service")
```

CLI adapter shape:

```python
def run_dashboard_service(args: argparse.Namespace) -> int:
    home = Path.home()
    if args.service_action == "install":
        status = install_dashboard_service(home=home, python=Path(sys.executable), port=args.port)
        print(f"Dashboard service installed at {status.url}")
        return 0 if status.reachable else 1
    if args.service_action == "status":
        status = dashboard_service_status(home=home)
        if status.reachable:
            print(f"Dashboard service is healthy at {status.url}")
            return 0
        print(f"Dashboard service is {status.detail}; expected {status.url}")
        return 1
    status = uninstall_dashboard_service(home=home)
    print("Dashboard service uninstalled")
    return 0
```

Import and register `_add_dashboard_service_parser` in `build_parser`, and import/register `run_dashboard_service` in `_COMMAND_HANDLERS`. Add exact new help strings to the Chinese localization mapping, preserving English fallback behavior.

- [ ] **Step 4: Run CLI tests and verify GREEN**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py tests/cli/test_cli_help_i18n.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Run static checks for the new Python surface**

Run: `PATH=.venv/bin:$PATH python -m ruff check src/codex_usage_tracker/dashboard_service.py src/codex_usage_tracker/cli/dashboard_service.py tests/cli/test_dashboard_service.py`

Run: `PATH=.venv/bin:$PATH python -m mypy`

Expected: both commands pass with no errors.

- [ ] **Step 6: Commit Task 3**

```bash
git add -- src/codex_usage_tracker/cli/dashboard_service.py src/codex_usage_tracker/cli/parser_data.py src/codex_usage_tracker/cli/parser.py src/codex_usage_tracker/cli/main.py src/codex_usage_tracker/cli/help_i18n.py tests/cli/test_dashboard_service.py
git commit -m "feat: expose dashboard service commands"
```

---

### Task 4: Documentation and Bundled Skill

**Files:**
- Modify: `docs/install.md`
- Modify: `docs/dashboard-guide.md`
- Modify: `docs/cli-reference.md`
- Modify: `skills/codex-usage-tracker/SKILL.md`
- Modify: `src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`

**Interfaces:**
- Consumes: the exact Task 3 command names and `http://127.0.0.1:47821` default.
- Produces: user-facing setup, operation, fallback, and privacy guidance; synchronized packaged skill behavior.

- [ ] **Step 1: Update docs with exact lifecycle workflow**

Document this primary macOS flow in all relevant locations:

```text
codex-usage-tracker dashboard-service install
codex-usage-tracker dashboard-service status
open http://127.0.0.1:47821
codex-usage-tracker dashboard-service uninstall
```

State that the service starts at login, restarts after failure, stays localhost-only, does not open browser tabs, and can use `install --port PORT` when the default is occupied. Clarify that foreground `serve-dashboard --open` remains the cross-platform/on-demand fallback and retains port `8765`.

- [ ] **Step 2: Update both skill copies identically**

Change the dashboard-open fast path to check `codex-usage-tracker dashboard-service status` first on macOS. If healthy, open/report `http://127.0.0.1:47821`; otherwise use the existing `serve-dashboard --context-api explicit --open` fallback. Do not add repository inspection or raw-log access to the fast path.

- [ ] **Step 3: Verify documentation and packaged-skill consistency**

Run: `cmp skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md`

Expected: exit code 0.

Run: `PATH=.venv/bin:$PATH python scripts/check_release.py`

Run: `git diff --check`

Expected: both checks pass.

- [ ] **Step 4: Commit Task 4**

```bash
git add -- docs/install.md docs/dashboard-guide.md docs/cli-reference.md skills/codex-usage-tracker/SKILL.md src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/SKILL.md
git commit -m "docs: explain persistent dashboard service"
```

---

### Task 5: Full Verification and Local Installation

**Files:**
- No intended source edits; fix only failures caused by Tasks 1-4 and commit those fixes separately.
- Local managed state after checks: `~/Library/LaunchAgents/com.codex-usage-tracker.dashboard.plist` and `~/.codex-usage-tracker/logs/`.

**Interfaces:**
- Consumes: completed CLI and lifecycle implementation.
- Produces: verified branch plus a healthy user LaunchAgent at the fixed local URL.

- [ ] **Step 1: Run focused service and CLI regression tests**

Run: `PATH=.venv/bin:$PATH python -m pytest tests/cli/test_dashboard_service.py tests/cli/test_cli_dashboard.py tests/cli/test_cli_lifecycle.py tests/cli/test_cli_help_i18n.py -q`

Expected: all tests pass.

- [ ] **Step 2: Run the repository's full local CI gate**

```bash
PATH=.venv/bin:$PATH python -m ruff check .
PATH=.venv/bin:$PATH python -m mypy
PATH=.venv/bin:$PATH python -m pytest
PATH=.venv/bin:$PATH python -m pytest --cov=codex_usage_tracker --cov-report=term-missing
PATH=.venv/bin:$PATH python -m compileall src
for file in src/codex_usage_tracker/plugin_data/dashboard/dashboard*.js; do node --check "$file"; done
PATH=.venv/bin:$PATH python scripts/check_release.py
git diff --check
```

Expected: every command passes. If an unrelated pre-existing failure appears, record it exactly and do not broaden the patch.

- [ ] **Step 3: Build and validate package artifacts**

```bash
rm -rf dist build src/codex_usage_tracker.egg-info src/codex_usage_tracking.egg-info
PATH=.venv/bin:$PATH python -m build
PATH=.venv/bin:$PATH python -m twine check dist/*
PATH=.venv/bin:$PATH python scripts/check_release.py --dist
PATH=.venv/bin:$PATH python scripts/smoke_installed_package.py
```

Expected: build, twine, distribution inspection, and installed-package smoke checks pass. The cleanup is limited to generated build artifacts named by the repository's documented validation workflow.

- [ ] **Step 4: Review final Git state and privacy**

Run: `git status --short --branch`, `git diff --stat main...HEAD`, and `git diff main...HEAD`.

Expected: only the spec, plan, implementation, synthetic tests, docs, and synchronized skill assets are changed; no plist, logs, database, real prompts, session content, secrets, `.idea/`, or `.playwright-cli/` files are tracked.

- [ ] **Step 5: Install the service from the stable Codex workspace**

Run: `PATH=.venv/bin:$PATH .venv/bin/python -m codex_usage_tracker dashboard-service install`

Expected: `Dashboard service installed at http://127.0.0.1:47821` and exit code 0. This is an explicitly requested non-production local user-service mutation.

- [ ] **Step 6: Verify persistence and reachability**

Run: `PATH=.venv/bin:$PATH .venv/bin/python -m codex_usage_tracker dashboard-service status`

Expected: `Dashboard service is healthy at http://127.0.0.1:47821`.

Run: `/Users/Monsky/.codex/bin/codex-probe-local-url http://127.0.0.1:47821`

Expected: HTTP success from the Codex Usage Tracker dashboard.

- [ ] **Step 7: Report completion**

Report the fixed URL, branch, commits, validation results, any skipped gates, and the exact `status` and `uninstall` commands. Do not stop or remove the existing interactive process on port `8765`; it may exit naturally.
