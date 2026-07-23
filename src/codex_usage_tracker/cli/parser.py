"""Compatibility import for the canonical CLI parser."""

from __future__ import annotations

import argparse


def build_parser(language: str | None = None) -> argparse.ArgumentParser:
    """Return the canonical parser without creating an import cycle."""
    from codex_usage_tracker.interfaces.cli.parser import build_parser as canonical_parser

    return canonical_parser(language)


__all__ = ["build_parser"]
