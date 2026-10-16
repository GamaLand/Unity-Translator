import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

spec = importlib.util.spec_from_file_location(
    "font_audit", Path(__file__).resolve().parents[1] / "tools/audit_unity_fonts.py"
)
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def synthetic_font(chars: str, *, missing_glyph: str = "") -> bytes:
    builder = FontBuilder(1000, isTTF=True)
    order = [".notdef", *[f"u{ord(char):04X}" for char in chars]]
    builder.setupGlyphOrder(order)
    mapping = {ord(char): f"u{ord(char):04X}" for char in chars}
    mapping.update({ord(char): ".notdef" for char in missing_glyph})
    builder.setupCharacterMap(mapping)
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((0, 0))
            pen.lineTo((500, 0))
            pen.lineTo((250, 700))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 0) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Synthetic", "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    stream = io.BytesIO()
    builder.save(stream)
    return stream.getvalue()


def test_complete_and_partial_unicode_cmap():
    complete = audit.embedded_coverage(synthetic_font(audit.REQUIRED))
    assert complete == {"status": "complete", "present": audit.REQUIRED, "missing": ""}
    partial = audit.embedded_coverage(synthetic_font("çÇ", missing_glyph="İ"))
    assert partial["status"] == "incomplete"
    assert partial["present"] == "çÇ"
    assert "İ" in partial["missing"]


def test_missing_invalid_and_oversized_data_are_unknown(monkeypatch):
    assert audit.embedded_coverage(b"")["status"] == "unknown"
    assert audit.embedded_coverage(b"invalid font")["status"] == "unknown"
    monkeypatch.setattr(audit, "MAX_FONT_BYTES", 2)
    assert audit.embedded_coverage(b"123")["reason"] == "font_size_limit"


def test_atlas_presence_does_not_claim_embedded_or_runtime_support():
    font = SimpleNamespace(
        m_FontData=[],
        m_Name="Synthetic",
        m_FontNames=["Synthetic"],
        m_CharacterRects=[SimpleNamespace(index=ord("İ"))],
    )
    result = audit.describe_font(font, 12)
    assert result["embedded_coverage"]["status"] == "unknown"
    assert result["serialized_atlas_present"] == "İ"
    assert "application_verified" not in result


def test_tmp_atlas_schema_is_checked_without_inventing_glyphs():
    assert audit.atlas_coverage({})["status"] == "unknown"
    assert audit.atlas_coverage({"m_glyphInfoList": [{"id": "304"}]})["status"] == "unknown"
    partial = audit.atlas_coverage({"m_glyphInfoList": [{"id": ord("İ")}]})
    assert partial["status"] == "incomplete"
    assert partial["present"] == "İ"
