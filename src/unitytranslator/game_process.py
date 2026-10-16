"""Read-only Windows process inspection; never starts or stops a process."""

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from unitytranslator.filesystem import checked_path


@dataclass(frozen=True)
class ProcessImage:
    pid: int
    name: str
    image: Path | None


@dataclass(frozen=True)
class GameProcessStatus:
    status: Literal["closed", "running", "unknown"]
    running_pids: tuple[int, ...] = ()
    ambiguous_pids: tuple[int, ...] = ()
    reason: str = ""


def windows_process_snapshot() -> tuple[ProcessImage, ...]:
    if os.name != "nt":
        raise OSError("Windows process inspection unavailable")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Entry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot is None or snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Process snapshot failed")
    rows: list[ProcessImage] = []
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        success = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            if len(rows) >= 20_000:
                raise OSError("Process snapshot limit exceeded")
            image = None
            handle = kernel.OpenProcess(
                0x1000, False, entry.th32ProcessID
            )  # QUERY_LIMITED_INFORMATION
            if handle:
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(buffer))
                    if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                        image = Path(buffer.value)
                finally:
                    kernel.CloseHandle(handle)
            rows.append(ProcessImage(int(entry.th32ProcessID), str(entry.szExeFile), image))
            success = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if (
            ctypes.get_last_error() != 18
        ):  # Only ERROR_NO_MORE_FILES proves the process enumeration completed.
            raise OSError("Process enumeration incomplete")
        return tuple(rows)
    finally:
        kernel.CloseHandle(snapshot)


def classify_game_processes(
    game: Path, executable_names: set[str], snapshot: tuple[ProcessImage, ...]
) -> GameProcessStatus:
    game = checked_path(game)
    names = {name.casefold() for name in executable_names}
    if not names:
        return GameProcessStatus("unknown", reason="no_executable_identity")
    running = []
    ambiguous = []
    for process in snapshot:
        if process.image is None:
            if process.name.casefold() in names:
                ambiguous.append(process.pid)
            continue
        # An identically named EXE in another installation is not the selected game.
        image = process.image
        if not image.is_absolute():
            if process.name.casefold() in names:
                ambiguous.append(process.pid)
            continue
        try:
            image = checked_path(image)
        except (ValueError, OSError):
            if image.is_relative_to(game) or process.name.casefold() in names:
                ambiguous.append(process.pid)
            continue
        if image.is_relative_to(game):
            running.append(process.pid)
    status: Literal["closed", "running", "unknown"] = (
        "running" if running else "unknown" if ambiguous else "closed"
    )
    return GameProcessStatus(status, tuple(sorted(running)), tuple(sorted(ambiguous)))


def inspect_game_processes(game: Path) -> GameProcessStatus:
    try:
        game = checked_path(game)
        names = set()
        entries = 0
        for directory, subdirs, files in os.walk(game, followlinks=False):
            for name in (*subdirs, *files):
                path = checked_path(Path(directory) / name)
                entries += 1
                if entries > 100_000:
                    return GameProcessStatus("unknown", reason="game_entry_limit")
                if path.is_file() and path.suffix.casefold() == ".exe":
                    names.add(path.name)
        if not names:
            return GameProcessStatus("unknown", reason="no_executable_identity")
        return classify_game_processes(game, names, windows_process_snapshot())
    except (OSError, ValueError):
        return GameProcessStatus("unknown", reason="process_or_path_inspection_failed")
