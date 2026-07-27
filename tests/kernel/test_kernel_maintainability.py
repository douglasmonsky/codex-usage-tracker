from __future__ import annotations

from pathlib import Path

from scripts.check_kernel_maintainability import maintainability_failures


def test_kernel_maintainability_accepts_small_cohesive_module(tmp_path: Path) -> None:
    source_root = tmp_path / "kernel"
    source_root.mkdir()
    (source_root / "cohesive.py").write_text(
        "def answer() -> int:\n    return 42\n",
        encoding="utf-8",
    )

    assert maintainability_failures(source_root) == []


def test_kernel_maintainability_does_not_gate_on_file_length(tmp_path: Path) -> None:
    source_root = tmp_path / "kernel"
    source_root.mkdir()
    (source_root / "oversized.py").write_text(
        "\n".join(f"value_{index} = {index}" for index in range(601)),
        encoding="utf-8",
    )

    assert maintainability_failures(source_root) == []


def test_kernel_maintainability_accepts_c_block_with_b_module_budget(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "kernel"
    source_root.mkdir()
    (source_root / "dispatcher.py").write_text(
        "def choose(values):\n"
        "    result = 0\n"
        + "".join(
            f"    if values.get({index}):\n        result += {index}\n"
            for index in range(12)
        )
        + "    return result\n"
        + "".join(
            f"\ndef simple_{index}():\n    return {index}\n"
            for index in range(12)
        ),
        encoding="utf-8",
    )

    assert maintainability_failures(source_root) == []


def test_kernel_maintainability_rejects_worse_than_c_complexity(tmp_path: Path) -> None:
    source_root = tmp_path / "kernel"
    source_root.mkdir()
    (source_root / "complex.py").write_text(
        "def choose(values):\n"
        "    result = 0\n"
        + "".join(
            f"    if values.get({index}):\n        result += {index}\n"
            for index in range(24)
        )
        + "    return result\n",
        encoding="utf-8",
    )

    failures = maintainability_failures(source_root)

    assert any("rank of D" in failure or "rank of F" in failure for failure in failures)
