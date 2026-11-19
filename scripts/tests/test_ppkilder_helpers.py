"""ppkilder.py: the general helpers (formatting, kilder.yaml, text), export and archive."""

from __future__ import annotations

import datetime as dt
import os
import types

import pytest
import yaml

import ppkilder
from conftest import write_pdf

TOP = "101_x"

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
    is_public, warning = ppkilder.public_status(entry)
    assert is_public is public
    assert bool(warning) is warns


@pytest.mark.parametrize(
    "arkiv, skipped",
    [(None, False), ("", False), ("skip", True), (" SKIP ", True), ("https://x", False)],
)
def test_archive_skipped(arkiv, skipped):
    assert ppkilder.archive_skipped({"arkiv": arkiv}) is skipped


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
    assert ppkilder.human_size(n) == text


def test_show():
    assert ppkilder.show(None) == "(empty)"
    assert ppkilder.show([]) == "(empty)"
    assert ppkilder.show([{"url": "a"}]) == "1 link"
    assert ppkilder.show([1, 2]) == "2 links"
    assert ppkilder.show("abc") == "abc"
    long = ppkilder.show("x" * 100, limit=10)
    assert long == "x" * 9 + "…" and len(long) == 10


def test_changed_fields_treats_empty_values_as_equal():
    before = {"url": None, "lenker": [], "tittel": "A", "sider": 3}
    after = {"url": "", "tittel": "B", "sider": 3, "ny": "x"}
    assert ppkilder.changed_fields(before, after) == {
        "tittel": ("A", "B"),
        "ny": (None, "x"),
    }


def test_changed_fields_ignore_and_none_before():
    assert ppkilder.changed_fields(None, {"id": "a", "url": "u"}, ignore={"id"}) == {
        "url": (None, "u")
    }


def test_describe():
    text = ppkilder.describe({"url": (None, "https://a"), "tittel": ("A", "B")})
    assert text == "tittel: A -> B; url = https://a"


@pytest.mark.parametrize(
    "file, sub, inside",
    [
        ("a/b", "", True),
        ("a/b", "a", True),
        ("a/b", "a/", True),
        ("ab/c", "a", False),
        ("a", "a", True),
    ],
)
def test_in_scope(file, sub, inside):
    assert ppkilder.in_scope(file, sub) is inside


def test_sha256_is_cached_per_mtime(tmp_path):
    pdf = write_pdf(tmp_path / "a.pdf", "one")
    first = ppkilder.sha256(pdf)
    pdf.write_text("two")  # same size, new mtime
    st = pdf.stat()
    os.utime(pdf, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert ppkilder.sha256(pdf) != first


# --------------------------------------------------------------------------- text


def test_clean_text():
    raw = "Bom­fast info  \n\n\n\nÉn linje\t\n"
    assert ppkilder.clean_text(raw) == "Bomfast info\n\nÉn linje\n"


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
    assert ppkilder.printed_page_numbers(doc) == ["i", "ii", "1"]


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
    assert ppkilder.printed_page_numbers(doc) == ["", "", "1", "2", "3", "4"]


def test_printed_page_numbers_without_clear_numbering():
    doc = [page("Tekst"), page("7"), page("Tekst"), page("Tekst")]
    assert ppkilder.printed_page_numbers(doc) == ["", "", "", ""]


def test_move_text_rewrites_source_line_and_cleans_up(tmp_path):
    target = tmp_path / TOP
    old = target / "tekst" / "a" / "b" / "doc.md"
    old.parent.mkdir(parents=True)
    old.write_text("<!--\nkilde: a/b/doc.pdf\n-->\nkilde: body stays\n", encoding="utf-8")
    (target / "tekst" / "keep.md").write_text("x")
    new = target / "tekst" / "c" / "doc2.md"

    ppkilder.move_text(target, "tekst/a/b/doc.md", new, "c/doc2.pdf")

    assert new.read_text(encoding="utf-8") == (
        "<!--\nkilde: c/doc2.pdf\n-->\nkilde: body stays\n"
    )
    assert not (target / "tekst" / "a").exists()  # empty folders removed
    assert (target / "tekst").is_dir()


def test_move_text_missing_source_is_a_no_op(tmp_path):
    new = tmp_path / "tekst" / "x.md"
    ppkilder.move_text(tmp_path, "tekst/none.md", new, "x.pdf")
    assert not new.exists()


# --------------------------------------------------------------------------- kilder.yaml


def test_yaml_round_trip_orders_fields_and_ids(tmp_path):
    entries = {
        "b": {"mine": "x", "sha256": "s", "id": "b", "tittel": "Bø"},
        "a": {"tittel": "Å", "id": "a", "hentet": dt.date(2026, 1, 2)},
    }
    path = tmp_path / "kilder.yaml"
    ppkilder.write_yaml(path, entries)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# cspell:disable\n")
    assert "ppkilder.py" in text
    assert "Bø" in text  # allow_unicode, not escaped
    items = yaml.safe_load(text)
    assert [e["id"] for e in items] == ["a", "b"]
    assert list(items[1]) == ["id", "tittel", "sha256", "mine"]  # FIELD_ORDER, then own
    assert ppkilder.read_yaml(path) == entries


def test_read_yaml_missing_empty_and_junk(tmp_path):
    assert ppkilder.read_yaml(tmp_path / "none.yaml") == {}
    f = tmp_path / "k.yaml"
    f.write_text("# only a comment\n")
    assert ppkilder.read_yaml(f) == {}
    f.write_text("- id: a\n- {tittel: no id}\n- just text\n")
    assert ppkilder.read_yaml(f) == {"a": {"id": "a"}}


def test_save_yaml(tmp_path, capsys):
    path = tmp_path / "top" / "kilder.yaml"
    ppkilder.save_yaml(path, {}, {}, dry_run=False)
    assert not path.exists() and not path.parent.exists()  # nothing to record

    entries = {"a": {"id": "a"}}
    ppkilder.save_yaml(path, entries, {}, dry_run=True)
    assert not path.exists()
    assert "would be written (1 entries added)" in capsys.readouterr().out

    ppkilder.save_yaml(path, entries, {}, dry_run=False)
    assert ppkilder.read_yaml(path) == entries
    mtime = path.stat().st_mtime_ns
    ppkilder.save_yaml(path, entries, entries, dry_run=False)
    assert path.stat().st_mtime_ns == mtime
    assert "no changes, file not rewritten" in capsys.readouterr().out


def test_check_sources_dir_refuses_public_repo(tmp_path):
    with pytest.raises(SystemExit, match="inside the public"):
        ppkilder.check_sources_dir(ppkilder.REPO / "kilder")
    with pytest.raises(SystemExit, match="not found"):
        ppkilder.check_sources_dir(tmp_path / "missing")
    ppkilder.check_sources_dir(tmp_path)  # fine


# --------------------------------------------------------------------------- export


def test_export_entry():
    entry = {
        "id": "a",
        "paperpile": "All Papers/secret.pdf",
        "tittel": "T",
        "url": "",
        "arkiv": "skip",
        "lenker": [],
        "hentet": dt.date(2026, 3, 4),
        "merknad": "private note",
        "sha256": "s",
    }
    assert ppkilder.export_entry(entry) == {"id": "a", "tittel": "T", "hentet": "2026-03-04"}


def test_private_entry():
    entry = {
        "id": "a",
        "tittel": "T",
        "dokument": "D",
        "url": "https://secret",
        "arkiv": "skip",
        "lenker": [{"tittel": "", "url": "https://secret/l"}],
        "hentet": dt.date(2026, 3, 4),
        "offentlig": "nei",
    }
    assert ppkilder.private_entry(entry) == {"id": "a", "tittel": "T", "dokument": "D"}
    assert ppkilder.private_entry({"id": "b", "tittel": ""}) == {"id": "b"}


def test_export(sources, tmp_path):
    ppkilder.write_yaml(
        sources / TOP / "kilder.yaml",
        {
            "pub": {
                "id": "pub",
                "paperpile": "All Papers/p.pdf",
                "url": "https://p",
                "merknad": "NOTE-X",
                "forfatter": "AUTHOR-X",
                "sha256": "s",
            },
            "priv": {
                "id": "priv",
                "tittel": "Innsyn",
                "url": "https://secret.example",
                "arkiv": "https://web.archive.org/secret.example",
                "lenker": [{"tittel": "", "url": "https://secret.example/l"}],
                "hentet": "2026-01-01",
                "offentlig": "nei",
            },
            "unclear": {"id": "unclear", "url": "https://u.example", "offentlig": "?"},
            "nolink": {"id": "nolink", "tittel": "T"},
            "skip": {"id": "skip", "url": "https://s", "arkiv": "skip"},
        },
    )
    out = tmp_path / "data"

    assert ppkilder.cmd_export(TOP, out, dry_run=True) == 1  # warning for "unclear"
    assert not out.exists()

    assert ppkilder.cmd_export(TOP, out, dry_run=False) == 1
    text = (out / f"{TOP}.yaml").read_text(encoding="utf-8")
    assert "generert av scripts/ppkilder.py export" in text
    assert yaml.safe_load(text) == [
        {"id": "nolink", "tittel": "T"},  # no link: exported, cited as plain text
        {"id": "priv", "tittel": "Innsyn"},  # private: title only
        {"id": "pub", "url": "https://p"},
        {"id": "skip", "url": "https://s"},
        {"id": "unclear"},  # unclear offentlig counts as private
    ]
    for secret in ("secret.example", "u.example", "NOTE-X", "AUTHOR-X", "p.pdf", "2026-01-01"):
        assert secret not in text


def test_export_removes_the_link_when_an_entry_becomes_private(sources, tmp_path):
    out = tmp_path / "data"
    yaml_file = sources / TOP / "kilder.yaml"
    ppkilder.write_yaml(yaml_file, {"a": {"id": "a", "tittel": "A", "url": "https://a"}})
    ppkilder.cmd_export(TOP, out, dry_run=False)
    ppkilder.write_yaml(
        yaml_file, {"a": {"id": "a", "tittel": "A", "url": "https://a", "offentlig": "nei"}}
    )

    ppkilder.cmd_export(TOP, out, dry_run=False)

    assert yaml.safe_load((out / f"{TOP}.yaml").read_text(encoding="utf-8")) == [
        {"id": "a", "tittel": "A"}
    ]


def test_export_empty_list_creates_no_file(sources, tmp_path):
    ppkilder.write_yaml(sources / TOP / "kilder.yaml", {})
    assert ppkilder.cmd_export(TOP, tmp_path / "data", dry_run=False) == 0
    assert not (tmp_path / "data").exists()


def test_export_rejects_subfolder_and_missing_list(sources, tmp_path):
    with pytest.raises(SystemExit, match="top folders only"):
        ppkilder.cmd_export(f"{TOP}/sub", tmp_path, dry_run=True)
    with pytest.raises(SystemExit, match="not found"):
        ppkilder.cmd_export("999_none", tmp_path, dry_run=True)


def run_main(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["ppkilder.py", *args])
    return ppkilder.main()


def test_main_export_all_needs_no_mirror(sources, tmp_path, monkeypatch):
    """export (and archive) read kilder.yaml only: no Paperpile mount, no .bib file."""
    ppkilder.write_yaml(sources / "001_a" / "kilder.yaml", {"a": {"id": "a", "url": "https://a"}})
    ppkilder.write_yaml(sources / "002_b" / "kilder.yaml", {"b": {"id": "b", "url": "https://b"}})
    out = tmp_path / "data"
    rc = run_main(
        monkeypatch,
        "--paperpile", str(tmp_path / "not-mounted"),
        "--sources", str(sources),
        "export", "--out", str(out),
    )  # fmt: skip
    assert rc == 0
    assert sorted(p.name for p in out.iterdir()) == ["001_a.yaml", "002_b.yaml"]

    rc = run_main(monkeypatch, "--sources", str(sources), "export", "002_b", "--out", str(out), "-n")
    assert rc == 0


# --------------------------------------------------------------------------- archive


@pytest.fixture
def wayback(monkeypatch):
    """A fake check_links_wayback: snapshots for the urls in `found`, none for others."""
    found: dict[str, str] = {}
    looked_up: list[str] = []

    def find_wayback(url, timeout, ua, context):
        looked_up.append(url)
        return (found.get(url), "", 200, "test") if url in found else (None, "", 0, "")

    helpers = types.SimpleNamespace(DEFAULT_USER_AGENT="test", find_wayback=find_wayback)
    monkeypatch.setattr(ppkilder, "load_wayback_helpers", lambda: helpers)
    return types.SimpleNamespace(found=found, looked_up=looked_up)


def archive_entries(sources):
    ppkilder.write_yaml(
        sources / TOP / "kilder.yaml",
        {
            "hit": {"id": "hit", "url": "https://hit"},
            "miss": {"id": "miss", "url": "https://miss"},
            "kept": {"id": "kept", "url": "https://kept", "arkiv": "https://mine"},
            "skip": {"id": "skip", "url": "https://skip", "arkiv": "skip"},
            "priv": {"id": "priv", "url": "https://priv", "offentlig": "nei"},
            "nourl": {"id": "nourl"},
            "wb": {"id": "wb", "url": "https://web.archive.org/web/1/x"},
        },
    )


def test_archive_fills_only_empty_public_fields(sources, wayback, capsys):
    archive_entries(sources)
    wayback.found["https://hit"] = "https://web.archive.org/web/2020/https://hit"

    assert ppkilder.cmd_archive(TOP, save=False, dry_run=False, delay=0, timeout=1) == 1

    assert sorted(wayback.looked_up) == ["https://hit", "https://miss"]
    e = ppkilder.read_yaml(sources / TOP / "kilder.yaml")
    assert e["hit"]["arkiv"] == "https://web.archive.org/web/2020/https://hit"
    assert "arkiv" not in e["miss"]
    assert e["kept"]["arkiv"] == "https://mine"
    assert e["skip"]["arkiv"] == "skip"
    assert "arkiv" not in e["priv"]
    out = capsys.readouterr().out
    assert "NO SNAPSHOT miss" in out
    assert "1 arkiv field filled in" in out


def test_archive_dry_run_writes_nothing(sources, wayback):
    archive_entries(sources)
    wayback.found["https://hit"] = "https://web.archive.org/web/2020/https://hit"
    before = (sources / TOP / "kilder.yaml").read_text()

    ppkilder.cmd_archive(TOP, save=True, dry_run=True, delay=0, timeout=1)

    assert (sources / TOP / "kilder.yaml").read_text() == before


def test_archive_rejects_subfolder_and_missing_list(sources, wayback):
    with pytest.raises(SystemExit, match="top folders only"):
        ppkilder.cmd_archive(f"{TOP}/sub", False, True, 0, 1)
    with pytest.raises(SystemExit, match="missing or empty"):
        ppkilder.cmd_archive("999_none", False, True, 0, 1)
