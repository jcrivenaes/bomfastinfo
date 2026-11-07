"""Smoke test of the real PDF conversion (pymupdf + pymupdf4llm) on a generated PDF."""

from __future__ import annotations

from pathlib import Path

import pytest

import kilder

pymupdf = pytest.importorskip("pymupdf")
pytest.importorskip("pymupdf4llm")

BODY = "Bompengar på E39 mellom Stord og Os. " * 12  # well above MIN_CHARS_PER_PAGE


def make_pdf(path: Path) -> None:
    """Cover page without a number, then three pages printed 1, 2, 3 in the footer."""
    doc = pymupdf.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 520, 600), f"Side {i}. {BODY}")
        if i:
            page.insert_text((300, 800), str(i))
    doc.set_metadata({"title": "Rapport om bompengar", "subject": "Ein test"})
    doc.save(path)


def test_convert_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(kilder, "has_norwegian_tesseract", lambda: False)
    pdf = tmp_path / "rapport.pdf"
    make_pdf(pdf)
    out = tmp_path / "tekst" / "sub" / "rapport.md"

    info = kilder.convert_pdf(pdf, out, "abc123", Path("sub/rapport.pdf"))

    assert info["pages"] == 4
    assert info["ocr"] is False
    assert info["converted"].startswith("pymupdf")
    assert (info["pdf_title"], info["pdf_subject"]) == ("Rapport om bompengar", "Ein test")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!--\nkilde: sub/rapport.pdf\nsha256: abc123\nsider: 4\n")
    assert "<!-- side pdf=1 -->" in text
    for n in (1, 2, 3):
        assert f"<!-- side pdf={n + 1} trykt={n} -->" in text
    assert "Bompengar på E39" in text
    assert "­" not in text and "\n\n\n" not in text
