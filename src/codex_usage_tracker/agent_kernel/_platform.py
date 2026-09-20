"""Small cross-platform seams used by the local agent kernel."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def peak_rss_bytes() -> int:
    """Return this process's peak resident set size in bytes."""

    if os.name == "nt":
        return _windows_peak_rss_bytes()

    import resource

    value = int(
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # type: ignore[attr-defined]
    )
    return value if sys.platform == "darwin" else value * 1024


def _windows_peak_rss_bytes() -> int:
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = (
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        )

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(
        process,
        ctypes.byref(counters),
        counters.cb,
    ):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.PeakWorkingSetSize)


def is_owner_only_directory(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISDIR(info.st_mode) and _is_owner_only(path, info, 0o700)


def is_owner_only_file(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and _is_owner_only(path, info, 0o600)


def fsync_file(path: Path) -> None:
    flags = os.O_RDWR if os.name == "nt" else os.O_RDONLY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_owner_only(path: Path, info: os.stat_result, expected_mode: int) -> bool:
    if os.name == "nt":
        return _windows_owner_is_current_user(path)
    getuid = getattr(os, "getuid", None)
    return (
        getuid is not None
        and info.st_uid == getuid()
        and stat.S_IMODE(info.st_mode) == expected_mode
    )


def _windows_owner_is_current_user(path: Path) -> bool:
    """Verify Windows ownership by comparing security identifiers."""

    import ctypes
    from ctypes import wintypes

    owner = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.GetNamedSecurityInfoW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    )
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.EqualSid.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    advapi.EqualSid.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = (ctypes.c_void_p,)
    kernel.LocalFree.restype = ctypes.c_void_p
    result = advapi.GetNamedSecurityInfoW(
        str(path),
        1,
        0x00000001,
        ctypes.byref(owner),
        None,
        None,
        None,
        ctypes.byref(descriptor),
    )
    if result != 0 or not owner.value:
        return False
    try:
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            return False
        try:
            required = wintypes.DWORD()
            advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
            token_buffer = ctypes.create_string_buffer(required.value)
            if not advapi.GetTokenInformation(
                token,
                1,
                token_buffer,
                required,
                ctypes.byref(required),
            ):
                return False
            current_sid = ctypes.c_void_p.from_buffer(token_buffer).value
            return bool(current_sid and advapi.EqualSid(owner, current_sid))
        finally:
            kernel.CloseHandle(token)
    finally:
        kernel.LocalFree(descriptor)
