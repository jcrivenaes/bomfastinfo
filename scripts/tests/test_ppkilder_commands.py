"""End-to-end tests of ppkilder.py convert/check/prune on a fake Paperpile mirror.

PDF conversion is stubbed (see conftest.conversions).
"""

from __future__ import annotations

import pytest

import kilder
import ppkilder
from conftest import write_pdf


class Paperpile:
    """A fake mirror (with the "All Papers" folder) plus the .bib export."""

    def __init__(self, root):
        self.root = root
        (root / "All Papers").mkdir(parents=True)
        self.bib = root / "bomfast-kilder.bib"
        self.items: dict[str, dict] = {}

    def add(self, key, top="001_ntp", pdf=True, labels=(), **fields):
        file = f"All Papers/{key}.pdf" if pdf is True else pdf or ""
        if file:
            write_pdf(self.root / file, f"%PDF {key}")
        self.items[key] = {
            "keywords": "; ".join(["bomfast-kilder", top.replace("_", r"\_"), *labels]),
            "file": file,
            **fields,
        }
        self.write()

    def remove(self, key):
        del self.items[key]
        self.write()

    def rename(self, old, new):
        self.items[new] = self.items.pop(old)
        self.write()

    def write(self):
        text = ""
        for key, fields in self.items.items():
            body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
            text += f"@misc{{{key},\n{body}\n}}\n\n"
        self.bib.write_text(text, encoding="utf-8")


@pytest.fixture
def pp(tmp_path):
    return Paperpile(tmp_path / "Paperpile")


def convert(pp, folders=(), force=(), dry_run=False):
    return ppkilder.cmd_convert(pp.root, pp.bib, list(folders), set(force), dry_run)


def check(pp, folders=(), prune=False, dry_run=False):
    return ppkilder.cmd_check(pp.root, pp.bib, list(folders), prune, dry_run)


def entries(sources, top="001_ntp"):
    return kilder.read_yaml(sources / top / "kilder.yaml")


# --------------------------------------------------------------------------- convert


def test_convert_new_sources(sources, pp, conversions, capsys):
    pp.add("doe_2024--rapport", labels=["NTP"], title="Rapport", year="2024", author="Doe, J.")
    pp.add("web_2025", top="002_web", pdf=False, url="https://example.no")

    assert convert(pp) == 0

    e = entries(sources)["doe_2024--rapport"]
    assert {k: e[k] for k in ("paperpile", "mappe", "tittel", "aar", "forfatter", "emneord", "tekst")} == {
        "paperpile": "All Papers/doe_2024--rapport.pdf",
        "mappe": "001_ntp",
        "tittel": "Rapport",
        "aar": 2024,
        "forfatter": "Doe, J.",
        "emneord": ["NTP"],
        "tekst": "tekst/doe_2024--rapport.md",
    }
    text = (sources / "001_ntp" / e["tekst"]).read_text(encoding="utf-8")
    assert text.startswith("<!--\nkilde: Paperpile, All Papers/doe_2024--rapport.pdf\n")
    assert f"sha256: {e['sha256']}\n" in text
    assert entries(sources, "002_web") == {
        "web_2025": {
            "id": "web_2025",
            "paperpile": "",
            "mappe": "002_web",
            "url": "https://example.no",
        }
    }
    assert (sources / ppkilder.BIB_COPY).read_bytes() == pp.bib.read_bytes()
    assert len(conversions) == 1
    out = capsys.readouterr().out
    assert "NEW        doe_2024--rapport" in out and "NO PDF     web_2025" in out


def test_convert_twice_is_a_no_op(sources, pp, conversions, capsys):
    pp.add("k")
    convert(pp)
    capsys.readouterr()
    assert convert(pp) == 0
    assert len(conversions) == 1
    assert "UNCHANGED     1" in capsys.readouterr().out


def test_convert_dry_run_writes_nothing(sources, pp, conversions):
    pp.add("k")
    convert(pp, dry_run=True)
    assert conversions == []
    assert list(sources.iterdir()) == []


def test_metadata_change_updates_entry_and_header_only(sources, pp, conversions, capsys):
    pp.add("k", title="Old title")
    convert(pp)
    e = entries(sources)
    e["k"]["merknad"] = "my note"
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    pp.items["k"]["title"] = "New title"
    pp.write()
    capsys.readouterr()

    convert(pp)

    k = entries(sources)["k"]
    assert (k["tittel"], k["merknad"]) == ("New title", "my note")
    assert "tittel: New title" in (sources / "001_ntp" / "tekst" / "k.md").read_text()
    assert len(conversions) == 1
    assert "METADATA   k: text untouched; kilder.yaml: tittel: Old title -> New title" in (
        capsys.readouterr().out
    )


def test_changed_pdf_is_converted_again(sources, pp, conversions, capsys):
    pp.add("k")
    convert(pp)
    (pp.root / "All Papers" / "k.pdf").write_text("%PDF new and longer content")
    capsys.readouterr()
    convert(pp)
    assert len(conversions) == 2
    assert "UPDATED    k: converting" in capsys.readouterr().out


def test_force(sources, pp, conversions, capsys):
    pp.add("k")
    convert(pp)
    convert(pp, force=["k", "nope"])
    assert len(conversions) == 2
    assert "--force: no such id in scope: nope" in capsys.readouterr().out


def test_label_change_moves_entry_and_text(sources, pp, conversions, capsys):
    pp.add("k", labels=["NTP"])
    convert(pp)
    e = entries(sources)
    e["k"]["merknad"] = "my note"
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    pp.items["k"]["keywords"] = r"bomfast-kilder; 005\_budsjett; NTP"
    pp.write()
    capsys.readouterr()

    assert convert(pp) == 0

    assert entries(sources) == {}
    moved = entries(sources, "005_budsjett")["k"]
    assert (moved["mappe"], moved["merknad"]) == ("005_budsjett", "my note")
    assert (sources / "005_budsjett" / "tekst" / "k.md").exists()
    assert not (sources / "001_ntp" / "tekst" / "k.md").exists()
    assert len(conversions) == 1
    assert "MOVED      k: 001_ntp -> 005_budsjett" in capsys.readouterr().out


def test_citekey_change_is_a_rename(sources, pp, conversions, capsys):
    pp.add("old_key")
    convert(pp)
    e = entries(sources)
    e["old_key"]["merknad"] = "my note"
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    pp.rename("old_key", "new_key")
    capsys.readouterr()

    assert check(pp) == 1  # RENAMED: run convert
    assert "RENAMED        old_key: citekey changed to new_key" in capsys.readouterr().out
    assert check(pp, prune=True) == 1
    assert "old_key" in entries(sources)  # prune keeps what convert carries over

    convert(pp)

    e = entries(sources)
    assert set(e) == {"new_key"}
    assert (e["new_key"]["merknad"], e["new_key"]["tekst"]) == ("my note", "tekst/new_key.md")
    text = (sources / "001_ntp" / "tekst" / "new_key.md").read_text()
    assert "id: new_key" in text
    assert not (sources / "001_ntp" / "tekst" / "old_key.md").exists()
    assert len(conversions) == 1
    assert "RENAMED    new_key: was old_key" in capsys.readouterr().out


def test_missing_pdf_keeps_metadata(sources, pp, conversions):
    pp.add("k", title="T")
    (pp.root / "All Papers" / "k.pdf").unlink()
    assert convert(pp) == 1
    k = entries(sources)["k"]
    assert (k["tittel"], k["paperpile"]) == ("T", "All Papers/k.pdf")
    assert "tekst" not in k


def test_conversion_failure_does_not_stop_the_run(sources, pp, monkeypatch, capsys):
    pp.add("bad")
    pp.add("good")

    def convert_pdf(pdf, out, checksum, rel):
        if pdf.stem == "bad":
            raise RuntimeError("broken PDF")
        from conftest import fake_convert

        return fake_convert(pdf, out, checksum, rel)

    monkeypatch.setattr(ppkilder, "convert_pdf", convert_pdf)
    assert convert(pp) == 1
    e = entries(sources)
    assert "sha256" in e["good"]
    assert e["bad"]["paperpile"] == "All Papers/bad.pdf"  # marker kept, so it is ours
    assert "sha256" not in e["bad"]
    assert "failed: RuntimeError: broken PDF" in capsys.readouterr().out


def test_id_used_by_kilder_py_is_skipped(sources, pp, conversions, capsys):
    theirs = {"id": "k", "fil": "k.pdf", "sha256": "s"}
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", {"k": theirs})
    pp.add("k")

    assert convert(pp) == 1
    assert entries(sources) == {"k": theirs}
    assert conversions == []
    assert "id already used in 001_ntp by kilder.py; skipped" in capsys.readouterr().out
    assert check(pp) == 1
    assert "ID CONFLICT" in capsys.readouterr().out


def test_folder_selection(sources, pp, conversions):
    pp.add("a", top="001_ntp")
    pp.add("b", top="002_web")
    convert(pp, folders=["002_web"])
    assert not (sources / "001_ntp").exists()
    assert set(entries(sources, "002_web")) == {"b"}


def test_mirror_not_mounted(sources, tmp_path):
    with pytest.raises(SystemExit, match="Is it mounted"):
        ppkilder.cmd_convert(tmp_path, tmp_path / "x.bib", [], set(), False)


# --------------------------------------------------------------------------- check / prune


def test_check_in_sync(sources, pp, conversions, capsys):
    pp.add("k", url="https://example.no/k")
    convert(pp)
    capsys.readouterr()
    assert check(pp) == 0
    assert capsys.readouterr().out.rstrip().endswith("OK")


def test_check_reports_problems(sources, pp, conversions, capsys):
    pp.add("changed", url="https://x")
    pp.add("meta", title="Old", url="https://x")
    pp.add("notext", url="https://x")
    convert(pp)
    (pp.root / "All Papers" / "changed.pdf").write_text("%PDF other")
    pp.items["meta"]["title"] = "New"
    pp.add("fresh", url="https://x")
    (sources / "001_ntp" / "tekst" / "notext.md").unlink()
    yaml_before = (sources / "001_ntp" / "kilder.yaml").read_text()
    bib_copy = (sources / ppkilder.BIB_COPY).read_bytes()
    capsys.readouterr()

    assert check(pp) == 1

    out = capsys.readouterr().out
    for line in (
        "CHANGED        changed",
        "METADATA       meta: tittel: Old -> New",
        "TEXT MISSING   notext",
        "NEW            fresh",
    ):
        assert line in out
    assert out.rstrip().endswith("4 issues")
    # check never writes, not even the copy of the .bib file
    assert (sources / "001_ntp" / "kilder.yaml").read_text() == yaml_before
    assert (sources / ppkilder.BIB_COPY).read_bytes() == bib_copy


def test_prune_removes_sources_gone_from_the_bib(sources, pp, conversions, capsys):
    pp.add("keep", url="https://x")
    pp.add("gone", url="https://x")
    convert(pp)
    pp.remove("gone")
    text = sources / "001_ntp" / "tekst" / "gone.md"
    capsys.readouterr()

    assert check(pp) == 1
    assert "GONE           gone" in capsys.readouterr().out

    assert check(pp, prune=True, dry_run=True) == 0
    assert "gone" in entries(sources) and text.exists()

    assert check(pp, prune=True) == 0
    assert set(entries(sources)) == {"keep"}
    assert not text.exists()
    assert (pp.root / "All Papers" / "gone.pdf").exists()  # the PDF is never touched


def test_prune_keeps_unusable_entries(sources, pp, conversions):
    pp.add("k", url="https://x")
    pp.add("other", url="https://x")  # a .bib file with no usable entry stops the run
    convert(pp)
    # Two top labels: the entry is skipped with a warning, but it is still in the
    # .bib file, so prune must not remove it.
    pp.items["k"]["keywords"] = r"bomfast-kilder; 001\_ntp; 002\_web"
    pp.write()
    assert check(pp, prune=True) == 1
    assert "k" in entries(sources)


def test_prune_never_touches_kilder_py_entries(sources, pp, conversions):
    theirs = {"id": "drive_doc", "fil": "d.pdf"}
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", {"drive_doc": theirs})
    pp.add("k", url="https://x")
    convert(pp)
    assert check(pp, prune=True) == 0
    assert entries(sources)["drive_doc"] == theirs


def test_kilder_py_leaves_paperpile_entries_alone(sources, drive, pp, conversions):
    pp.add("k", url="https://x")
    convert(pp)
    write_pdf(drive / "001_ntp" / "d.pdf")
    before = entries(sources)["k"]

    kilder.cmd_convert(drive, "001_ntp", set(), False)
    assert kilder.cmd_check(drive, "001_ntp", prune=True) == 0

    e = entries(sources)
    assert set(e) == {"k", "d"}
    assert e["k"] == before
    assert check(pp) == 0
