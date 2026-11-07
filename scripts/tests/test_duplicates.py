"""Duplicate PDFs (same sha256 in several entries), in kilder.py and ppkilder.py."""

from __future__ import annotations

import kilder
import ppkilder
from conftest import write_pdf
from test_ppkilder_commands import Paperpile

SAME = "%PDF-1.4 the same report"


def entries(sources, top):
    return kilder.read_yaml(sources / top / "kilder.yaml")


def dup_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("DUPLICATE ")]


# --------------------------------------------------------------------------- helpers


def test_checksum_index_and_groups(sources):
    kilder.write_yaml(
        sources / "001_a" / "kilder.yaml",
        {
            "x": {"id": "x", "sha256": "s1"},
            "y": {"id": "y", "sha256": "s2"},
            "links": {"id": "links"},  # no checksum: never a duplicate
        },
    )
    kilder.write_yaml(
        sources / "002_b" / "kilder.yaml",
        {"z": {"id": "z", "sha256": "s1", "paperpile": "All Papers/z.pdf"}},
    )
    index = kilder.checksum_index()
    assert [[(t, e["id"]) for t, e in g] for g in kilder.duplicate_groups(index)] == [
        [("001_a", "x"), ("002_b", "z")]
    ]
    assert kilder.same_pdf_as(index["s1"]) == "same PDF as x (001_a, Drive), z (002_b, Paperpile)"

    # `current` replaces what is on disk for that top folder
    index = kilder.checksum_index({"001_a": {"y": {"id": "y", "sha256": "s1"}}})
    assert [e["id"] for _t, e in index["s1"]] == ["y", "z"]
    assert "s2" not in index


def test_other_copies():
    a = {"id": "a", "sha256": "s"}
    stale = {"id": "b", "sha256": "changed since"}
    same_id_elsewhere = {"id": "a", "sha256": "s"}
    index = {"s": [("001", a), ("001", stale), ("002", same_id_elsewhere)]}
    assert kilder.other_copies(index, "s", "001", a) == [("002", same_id_elsewhere)]
    assert kilder.other_copies(index, "s", "001", {"id": "a"}) == [("002", same_id_elsewhere)]
    assert kilder.other_copies(index, "none", "001", a) == []


# --------------------------------------------------------------------------- kilder.py


def test_kilder_convert_notices_copies(sources, drive, conversions, capsys):
    top = drive / "101_x"
    write_pdf(top / "s1" / "rapport.pdf", SAME)
    write_pdf(top / "s2" / "kopi.pdf", SAME)
    write_pdf(top / "other.pdf")

    kilder.cmd_convert(drive, "101_x", set(), dry_run=True)
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  s2/kopi.pdf: same PDF as rapport (101_x, Drive); kept as its own entry"
    ]

    kilder.cmd_convert(drive, "101_x", set(), dry_run=False)
    out = capsys.readouterr().out
    assert len(dup_lines(out)) == 1
    assert "DUPLICATE     1" in out  # in the summary
    assert set(entries(sources, "101_x")) == {"rapport", "kopi", "other"}  # both kept

    kilder.cmd_convert(drive, "101_x", set(), dry_run=False)
    assert dup_lines(capsys.readouterr().out) == []  # convert only tells once; check tells


def test_kilder_convert_notices_changed_pdf_matching_another(sources, drive, conversions, capsys):
    top = drive / "101_x"
    write_pdf(top / "a.pdf", SAME)
    b = write_pdf(top / "b.pdf", "%PDF b")
    kilder.cmd_convert(drive, "101_x", set(), False)
    b.write_text(SAME)  # b changes and now has the same content as a
    capsys.readouterr()

    kilder.cmd_convert(drive, "101_x", set(), False)

    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  b.pdf: same PDF as a (101_x, Drive); kept as its own entry"
    ]


def test_kilder_check_reports_a_notice_not_an_issue(sources, drive, conversions, capsys):
    write_pdf(drive / "101_x" / "a.pdf", SAME)
    write_pdf(drive / "101_x" / "sub" / "b.pdf", SAME)
    write_pdf(drive / "102_y" / "c.pdf", SAME)
    for top in ("101_x", "102_y"):
        kilder.cmd_convert(drive, top, set(), False)
        e = entries(sources, top)
        for entry in e.values():
            entry["url"] = "https://example.no"
        kilder.write_yaml(sources / top / "kilder.yaml", e)
    capsys.readouterr()

    assert kilder.cmd_check(drive, "101_x") == 0
    out = capsys.readouterr().out
    assert dup_lines(out) == [
        "DUPLICATE      a: same PDF as b (101_x, Drive), c (102_y, Drive)"
    ]  # one line per group, across top folders
    assert out.rstrip().endswith("OK")

    # only groups with an entry in scope are reported
    assert kilder.cmd_check(drive, "101_x/sub") == 0
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE      b: same PDF as a (101_x, Drive), c (102_y, Drive)"
    ]


def test_kilder_prune_does_not_report_removed_copies(sources, drive, conversions, capsys):
    top = drive / "101_x"
    write_pdf(top / "a.pdf", SAME)
    write_pdf(top / "b.pdf", SAME)
    kilder.cmd_convert(drive, "101_x", set(), False)
    (top / "b.pdf").unlink()  # the copy is deleted on Drive
    capsys.readouterr()

    kilder.cmd_check(drive, "101_x", prune=True)

    assert dup_lines(capsys.readouterr().out) == []
    assert set(entries(sources, "101_x")) == {"a"}


# --------------------------------------------------------------------------- ppkilder.py


def test_paperpile_copy_of_a_drive_pdf(sources, drive, tmp_path, conversions, capsys):
    write_pdf(drive / "001_ntp" / "ntp.pdf", SAME)
    kilder.cmd_convert(drive, "001_ntp", set(), False)
    pp = Paperpile(tmp_path / "Paperpile")
    pp.add("regjeringen_2017--ntp", top="005_budsjett", url="https://x")
    (pp.root / "All Papers" / "regjeringen_2017--ntp.pdf").write_text(SAME)
    capsys.readouterr()

    ppkilder.cmd_convert(pp.root, pp.bib, [], set(), False)
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  regjeringen_2017--ntp: same PDF as ntp (001_ntp, Drive); "
        "kept as its own entry"
    ]

    assert ppkilder.cmd_check(pp.root, pp.bib, []) == 0
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE      regjeringen_2017--ntp: same PDF as ntp (001_ntp, Drive)"
    ]
    # kilder.py sees the same pair from its side
    kilder.cmd_check(drive, "001_ntp")
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE      ntp: same PDF as regjeringen_2017--ntp (005_budsjett, Paperpile)"
    ]


def test_paperpile_copies_in_one_run_and_gone_entries(sources, tmp_path, conversions, capsys):
    pp = Paperpile(tmp_path / "Paperpile")
    pp.add("a", url="https://x")
    pp.add("b", url="https://x")
    for key in ("a", "b"):
        (pp.root / "All Papers" / f"{key}.pdf").write_text(SAME)

    ppkilder.cmd_convert(pp.root, pp.bib, [], set(), False)
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  b: same PDF as a (001_ntp, Paperpile); kept as its own entry"
    ]

    ppkilder.cmd_check(pp.root, pp.bib, ["002_other"])
    assert dup_lines(capsys.readouterr().out) == []  # out of scope

    pp.remove("b")  # removed from Paperpile: gone, not a duplicate any more
    ppkilder.cmd_check(pp.root, pp.bib, [])
    out = capsys.readouterr().out
    assert dup_lines(out) == [] and "GONE           b" in out
