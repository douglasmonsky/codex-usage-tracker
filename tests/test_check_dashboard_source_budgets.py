from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_dashboard_source_budgets.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _write_source(root: Path, name: str, line_count: int) -> Path:
    path = root / "frontend" / "dashboard" / "src" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("const value = 1;\n" * line_count, encoding="utf-8")
    return path


def test_baseline_allows_existing_exception_and_blocks_growth(tmp_path: Path) -> None:
    path = _write_source(tmp_path, "large.ts", 501)
    written = _run(tmp_path, "--write-baseline")
    assert written.returncode == 0
    assert _run(tmp_path).returncode == 0

    path.write_text(path.read_text(encoding="utf-8") + "const next = 2;\n", encoding="utf-8")
    result = _run(tmp_path)
    assert result.returncode == 1
    assert "physical lines grew from 501 to 502" in result.stdout


def test_new_oversized_file_is_rejected(tmp_path: Path) -> None:
    assert _run(tmp_path, "--write-baseline").returncode == 0
    _write_source(tmp_path, "new-large.tsx", 501)

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "new oversized source file" in result.stdout


def test_improvement_requires_baseline_refresh(tmp_path: Path) -> None:
    path = _write_source(tmp_path, "large.ts", 501)
    assert _run(tmp_path, "--write-baseline").returncode == 0
    path.write_text("const value = 1;\n" * 499, encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 1
    assert "lines fell from 501 to 499" in result.stdout
    assert "refresh the baseline to lock in the improvement" in result.stdout
