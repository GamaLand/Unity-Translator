"""Salt okunur, süreçte izole Unity Font keşfi; oyun içi görünüm kanıtı değildir."""

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

from fontTools.ttLib import TTFont

from unitytranslator.filesystem import ProjectPaths, checked_path, hash_file
from unitytranslator.json_boundary import strict_json

REQUIRED = "çÇğĞıİöÖşŞüÜ"
MAX_FONT_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024


def embedded_coverage(data: bytes) -> dict:
    if not data:
        return {"status": "unknown", "reason": "no_embedded_font"}
    if len(data) > MAX_FONT_BYTES:
        return {"status": "unknown", "reason": "font_size_limit"}
    try:
        with TTFont(io.BytesIO(data), lazy=True, recalcBBoxes=False, recalcTimestamp=False) as font:
            cmap = font.getBestCmap()
            if cmap is None:
                return {"status": "unknown", "reason": "no_unicode_cmap"}
            present = "".join(
                char
                for char in REQUIRED
                if (glyph := cmap.get(ord(char))) is not None
                and glyph != ".notdef"
                and font.getGlyphID(glyph) > 0
            )
            return {
                "status": "complete" if present == REQUIRED else "incomplete",
                "present": present,
                "missing": "".join(char for char in REQUIRED if char not in present),
            }
    except Exception:
        # Dosyadan gelen hata metni ve font ikili verisi rapora taşınmaz.
        return {"status": "unknown", "reason": "invalid_or_unsupported_font"}


def describe_font(font, path_id: int) -> dict:
    raw = font.m_FontData
    coverage = (
        embedded_coverage(bytes(raw))
        if len(raw) <= MAX_FONT_BYTES
        else {"status": "unknown", "reason": "font_size_limit"}
    )
    atlas_indices = {item.index for item in font.m_CharacterRects}
    return {
        "path_id": path_id,
        "name": font.m_Name[:256],
        "font_names": [name[:256] for name in font.m_FontNames[:32]],
        "embedded_bytes": len(raw),
        "embedded_coverage": coverage,
        "serialized_atlas_present": "".join(c for c in REQUIRED if ord(c) in atlas_indices),
        "fallback_count": len(getattr(font, "m_FallbackFonts", None) or []),
    }


def atlas_coverage(tree: dict) -> dict:
    glyphs = tree.get("m_glyphInfoList")
    if not isinstance(glyphs, list) or any(
        not isinstance(g, dict) or type(g.get("id")) is not int for g in glyphs
    ):
        return {"status": "unknown", "reason": "unsupported_tmp_glyph_schema"}
    indices = {g["id"] for g in glyphs}
    present = "".join(c for c in REQUIRED if ord(c) in indices)
    return {
        "status": "complete" if present == REQUIRED else "incomplete",
        "present": present,
        "missing": "".join(c for c in REQUIRED if c not in present),
    }


def inspect_asset(path: Path, game: Path) -> dict:
    import UnityPy

    before = hash_file(path)
    result = {"fonts": [], "tmp_fonts": [], "errors": [], "sha256": before}
    metadata = {}

    def script_for(obj, pointer):
        assets_file = obj.assets_file
        if pointer.m_FileID:
            relative = assets_file.externals[pointer.m_FileID - 1].path
            reference = checked_path(path.parent / relative)
            if not reference.is_relative_to(game) or reference.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Script metadata path or size")
            if reference not in metadata:
                digest = hash_file(reference)
                loaded = UnityPy.load(str(reference))
                files = list(loaded.files.values())
                if len(files) != 1:
                    raise ValueError("Ambiguous script metadata")
                metadata[reference] = (files[0], digest)
            assets_file = metadata[reference][0]
        script = assets_file.objects.get(pointer.m_PathID)
        if script is None or script.type.name != "MonoScript":
            return None
        return script.read()

    try:
        environment = UnityPy.load(str(path))
        for obj in environment.objects:
            if obj.type.name == "MonoBehaviour":
                try:
                    head = obj.parse_monobehaviour_head()
                    script = script_for(obj, head.m_Script)
                    if script is None or (script.m_Namespace, script.m_ClassName) != (
                        "TMPro", "TMP_FontAsset"
                    ):
                        continue
                    try:
                        coverage = atlas_coverage(obj.read_typetree())
                    except Exception:
                        coverage = {"status": "unknown", "reason": "tmp_type_tree_unavailable"}
                    result["tmp_fonts"].append(
                        {"path_id": obj.path_id, "name": head.m_Name[:256], "atlas": coverage}
                    )
                except Exception:
                    result["errors"].append(
                        {"path_id": obj.path_id, "code": "font_script_identification_failed"}
                    )
                if len(result["tmp_fonts"]) + len(result["errors"]) > 1000:
                    raise ValueError("Font identification count limit")
                continue
            if obj.type.name != "Font":
                continue
            if len(result["fonts"]) + len(result["errors"]) >= 1000:
                raise ValueError("Font count limit")
            try:
                result["fonts"].append(describe_font(obj.read(), obj.path_id))
            except Exception:
                result["errors"].append({"path_id": obj.path_id, "code": "font_read_failed"})
        result["script_metadata"] = [
            {"asset": ref.relative_to(game).as_posix(), "sha256": digest}
            for ref, (_, digest) in metadata.items()
        ]
        return result
    finally:
        for reference, (_, digest) in metadata.items():
            if hash_file(reference) != digest:
                raise ValueError("Script metaverisi analiz sırasında değişti.")
        if hash_file(path) != before:
            raise ValueError("Kaynak analiz sırasında değişti.")


def audit_asset(path: Path, game: Path) -> dict:
    path = checked_path(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024 * 1024:
        raise ValueError("Asset bulunamadı veya boyut sınırı aşıldı.")
    before = hash_file(path)
    # Native Unity okuyucusu geliştiricinin ana sürecinde çalışmaz.
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(path), "--game", str(game)],
        capture_output=True,
        timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if hash_file(path) != before:
        raise ValueError("Kaynak analiz sırasında değişti.")
    if process.returncode or len(process.stdout) > MAX_REPORT_BYTES:
        raise ValueError("Font okuma alt süreci başarısız oldu veya rapor sınırı aşıldı.")
    result = strict_json(process.stdout)
    if result["sha256"] != before:
        raise ValueError("Alt süreç kaynak hash eşleşmesi başarısız.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--game", type=Path)
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.game is None:
            parser.error("Worker requires game root")
        worker, game = checked_path(args.worker), checked_path(args.game)
        if not worker.is_relative_to(game):
            raise ValueError("Worker asset oyun kökü dışında.")
        print(json.dumps(inspect_asset(worker, game)))
        return 0
    if args.game is None or args.output is None or not args.asset:
        parser.error("--game, --asset ve --output gerekli")
    game = checked_path(args.game)
    output = checked_path(args.output)
    workspace = Path(__file__).resolve().parents[1]
    if not output.is_relative_to(workspace):
        raise ValueError("Rapor çalışma alanında olmalı.")
    paths = ProjectPaths(game, output.parent)
    results = []
    for relative in args.asset:
        part = Path(relative)
        if part.is_absolute() or part.drive:
            raise ValueError("Asset yolu oyun köküne göreli olmalı.")
        asset = checked_path(game / part)
        if not asset.is_relative_to(game):
            raise ValueError("Asset oyun kökü dışında.")
        results.append({"asset": part.as_posix(), **audit_asset(asset, game)})
    paths.write_json(
        output.name,
        {
            "required_characters": REQUIRED,
            "assets": results,
            "application_verified": False,
            "limitations": "cmap ve serialized atlas statik bulgudur. Sahnenin kullandığı font, "
            "dinamik fallback, Türkçe büyük/küçük harf ve gerçek görünüm doğrulanmadı. "
            "Font ikili verisi dışa aktarılmadı; oyun çalıştırılmadı.",
        },
    )
    print(
        f"{sum(len(item['fonts']) for item in results)} Font, "
        f"{sum(len(item['tmp_fonts']) for item in results)} TMP_FontAsset; {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
