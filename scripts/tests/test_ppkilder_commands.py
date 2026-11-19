"""End-to-end tests of ppkilder.py convert/check/prune on a fake Paperpile mirror.

PDF conversion is stubbed (see conftest.conversions).
"""

from __future__ import annotations

import os

import pytest
import yaml

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
    return ppkilder.read_yaml(sources / top / "kilder.yaml")


def exported(out_dir, top="001_ntp"):
    """{id: entry} of the public list."""
    return {e["id"]: e for e in yaml.safe_load((out_dir / f"{top}.yaml").read_text())}


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
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
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
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
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
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
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


def test_id_used_by_an_entry_not_from_paperpile_is_skipped(sources, pp, conversions, capsys):
    theirs = {"id": "k", "fil": "k.pdf", "sha256": "s"}
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", {"k": theirs})
    pp.add("k")

    assert convert(pp) == 1
    assert entries(sources) == {"k": theirs}
    assert conversions == []
    assert "id already used in 001_ntp by an entry not from Paperpile; skipped" in capsys.readouterr().out
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


def test_check_does_not_hash_unchanged_pdfs(sources, pp, conversions, monkeypatch, capsys):
    """The mirror is an rclone mount: hashing a PDF downloads it."""
    pp.add("a_2020--x")
    pp.add("b_2020--y")
    convert(pp)
    hashed = []
    real = ppkilder.sha256
    monkeypatch.setattr(ppkilder, "sha256", lambda p: hashed.append(p.name) or real(p))

    assert check(pp) == 0
    assert hashed == []

    pdf = pp.root / "All Papers" / "b_2020--y.pdf"
    pdf.write_text("%PDF b_2020--z")  # same size, newer than its text file
    st = pdf.stat()
    os.utime(pdf, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
    capsys.readouterr()
    assert check(pp) == 1
    assert hashed == ["b_2020--y.pdf"]
    assert "CHANGED        b_2020--y: checksum in the mirror" in capsys.readouterr().out

    hashed.clear()
    ppkilder.cmd_check(pp.root, pp.bib, [], checksum=True)
    assert sorted(hashed) == ["a_2020--x.pdf", "b_2020--y.pdf"]


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


def test_prune_never_touches_entries_not_from_paperpile(sources, pp, conversions):
    theirs = {"id": "drive_doc", "fil": "d.pdf"}  # e.g. left from the old kilder.py
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", {"drive_doc": theirs})
    pp.add("k", url="https://x")
    convert(pp)
    assert check(pp, prune=True) == 0
    assert entries(sources)["drive_doc"] == theirs


# --------------------------------------------------------------------------- control labels


def test_private_label(sources, pp, conversions):
    pp.add(
        "artikkel",
        labels=[r"\_PRIVAT", "NTP"],
        url="https://avis.example/betalingsmur",
        title="Betalingsmur",
    )
    pp.add("rapport", labels=["NTP"], url="https://example.no/r")

    convert(pp)

    e = entries(sources)
    assert (e["artikkel"]["offentlig"], e["artikkel"]["arkiv"]) == ("nei", "skip")
    assert e["artikkel"]["emneord"] == ["NTP"]  # control labels are not topics
    assert "offentlig" not in e["rapport"] and "arkiv" not in e["rapport"]
    text = (sources / "001_ntp" / "tekst" / "artikkel.md").read_text()
    assert "_privat" not in text.lower()

    out_dir = sources.parent / "data"
    ppkilder.cmd_export("001_ntp", out_dir, dry_run=False)
    public = (out_dir / "001_ntp.yaml").read_text()
    assert "avis.example" not in public
    assert exported(out_dir)["artikkel"] == {"id": "artikkel", "tittel": "Betalingsmur"}
    assert exported(out_dir)["rapport"]["url"] == "https://example.no/r"


@pytest.mark.parametrize("private_first", [True, False])
@pytest.mark.parametrize("folders", [(), ("002_web",)])
def test_private_label_on_a_duplicate_citekey_still_counts(
    sources, pp, conversions, capsys, private_first, folders
):
    """Entry order (and the folders convert runs on) must not leave the entry public."""
    pp.add("artikkel", url="https://avis.example/sak")
    pp.add("web", top="002_web", pdf=False, url="https://example.no")
    convert(pp)
    assert "offentlig" not in entries(sources)["artikkel"]
    copy = "@misc{artikkel,\n  keywords = {bomfast-kilder; 001\\_ntp; \\_PRIVAT}\n}\n\n"
    text = pp.bib.read_text(encoding="utf-8")
    pp.bib.write_text(copy + text if private_first else text + copy, encoding="utf-8")
    capsys.readouterr()

    convert(pp, folders)

    e = entries(sources)["artikkel"]
    assert (e["offentlig"], e["arkiv"]) == ("nei", "skip")
    assert e["url"] == "https://avis.example/sak"  # otherwise left as it was
    out = capsys.readouterr().out
    assert "WARNING    artikkel: the citekey is used 2 times" in out
    assert "METADATA   artikkel: skipped in the .bib file, but its control labels" in out
    out_dir = sources.parent / "data"
    ppkilder.cmd_export("001_ntp", out_dir, dry_run=False)
    assert set(exported(out_dir)["artikkel"]) <= {"id", "tittel"}  # no link left
    assert "avis.example" not in (out_dir / "001_ntp.yaml").read_text()


def test_private_label_counts_when_the_only_source_is_a_duplicate(
    sources, pp, conversions, capsys
):
    """No usable source left: convert stops as before, but applies the labels first."""
    pp.add("artikkel", url="https://avis.example/sak")
    convert(pp)
    bib_copy = (sources / ppkilder.BIB_COPY).read_bytes()
    with pp.bib.open("a", encoding="utf-8") as f:
        f.write("@misc{artikkel,\n  keywords = {bomfast-kilder; 001\\_ntp; \\_PRIVAT}\n}\n")

    with pytest.raises(SystemExit, match="No sources with a top folder label"):
        convert(pp)

    e = entries(sources)["artikkel"]
    assert (e["offentlig"], e["arkiv"]) == ("nei", "skip")
    assert (sources / ppkilder.BIB_COPY).read_bytes() == bib_copy  # not updated
    with pytest.raises(SystemExit):
        check(pp, prune=True)  # prune still refuses an export without sources
    assert "artikkel" in entries(sources)


@pytest.mark.parametrize(
    "keywords",
    [
        r"bomfast-kilder; 001\_ntp; 002\_web; \_PRIVAT",  # two top folder labels
        r"bomfast-kilder; \_PRIVAT",  # no top folder label
        r"\_PRIVAT",  # not even bomfast-kilder: ignored
    ],
)
def test_private_label_counts_on_an_unusable_entry(sources, pp, conversions, keywords):
    pp.add("artikkel", url="https://avis.example/sak")
    pp.add("other")
    convert(pp)
    pp.items["artikkel"]["keywords"] = keywords
    pp.write()

    convert(pp)

    e = entries(sources)["artikkel"]
    assert (e["offentlig"], e["arkiv"]) == ("nei", "skip")


def test_private_label_reaches_every_copy_of_an_id(sources, pp, conversions, capsys):
    pp.add("artikkel", url="https://avis.example/sak")
    convert(pp)
    copy = dict(entries(sources)["artikkel"])
    ppkilder.write_yaml(sources / "000_copy" / "kilder.yaml", {"artikkel": copy})
    pp.items["artikkel"]["keywords"] += r"; \_ABO"
    pp.write()
    capsys.readouterr()

    convert(pp)

    for top in ("000_copy", "001_ntp"):
        assert entries(sources, top)["artikkel"]["arkiv"] == "skip"
    out = capsys.readouterr().out
    assert "METADATA   artikkel (000_copy): control labels in the .bib file" in out


def test_duplicate_citekey_without_labels_changes_nothing(sources, pp, conversions):
    pp.add("artikkel")
    pp.add("other")
    convert(pp)
    before = entries(sources)
    with pp.bib.open("a", encoding="utf-8") as f:
        f.write("@misc{artikkel,\n  keywords = {bomfast-kilder; 001\\_ntp}\n}\n")

    convert(pp)

    assert entries(sources) == before


def test_innsyn_label_is_private(sources, pp, conversions, capsys):
    pp.add("innsyn", labels=["_innsyn", "Rogfast"], url="https://example.no/i")
    pp.add("rapport", url="https://example.no/r")

    convert(pp)

    e = entries(sources)["innsyn"]
    assert (e["offentlig"], e["arkiv"]) == ("nei", "skip")
    assert e["emneord"] == ["Rogfast"]
    assert "unknown label" not in capsys.readouterr().out
    out_dir = sources.parent / "data"
    ppkilder.cmd_export("001_ntp", out_dir, dry_run=False)
    public = exported(out_dir)
    assert "url" in public["rapport"]
    assert set(public["innsyn"]) <= {"id", "tittel"}  # citable, but no link


def test_subscription_label_exports_without_archive(sources, pp, conversions):
    pp.add("abo", labels=["_abo"], url="https://avis.example/sak")

    convert(pp)

    abo = entries(sources)["abo"]
    assert abo["arkiv"] == "skip" and "offentlig" not in abo
    out_dir = sources.parent / "data"
    ppkilder.cmd_export("001_ntp", out_dir, dry_run=False)
    assert "https://avis.example/sak" in (out_dir / "001_ntp.yaml").read_text()
    assert "skip" not in (out_dir / "001_ntp.yaml").read_text()


def test_label_overrides_kilder_yaml(sources, pp, conversions, capsys):
    pp.add("k", url="https://x")
    convert(pp)
    e = entries(sources)
    e["k"].update(offentlig="ja", arkiv="https://web.archive.org/web/2020/https://x")
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    pp.items["k"]["keywords"] += "; _PRIVAT"
    pp.write()
    capsys.readouterr()

    assert check(pp) == 1
    out = capsys.readouterr().out
    assert "METADATA       k: arkiv: https://web.archive.org" in out
    assert "offentlig: ja -> nei (run convert)" in out
    convert(pp)
    k = entries(sources)["k"]
    assert (k["offentlig"], k["arkiv"]) == ("nei", "skip")
    assert len(conversions) == 1  # metadata only, no new conversion


def test_removing_labels_changes_nothing(sources, pp, conversions, capsys):
    pp.add("p", labels=["_PRIVAT"], url="https://x")
    pp.add("a", labels=["_ABO"], url="https://x")
    convert(pp)
    for key in ("p", "a"):
        pp.items[key]["keywords"] = pp.items[key]["keywords"].split("; _")[0]
    pp.write()
    capsys.readouterr()

    convert(pp)
    e = entries(sources)
    assert (e["p"]["offentlig"], e["p"]["arkiv"], e["a"]["arkiv"]) == ("nei", "skip", "skip")

    assert check(pp) == 0  # notices, not issues
    out = capsys.readouterr().out
    assert "NO LABEL       p: offentlig: nei in kilder.yaml, but no _PRIVAT/_INNSYN label" in out
    assert "NO LABEL       a: arkiv: skip in kilder.yaml, but no _ABO" in out

    e["p"]["offentlig"] = "ja"  # making it public is a deliberate edit in kilder.yaml
    del e["a"]["arkiv"]
    ppkilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    convert(pp)
    e = entries(sources)
    assert e["p"]["offentlig"] == "ja" and "arkiv" not in e["a"]
    check(pp)
    assert "NO LABEL       a" not in capsys.readouterr().out


def test_no_url_label_silences_no_url(sources, pp, conversions, capsys):
    pp.add("vv_2020--intern", labels=["_NO_URL"])
    pp.add("vv_2021--mangler")
    convert(pp)
    capsys.readouterr()

    assert check(pp) == 0

    out = capsys.readouterr().out
    assert "NO URL         vv_2021--mangler: no url (add it in Paperpile, or the label _NO_URL" in out
    assert "vv_2020--intern" not in out.split("Summary")[0]  # no line for it without -v
    assert "NO URL OK        1   entries without url, marked with _NO_URL" in out
    intern = entries(sources)["vv_2020--intern"]
    # not kept from archive.org, and not a topic
    assert "arkiv" not in intern and "offentlig" not in intern
    assert "emneord" not in intern


def test_no_url_label_with_other_labels(sources, pp, conversions):
    pp.add("abo", labels=["_no_url", "_ABO"])
    pp.add("other")
    convert(pp)
    assert entries(sources)["abo"]["arkiv"] == "skip"  # _ABO still counts
    # on an unusable entry, _NO_URL alone restricts nothing
    pp.add("two", top="001_ntp", labels=[r"002\_x", "_NO_URL"])
    assert "two" not in ppkilder.read_sources(pp.bib)[4]


def test_citekey_style_is_a_notice(sources, pp, conversions, capsys):
    pp.add("doe_2024--rapport")
    pp.add("metier_moreforskning_2009--rogfast-ks1")
    pp.add("Doe_2024--Rapport")

    assert convert(pp) == 0  # converted anyway

    out = capsys.readouterr().out
    assert set(entries(sources)) == {
        "doe_2024--rapport", "metier_moreforskning_2009--rogfast-ks1", "Doe_2024--Rapport"
    }
    assert "CITEKEY    metier_moreforskning_2009--rogfast-ks1: has - or empty" in out
    assert "converted anyway" in out
    assert "CITEKEY    doe_2024--rapport" not in out

    assert check(pp) == 0  # a notice, not an issue
    out = capsys.readouterr().out
    assert "CITEKEY        Doe_2024--Rapport: has capital letters" in out
    assert "CITEKEY          2   citekey not on the form" in out


def test_unknown_and_near_miss_labels_warn(sources, pp, conversions, capsys):
    pp.add("k", labels=["_PRIVATE", "_annet", "Privat", "abo", "privatisering"], url="https://x")
    convert(pp)
    out = capsys.readouterr().out
    assert "unknown label '_PRIVATE' (did you mean _PRIVAT?); like every label" in out
    assert "unknown label '_annet'; like every label starting with _" in out
    assert "the label 'Privat' looks like _PRIVAT, but is not" in out
    assert "the label 'abo' looks like _ABO, but is not" in out
    assert "'privatisering'" not in out
    k = entries(sources)["k"]
    assert k["arkiv"] == "skip"  # any _ label: no archive.org
    assert "offentlig" not in k  # but only _PRIVAT makes it private
    assert k["emneord"] == ["Privat", "abo", "privatisering"]
