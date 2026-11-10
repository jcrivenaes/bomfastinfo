"""Unit tests for ppkilder.py: BibTeX parsing, LaTeX decoding and the entry helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

import kilder
import ppkilder
from conftest import write_pdf

# --------------------------------------------------------------------------- parse_bib


def test_parse_bib_values():
    text = """
@article{key_one,
  title = {A {Protected} title, with \\{escaped\\} braces},
  author = "Doe, Jane and Roe, R.",
  year = 2024,
  note = "first " # {second} # third,
  abstract = {wrapped
      over    lines},
}

@misc{key-two, url = {https://example.no/a?b=c&d}}
"""
    entries = ppkilder.parse_bib(text)
    assert [k for k, _ in entries] == ["key_one", "key-two"]
    fields = entries[0][1]
    assert fields["title"] == "A {Protected} title, with \\{escaped\\} braces"
    assert fields["author"] == "Doe, Jane and Roe, R."
    assert fields["year"] == "2024"
    assert fields["note"] == "first secondthird"
    assert fields["abstract"] == "wrapped over lines"
    assert entries[1][1] == {"url": "https://example.no/a?b=c&d"}


def test_parse_bib_field_names_are_lowercase():
    [(_, fields)] = ppkilder.parse_bib("@Book{k, Title = {T}, YEAR = {1999}}")
    assert fields == {"title": "T", "year": "1999"}


def test_parse_bib_empty():
    assert ppkilder.parse_bib("") == []
    assert ppkilder.parse_bib("\n  \n") == []


@pytest.mark.parametrize(
    "text, message",
    [
        ("junk before\n@misc{k, title={T}}", "line 1: not a complete entry"),
        ("@misc{k, title={T}}\n@article{broken", "line 2: not a complete entry"),
        ("@misc{k, title={never {closed}\n", "value is never closed"),
        ("@misc{k, title={T}\n", "line 2: expected a field"),  # entry never closed
        ('@misc{k, title="never closed}\n', "value is never closed"),
        ("@misc{k, title={T} junk}", "expected a field"),
        ("@misc{k, title=, year={1}}", "expected a value"),
    ],
)
def test_parse_bib_rejects_broken_exports(text, message):
    # A broken export must stop the run: a lost entry would look gone to prune.
    with pytest.raises(ppkilder.BibError, match=message):
        ppkilder.parse_bib(text)


# --------------------------------------------------------------------------- unlatex


@pytest.mark.parametrize(
    "latex, text",
    [
        (r"Bj{\o}rnafjorden", "Bjørnafjorden"),
        (r"Bj\o rnafjorden", "Bjørnafjorden"),
        (r"{\AA}dland", "Ådland"),
        (r"\AA dland", "Ådland"),
        (r"Tr{\ae}", "Træ"),
        (r"Caf\'e", "Café"),
        (r"Caf\'{e}", "Café"),
        (r"Sch{\"o}n", "Schön"),
        (r'Sch\"{o}n', "Schön"),
        (r"\v{c}esky", "česky"),
        (r"Fran\c cois", "François"),
        (r"na\"{\i}ve", "naïve"),
        (r"\textit{Rapport} nr. 3", "Rapport nr. 3"),
        (r"{NTP} 2025\_2036", "NTP 2025_2036"),
        (r"50\% \& mer", "50% & mer"),
        (r"\url{https://example.no/a_b}", "https://example.no/a_b"),
        (r'say \"hi\"', 'say "hi"'),
        ("plain text", "plain text"),
    ],
)
def test_unlatex(latex, text):
    assert ppkilder.unlatex(latex) == text


# --------------------------------------------------------------------------- metadata


def test_bib_metadata():
    meta = ppkilder.bib_metadata(
        {
            "title": r"Konseptvalgutgreiing for {E39} Stord{\textendash}Os",
            "author": r"Statens vegvesen and {Bj{\o}rn} Hansen",
            "year": "2016",
            "url": "https://example.no/kvu",
        }
    )
    assert meta == {
        "tittel": "Konseptvalgutgreiing for E39 StordOs",
        "forfatter": "Statens vegvesen; Bjørn Hansen",
        "aar": 2016,
        "url": "https://example.no/kvu",
    }


def test_bib_metadata_url_fallbacks():
    assert ppkilder.bib_metadata({"url": "undefined"})["url"] == ""
    meta = ppkilder.bib_metadata({"howpublished": r"\url{https://example.no/x\_y}"})
    assert meta["url"] == "https://example.no/x_y"
    assert ppkilder.bib_metadata({"year": "2020?"})["aar"] == "2020?"
    assert ppkilder.bib_metadata({}) == {"tittel": "", "forfatter": "", "aar": "", "url": ""}


@pytest.mark.parametrize(
    "path, ok",
    [
        ("All Papers/A/a.pdf", True),
        ("001_ntp", True),
        ("../etc/passwd", False),
        ("a/./b", False),
        ("a//b", False),
        ("/abs", False),
        ("", False),
    ],
)
def test_safe_parts(path, ok):
    assert ppkilder.safe_parts(path) is ok


# --------------------------------------------------------------------------- read_sources


def bib_entry(key, keywords="", file="", **fields):
    parts = [f"@misc{{{key},"]
    if keywords:
        parts.append(f"  keywords = {{{keywords}}},")
    if file:
        parts.append(f"  file = {{{file}}},")
    parts += [f"  {k} = {{{v}}}," for k, v in fields.items()]
    return "\n".join(parts) + "\n}\n"


def test_read_sources(tmp_path, capsys):
    bib = tmp_path / "x.bib"
    bib.write_text(
        bib_entry(
            "good",
            r"bomfast-kilder; 001\_ntp; NTP; Rogfast; NTP",
            r"All Papers/G/good.pdf;All Papers/G/vedlegg.xlsx",
            title="Good",
        )
        + bib_entry("noslabel", "NTP")  # neither top label nor bomfast-kilder: ignored
        + bib_entry("notop", "bomfast-kilder")
        + bib_entry("two", r"001\_a;002\_b")
        + bib_entry("nested", r"001\_ntp/sub")
        + bib_entry("badfile", r"001\_ntp", "../outside.pdf")
        + bib_entry("notpdf", r"001\_ntp", "All Papers/x.docx")
        + bib_entry("twice", r"001\_ntp")  # citekey used twice: both rejected
        + bib_entry("twice", r"001\_ntp", "All Papers/t.pdf")
        + bib_entry("web", r"002\_web", url="https://example.no"),
        encoding="utf-8",
    )
    sources, in_bib, skipped, raw, held = ppkilder.read_sources(bib)

    assert [s.id for s in sources] == ["good", "web"]
    good = sources[0]
    assert (good.top, good.pdf, good.attachments, good.topics) == (
        "001_ntp",
        "All Papers/G/good.pdf",
        ["All Papers/G/vedlegg.xlsx"],
        ["NTP", "Rogfast"],
    )
    assert good.tekst == "tekst/good.md"
    assert sources[1].pdf == ""
    # unusable entries still count as "in the .bib file", so prune keeps them
    assert in_bib == {
        "good", "web", "notop", "two", "nested", "badfile", "notpdf", "twice"
    }
    assert skipped == {"WARNING": 6, "IGNORED": 1}
    assert raw == bib.read_bytes()
    out = capsys.readouterr().out
    assert "several top folder labels: 001_a, 002_b" in out
    assert "the citekey is used 2 times" in out
    assert held == {"twice": ppkilder.Held()}


@pytest.mark.parametrize("private_first", [True, False])
def test_read_sources_rejects_every_occurrence_of_a_duplicate_citekey(
    tmp_path, capsys, private_first
):
    """Entry order must not decide whether _PRIVAT on one of the copies counts."""
    public = bib_entry("dup", r"001\_ntp", "All Papers/d.pdf")
    private = bib_entry("dup", r"001\_ntp; \_PRIVAT", "All Papers/d.pdf")
    bib = tmp_path / "x.bib"
    bib.write_text(
        (private + public if private_first else public + private)
        + bib_entry("other", r"001\_ntp"),
        encoding="utf-8",
    )
    sources, in_bib, skipped, _raw, held = ppkilder.read_sources(bib)

    assert [s.id for s in sources] == ["other"]
    assert in_bib == {"dup", "other"}  # prune keeps the existing entry
    assert skipped == {"WARNING": 1}
    assert "dup: the citekey is used 2 times" in capsys.readouterr().out
    assert held == {"dup": ppkilder.Held(private=True, no_archive=True)}


@pytest.mark.parametrize(
    "content, message",
    [
        (None, "BibTeX file not found"),
        ("@misc{broken", "Cannot read"),
        ("", "No sources with a top folder label"),
        (bib_entry("k", "NTP"), "No sources with a top folder label"),
    ],
)
def test_read_sources_refuses_unusable_exports(tmp_path, content, message):
    bib = tmp_path / "x.bib"
    if content is not None:
        bib.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        ppkilder.read_sources(bib)


# --------------------------------------------------------------------------- entries


def source(**kw):
    defaults = dict(id="k", top="001_ntp", pdf="All Papers/k.pdf", meta={})
    return ppkilder.Source(**{**defaults, **kw})


def test_apply_metadata():
    entry = {
        "id": "k",
        "paperpile": "All Papers/k.pdf",
        "bytes": 10,
        "tittel": "Old",
        "url": "https://mine",
        "emneord": ["Stale"],
        "vedlegg": ["old.xlsx"],
        "merknad": "kept",
    }
    ppkilder.apply_metadata(
        entry, source(topics=["NTP"], meta={"tittel": "New", "url": ""})
    )
    assert entry == {
        "id": "k",
        "paperpile": "All Papers/k.pdf",
        "bytes": 10,  # same PDF path: kept
        "mappe": "001_ntp",
        "tittel": "New",  # Paperpile wins
        "url": "https://mine",  # empty in the .bib: left alone
        "emneord": ["NTP"],  # always follows the labels
        "merknad": "kept",
    }


def test_apply_metadata_new_pdf_drops_bytes():
    entry = {"id": "k", "paperpile": "All Papers/old.pdf", "bytes": 10, "sha256": "s"}
    ppkilder.apply_metadata(entry, source(pdf="All Papers/new.pdf"))
    assert "bytes" not in entry
    assert entry["sha256"] == "s"  # still compared on the next run


def test_render_and_sync_header(tmp_path):
    entry = {
        "id": "k",
        "paperpile": "All Papers/k.pdf",
        "tittel": "A --> B",
        "aar": 2020,
        "emneord": ["NTP", "Rogfast"],
        "sha256": "abc",
        "sider": 2,
        "konvertert": "fake",
    }
    header = ppkilder.render_header(entry)
    assert header.startswith("<!--\nkilde: Paperpile, All Papers/k.pdf\nid: k\n")
    assert "tittel: A -> B\n" in header  # cannot close the comment early
    assert "emneord: NTP; Rogfast\n" in header
    assert "forfatter" not in header  # empty fields are left out
    assert header.endswith("-->\n")

    text = tmp_path / "k.md"
    body = "\n<!-- side pdf=1 -->\n\nBody with\n-->\nin it\n"
    text.write_text("<!--\nkilde: old\n-->\n" + body, encoding="utf-8")
    ppkilder.sync_header(text, entry)
    assert text.read_text(encoding="utf-8") == header + body
    ppkilder.sync_header(tmp_path / "missing.md", entry)  # no-op
    assert not (tmp_path / "missing.md").exists()


def test_entry_folder_and_selected():
    assert ppkilder.entry_folder("001_a", {"mappe": "002_b"}) == "002_b"
    assert ppkilder.entry_folder("001_a", {"tekst": "tekst/sub/k.md"}) == "001_a/sub"
    assert ppkilder.entry_folder("001_a", {}) == "001_a"
    assert ppkilder.selected("001_a", [])
    assert ppkilder.selected("001_a", ["002_b", "/001_a/"])
    assert not ppkilder.selected("001_ab", ["001_a"])


def test_find_renames(tmp_path):
    mirror = tmp_path / "mirror"
    by_sha = write_pdf(mirror / "All Papers" / "moved.pdf", "same bytes")
    owned = {
        "old_path": ("001_a", {"id": "old_path", "paperpile": "All Papers/p.pdf"}),
        "old_sha": ("001_a", {"id": "old_sha", "paperpile": "x", "sha256": kilder.sha256(by_sha)}),
        "still": ("001_a", {"id": "still", "paperpile": "All Papers/s.pdf"}),
    }
    sources = [
        source(id="new_path", pdf="All Papers/p.pdf"),
        source(id="new_sha", pdf="All Papers/moved.pdf"),
        source(id="still", pdf="All Papers/s.pdf"),
        source(id="nofile", pdf=""),
        source(id="theirs", pdf="All Papers/p.pdf"),
    ]
    renames = ppkilder.find_renames(
        sources, owned, {"new_path", "new_sha", "still", "nofile", "theirs"}, {"theirs": "001_a"}, mirror
    )
    assert renames == {"new_path": "old_path", "new_sha": "old_sha"}


def test_copy_bib(sources, tmp_path):
    bib = tmp_path / "export.bib"
    bib.write_bytes(b"@misc{a}")
    copy = sources / ppkilder.BIB_COPY

    ppkilder.copy_bib(bib, b"@misc{a}", write=False)
    assert not copy.exists()
    ppkilder.copy_bib(bib, b"@misc{a}", write=True)
    assert copy.read_bytes() == b"@misc{a}"
    ppkilder.copy_bib(bib, b"@misc{b}", write=True)  # what was parsed, not what is there now
    assert copy.read_bytes() == b"@misc{b}"
    ppkilder.copy_bib(copy, b"@misc{c}", write=True)  # running on the copy itself
    assert copy.read_bytes() == b"@misc{b}"


def test_lists_owned_and_foreign(sources, capsys):
    kilder.write_yaml(
        sources / "001_a" / "kilder.yaml",
        {"pp": {"id": "pp", "paperpile": "x"}, "drive": {"id": "drive", "fil": "d.pdf"}},
    )
    kilder.write_yaml(sources / "002_b" / "kilder.yaml", {"pp": {"id": "pp", "paperpile": "y"}})
    lists = ppkilder.Lists()
    assert {k: top for k, (top, _) in lists.owned().items()} == {"pp": "001_a"}
    assert "in both 001_a and 002_b" in capsys.readouterr().out
    assert lists.foreign() == {"drive": "001_a"}


def test_check_mirror(tmp_path):
    with pytest.raises(SystemExit, match="Is it mounted"):
        ppkilder.check_mirror(tmp_path)
    (tmp_path / "All Papers").mkdir()
    ppkilder.check_mirror(tmp_path)


def test_default_bib(monkeypatch, tmp_path):
    monkeypatch.delenv("BOMFAST_BIB", raising=False)
    assert ppkilder.default_bib(tmp_path) == tmp_path / "bomfast-kilder.bib"
    monkeypatch.setenv("BOMFAST_BIB", "~/x.bib")
    assert ppkilder.default_bib(tmp_path) == Path("~/x.bib").expanduser()



@pytest.mark.parametrize(
    "label, control, resembles",
    [
        ("_PRIVAT", True, None),
        ("_privat", True, None),
        ("_ABO", True, None),
        ("_PRIVATE", True, "_PRIVAT"),
        ("_annet", True, None),
        ("PRIVAT", False, "_PRIVAT"),
        ("private", False, "_PRIVAT"),
        ("prvat", False, "_PRIVAT"),
        ("ABO", False, "_ABO"),
        ("privatisering", False, None),
        ("abonnement", False, None),
        ("NTP", False, None),
    ],
)
def test_control_labels(label, control, resembles):
    assert ppkilder.is_control_label(label) is control
    assert ppkilder.resembles_control_label(label) == resembles
