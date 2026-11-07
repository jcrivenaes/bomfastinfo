"""Unit tests for the pure helpers in kilder.py (also used by ppkilder.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

import kilder
from conftest import write_pdf

# --------------------------------------------------------------------------- offentlig/arkiv


@pytest.mark.parametrize(
    "entry, public, warns",
    [
        ({}, True, False),
        ({"offentlig": True}, True, False),
        ({"offentlig": False}, False, False),
        ({"offentlig": "ja"}, True, False),
        ({"offentlig": " Yes "}, True, False),
        ({"offentlig": "nei"}, False, False),
        ({"offentlig": "NO"}, False, False),
        ({"offentlig": "kanskje"}, False, True),  # unknown -> private, with a warning
        ({"offentlig": None}, False, True),
    ],
)
def test_public_status(entry, public, warns):
    is_public, warning = kilder.public_status(entry)
    assert is_public is public
    assert bool(warning) is warns


@pytest.mark.parametrize(
    "arkiv, skipped",
    [(None, False), ("", False), ("skip", True), (" SKIP ", True), ("https://x", False)],
)
def test_archive_skipped(arkiv, skipped):
    assert kilder.archive_skipped({"arkiv": arkiv}) is skipped


# --------------------------------------------------------------------------- formatting


@pytest.mark.parametrize(
    "n, text",
    [
        (None, "?"),
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1.0 kB"),
        (1_500_000, "1.5 MB"),
        (2_000_000_000_000, "2000.0 GB"),
    ],
)
def test_human_size(n, text):
    assert kilder.human_size(n) == text


def test_show():
    assert kilder.show(None) == "(empty)"
    assert kilder.show([]) == "(empty)"
    assert kilder.show([{"url": "a"}]) == "1 link"
    assert kilder.show([1, 2]) == "2 links"
    assert kilder.show("abc") == "abc"
    long = kilder.show("x" * 100, limit=10)
    assert long == "x" * 9 + "…" and len(long) == 10


def test_changed_fields_treats_empty_values_as_equal():
    before = {"url": None, "lenker": [], "tittel": "A", "sider": 3}
    after = {"url": "", "tittel": "B", "sider": 3, "ny": "x"}
    assert kilder.changed_fields(before, after) == {
        "tittel": ("A", "B"),
        "ny": (None, "x"),
    }


def test_changed_fields_ignore_and_none_before():
    assert kilder.changed_fields(None, {"id": "a", "url": "u"}, ignore={"id"}) == {
        "url": (None, "u")
    }


def test_describe():
    text = kilder.describe({"url": (None, "https://a"), "tittel": ("A", "B")})
    assert text == "tittel: A -> B; url = https://a"


# --------------------------------------------------------------------------- exclusion


@pytest.mark.parametrize(
    "rel, extra, reason",
    [
        ("a/b.pdf", [], None),
        ("old_backup/b.pdf", [], "built-in: *backup*"),
        (".Trash-1000/b.pdf", [], "built-in: .Trash*"),
        ("a/b.pdf~", [], "built-in: *~"),
        # a name pattern matches any path component
        ("x/utkast/y/b.pdf", ["utkast"], "EXCLUDE.txt: utkast"),
        ("x/utkast2/b.pdf", ["utkast"], None),
        # a path pattern matches from the top folder, and everything below it
        ("reg/90_Arb/b.pdf", ["reg/90_Arb"], "EXCLUDE.txt: reg/90_Arb"),
        ("reg/90_Arb/deep/b.pdf", ["/reg/90_Arb/"], "EXCLUDE.txt: /reg/90_Arb/"),
        ("other/reg/90_Arb/b.pdf", ["reg/90_Arb"], None),
        ("reg/90_Arbeid/b.pdf", ["reg/90_Arb"], None),
    ],
)
def test_exclusion_reason(rel, extra, reason):
    assert kilder.exclusion_reason(Path(rel), extra) == reason
    assert kilder.is_excluded(Path(rel), extra) is (reason is not None)


def test_read_exclude_skips_comments_and_blank_lines(sources):
    (sources / "101_x").mkdir()
    (sources / "101_x" / "EXCLUDE.txt").write_text(
        "# comment\n\nutkast\n  a/b  \n", encoding="utf-8"
    )
    assert kilder.read_exclude("101_x") == ["utkast", "a/b"]
    assert kilder.read_exclude("102_none") == []


def test_find_pdfs_and_find_excluded(sources, drive):
    top = drive / "101_x"
    write_pdf(top / "a.pdf")
    write_pdf(top / "sub" / "B.PDF")
    write_pdf(top / "utkast" / "c.pdf")
    write_pdf(top / "backup" / "d.pdf")
    (top / "notes.txt").write_text("x")
    (sources / "101_x").mkdir()
    (sources / "101_x" / "EXCLUDE.txt").write_text("utkast\n")
    assert [p.relative_to(top).as_posix() for p in kilder.find_pdfs(top)] == [
        "a.pdf",
        "sub/B.PDF",
    ]
    assert [p.name for p in kilder.find_pdfs(top, "sub")] == ["B.PDF"]
    assert kilder.find_excluded(top) == [
        ("backup/d.pdf", "built-in: *backup*"),
        ("utkast/c.pdf", "EXCLUDE.txt: utkast"),
    ]


# --------------------------------------------------------------------------- Drive files


@pytest.mark.parametrize(
    "content, url",
    [
        ("[InternetShortcut]\r\nURL=https://example.no/a?b=1\r\n", "https://example.no/a?b=1"),
        ("see https://example.no/x for details", "https://example.no/x"),
        ("no link here", ""),
    ],
)
def test_read_url(tmp_path, content, url):
    f = tmp_path / "a.url"
    f.write_text(content, encoding="utf-8")
    assert kilder.read_url(f) == url


def test_read_extra_links(tmp_path):
    f = tmp_path / "a_annet.txt"
    f.write_text(
        '"Høring": https://example.no/h\n'
        "Vedlegg 2: https://example.no/v\n"
        "bare https://example.no/b\n"
        "nothing\n",
        encoding="utf-8",
    )
    assert kilder.read_extra_links(f) == [
        {"tittel": "Høring", "url": "https://example.no/h"},
        {"tittel": "Vedlegg 2", "url": "https://example.no/v"},
        {"tittel": "", "url": "https://example.no/b"},
    ]


def test_update_links_only_fills_empty_fields(tmp_path):
    pdf = write_pdf(tmp_path / "a.pdf")
    (tmp_path / "a.url").write_text("URL=https://drive.example/a")
    (tmp_path / "a_annet.txt").write_text("x: https://drive.example/x")

    fresh = {}
    kilder.update_links(fresh, pdf)
    assert fresh == {
        "url": "https://drive.example/a",
        "lenker": [{"tittel": "x", "url": "https://drive.example/x"}],
    }

    edited = {"url": "https://mine", "lenker": [{"tittel": "", "url": "https://mine/l"}]}
    kilder.update_links(edited, pdf)
    assert edited["url"] == "https://mine"
    assert edited["lenker"] == [{"tittel": "", "url": "https://mine/l"}]


def test_update_links_without_drive_files(tmp_path):
    entry = {}
    kilder.update_links(entry, write_pdf(tmp_path / "a.pdf"))
    assert entry == {"url": ""}


# --------------------------------------------------------------------------- text


def test_clean_text():
    raw = "Bom­fast info  \n\n\n\nÉn linje\t\n"
    assert kilder.clean_text(raw) == "Bomfast info\n\nÉn linje\n"


class FakePage:
    def __init__(self, text: str, label: str = "") -> None:
        self.text, self.label = text, label

    def get_text(self) -> str:
        return self.text

    def get_label(self) -> str:
        return self.label


def page(top: str, body: str = "body", bottom: str = "") -> FakePage:
    return FakePage("\n".join(x for x in (top, body, bottom) if x))


def test_printed_page_numbers_uses_labels():
    doc = [FakePage("x", "i"), FakePage("x", "ii"), FakePage("x", "1")]
    assert kilder.printed_page_numbers(doc) == ["i", "ii", "1"]


def test_printed_page_numbers_finds_offset():
    # cover and contents without numbers, then printed 1, 2, 3, 4 on pdf pages 3-6;
    # the contents page lists "12", which must not be taken as a page number.
    doc = [
        page("Cover"),
        page("Innhold", "Kapittel", "12"),
        page("1"),
        page("Tekst", "x", "2"),
        page("3"),
        page("Tekst", "x", "4"),
    ]
    assert kilder.printed_page_numbers(doc) == ["", "", "1", "2", "3", "4"]


def test_printed_page_numbers_without_clear_numbering():
    doc = [page("Tekst"), page("7"), page("Tekst"), page("Tekst")]
    assert kilder.printed_page_numbers(doc) == ["", "", "", ""]


# --------------------------------------------------------------------------- kilder.yaml


def test_yaml_round_trip_orders_fields_and_ids(tmp_path):
    entries = {
        "b": {"mine": "x", "sha256": "s", "id": "b", "tittel": "Bø"},
        "a": {"tittel": "Å", "id": "a", "hentet": dt.date(2026, 1, 2)},
    }
    path = tmp_path / "kilder.yaml"
    kilder.write_yaml(path, entries)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# cspell:disable\n")
    assert "Bø" in text  # allow_unicode, not escaped
    items = yaml.safe_load(text)
    assert [e["id"] for e in items] == ["a", "b"]
    assert list(items[1]) == ["id", "tittel", "sha256", "mine"]  # FIELD_ORDER, then own
    assert kilder.read_yaml(path) == entries


def test_read_yaml_missing_empty_and_junk(tmp_path):
    assert kilder.read_yaml(tmp_path / "none.yaml") == {}
    f = tmp_path / "k.yaml"
    f.write_text("# only a comment\n")
    assert kilder.read_yaml(f) == {}
    f.write_text("- id: a\n- {tittel: no id}\n- just text\n")
    assert kilder.read_yaml(f) == {"a": {"id": "a"}}


def test_save_yaml(tmp_path, capsys):
    path = tmp_path / "top" / "kilder.yaml"
    kilder.save_yaml(path, {}, {}, dry_run=False)
    assert not path.exists() and not path.parent.exists()  # nothing to record

    entries = {"a": {"id": "a"}}
    kilder.save_yaml(path, entries, {}, dry_run=True)
    assert not path.exists()
    assert "would be written (1 entries added)" in capsys.readouterr().out

    kilder.save_yaml(path, entries, {}, dry_run=False)
    assert kilder.read_yaml(path) == entries
    mtime = path.stat().st_mtime_ns
    kilder.save_yaml(path, entries, entries, dry_run=False)
    assert path.stat().st_mtime_ns == mtime
    assert "no changes, file not rewritten" in capsys.readouterr().out


# --------------------------------------------------------------------------- ids and moves


def test_assign_ids(tmp_path):
    top = tmp_path / "101_x"
    pdfs = [
        write_pdf(top / "a.pdf"),
        write_pdf(top / "s1" / "dup.pdf"),
        write_pdf(top / "s2" / "dup.pdf"),
        write_pdf(top / "kept_elsewhere.pdf"),
        write_pdf(top / "s3" / "taken.pdf"),
    ]
    entries = {
        # existing file keeps its id, even if it is not the stem
        "old_id": {"id": "old_id", "fil": "kept_elsewhere.pdf"},
        # an entry without fil (e.g. links-only, or from ppkilder) blocks its id
        "taken": {"id": "taken"},
    }
    ids = {p.relative_to(top).as_posix(): i for p, i in kilder.assign_ids(pdfs, top, entries).items()}
    assert ids == {
        "a.pdf": "a",
        "s1/dup.pdf": "s1__dup",
        "s2/dup.pdf": "s2__dup",
        "kept_elsewhere.pdf": "old_id",
        "s3/taken.pdf": "s3__taken",
    }


def test_assign_ids_reuses_id_of_vanished_file(tmp_path):
    top = tmp_path / "101_x"
    pdf = write_pdf(top / "new_sub" / "a.pdf")
    entries = {"a": {"id": "a", "fil": "old_sub/a.pdf"}}  # gone from Drive
    assert kilder.assign_ids([pdf], top, entries) == {pdf: "a"}


@pytest.mark.parametrize(
    "file, sub, inside",
    [
        ("a/b.pdf", "", True),
        ("a/b.pdf", "a", True),
        ("a/b.pdf", "a/", True),
        ("ab/c.pdf", "a", False),
        ("a.pdf", "a.pdf", True),
    ],
)
def test_in_scope(file, sub, inside):
    assert kilder.in_scope(file, sub) is inside


def test_split_folder():
    assert kilder.split_folder("101_x/a/b/") == ("101_x", "a/b")
    assert kilder.split_folder("/101_x") == ("101_x", "")


def test_detect_moves_prefers_same_name(tmp_path):
    top = tmp_path / "101_x"
    content = "%PDF same content"
    on_drive = {
        rel: write_pdf(top / rel, content)
        for rel in ("copy_of_a.pdf", "new/a.pdf", "unrelated.pdf")
    }
    on_drive["unrelated.pdf"].write_text("%PDF other")
    entries = {
        "a": {"id": "a", "fil": "old/a.pdf", "sha256": kilder.sha256(on_drive["new/a.pdf"])},
        "here": {"id": "here", "fil": "unrelated.pdf", "sha256": "x"},
        "nofile": {"id": "nofile"},
    }
    assert kilder.detect_moves(on_drive, entries) == {"new/a.pdf": "a"}


def test_detect_moves_rename(tmp_path):
    pdf = write_pdf(tmp_path / "renamed.pdf")
    entries = {"orig": {"id": "orig", "fil": "orig.pdf", "sha256": kilder.sha256(pdf)}}
    assert kilder.detect_moves({"renamed.pdf": pdf}, entries) == {"renamed.pdf": "orig"}


def test_move_text_rewrites_source_line_and_cleans_up(tmp_path):
    target = tmp_path / "101_x"
    old = target / "tekst" / "a" / "b" / "doc.md"
    old.parent.mkdir(parents=True)
    old.write_text("<!--\nkilde: a/b/doc.pdf\n-->\nkilde: body stays\n", encoding="utf-8")
    (target / "tekst" / "keep.md").write_text("x")
    new = target / "tekst" / "c" / "doc2.md"

    kilder.move_text(target, "tekst/a/b/doc.md", new, "c/doc2.pdf")

    assert new.read_text(encoding="utf-8") == (
        "<!--\nkilde: c/doc2.pdf\n-->\nkilde: body stays\n"
    )
    assert not (target / "tekst" / "a").exists()  # empty folders removed
    assert (target / "tekst").is_dir()


def test_move_text_missing_source_is_a_no_op(tmp_path):
    new = tmp_path / "tekst" / "x.md"
    kilder.move_text(tmp_path, "tekst/none.md", new, "x.pdf")
    assert not new.exists()


def test_sha256_is_cached_per_mtime(tmp_path):
    pdf = write_pdf(tmp_path / "a.pdf", "one")
    first = kilder.sha256(pdf)
    pdf.write_text("two")  # same size, new mtime
    import os

    st = pdf.stat()
    os.utime(pdf, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert kilder.sha256(pdf) != first


# --------------------------------------------------------------------------- export, safety


def test_export_entry():
    entry = {
        "id": "a",
        "fil": "secret/a.pdf",
        "tittel": "T",
        "url": "",
        "arkiv": "skip",
        "lenker": [],
        "hentet": dt.date(2026, 3, 4),
        "merknad": "private note",
        "sha256": "s",
    }
    assert kilder.export_entry(entry) == {"id": "a", "tittel": "T", "hentet": "2026-03-04"}


def test_check_sources_dir_refuses_public_repo(tmp_path):
    with pytest.raises(SystemExit, match="inside the public"):
        kilder.check_sources_dir(kilder.REPO / "kilder")
    with pytest.raises(SystemExit, match="not found"):
        kilder.check_sources_dir(tmp_path / "missing")
    kilder.check_sources_dir(tmp_path)  # fine
