"""Check public Markdown links and the source/packaging guide layout offline."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

LANGUAGES = ("en", "tr", "de", "fr", "es", "pt", "ru", "zh")


def check(root: Path) -> tuple[int, int]:
    root = root.resolve()
    documents = [root / "README.md"]
    for folder in ("docs", "guide", "adapters"):
        documents.extend(
            path
            for path in (root / folder).rglob("*.md")
            if not {"obj", "bin"}.intersection(path.relative_to(root).parts)
        )
    errors = []
    links = 0
    for document in documents:
        # Ignore fenced examples; this check validates file destinations, not URL reachability.
        content = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.S)
        for destination in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content):
            destination = destination.strip()
            if destination.startswith("<"):
                destination = destination.split(">", 1)[0][1:]
            else:
                destination = destination.split(' "', 1)[0]
            parsed = urlsplit(destination)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (document.parent / unquote(parsed.path)).resolve()
            links += 1
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f"{document.relative_to(root)} -> {destination}")
    for code in LANGUAGES:
        if not (root / "guide" / (code + ".md")).is_file():
            errors.append("Missing user guide: " + code)
    if (root / "rehber").exists():
        errors.append("Obsolete user-guide directory remains")
    if errors:
        raise ValueError("Documentation check failed:\n" + "\n".join(errors))
    return len(documents), links


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    documents, links = check(root)
    print(f"{documents} Markdown files and {links} local links verified; eight guides present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
