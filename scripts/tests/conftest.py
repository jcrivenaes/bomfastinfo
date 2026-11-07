"""Shared fixtures for the kilder.py / ppkilder.py tests.

Run from the repo root:  python3 -m pytest scripts
Nothing here touches the real Drive folder, Paperpile mirror or sources repo: every test
gets its own temporary sources repo, and PDF conversion is replaced by a fast stub
(except in test_convert_pdf.py, which converts a real, generated PDF).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import kilder  # noqa: E402
import ppkilder  # noqa: E402


@pytest.fixture(autouse=True)
def quiet_log(monkeypatch):
    """A fresh, non-verbose Log per test, so -v in one test cannot leak into the next."""
    monkeypatch.setattr(kilder, "LOG", kilder.Log())


@pytest.fixture
def sources(tmp_path, monkeypatch) -> Path:
    """An empty private sources repo, set as kilder.SOURCES_DIR (ppkilder reads it too)."""
    d = tmp_path / "sources"
    d.mkdir()
    monkeypatch.setattr(kilder, "SOURCES_DIR", d)
    return d


@pytest.fixture
def drive(tmp_path) -> Path:
    d = tmp_path / "drive"
    d.mkdir()
    return d


def fake_convert(pdf: Path, out: Path, checksum: str, rel: Path) -> dict:
    """Stand-in for convert_pdf: writes a text file with the same header shape."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "<!--\n"
        f"kilde: {rel.as_posix()}\n"
        f"sha256: {checksum}\n"
        "-->\n\n"
        f"<!-- side pdf=1 -->\n\n{pdf.read_text(encoding='utf-8')}\n",
        encoding="utf-8",
    )
    return {
        "pages": 1,
        "converted": "fake 1.0, 2026-01-01",
        "ocr": False,
        "pdf_title": "",
        "pdf_subject": "",
    }


@pytest.fixture
def conversions(monkeypatch) -> list[Path]:
    """Replace convert_pdf in both scripts; returns the list of converted PDFs."""
    calls: list[Path] = []

    def stub(pdf, out, checksum, rel):
        calls.append(pdf)
        return fake_convert(pdf, out, checksum, rel)

    monkeypatch.setattr(kilder, "convert_pdf", stub)
    monkeypatch.setattr(ppkilder, "convert_pdf", stub)
    return calls


def write_pdf(path: Path, content: str = "") -> Path:
    """A fake PDF: only the bytes matter (checksum, size), conversion is stubbed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or f"%PDF-1.4 {path.name}", encoding="utf-8")
    return path
