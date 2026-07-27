"""Shared application façade used by every kernel adapter."""

from .runtime import RuntimePaths, default_runtime_paths, discover_sources
from .service import KernelApplication, build_application

__all__ = [
    "KernelApplication",
    "RuntimePaths",
    "build_application",
    "default_runtime_paths",
    "discover_sources",
]
