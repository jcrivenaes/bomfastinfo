"""Duplicate PDFs (same sha256 in several entries)."""

from __future__ import annotations

import ppkilder
from test_ppkilder_commands import Paperpile

SAME = "%PDF-1.4 the same report"


def dup_lines(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("DUPLICATE ")]


# --------------------------------------------------------------------------- helpers


def test_checksum_index_and_groups(sources):
    ppkilder.write_yaml(
        sources / "001_a" / "kilder.yaml",
        {
            "x": {"id": "x", "sha256": "s1"},
            "y": {"id": "y", "sha256": "s2"},
            "links": {"id": "links"},  # no checksum: never a duplicate
        },
    )
    ppkilder.write_yaml(
        sources / "002_b" / "kilder.yaml",
        {"z": {"id": "z", "sha256": "s1", "paperpile": "All Papers/z.pdf"}},
    )
    index = ppkilder.checksum_index()
    assert [[(t, e["id"]) for t, e in g] for g in ppkilder.duplicate_groups(index)] == [
        [("001_a", "x"), ("002_b", "z")]
    ]
    assert ppkilder.same_pdf_as(index["s1"]) == "same PDF as x (001_a, not from Paperpile), z (002_b)"

    # `current` replaces what is on disk for that top folder
    index = ppkilder.checksum_index({"001_a": {"y": {"id": "y", "sha256": "s1"}}})
    assert [e["id"] for _t, e in index["s1"]] == ["y", "z"]
    assert "s2" not in index


def test_other_copies():
    a = {"id": "a", "sha256": "s"}
    stale = {"id": "b", "sha256": "changed since"}
    same_id_elsewhere = {"id": "a", "sha256": "s"}
    index = {"s": [("001", a), ("001", stale), ("002", same_id_elsewhere)]}
    assert ppkilder.other_copies(index, "s", "001", a) == [("002", same_id_elsewhere)]
    assert ppkilder.other_copies(index, "s", "001", {"id": "a"}) == [("002", same_id_elsewhere)]
    assert ppkilder.other_copies(index, "none", "001", a) == []


# --------------------------------------------------------------------------- commands


def test_paperpile_copy_of_an_entry_not_from_paperpile(sources, tmp_path, conversions, capsys):
    pp = Paperpile(tmp_path / "Paperpile")
    pp.add("regjeringen_2017--ntp", top="005_budsjett", url="https://x")
    pdf = pp.root / "All Papers" / "regjeringen_2017--ntp.pdf"
    pdf.write_text(SAME)
    # e.g. written by hand, or left from the old Drive-based kilder.py
    ppkilder.write_yaml(
        sources / "001_ntp" / "kilder.yaml",
        {"ntp": {"id": "ntp", "url": "https://n", "sha256": ppkilder.sha256(pdf)}},
    )

    ppkilder.cmd_convert(pp.root, pp.bib, [], set(), False)
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  regjeringen_2017--ntp: same PDF as ntp (001_ntp, not from Paperpile); "
        "kept as its own entry"
    ]

    assert ppkilder.cmd_check(pp.root, pp.bib, []) == 0
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE      regjeringen_2017--ntp: same PDF as ntp (001_ntp, not from Paperpile)"
    ]


def test_paperpile_copies_in_one_run_and_gone_entries(sources, tmp_path, conversions, capsys):
    pp = Paperpile(tmp_path / "Paperpile")
    pp.add("a", url="https://x")
    pp.add("b", url="https://x")
    for key in ("a", "b"):
        (pp.root / "All Papers" / f"{key}.pdf").write_text(SAME)

    ppkilder.cmd_convert(pp.root, pp.bib, [], set(), False)
    assert dup_lines(capsys.readouterr().out) == [
        "DUPLICATE  b: same PDF as a (001_ntp); kept as its own entry"
    ]

    ppkilder.cmd_check(pp.root, pp.bib, ["002_other"])
    assert dup_lines(capsys.readouterr().out) == []  # out of scope

    pp.remove("b")  # removed from Paperpile: gone, not a duplicate any more
    ppkilder.cmd_check(pp.root, pp.bib, [])
    out = capsys.readouterr().out
    assert dup_lines(out) == [] and "GONE           b" in out
