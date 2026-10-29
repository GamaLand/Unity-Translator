"""Static views of the audited _ren.py block format; Python is never evaluated.

The behavior follows Ren'Py's MIT-licensed ren_py_to_rpy conversion. Original
characters and spans remain authoritative; see resources/renpy-source-NOTICE.txt.
"""

from dataclasses import dataclass

PYTHON_BLOCKS_V1 = "renpy-python-blocks-v1"
PYTHON_BLOCKS_V2 = "renpy-python-blocks-v2"


@dataclass(frozen=True)
class PythonSourceView:
    text: str
    original_lines: tuple[int, ...]
    converted_lines: tuple[int, ...]
    inserted_spaces: tuple[int, ...]
    ignored_lines: int

    def span(self, start: int, end: int, line: int) -> tuple[int, int]:
        index = line - 1
        delta = self.original_lines[index] - self.converted_lines[index]
        delta -= self.inserted_spaces[index]
        return start + delta, end + delta


def python_source_view(text: str) -> PythonSourceView:
    """Retain line mapping while applying only the fixed block-marker state machine."""
    physical = text.splitlines()
    segments = text.splitlines(keepends=True)
    output: list[str] = []
    original, converted, spaces = [], [], []
    input_offset = output_offset = ignored = indent = 0
    state = "before"
    for source, segment in zip(physical, segments, strict=True):
        original.append(input_offset)
        converted.append(output_offset)
        input_offset += len(segment)
        added = 0
        if state != "renpy" and source.startswith('"""renpy'):
            state, result = "renpy", ""
        elif state == "renpy" and source == '"""':
            state, result = "python", ""
        elif state == "renpy":
            result = source
            stripped = source.strip()
            if stripped and not stripped.startswith("#"):
                indent = len(source) - len(source.lstrip(" "))
                indent += 4 if stripped.endswith(":") else 0
        elif state == "python":
            added = indent
            result = " " * added + source
        else:
            result = ""
            ignored += bool(source.strip())
        output.append(result)
        spaces.append(added)
        output_offset += len(result) + 1
    if state == "before":
        raise ValueError('The _ren.py source has no """renpy block.')
    if state == "renpy":
        raise ValueError('The _ren.py source has an unterminated """renpy block.')
    return PythonSourceView("\n".join(output), tuple(original), tuple(converted),
                            tuple(spaces), ignored)


def source_order(name: str) -> str:
    """The engine sorts source basenames, including the _ren.py spelling."""
    if name.endswith("_ren.py"):
        return name[:-7]
    if name.endswith(".rpy"):
        return name[:-4]
    raise ValueError("Unsupported original Ren'Py source filename.")
