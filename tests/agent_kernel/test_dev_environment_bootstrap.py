from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from scripts import bootstrap_dev_environment as bootstrap


def _write_project(
    root: Path,
    *,
    scalene: str = "scalene==2.3.0",
    locked: bool = False,
    extra_dev: tuple[str, ...] = (),
) -> None:
    root.mkdir()
    requirements = ('  "pytest>=8.0",', *(f'  "{item}",' for item in extra_dev))
    (root / "pyproject.toml").write_text(
        "\n".join(
            (
                "[project]",
                'name = "synthetic-project"',
                'version = "0.0.0"',
                "",
                "[project.optional-dependencies]",
                "dev = [",
                *requirements,
                f'  "{scalene}",',
                "]",
                "",
            )
        ),
        encoding="utf-8",
    )
    if locked:
        (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")


class _PythonEnvironment:
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        root: Path,
        *,
        installed: dict[str, str | None] | None = None,
        editable_source: Path | None = None,
        marker_environment: dict[str, str] | None = None,
    ) -> None:
        self.root = root
        self.installed = installed
        self.editable_source: Path | None = root if editable_source is None else editable_source
        self.marker_environment = marker_environment
        self.commands: list[tuple[str, ...]] = []
        self.uv = "/synthetic/bin/uv"
        if installed is not None and installed.get("scalene") is not None:
            scalene = root / ".venv" / "bin" / "scalene"
            scalene.parent.mkdir(parents=True, exist_ok=True)
            scalene.write_text("", encoding="utf-8")
        monkeypatch.setattr(
            bootstrap,
            "_which",
            lambda executable: self.uv if executable == "uv" else None,
        )
        monkeypatch.setattr(bootstrap, "_run", self.run)

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        stream: bool = False,
    ) -> bootstrap.CommandResult:
        del cwd, env, stream
        argv = tuple(str(part) for part in command)
        self.commands.append(argv)

        if argv == (self.uv, "--version"):
            return bootstrap.CommandResult(0, "uv 0.11.19\n", "")
        if argv[:2] == (self.uv, "venv"):
            python = self.root / ".venv" / "bin" / "python"
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("", encoding="utf-8")
            self.installed = {}
            return bootstrap.CommandResult(0, "", "")
        if argv[:3] == (self.uv, "pip", "install") or argv[:2] == (
            self.uv,
            "sync",
        ):
            self.installed = {"pytest": "8.4.2", "scalene": "2.3.0"}
            self.editable_source = self.root
            scalene = self.root / ".venv" / "bin" / "scalene"
            scalene.parent.mkdir(parents=True, exist_ok=True)
            scalene.write_text("", encoding="utf-8")
            return bootstrap.CommandResult(0, "", "")
        if argv[:3] == (self.uv, "pip", "check"):
            return bootstrap.CommandResult(0, "Checked 2 packages\n", "")
        if "--_verify-python-contract" in argv:
            installed = self.installed
            if installed is None:
                return bootstrap.CommandResult(1, "", "environment missing")
            contract = bootstrap.read_dev_tool_contract(self.root / "pyproject.toml")
            problems = bootstrap._requirement_problems(
                contract.requirements,
                installed,
                environment=self.marker_environment,
            )
            editable_problem = bootstrap._editable_source_problem(
                self.editable_source,
                self.root,
            )
            if editable_problem is not None:
                problems.append(editable_problem)
            return bootstrap.CommandResult(
                0,
                json.dumps({"problems": problems, "versions": installed}),
                "",
            )
        if len(argv) == 2 and argv[0].endswith("/scalene") and argv[1] == "--version":
            return bootstrap.CommandResult(
                0,
                "Scalene version 2.3.0 (synthetic)\n",
                "",
            )
        if len(argv) == 2 and argv[1] == "--version":
            return bootstrap.CommandResult(0, "Python 3.13.2\n", "")
        raise AssertionError(f"unexpected command: {argv}")


def test_declared_dev_tools_require_an_exact_scalene_pin(tmp_path: Path) -> None:
    root = tmp_path / "project"
    _write_project(root)

    contract = bootstrap.read_dev_tool_contract(root / "pyproject.toml")

    assert contract.project_distribution == "synthetic-project"
    assert contract.requirements == ("pytest>=8.0", "scalene==2.3.0")
    assert contract.scalene_version == "2.3.0"


def test_python_310_fallback_reads_the_same_dev_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.setattr(bootstrap, "tomllib", None)

    contract = bootstrap.read_dev_tool_contract(root / "pyproject.toml")

    assert contract.requirements == ("pytest>=8.0", "scalene==2.3.0")
    assert contract.scalene_version == "2.3.0"


@pytest.mark.parametrize("requirement", ["scalene>=2.3.0", "pytest>=8.0"])
def test_declared_dev_tools_fail_when_scalene_is_not_exactly_pinned(
    tmp_path: Path,
    requirement: str,
) -> None:
    root = tmp_path / "project"
    _write_project(root, scalene=requirement)

    with pytest.raises(bootstrap.BootstrapError, match="exact scalene=="):
        bootstrap.read_dev_tool_contract(root / "pyproject.toml")


def test_fresh_python_environment_is_created_from_the_dev_extra(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    fake = _PythonEnvironment(monkeypatch, root)

    result = bootstrap.prepare_python_environment(root, check_only=False)

    assert result.changed is True
    assert result.scalene_version == "2.3.0"
    assert any(command[:2] == (fake.uv, "venv") for command in fake.commands)
    install = next(
        command for command in fake.commands if command[:3] == (fake.uv, "pip", "install")
    )
    assert install[-2:] == ("--editable", ".[dev]")
    assert "scalene==2.3.0" not in install


def test_stale_python_environment_is_repaired_without_recreating_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    fake = _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "8.4.2", "scalene": None},
    )

    result = bootstrap.prepare_python_environment(root, check_only=False)

    assert result.changed is True
    assert not any(command[:2] == (fake.uv, "venv") for command in fake.commands)
    assert sum(command[:3] == (fake.uv, "pip", "install") for command in fake.commands) == 1


def test_ready_python_environment_is_an_idempotent_noop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    fake = _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "8.4.2", "scalene": "2.3.0"},
    )

    result = bootstrap.prepare_python_environment(root, check_only=False)

    assert result.changed is False
    assert not any(command[:2] == (fake.uv, "venv") for command in fake.commands)
    assert not any(command[:3] == (fake.uv, "pip", "install") for command in fake.commands)


def test_check_only_reports_a_stale_environment_without_mutating_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    fake = _PythonEnvironment(monkeypatch, root)

    with pytest.raises(bootstrap.BootstrapError, match="Run the bootstrap without --check"):
        bootstrap.prepare_python_environment(root, check_only=True)

    assert not any(command[:2] == (fake.uv, "venv") for command in fake.commands)
    assert not any(command[:3] == (fake.uv, "pip", "install") for command in fake.commands)


def test_check_rejects_a_declared_lower_bound_violation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "7.9.0", "scalene": "2.3.0"},
    )

    with pytest.raises(bootstrap.BootstrapError, match="pytest>=8.0.*7.9.0"):
        bootstrap.prepare_python_environment(root, check_only=True)


def test_check_evaluates_active_pep508_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(
        root,
        extra_dev=("tomli>=2.0; python_version < '3.11'",),
    )
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "8.4.2", "scalene": "2.3.0", "tomli": None},
        marker_environment={"python_version": "3.10"},
    )

    with pytest.raises(bootstrap.BootstrapError, match="tomli>=2.0"):
        bootstrap.prepare_python_environment(root, check_only=True)


@pytest.mark.parametrize("editable_source_name", ["missing", "wrong"])
def test_check_rejects_missing_or_wrong_editable_project_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    editable_source_name: str,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    editable_source = None if editable_source_name == "missing" else tmp_path / "other-project"
    fake = _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "8.4.2", "scalene": "2.3.0"},
        editable_source=editable_source,
    )
    fake.editable_source = editable_source

    with pytest.raises(bootstrap.BootstrapError, match="editable project"):
        bootstrap.prepare_python_environment(root, check_only=True)


@pytest.mark.parametrize("check_only", [False, True])
def test_venv_symlink_outside_worktree_is_rejected_before_use_or_repair(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    check_only: bool,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    external = tmp_path / "external-venv"
    external.mkdir()
    (root / ".venv").symlink_to(external, target_is_directory=True)
    monkeypatch.setattr(
        bootstrap,
        "_which",
        lambda _executable: pytest.fail("unsafe venv must fail before tool discovery"),
    )

    with pytest.raises(bootstrap.BootstrapError, match=r"\.venv symlink"):
        bootstrap.prepare_python_environment(root, check_only=check_only)


def test_future_lockfile_uses_frozen_uv_sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root, locked=True)
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    fake = _PythonEnvironment(
        monkeypatch,
        root,
        installed={"pytest": "8.4.2", "scalene": None},
    )

    bootstrap.prepare_python_environment(root, check_only=False)

    assert (fake.uv, "sync", "--extra", "dev", "--frozen") in fake.commands
    assert not any(command[:3] == (fake.uv, "pip", "install") for command in fake.commands)


def test_missing_uv_fails_with_an_actionable_install_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _write_project(root)
    monkeypatch.setattr(bootstrap, "_which", lambda _executable: None)

    with pytest.raises(bootstrap.BootstrapError, match="uv is required"):
        bootstrap.prepare_python_environment(root, check_only=False)


def _write_gitnexus_tool_contract(root: Path) -> None:
    tool_root = root / "tools" / "gitnexus"
    tool_root.mkdir(parents=True)
    (tool_root / "package.json").write_text(
        json.dumps(
            {
                "name": "synthetic-gitnexus-tool",
                "version": "0.0.0",
                "private": True,
                "dependencies": {"gitnexus": "1.6.9"},
            }
        ),
        encoding="utf-8",
    )
    (tool_root / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "synthetic-gitnexus-tool",
                "version": "0.0.0",
                "lockfileVersion": 3,
                "packages": {
                    "": {"dependencies": {"gitnexus": "1.6.9"}},
                    "node_modules/gitnexus": {
                        "version": "1.6.9",
                        "integrity": "sha512-synthetic-integrity",
                    },
                },
            }
        ),
        encoding="utf-8",
    )


class _GitNexusEnvironment:
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        root: Path,
        *,
        indexed: bool,
        stale: bool,
        tool_present: bool = True,
        tool_version: str = "1.6.9",
        npm_present: bool = True,
        reported_root: Path | None = None,
        reported_branch: str = "fix/synthetic",
        current_branch: str | None = None,
        git_changed_files: int = 0,
        gitnexus_changed_files: int | None = None,
    ) -> None:
        self.root = root
        self.indexed = indexed
        self.stale = stale
        self.reported_root = reported_root or root
        self.reported_branch = reported_branch
        self.current_branch = current_branch or reported_branch
        self.git_changed_files = git_changed_files
        self.gitnexus_changed_files = (
            git_changed_files if gitnexus_changed_files is None else gitnexus_changed_files
        )
        self.commands: list[tuple[str, ...]] = []
        self.tool_version = tool_version
        self.node = "/synthetic/bin/node"
        self.git = "/synthetic/bin/git"
        self.npm = "/synthetic/bin/npm" if npm_present else None
        _write_gitnexus_tool_contract(root)
        if tool_present:
            self._create_tool()
        paths = {"git": self.git, "node": self.node, "npm": self.npm}
        monkeypatch.setattr(bootstrap, "_which", lambda executable: paths.get(executable))
        monkeypatch.setattr(bootstrap, "_run", self.run)
        monkeypatch.setattr(bootstrap, "_run_gitnexus_analyzer", self.run_analyzer)
        monkeypatch.setenv("XDG_CACHE_HOME", str(root / ".cache"))

    @property
    def entrypoint(self) -> Path:
        return (
            self.root
            / "tools"
            / "gitnexus"
            / "node_modules"
            / "gitnexus"
            / "dist"
            / "cli"
            / "index.js"
        )

    def _create_tool(self) -> None:
        self.entrypoint.parent.mkdir(parents=True, exist_ok=True)
        self.entrypoint.write_text("// synthetic pinned GitNexus\n", encoding="utf-8")

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        stream: bool = False,
    ) -> bootstrap.CommandResult:
        del cwd, stream
        argv = tuple(str(part) for part in command)
        self.commands.append(argv)

        if argv == (self.node, "--version"):
            return bootstrap.CommandResult(0, "v26.5.0\n", "")
        if self.npm is not None and argv[:2] == (self.npm, "ci"):
            assert env is not None
            assert env["npm_config_cache"].startswith(str(self.root / ".gitnexus"))
            assert env["SCARF_ANALYTICS"] == "false"
            self._create_tool()
            self.tool_version = "1.6.9"
            return bootstrap.CommandResult(0, "", "")
        if argv == (self.git, "branch", "--show-current"):
            return bootstrap.CommandResult(0, f"{self.current_branch}\n", "")
        if argv == (self.git, "rev-parse", "HEAD"):
            return bootstrap.CommandResult(0, "abcdef0123456789\n", "")
        if argv == (self.git, "rev-parse", "--verify", "origin/main"):
            return bootstrap.CommandResult(0, "1234567890abcdef\n", "")
        if argv == (
            self.git,
            "diff",
            "--name-only",
            "-z",
            "origin/main",
            "--",
        ):
            names = "".join(f"changed-{index:04d}.py\0" for index in range(self.git_changed_files))
            return bootstrap.CommandResult(0, names, "")
        if argv == (self.node, str(self.entrypoint), "--version"):
            return bootstrap.CommandResult(0, f"{self.tool_version}\n", "")
        if argv[-1] == "status":
            if not self.indexed:
                return bootstrap.CommandResult(0, "Repository not indexed.\n", "")
            state = "stale (re-run gitnexus analyze)" if self.stale else "up-to-date"
            return bootstrap.CommandResult(
                0,
                (
                    f"Repository: {self.reported_root.resolve()}\n"
                    f"Branch: {self.reported_branch}\n"
                    "Indexed commit: abcdef0\n"
                    "Current commit: abcdef0\n"
                    f"Status: {state}\n"
                ),
                "",
            )
        if "detect_changes" in argv:
            return bootstrap.CommandResult(
                0,
                (
                    f"Changes: {self.gitnexus_changed_files} files, 4 symbols\n"
                    "Affected processes: 0\n"
                    "Risk level: low\n"
                ),
                "",
            )
        raise AssertionError(f"unexpected command: {argv}")

    def run_analyzer(
        self,
        command: list[str],
        *,
        cwd: Path,
    ) -> bootstrap.CommandResult:
        del cwd
        argv = tuple(str(part) for part in command)
        self.commands.append(argv)
        self.indexed = True
        self.stale = False
        return bootstrap.CommandResult(0, "", "")


_GITNEXUS_FTS_CORRUPTION = (
    "FTS index 'file_fts' inconsistent: node offset 42 missing during delete. "
    "Drop and recreate FTS index."
)
_GITNEXUS_FTS_CORRUPTION_WITH_IS = (
    "[gitnexus diagnostic]\n"
    "FTS  index  'file_fts'\n"
    "is inconsistent :\n"
    "node offset 314 missing during delete.\n"
    "Drop and recreate FTS index.\n"
    "[diagnostic end]"
)


class _FailingGitNexusEnvironment(_GitNexusEnvironment):
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        root: Path,
        *,
        analysis_results: list[bootstrap.CommandResult],
        clean_result: bootstrap.CommandResult | None = None,
        indexed: bool = True,
        stale: bool = True,
    ) -> None:
        self.analysis_results = analysis_results.copy()
        self.clean_result = clean_result or bootstrap.CommandResult(0, "", "")
        super().__init__(monkeypatch, root, indexed=indexed, stale=stale)

    def run(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        stream: bool = False,
    ) -> bootstrap.CommandResult:
        argv = tuple(str(part) for part in command)
        if argv[-2:] == ("clean", "--force"):
            self.commands.append(argv)
            if self.clean_result.returncode == 0:
                self.indexed = False
                self.stale = False
            return self.clean_result
        return super().run(command, cwd=cwd, env=env, stream=stream)

    def run_analyzer(
        self,
        command: list[str],
        *,
        cwd: Path,
    ) -> bootstrap.CommandResult:
        del cwd
        argv = tuple(str(part) for part in command)
        self.commands.append(argv)
        if not self.analysis_results:
            raise AssertionError("unexpected extra GitNexus analysis")
        result = self.analysis_results.pop(0)
        if result.returncode == 0:
            self.indexed = True
            self.stale = False
        return result


class _AnalyzerProcess:
    def __init__(
        self,
        payload: bytes,
        *,
        returncode: int,
        events: list[str],
    ) -> None:
        self.stdout = io.BufferedReader(io.BytesIO(payload))
        self.returncode = returncode
        self.events = events

    def __enter__(self) -> _AnalyzerProcess:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        del exc_type, exc, traceback
        self.stdout.close()

    def wait(self) -> int:
        self.events.append("wait")
        return self.returncode


class _AnalyzerProgressSink(io.StringIO):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def write(self, text: str) -> int:
        self.events.append("write")
        return super().write(text)


@pytest.mark.parametrize(
    "diagnostic",
    [
        _GITNEXUS_FTS_CORRUPTION,
        _GITNEXUS_FTS_CORRUPTION_WITH_IS,
    ],
)
def test_gitnexus_fts_corruption_signature_accepts_supported_variants(
    diagnostic: str,
) -> None:
    result = bootstrap.CommandResult(1, "", diagnostic)

    assert bootstrap._is_recognized_gitnexus_fts_corruption(result) is True


@pytest.mark.parametrize(
    "diagnostic",
    [
        _GITNEXUS_FTS_CORRUPTION.replace("file_fts", "symbol_fts"),
        _GITNEXUS_FTS_CORRUPTION.replace("node offset 42", "node offset unknown"),
        _GITNEXUS_FTS_CORRUPTION.replace("missing during delete", "missing during insert"),
        _GITNEXUS_FTS_CORRUPTION.replace(
            "Drop and recreate FTS index.",
            "Rebuild the index.",
        ),
    ],
)
def test_gitnexus_fts_corruption_signature_rejects_near_misses(
    diagnostic: str,
) -> None:
    result = bootstrap.CommandResult(1, diagnostic, "")

    assert bootstrap._is_recognized_gitnexus_fts_corruption(result) is False


def test_gitnexus_analyzer_runner_streams_and_keeps_a_bounded_diagnostic_tail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    progress = "GitNexus indexing started\n"
    diagnostic = f"\n{_GITNEXUS_FTS_CORRUPTION_WITH_IS}\n"
    emitted = (
        progress
        + ("x" * (bootstrap._GITNEXUS_ANALYZER_TAIL_CHARS + 128))
        + diagnostic
    )
    events: list[str] = []
    process = _AnalyzerProcess(
        emitted.encode(),
        returncode=9,
        events=events,
    )
    command = ["/synthetic/bin/node", "gitnexus.js", "analyze", "--index-only"]

    def open_process(
        received_command: list[str],
        *,
        cwd: Path,
        stdout: int,
        stderr: int,
    ) -> _AnalyzerProcess:
        assert received_command == command
        assert cwd == tmp_path
        assert stdout == bootstrap.subprocess.PIPE
        assert stderr == bootstrap.subprocess.STDOUT
        return process

    sink = _AnalyzerProgressSink(events)
    monkeypatch.setattr(bootstrap.subprocess, "Popen", open_process)
    monkeypatch.setattr(bootstrap.sys, "stdout", sink)

    result = bootstrap._run_gitnexus_analyzer(command, cwd=tmp_path)

    assert sink.getvalue() == emitted
    assert events.index("write") < events.index("wait")
    assert result.returncode == 9
    assert result.stderr == ""
    assert result.stdout.startswith(bootstrap._GITNEXUS_ANALYZER_TRUNCATION_NOTICE)
    assert len(result.stdout) <= (
        bootstrap._GITNEXUS_ANALYZER_TAIL_CHARS
        + len(bootstrap._GITNEXUS_ANALYZER_TRUNCATION_NOTICE)
    )
    assert progress not in result.stdout
    assert diagnostic.strip() in result.stdout
    assert bootstrap._is_recognized_gitnexus_fts_corruption(result) is True


def test_ready_gitnexus_index_is_not_reanalyzed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(monkeypatch, root, indexed=True, stale=False)

    result = bootstrap.prepare_gitnexus(root, check_only=False)

    assert result.changed is False
    assert result.state == "up_to_date"
    assert not any("analyze" in command for command in fake.commands)
    assert not any("detect_changes" in command for command in fake.commands)


def test_gitnexus_rejects_registry_identity_for_another_worktree(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=True,
        stale=False,
        reported_root=tmp_path / "other-worktree",
    )

    with pytest.raises(bootstrap.BootstrapError, match="different worktree"):
        bootstrap.prepare_gitnexus(root, check_only=True)


def test_gitnexus_rejects_registry_identity_for_another_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=True,
        stale=False,
        reported_branch="fix/other-worktree",
        current_branch="fix/current-worktree",
    )

    with pytest.raises(bootstrap.BootstrapError, match="exact worktree branch"):
        bootstrap.prepare_gitnexus(root, check_only=True)


def test_gitnexus_compare_uses_exact_worktree_branch_and_remote_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=True,
        stale=False,
        reported_branch="fix/exact-worktree",
        git_changed_files=58,
        gitnexus_changed_files=57,
    )

    result = bootstrap.prepare_gitnexus(root, check_only=True)

    assert result.state == "up_to_date"
    detect = next(command for command in fake.commands if "detect_changes" in command)
    assert detect[detect.index("--base-ref") + 1] == "origin/main"
    assert detect[detect.index("--repo") + 1] == str(root.resolve())
    assert detect[detect.index("--branch") + 1] == "fix/exact-worktree"


def test_gitnexus_compare_rejects_more_files_than_git_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=True,
        stale=False,
        git_changed_files=58,
        gitnexus_changed_files=322,
    )

    with pytest.raises(bootstrap.BootstrapError, match="322 files.*58"):
        bootstrap.prepare_gitnexus(root, check_only=True)


def test_stale_gitnexus_index_is_reanalyzed_once_under_index_only_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(monkeypatch, root, indexed=True, stale=True)

    result = bootstrap.prepare_gitnexus(root, check_only=False)

    analyzes = [command for command in fake.commands if "analyze" in command]
    assert result.changed is True
    assert result.state == "up_to_date"
    assert len(analyzes) == 1
    assert analyzes[0][-2:] == ("analyze", "--index-only")
    assert "--embeddings" not in analyzes[0]
    assert "--force" not in analyzes[0]


def test_recognized_gitnexus_fts_corruption_cleans_and_retries_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _FailingGitNexusEnvironment(
        monkeypatch,
        root,
        analysis_results=[
            bootstrap.CommandResult(1, "", _GITNEXUS_FTS_CORRUPTION),
            bootstrap.CommandResult(0, "", ""),
        ],
    )

    result = bootstrap.prepare_gitnexus(root, check_only=False)

    recovery_commands = [
        command
        for command in fake.commands
        if "analyze" in command or "clean" in command
    ]
    assert result.changed is True
    assert result.state == "up_to_date"
    assert [command[-2:] for command in recovery_commands] == [
        ("analyze", "--index-only"),
        ("clean", "--force"),
        ("analyze", "--index-only"),
    ]
    assert recovery_commands[1] == (
        fake.node,
        str(fake.entrypoint),
        "clean",
        "--force",
    )


def test_unrelated_gitnexus_analysis_failure_does_not_clean_or_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _FailingGitNexusEnvironment(
        monkeypatch,
        root,
        analysis_results=[
            bootstrap.CommandResult(1, "", "unrelated analyzer failure"),
        ],
    )

    with pytest.raises(bootstrap.BootstrapError, match="unrelated analyzer failure"):
        bootstrap.prepare_gitnexus(root, check_only=False)

    assert sum("analyze" in command for command in fake.commands) == 1
    assert not any("clean" in command for command in fake.commands)


def test_gitnexus_fts_corruption_without_exact_identity_does_not_clean_or_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _FailingGitNexusEnvironment(
        monkeypatch,
        root,
        analysis_results=[
            bootstrap.CommandResult(1, "", _GITNEXUS_FTS_CORRUPTION),
        ],
        indexed=False,
        stale=False,
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match="FTS index 'file_fts' inconsistent",
    ):
        bootstrap.prepare_gitnexus(root, check_only=False)

    assert sum("analyze" in command for command in fake.commands) == 1
    assert not any("clean" in command for command in fake.commands)


def test_gitnexus_fts_recovery_clean_failure_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _FailingGitNexusEnvironment(
        monkeypatch,
        root,
        analysis_results=[
            bootstrap.CommandResult(1, "", _GITNEXUS_FTS_CORRUPTION),
        ],
        clean_result=bootstrap.CommandResult(1, "", "synthetic clean failure"),
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match="automatic clean failed.*synthetic clean failure",
    ):
        bootstrap.prepare_gitnexus(root, check_only=False)

    assert sum("analyze" in command for command in fake.commands) == 1
    assert sum("clean" in command for command in fake.commands) == 1


def test_gitnexus_fts_recovery_retry_failure_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _FailingGitNexusEnvironment(
        monkeypatch,
        root,
        analysis_results=[
            bootstrap.CommandResult(1, "", _GITNEXUS_FTS_CORRUPTION),
            bootstrap.CommandResult(1, "", "synthetic retry failure"),
        ],
    )

    with pytest.raises(
        bootstrap.BootstrapError,
        match="one allowed index-only retry failed.*synthetic retry failure",
    ):
        bootstrap.prepare_gitnexus(root, check_only=False)

    assert sum("analyze" in command for command in fake.commands) == 2
    assert sum("clean" in command for command in fake.commands) == 1


def test_gitnexus_rechecks_after_lock_and_skips_duplicate_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(monkeypatch, root, indexed=True, stale=True)
    original_run = fake.run
    status_calls = 0

    def complete_during_lock(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        stream: bool = False,
    ) -> bootstrap.CommandResult:
        nonlocal status_calls
        if command[-1] == "status":
            status_calls += 1
            if status_calls == 2:
                fake.stale = False
        return original_run(command, cwd=cwd, env=env, stream=stream)

    monkeypatch.setattr(bootstrap, "_run", complete_during_lock)

    result = bootstrap.prepare_gitnexus(root, check_only=False)

    assert result.changed is False
    assert status_calls >= 3
    assert not any("analyze" in command for command in fake.commands)


def test_gitnexus_lock_timeout_is_actionable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / ".cache"))
    monkeypatch.setattr(bootstrap, "_lock_file_nonblocking", lambda _handle: False)

    with (
        pytest.raises(bootstrap.BootstrapError, match="host-owned analysis finish"),
        bootstrap._gitnexus_analysis_lock(root, timeout_seconds=0.0),
    ):
        raise AssertionError("unreachable")


def test_missing_pinned_gitnexus_tool_repairs_then_immediately_passes_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=False,
        stale=False,
        tool_present=False,
    )

    result = bootstrap.prepare_gitnexus(root, check_only=False)
    mutation_count = len(
        [
            command
            for command in fake.commands
            if "analyze" in command or (fake.npm is not None and command[:2] == (fake.npm, "ci"))
        ]
    )
    checked = bootstrap.prepare_gitnexus(root, check_only=True)

    analyze = next(command for command in fake.commands if "analyze" in command)
    assert result.changed is True
    assert checked.changed is False
    assert analyze == (fake.node, str(fake.entrypoint), "analyze", "--index-only")
    assert fake.entrypoint.is_file()
    assert mutation_count == 2
    assert (
        sum(
            "analyze" in command or (fake.npm is not None and command[:2] == (fake.npm, "ci"))
            for command in fake.commands
        )
        == mutation_count
    )


def test_wrong_local_gitnexus_version_is_repaired_from_exact_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=True,
        stale=False,
        tool_version="1.7.0",
    )

    result = bootstrap.prepare_gitnexus(root, check_only=False)

    assert result.changed is True
    assert result.gitnexus_version == "1.6.9"
    assert (
        sum(fake.npm is not None and command[:2] == (fake.npm, "ci") for command in fake.commands)
        == 1
    )


def test_check_only_reports_missing_pinned_gitnexus_without_installing_or_analyzing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=False,
        stale=False,
        tool_present=False,
    )

    with pytest.raises(bootstrap.BootstrapError, match="pinned GitNexus"):
        bootstrap.prepare_gitnexus(root, check_only=True)

    assert not any(
        fake.npm is not None and command[:2] == (fake.npm, "ci") for command in fake.commands
    )
    assert not any("analyze" in command for command in fake.commands)


def test_gitnexus_repair_requires_local_npm_without_global_or_transient_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    fake = _GitNexusEnvironment(
        monkeypatch,
        root,
        indexed=False,
        stale=False,
        tool_present=False,
        npm_present=False,
    )

    with pytest.raises(bootstrap.BootstrapError, match="npm is required"):
        bootstrap.prepare_gitnexus(root, check_only=False)

    assert fake.commands == [(fake.node, "--version")]


def test_repository_gitnexus_tool_is_private_exact_and_integrity_locked() -> None:
    root = Path(__file__).resolve().parents[2]

    bootstrap._validate_gitnexus_tool_contract(root)
    package = json.loads((root / "tools" / "gitnexus" / "package.json").read_text())
    lock = json.loads((root / "tools" / "gitnexus" / "package-lock.json").read_text())

    assert package["private"] is True
    assert package["dependencies"] == {"gitnexus": "1.6.9"}
    assert lock["packages"][""]["dependencies"] == {"gitnexus": "1.6.9"}
    pinned = lock["packages"]["node_modules/gitnexus"]
    assert pinned["version"] == "1.6.9"
    assert pinned["integrity"].startswith("sha512-")


def test_repository_guidance_bootstraps_and_exposes_scalene_to_agent_perf() -> None:
    root = Path(__file__).resolve().parents[2]
    guidance = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "python3 scripts/bootstrap_dev_environment.py --check" in guidance
    assert 'PATH="$PWD/.venv/bin:$PATH" agent-perf' in guidance
    assert "Never install Scalene" in guidance
    assert "--base-ref origin/main" in guidance
    assert '--repo "$(pwd -P)"' in guidance
    assert 'base_ref: "main"' not in guidance
    assert "tools/gitnexus/node_modules/gitnexus/dist/cli/index.js" in guidance
    assert "npx gitnexus" not in guidance
    assert "node .gitnexus/run.cjs" not in guidance


def test_repository_root_validation_rejects_a_non_root_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requested = tmp_path / "repo" / "nested"
    requested.mkdir(parents=True)
    git = "/synthetic/bin/git"
    monkeypatch.setattr(
        bootstrap,
        "_which",
        lambda executable: git if executable == "git" else None,
    )
    monkeypatch.setattr(
        bootstrap,
        "_run",
        lambda _command, **_kwargs: bootstrap.CommandResult(
            0,
            f"{requested.parent}\n",
            "",
        ),
    )

    with pytest.raises(bootstrap.BootstrapError, match="not the exact Git worktree root"):
        bootstrap.validate_repository_root(requested)
