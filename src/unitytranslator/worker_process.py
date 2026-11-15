"""Bounded local worker IPC with cancellation; no input can select executable commands."""

import math
import os
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Callable, Sequence
from typing import IO, Any

from unitytranslator.diagnostics import Diagnostic
from unitytranslator.json_boundary import strict_json


def run_json_worker(
    command: Sequence[str],
    *,
    timeout: float,
    cancelled: Callable[[], bool],
    max_output: int = 32 * 1024 * 1024,
    stream_report: bool = False,
) -> dict[str, Any]:
    """The command is constructed exclusively by bundled reader implementations."""
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("Worker timeout must be between zero and 120 seconds.")
    if cancelled():
        raise ValueError("Source extraction was cancelled.")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancelled():
                    raise ValueError("Source extraction was cancelled.")
                if time.monotonic() > deadline:
                    raise ValueError("Source worker exceeded its time limit.")
                if (
                    os.fstat(output.fileno()).st_size > max_output
                    or os.fstat(errors.fileno()).st_size > 1024 * 1024
                ):
                    raise ValueError("Source worker exceeded its IPC size limit.")
                time.sleep(0.05)
            if os.fstat(output.fileno()).st_size > max_output:
                raise ValueError("Source worker exceeded its IPC size limit.")
            if process.returncode:
                raise Diagnostic(
                    "Source worker failed ({p0}): {p1}",
                    p0=process.returncode, p1=failure_summary(output, errors),
                )
            output.seek(0)
            if stream_report:
                from unitytranslator.report_stream import read_report

                def interrupted() -> bool:
                    if time.monotonic() > deadline:
                        raise ValueError("Source worker exceeded its time limit.")
                    return cancelled()

                return read_report(output, cancelled=interrupted, max_bytes=max_output)
            value = strict_json(output.read(max_output + 1))
            if not isinstance(value, dict):
                raise ValueError("Source worker returned an invalid result.")
            return value
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


SUMMARY_CHARACTERS = 300


def _line(raw: str | bytes) -> str:
    """One printable line; worker text is untrusted diagnostic data, never markup."""
    decoded = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    # Category C includes control, format (bidi) and lone surrogate characters.
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in decoded)
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_CHARACTERS else text[:SUMMARY_CHARACTERS - 3] + "..."


def failure_summary(output: IO[bytes], errors: IO[bytes]) -> str:
    """Bounded failure details: the worker's fatal record and the last stderr line."""
    parts = []
    output.seek(0)
    # A 1,024-character fatal message is at most 12 KiB as ASCII-escaped JSON.
    head = output.read(16 * 1024)
    record = None
    # Earlier lines (library warnings) must not hide the worker's fatal record.
    for candidate in (head, *reversed(head.splitlines())):
        try:
            value = strict_json(candidate)
        except (ValueError, RecursionError):
            continue
        if isinstance(value, dict) and isinstance(value.get("fatal"), str):
            record = value
            break
    if record is not None:
        message = record.get("message")
        parts.append(_line(record["fatal"] + (
            ": " + message if isinstance(message, str) and message else ""
        )))
    elif head.strip():
        parts.append("output: " + _line(head.strip().splitlines()[0]))
    size = os.fstat(errors.fileno()).st_size
    errors.seek(max(0, size - 4096))
    lines = [line for line in errors.read(4096).splitlines() if line.strip()]
    if lines:
        parts.append("stderr: " + _line(lines[-1]))
    return "; ".join(parts) or "no diagnostic output"
