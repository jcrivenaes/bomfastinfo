"""End-to-end tests of kilder.py convert/check/prune/export on a fake Drive folder.

PDF conversion is stubbed (see conftest.conversions), so these test the bookkeeping:
which entries and text files exist after each run, and what the commands report.
"""

from __future__ import annotations

import os

import pytest
import yaml

import kilder
from conftest import write_pdf

TOP = "101_hordfast"


@pytest.fixture
def top(drive):
    t = drive / TOP
    t.mkdir()
    return t


def entries(sources):
    return kilder.read_yaml(sources / TOP / "kilder.yaml")


def convert(drive, folder=TOP, force=(), dry_run=False):
    kilder.cmd_convert(drive, folder, set(force), dry_run)


def touch_later(path):
    """Make path newer than everything written so far (mtime resolution can be coarse)."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))


# --------------------------------------------------------------------------- convert


def test_convert_new_pdfs(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    write_pdf(top / "sub" / "b.pdf")
    (top / "a.url").write_text("[InternetShortcut]\nURL=https://example.no/a\n")

    convert(drive)

    e = entries(sources)
    assert set(e) == {"a", "b"}
    assert e["a"]["fil"] == "a.pdf"
    assert e["a"]["url"] == "https://example.no/a"
    assert e["b"]["tekst"] == "tekst/sub/b.md"
    assert e["b"]["sha256"] == kilder.sha256(top / "sub" / "b.pdf")
    assert (sources / TOP / "tekst" / "sub" / "b.md").exists()
    assert len(conversions) == 2
    out = capsys.readouterr().out
    assert "NEW        a.pdf" in out
    assert "kilder.yaml: written (2 entries added)" in out


def test_convert_twice_is_a_no_op(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    convert(drive)
    capsys.readouterr()

    convert(drive)

    assert len(conversions) == 1
    out = capsys.readouterr().out
    assert "UNCHANGED     1" in out
    assert "kilder.yaml: no changes, file not rewritten" in out


def test_convert_keeps_hand_edited_fields(sources, drive, top, conversions):
    pdf = write_pdf(top / "a.pdf")
    (top / "a.url").write_text("URL=https://drive.example/a")
    convert(drive)
    e = entries(sources)
    e["a"].update(url="https://mine.example/a", merknad="viktig", tittel="Min tittel")
    kilder.write_yaml(sources / TOP / "kilder.yaml", e)

    pdf.write_text("%PDF-1.4 changed content")
    touch_later(pdf)
    convert(drive)

    a = entries(sources)["a"]
    assert len(conversions) == 2  # the PDF changed, so it was converted again
    assert a["sha256"] == kilder.sha256(pdf)
    assert (a["url"], a["merknad"], a["tittel"]) == (
        "https://mine.example/a",
        "viktig",
        "Min tittel",
    )


def test_convert_dry_run_writes_nothing(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    convert(drive, dry_run=True)
    assert conversions == []
    assert not (sources / TOP).exists()
    assert "NEW        a.pdf: not in kilder.yaml before; text would be" in capsys.readouterr().out


def test_convert_rebuilds_missing_text_and_force(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    convert(drive)
    (sources / TOP / "tekst" / "a.md").unlink()
    capsys.readouterr()

    convert(drive)
    assert "REBUILT    a.pdf: converting" in capsys.readouterr().out
    convert(drive, force=["a"])
    assert "--force (PDF unchanged)" in capsys.readouterr().out
    convert(drive, force=["nope"])
    assert "--force: no such id in 101_hordfast: nope" in capsys.readouterr().out
    assert len(conversions) == 3  # first run, rebuild, force; not "nope"
    convert(drive, force=["a", "nope"])  # a valid id still counts next to an unknown one
    assert len(conversions) == 4


def test_convert_follows_a_move_to_another_subfolder(sources, drive, top, conversions, capsys):
    write_pdf(top / "old" / "a.pdf")
    convert(drive)
    (top / "new").mkdir()
    (top / "old" / "a.pdf").rename(top / "new" / "a.pdf")
    capsys.readouterr()

    convert(drive)

    a = entries(sources)["a"]
    assert (a["fil"], a["tekst"]) == ("new/a.pdf", "tekst/new/a.md")
    text = sources / TOP / "tekst" / "new" / "a.md"
    assert "kilde: new/a.pdf" in text.read_text(encoding="utf-8")
    assert not (sources / TOP / "tekst" / "old").exists()
    assert len(conversions) == 1  # moved, not converted again
    assert "id a kept" in capsys.readouterr().out


def test_convert_follows_a_rename(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    convert(drive)
    (top / "a.pdf").rename(top / "b.pdf")
    capsys.readouterr()

    convert(drive)

    e = entries(sources)
    assert set(e) == {"b"}
    assert e["b"]["fil"] == "b.pdf"
    assert (sources / TOP / "tekst" / "b.md").exists()
    assert not (sources / TOP / "tekst" / "a.md").exists()
    assert "id a -> b: update references in articles!" in capsys.readouterr().out


def test_convert_subfolder_uses_ids_of_whole_top_folder(sources, drive, top, conversions):
    write_pdf(top / "s1" / "dup.pdf", "one")
    write_pdf(top / "s2" / "dup.pdf", "two")
    convert(drive, f"{TOP}/s2")
    assert set(entries(sources)) == {"s2__dup"}  # the same id as a run on the top folder


def test_convert_skips_excluded_and_links_only(sources, drive, top, conversions):
    write_pdf(top / "utkast" / "draft.pdf")
    (sources / TOP).mkdir()
    (sources / TOP / "EXCLUDE.txt").write_text("utkast\n")
    (top / "web_annet.txt").write_text('"Side": https://example.no/side\n')

    convert(drive)

    assert entries(sources) == {
        "web": {"id": "web", "lenker": [{"tittel": "Side", "url": "https://example.no/side"}]}
    }


def test_convert_leaves_paperpile_entries_alone(sources, drive, top, conversions):
    pp = {"id": "pp_2020", "paperpile": "All Papers/P/x.pdf", "tekst": "tekst/pp_2020.md"}
    kilder.write_yaml(sources / TOP / "kilder.yaml", {"pp_2020": pp})
    write_pdf(top / "a.pdf")

    convert(drive)

    e = entries(sources)
    assert e["pp_2020"] == pp
    assert set(e) == {"a", "pp_2020"}


def test_convert_unknown_folder_exits(drive, sources):
    with pytest.raises(SystemExit, match="Not found"):
        convert(drive, "999_none")


# --------------------------------------------------------------------------- check / prune


def test_check_in_sync(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    (top / "a.url").write_text("URL=https://example.no/a")
    convert(drive)
    capsys.readouterr()
    assert kilder.cmd_check(drive, TOP) == 0
    assert capsys.readouterr().out.rstrip().endswith("OK")


def test_check_reports_problems(sources, drive, top, conversions, capsys):
    a = write_pdf(top / "a.pdf")
    write_pdf(top / "b.pdf")
    (top / "a.url").write_text("URL=https://example.no/a")
    convert(drive)
    e = entries(sources)
    e["a"]["url"] = "https://other.example/a"  # kilder.yaml wins, but check tells
    e["b"]["offentlig"] = "tja"
    kilder.write_yaml(sources / TOP / "kilder.yaml", e)
    a.write_text("%PDF changed")
    write_pdf(top / "c.pdf")
    (sources / TOP / "tekst" / "b.md").unlink()
    (sources / TOP / "tekst" / "orphan.md").write_text("x")
    capsys.readouterr()

    assert kilder.cmd_check(drive, TOP) == 1

    out = capsys.readouterr().out
    for line in (
        "NEW            c.pdf",
        "CHANGED        a.pdf",
        "URL MISMATCH   a",
        "TEXT MISSING   b",
        "OFFENTLIG?     b",
        "ORPHAN         tekst/orphan.md",
    ):
        assert line in out
    assert "NO URL         b" in out  # reported, but not an issue
    assert out.rstrip().endswith("6 issues")
    assert entries(sources) == e  # check never writes


def test_prune_removes_gone_entries_and_orphans(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    write_pdf(top / "b.pdf")
    convert(drive)
    (top / "b.pdf").unlink()
    (sources / TOP / "tekst" / "orphan.md").write_text("x")
    capsys.readouterr()

    assert kilder.cmd_check(drive, TOP, prune=True, dry_run=True) == 0
    out = capsys.readouterr().out
    assert "WOULD REMOVE   b" in out and "WOULD DELETE   tekst/orphan.md" in out
    assert set(entries(sources)) == {"a", "b"}
    assert (sources / TOP / "tekst" / "b.md").exists()

    assert kilder.cmd_check(drive, TOP, prune=True) == 0
    assert set(entries(sources)) == {"a"}
    assert not (sources / TOP / "tekst" / "b.md").exists()
    assert not (sources / TOP / "tekst" / "orphan.md").exists()
    assert (top / "a.pdf").exists()


def test_prune_removes_newly_excluded(sources, drive, top, conversions):
    write_pdf(top / "utkast" / "a.pdf")
    convert(drive)
    (sources / TOP / "EXCLUDE.txt").write_text("utkast\n")
    assert kilder.cmd_check(drive, TOP) == 1
    assert kilder.cmd_check(drive, TOP, prune=True) == 0
    assert entries(sources) == {}


def test_prune_keeps_moved_files(sources, drive, top, conversions, capsys):
    write_pdf(top / "a.pdf")
    convert(drive)
    (top / "a.pdf").rename(top / "renamed.pdf")
    capsys.readouterr()

    assert kilder.cmd_check(drive, TOP, prune=True) == 1  # MOVED: run convert
    assert set(entries(sources)) == {"a"}
    assert "MOVED          a: a.pdf -> renamed.pdf" in capsys.readouterr().out


def test_check_ignores_paperpile_entries(sources, drive, top, conversions):
    pp = {"id": "pp", "paperpile": "All Papers/x.pdf", "url": "https://x", "tekst": "tekst/pp.md"}
    kilder.write_yaml(sources / TOP / "kilder.yaml", {"pp": pp})
    (sources / TOP / "tekst").mkdir()
    (sources / TOP / "tekst" / "pp.md").write_text("x")
    assert kilder.cmd_check(drive, TOP, prune=True) == 0
    assert entries(sources) == {"pp": pp}


# --------------------------------------------------------------------------- export


def test_export(sources, tmp_path, capsys):
    kilder.write_yaml(
        sources / TOP / "kilder.yaml",
        {
            "pub": {"id": "pub", "fil": "p.pdf", "url": "https://p", "merknad": "NOTE-X", "sha256": "s"},
            "priv": {"id": "priv", "url": "https://secret.example", "offentlig": "nei"},
            "unclear": {"id": "unclear", "url": "https://u", "offentlig": "?"},
            "nolink": {"id": "nolink", "tittel": "T"},
            "skip": {"id": "skip", "url": "https://s", "arkiv": "skip"},
        },
    )
    out = tmp_path / "data"

    assert kilder.cmd_export(TOP, out, dry_run=True) == 1  # warning for "unclear"
    assert not out.exists()

    assert kilder.cmd_export(TOP, out, dry_run=False) == 1
    exported = yaml.safe_load((out / f"{TOP}.yaml").read_text(encoding="utf-8"))
    assert exported == [
        {"id": "pub", "url": "https://p"},
        {"id": "skip", "url": "https://s"},
    ]
    text = (out / f"{TOP}.yaml").read_text(encoding="utf-8")
    assert "secret.example" not in text and "NOTE-X" not in text and "p.pdf" not in text


def test_export_empties_stale_public_file(sources, tmp_path):
    out = tmp_path / "data"
    yaml_file = sources / TOP / "kilder.yaml"
    kilder.write_yaml(yaml_file, {"a": {"id": "a", "url": "https://a"}})
    kilder.cmd_export(TOP, out, dry_run=False)
    kilder.write_yaml(yaml_file, {"a": {"id": "a", "url": "https://a", "offentlig": "nei"}})

    kilder.cmd_export(TOP, out, dry_run=False)

    assert yaml.safe_load((out / f"{TOP}.yaml").read_text(encoding="utf-8")) == []


def test_export_nothing_public_creates_no_file(sources, tmp_path):
    kilder.write_yaml(sources / TOP / "kilder.yaml", {"a": {"id": "a", "offentlig": "nei"}})
    assert kilder.cmd_export(TOP, tmp_path / "data", dry_run=False) == 0
    assert not (tmp_path / "data").exists()


def test_export_rejects_subfolder_and_missing_list(sources, tmp_path):
    with pytest.raises(SystemExit, match="top folders only"):
        kilder.cmd_export(f"{TOP}/sub", tmp_path, dry_run=True)
    with pytest.raises(SystemExit, match="not found"):
        kilder.cmd_export("999_none", tmp_path, dry_run=True)


# --------------------------------------------------------------------------- deleted folders


def run_main(monkeypatch, drive, sources, *args):
    monkeypatch.setattr("sys.argv", ["kilder.py", "--drive", str(drive), "--sources", str(sources), *args])
    return kilder.main()


def test_prune_all_includes_top_folders_deleted_from_drive(
    sources, drive, conversions, monkeypatch, capsys
):
    import shutil

    write_pdf(drive / "001_ntp" / "b.pdf")
    write_pdf(drive / "006_div" / "sub" / "a.pdf")
    run_main(monkeypatch, drive, sources, "convert", "--all")
    shutil.rmtree(drive / "006_div")
    # a folder with only Paperpile entries is not one of ours: left alone
    kilder.write_yaml(sources / "007_pp" / "kilder.yaml", {"p": {"id": "p", "paperpile": "x"}})
    capsys.readouterr()

    assert run_main(monkeypatch, drive, sources, "check", "--all") == 1
    out = capsys.readouterr().out
    assert "006_div is not on Drive (deleted or renamed?)" in out
    assert "GONE           a: sub/a.pdf" in out
    assert "007_pp" not in out

    assert run_main(monkeypatch, drive, sources, "prune", "--all") == 0
    assert kilder.read_yaml(sources / "006_div" / "kilder.yaml") == {}
    assert not (sources / "006_div" / "tekst" / "sub").exists()  # no empty folders left
    assert set(kilder.read_yaml(sources / "001_ntp" / "kilder.yaml")) == {"b"}


def test_refuses_to_run_when_drive_is_not_mounted(sources, drive, conversions, monkeypatch):
    write_pdf(drive / "001_ntp" / "b.pdf")
    run_main(monkeypatch, drive, sources, "convert", "--all")
    empty = drive.parent / "unmounted"
    empty.mkdir()
    for command in (["prune", "--all"], ["prune", "001_ntp"], ["check", "001_ntp"]):
        with pytest.raises(SystemExit, match="Is it mounted"):
            run_main(monkeypatch, empty, sources, *command)
    assert set(kilder.read_yaml(sources / "001_ntp" / "kilder.yaml")) == {"b"}


def test_prune_removes_empty_text_folders(sources, drive, top, conversions):
    write_pdf(top / "a" / "b" / "x.pdf")
    write_pdf(top / "keep.pdf")
    convert(drive)
    (sources / TOP / "tekst" / "o" / "orphan.md").parent.mkdir()
    (sources / TOP / "tekst" / "o" / "orphan.md").write_text("x")
    (top / "a" / "b" / "x.pdf").unlink()

    kilder.cmd_check(drive, TOP, prune=True)

    assert sorted(p.name for p in (sources / TOP / "tekst").iterdir()) == ["keep.md"]
