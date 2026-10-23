"""Bounded local worker IPC with cancellation; no input can select executable commands."""

import math
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from typing import Any

from unitytranslator.json_boundary import strict_json


def run_json_worker(
    command: Sequence[str],
    *,
    timeout: float,
    cancelled: Callable[[], bool],
    max_output: int = 32 * 1024 * 1024,
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
                output.seek(0)
                details = output.read(4096).decode("utf-8", errors="replace")
                raise ValueError(f"Source worker failed ({process.returncode}): {details}")
            output.seek(0)
            value = strict_json(output.read(max_output + 1))
            if not isinstance(value, dict):
                raise ValueError("Source worker returned an invalid result.")
            return value
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
