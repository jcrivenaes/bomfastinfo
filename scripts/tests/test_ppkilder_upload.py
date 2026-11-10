"""ppkilder.py upload: Paperpile PDFs to archive.org, with a fake ia CLI and item."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.error
from pathlib import Path

import archive_org_upload as ia
import kilder
import ppkilder
import pytest
from test_ppkilder_commands import Paperpile, convert, entries

ITEM = "test-item"


class FakeArchive:
    """Stands in for the `ia` CLI (subprocess.run) and the item metadata API."""

    def __init__(self):
        self.files: dict[str, str] = {}  # remote name -> md5
        self.commands: list[list[str]] = []
        self.visible = True  # does an upload show up in the item metadata?

    def run(self, cmd, check=False, **kwargs):
        cmd = [str(c) for c in cmd]
        self.commands.append(cmd)
        if cmd[:2] == ["ia", "upload"] and self.visible:
            name = cmd[cmd.index("--remote-name") + 1]
            self.files[name] = hashlib.md5(Path(cmd[3]).read_bytes()).hexdigest()
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def metadata(self, item):
        assert item == ITEM
        return {"files": [{"name": n, "md5": m} for n, m in self.files.items()]}

    def uploads(self):
        return [c for c in self.commands if c[:2] == ["ia", "upload"]]


@pytest.fixture
def archive(monkeypatch):
    fake = FakeArchive()
    monkeypatch.setattr(subprocess, "run", fake.run)
    monkeypatch.setattr(ia.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ia, "item_metadata", fake.metadata)
    return fake


@pytest.fixture
def pp(tmp_path):
    return Paperpile(tmp_path / "Paperpile")


@pytest.fixture
def results(tmp_path):
    return tmp_path / "uploads_webarchive" / "results.jsonl"


def add(pp, key, **kw):
    """A source whose PDF passes ia.validate_pdf (starts with %PDF-)."""
    pp.add(key, **kw)
    path = pp.root / "All Papers" / f"{key}.pdf"
    if path.exists():
        path.write_text(f"%PDF-1.4 {key}")


def upload(pp, ids, results, really=True):
    return ppkilder.cmd_upload(pp.root, pp.bib, list(ids), really, ITEM, results)


def records(results):
    return [json.loads(line) for line in results.read_text().splitlines()]


def test_dry_run_changes_nothing(sources, pp, conversions, archive, results, capsys):
    add(pp, "a", url="https://example.no/a.pdf")
    convert(pp)
    capsys.readouterr()

    assert upload(pp, ["a"], results, really=False) == 0

    out = capsys.readouterr().out
    assert "WOULD UPLOAD a: All Papers/a.pdf" in out and f"{ITEM}/a.pdf" in out
    assert "Add --upload" in out
    assert archive.commands == [] and not results.exists()
    assert "arkiv" not in entries(sources)["a"]


def test_upload_writes_arkiv_and_results(sources, pp, conversions, archive, results, capsys):
    add(pp, "a", url="https://example.no/a.pdf", title="Rapport A")
    convert(pp)

    assert upload(pp, ["a"], results) == 0

    url = f"https://archive.org/download/{ITEM}/a.pdf"
    assert entries(sources)["a"]["arkiv"] == url
    assert "UPLOADED   a: " + url in capsys.readouterr().out
    [up] = archive.uploads()
    assert up[2] == ITEM and up[3].endswith("All Papers/a.pdf")
    assert ["ia", "metadata", ITEM, "--target", "files/a.pdf", "--modify",
            "original_url:https://example.no/a.pdf"] in archive.commands
    [rec] = records(results)
    assert rec["file_url"] == url and rec["title"] == "Rapport A"
    assert rec["sha256"] == entries(sources)["a"]["sha256"]

    # the second time: arkiv is set, so it is refused and nothing is uploaded again
    assert upload(pp, ["a"], results) == 1
    assert "REFUSED    a: arkiv already set" in capsys.readouterr().out
    assert len(archive.uploads()) == 1


@pytest.mark.parametrize(
    "setup, reason",
    [
        (lambda e: e.update(offentlig="nei"), "offentlig: nei"),
        (lambda e: e.update(offentlig="kanskje"), "offentlig: kanskje"),
        (lambda e: e.update(arkiv="skip"), "arkiv: skip"),
        (lambda e: e.update(arkiv="https://web.archive.org/x"), "arkiv already set"),
    ],
)
def test_refused_by_kilder_yaml(sources, pp, conversions, archive, results, capsys, setup, reason):
    add(pp, "a")
    convert(pp)
    e = entries(sources)
    setup(e["a"])
    kilder.write_yaml(sources / "001_ntp" / "kilder.yaml", e)
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 1

    assert f"REFUSED    a: {reason}" in capsys.readouterr().out
    assert archive.commands == []


@pytest.mark.parametrize("label", ["_PRIVAT", "_ABO", "_x"])
def test_refused_by_label_added_after_convert(sources, pp, conversions, archive, results, capsys, label):
    add(pp, "a")
    convert(pp)
    pp.items["a"]["keywords"] += f"; {label}"
    pp.write()
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 1

    out = capsys.readouterr().out
    assert "REFUSED    a: has " in out and "run convert" in out
    assert archive.commands == []


def test_refused_other_cases(sources, pp, conversions, archive, results, capsys):
    add(pp, "a")
    add(pp, "changed")
    add(pp, "web", pdf=False, url="https://example.no")
    add(pp, "gone")
    kilder.write_yaml(sources / "002_drive" / "kilder.yaml",
                      {"drive": {"id": "drive", "fil": "x.pdf", "sha256": "s"}})
    convert(pp)
    (pp.root / "All Papers" / "changed.pdf").write_text("%PDF-1.4 new content")
    pp.remove("gone")
    add(pp, "new")  # in the .bib file, never converted
    capsys.readouterr()

    assert upload(pp, ["nope", "new", "drive", "web", "gone", "changed", "a"], results,
                  really=False) == 1

    out = capsys.readouterr().out
    for line in [
        "REFUSED    nope: no such id",
        "REFUSED    new: not in kilder.yaml (run convert first)",
        "REFUSED    drive: not from Paperpile",
        "REFUSED    web: no PDF in Paperpile",
        "REFUSED    gone: not in the .bib file any more",
        "REFUSED    changed: the PDF changed since the last convert",
        "WOULD UPLOAD a: ",
    ]:
        assert line in out
    assert "6 not done" in out


def test_earlier_upload_with_same_pdf_is_linked(sources, pp, conversions, archive, results, capsys):
    add(pp, "a")
    convert(pp)
    sha = entries(sources)["a"]["sha256"]
    results.parent.mkdir()
    url = f"https://archive.org/download/{ITEM}/by-hand.pdf"
    results.write_text("not json\n" + json.dumps({"sha256": sha, "file_url": url}) + "\n")
    archive.files["by-hand.pdf"] = md5_of(pp.root / "All Papers" / "a.pdf")

    assert upload(pp, ["a"], results, really=False) == 0
    assert f"WOULD LINK a: already uploaded, {url}" in capsys.readouterr().out
    assert "arkiv" not in entries(sources)["a"]

    assert upload(pp, ["a"], results) == 0
    assert entries(sources)["a"]["arkiv"] == url
    assert archive.commands == [] and len(results.read_text().splitlines()) == 2  # nothing new


def md5_of(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def log_upload(results, sha, name):
    """Append an earlier upload of `name` in the test item to results.jsonl."""
    results.parent.mkdir(exist_ok=True)
    url = f"https://archive.org/download/{ITEM}/{name}"
    with results.open("a") as f:
        f.write(json.dumps({"sha256": sha, "file_url": url}) + "\n")
    return url


@pytest.mark.parametrize("remote_now", ["replaced", "removed"])
def test_stale_earlier_upload_is_not_linked(
    sources, pp, conversions, archive, results, capsys, remote_now
):
    """results.jsonl is history: the file may have been replaced (archive_org_upload.py
    with the same remote name) or removed on archive.org since."""
    add(pp, "a")
    convert(pp)
    old = log_upload(results, entries(sources)["a"]["sha256"], "by-hand.pdf")
    if remote_now == "replaced":
        archive.files["by-hand.pdf"] = "md5-of-another-pdf"
    capsys.readouterr()

    assert upload(pp, ["a"], results, really=False) == 0
    out = capsys.readouterr().out
    assert f"STALE      a: {old} in results.jsonl " in out and "not linked" in out
    assert "WOULD UPLOAD a: " in out and "WOULD LINK" not in out

    assert upload(pp, ["a"], results) == 0
    new = f"https://archive.org/download/{ITEM}/a.pdf"
    assert entries(sources)["a"]["arkiv"] == new
    assert len(archive.uploads()) == 1
    assert records(results)[-1]["file_url"] == new


def test_newest_matching_earlier_upload_is_linked(
    sources, pp, conversions, archive, results, capsys
):
    add(pp, "a")
    convert(pp)
    sha = entries(sources)["a"]["sha256"]
    good = log_upload(results, sha, "first.pdf")
    stale = log_upload(results, sha, "second.pdf")
    archive.files["first.pdf"] = md5_of(pp.root / "All Papers" / "a.pdf")
    archive.files["second.pdf"] = "md5-of-another-pdf"
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 0

    out = capsys.readouterr().out
    assert f"STALE      a: {stale}" in out and f"LINKED     a: already uploaded, {good}" in out
    assert entries(sources)["a"]["arkiv"] == good
    assert archive.uploads() == []


def test_stale_link_and_name_taken_is_a_conflict(
    sources, pp, conversions, archive, results, capsys
):
    """The earlier upload was a.pdf itself, replaced since: never linked or replaced."""
    add(pp, "a")
    convert(pp)
    log_upload(results, entries(sources)["a"]["sha256"], "a.pdf")
    archive.files["a.pdf"] = "md5-of-another-pdf"
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 1

    out = capsys.readouterr().out
    assert "STALE      a: " in out
    assert "FAILED     a: a.pdf is already in test-item, with other content" in out
    assert "arkiv" not in entries(sources)["a"] and archive.uploads() == []


def test_earlier_upload_cannot_be_checked(
    sources, pp, conversions, archive, results, monkeypatch, capsys
):
    add(pp, "a")
    convert(pp)
    log_upload(results, entries(sources)["a"]["sha256"], "by-hand.pdf")

    def offline(item):
        raise OSError("network down")

    monkeypatch.setattr(ia, "item_metadata", offline)
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 1

    assert "FAILED     a: cannot check the earlier upload" in capsys.readouterr().out
    assert "arkiv" not in entries(sources)["a"] and archive.uploads() == []


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("no route to host"),
        TimeoutError("timed out"),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ],
    ids=["network", "timeout", "json"],
)
def test_metadata_error_fails_one_source_and_the_batch_goes_on(
    sources, pp, conversions, archive, results, monkeypatch, capsys, error
):
    add(pp, "a")
    add(pp, "b")
    convert(pp)
    calls = []

    def flaky(item):
        calls.append(item)
        if len(calls) == 1:  # the first lookup, for a
            raise error
        return archive.metadata(item)

    monkeypatch.setattr(ia, "item_metadata", flaky)
    capsys.readouterr()

    assert upload(pp, ["a", "b"], results) == 1

    out = capsys.readouterr().out
    assert f"FAILED     a: {type(error).__name__}: " in out and "run again" in out
    assert "UPLOADED   b: " in out
    assert "arkiv" not in entries(sources)["a"]
    assert [r["document_id"] for r in records(results)] == ["b"]

    # the same command again retries a
    assert upload(pp, ["a"], results) == 0
    assert entries(sources)["a"]["arkiv"].endswith("/a.pdf")


def test_reusing_a_remote_file_without_ia_fails_one_source(
    sources, pp, conversions, archive, results, monkeypatch, capsys
):
    """original_url needs ia also when the file is already there."""
    add(pp, "a", url="https://example.no/a.pdf")
    add(pp, "b")  # no url: reusing its file needs no ia
    convert(pp)
    for key in ("a", "b"):
        archive.files[f"{key}.pdf"] = md5_of(pp.root / "All Papers" / f"{key}.pdf")
    monkeypatch.setattr(ia.shutil, "which", lambda name: None)
    capsys.readouterr()

    assert upload(pp, ["a", "b"], results) == 1

    out = capsys.readouterr().out
    assert "FAILED     a: ia CLI not found" in out
    assert "UPLOADED   b: " in out
    assert "arkiv" not in entries(sources)["a"]
    assert archive.commands == []  # ia was never run


def test_not_visible_yet_then_rerun(sources, pp, conversions, archive, results, monkeypatch, capsys):
    add(pp, "a")
    convert(pp)
    archive.visible = False
    monkeypatch.setattr(ia, "wait_for_uploaded_file", lambda *a, **k: False)

    assert upload(pp, ["a"], results) == 1
    assert "FAILED     a: uploaded, but not visible" in capsys.readouterr().out
    assert "arkiv" not in entries(sources)["a"] and not results.exists()

    # archive.org has finished: the same command finds the file and does not upload it again
    pdf = pp.root / "All Papers" / "a.pdf"
    archive.files["a.pdf"] = hashlib.md5(pdf.read_bytes()).hexdigest()
    assert upload(pp, ["a"], results) == 0
    assert entries(sources)["a"]["arkiv"].endswith("/a.pdf")
    assert len(archive.uploads()) == 1 and len(records(results)) == 1


def test_other_file_with_same_name_is_not_replaced(sources, pp, conversions, archive, results, capsys):
    add(pp, "a")
    convert(pp)
    archive.files["a.pdf"] = "someothermd5"

    assert upload(pp, ["a"], results) == 1

    assert "already in test-item, with other content; not replaced" in capsys.readouterr().out
    assert archive.uploads() == [] and "arkiv" not in entries(sources)["a"]


def test_same_pdf_twice_in_one_run_is_uploaded_once(sources, pp, conversions, archive, results):
    add(pp, "a")
    add(pp, "b")
    (pp.root / "All Papers" / "b.pdf").write_text("%PDF-1.4 a")
    convert(pp)

    assert upload(pp, ["a", "b", "a"], results) == 0  # repeated ids count once

    assert len(archive.uploads()) == 1
    e = entries(sources)
    assert e["a"]["arkiv"] == e["b"]["arkiv"]


def test_refused_when_citekey_is_used_twice(sources, pp, conversions, archive, results, capsys):
    """A second copy of the citekey with _PRIVAT must block the upload, wherever it is."""
    add(pp, "a")
    add(pp, "b")  # read_sources refuses a .bib file with no usable sources at all
    convert(pp)
    with pp.bib.open("a", encoding="utf-8") as f:
        f.write("@misc{a,\n  keywords = {001\\_ntp; \\_PRIVAT},\n}\n")
    capsys.readouterr()

    assert upload(pp, ["a"], results) == 1

    out = capsys.readouterr().out
    assert "WARNING    a: the citekey is used 2 times" in out
    assert "REFUSED    a: unusable in the .bib file" in out
    assert archive.commands == []


@pytest.mark.parametrize(
    "other_top, other",
    [
        # a kilder.py entry sorted after the Paperpile one
        ("009_drive", {"id": "a", "fil": "a.pdf", "sha256": "s"}),
        # a copy of the Paperpile entry in another folder
        ("000_copy", None),
    ],
)
def test_refused_when_id_is_in_several_lists(
    sources, pp, conversions, archive, results, capsys, other_top, other
):
    add(pp, "a")
    add(pp, "b")
    convert(pp)
    second = sources / other_top / "kilder.yaml"
    kilder.write_yaml(second, {"a": other or dict(entries(sources)["a"])})
    before = second.read_text()
    capsys.readouterr()

    assert upload(pp, ["a", "b"], results) == 1

    out = capsys.readouterr().out
    tops = ", ".join(sorted(["001_ntp", other_top]))
    assert f"REFUSED    a: in several kilder.yaml files ({tops})" in out
    assert "not from Paperpile" not in out
    assert [c[3].endswith("b.pdf") for c in archive.uploads()] == [True]  # only b
    assert second.read_text() == before  # neither copy of a got an arkiv link
    assert "arkiv" not in entries(sources)["a"]
    assert entries(sources)["b"]["arkiv"].endswith("/b.pdf")
