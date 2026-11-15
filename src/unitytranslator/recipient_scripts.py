"""Build self-contained recipient installer scripts from bundled resources.

Each exported installer is one frozen script: the shared recipient core is inlined at a
single exact marker line, so installed copies and metadata folders never load a module
from elsewhere. Generation is deterministic and runs no PowerShell.
"""

from importlib.resources import files

CORE = "recipient-core.ps1"
MARKER = b"# UNITYTRANSLATOR-RECIPIENT-CORE"
# Entry scripts that carry the core themselves.
INLINED = frozenset({"patch-installer.ps1", "renpy-copy.ps1"})
# Dot-sourced by renpy-copy.ps1 and therefore uses the core inlined there.
DEPENDENT = frozenset({"renpy-additive.ps1"})


def _resource(name: str) -> bytes:
    return files("unitytranslator.resources").joinpath(name).read_bytes()


def recipient_core() -> bytes:
    core = _resource(CORE)
    if MARKER in core:
        raise ValueError("Unknown or invalid bundled installer script.")
    return core


def inline_core(script: bytes, core: bytes) -> bytes:
    """Replace the one marker line with the core, using that line's line ending."""
    lines = script.splitlines(keepends=True)
    hits = [index for index, line in enumerate(lines) if line.rstrip(b"\r\n") == MARKER]
    if len(hits) != 1 or script.count(MARKER) != 1:
        raise ValueError("Recipient installer core marker must appear exactly once.")
    if MARKER in core:
        raise ValueError("Unknown or invalid bundled installer script.")
    index = hits[0]
    newline = b"\r\n" if lines[index].endswith(b"\r\n") else b"\n"
    body = newline.join(core.splitlines()) + newline
    return b"".join([*lines[:index], body, *lines[index + 1 :]])


def installer_bytes(name: str) -> bytes:
    """Return the exact bytes that a package ships for one bundled installer script."""
    if name in INLINED:
        return inline_core(_resource(name), recipient_core())
    if name in DEPENDENT:
        script = _resource(name)
        if MARKER in script:
            raise ValueError("Unknown or invalid bundled installer script.")
        return script
    raise ValueError("Unknown or invalid bundled installer script.")
