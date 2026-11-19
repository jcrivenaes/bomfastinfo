#!/usr/bin/env python3
# cspell:disable
"""Convert the sources in a Paperpile BibTeX export to text and maintain kilder.yaml.

Paperpile is the only place source documents are kept. Paperpile has no API, so two
things are read:
  - the .bib file from Paperpile's BibTeX workflow (profile picture -> Workflows and
    Integrations -> BibTeX export), auto-exporting only the bomfast-kilder label to Google
    Drive. Paperpile names it bomfast-kilder.bib and puts it at the top of the account that
    owns Paperpile; move it into the Paperpile folder (allowed, it keeps syncing), so it is
    shared and mounted together with the PDFs
  - the PDFs in Paperpile's mirror on Google Drive, through a local rclone mount

The text versions and kilder.yaml go into a separate PRIVATE repo (default
~/work/git/bomfast-kilder): <sources>/<top folder>/kilder.yaml and tekst/. They may hold
paywalled articles or documents obtained via innsyn, so they never go into bomfastinfo.
`export` writes a public list (only open fields of public entries) into bomfastinfo.

Usage:
    # Convert everything in the .bib file (only new or changed PDFs):
    python3 scripts/ppkilder.py convert

    # Only some folders, and/or a dry run (nothing is written):
    python3 scripts/ppkilder.py convert 001_nasjonal_transportplan_ntp
    python3 scripts/ppkilder.py convert -n

    # Force re-conversion of one source:
    python3 scripts/ppkilder.py convert --force regjeringen_2017--ntp_2018_2029

    # Check that the .bib file, the mirror and the repo agree (never writes, not even
    # the copy of the .bib file):
    python3 scripts/ppkilder.py check

    # Remove entries and text files for sources that are no longer in the .bib file:
    python3 scripts/ppkilder.py prune -n

    # Send the PDFs of some sources to archive.org (item bomfast-kildedokumenter) and
    # write the link to arkiv. A dry run unless --upload; needs `ia configure` once:
    python3 scripts/ppkilder.py upload regjeringen_2017--ntp_2018_2029
    python3 scripts/ppkilder.py upload regjeringen_2017--ntp_2018_2029 --upload

    # Fill in empty `arkiv` fields with Wayback Machine snapshots of each `url`
    # (reads kilder.yaml only, needs neither the mirror nor the .bib file):
    python3 scripts/ppkilder.py archive 001_nasjonal_transportplan_ntp
    python3 scripts/ppkilder.py archive -n
    # Also ask Wayback to capture URLs that have no snapshot yet (slow, rate-limited):
    python3 scripts/ppkilder.py archive 101_hordfast --save

    # Write the public source list for the website (data/kilder/<folder>.yaml):
    python3 scripts/ppkilder.py export
    python3 scripts/ppkilder.py export 101_hordfast -n

    Without folders, every command works on all top folders (convert/check/prune: all
    in the .bib file; archive/export: all that have a kilder.yaml).

Output:
    One line with a status tag per changed source (NEW, UPDATED, REBUILT, MOVED,
    RENAMED, METADATA, WARNING, ...), and a summary with counts at the end.
    -v/--verbose also lists unchanged sources, --log FILE appends the full output to FILE.
    With --dry-run the same lines describe what *would* happen; nothing is written.

How a .bib entry is read:
    citekey   the id, and the name of the text file: <citekey>.md. Used in the kilde
              shortcode, so it must be unique across all folders. House style:
              <who>_<year>--<what>, e.g. regjeringen_2017--ntp_2018_2029 (lowercase
              a-z and 0-9, words joined by _, the year right before --). check and
              convert report CITEKEY for others, as a notice only. A citekey used by
              several .bib entries is skipped in all of them, with a warning.
              Control labels always count, also on entries that are skipped (used
              twice, bad labels or file path, ...; _PRIVAT on one copy is enough),
              and in every kilder.yaml that has the id: convert applies them to
              existing entries before anything else, whatever folders it runs on.
    keywords  the Paperpile labels, in no particular order:
              - exactly one top folder label, three digits and _, is the destination:
                    005_statsbudsjett_samferdsel
                -> <sources>/005_statsbudsjett_samferdsel/tekst/<citekey>.md
                No subfolders. None or several such labels give a warning, and the
                source is skipped (but never removed by prune).
              - bomfast-kilder only selects what Paperpile exports, and is not stored.
              - labels starting with _ are control labels, never topics (any case):
                    _PRIVAT   offentlig: nei + arkiv: skip: not in the public list
                              (export), never sent to archive.org
                    _INNSYN   the same as _PRIVAT (documents obtained via innsyn)
                    _ABO      arkiv: skip: paywalled; in the public list with its
                              url, but never archived (a Wayback capture could
                              republish the full text)
                    _NO_URL   there is no url on purpose (e.g. not online): check
                              does not report NO URL. Does not set arkiv: skip,
                              since an upload may be the only public copy.
                    _other    arkiv: skip as well, with a warning (unknown label)
                Removing a label does NOT undo it: edit offentlig/arkiv in
                kilder.yaml for that; check reports the mismatch (NO LABEL). Run
                convert after adding a label, before export/archive. A near miss
                (PRIVAT, privat, _PRIVATE, ABO) gives a warning.
              - all other labels (NTP, Rogfast, ...) go to `emneord` in kilder.yaml.
              Entries without a top folder label or bomfast-kilder are ignored.
    file      paths in the mirror, separated by ";". The first is converted, the others
              are listed in `vedlegg`. An entry without file still gets a kilder.yaml
              entry (useful for web pages), just no text file.

kilder.yaml:
    From the .bib file: tittel, forfatter, aar, url, emneord. Paperpile is the source of
    truth for these: correct them there. An empty field in the .bib file leaves the value
    alone, except emneord, which always follows the labels.
    Technical fields: paperpile (path in the mirror), mappe (the top folder), vedlegg,
    bytes, sha256, sider, tekst, konvertert, ocr. Other fields (dokument, arkiv, lenker,
    hentet, offentlig, merknad, ...) are yours and are kept on every run. Comments in
    the YAML file are not kept.
        offentlig: nei   only id and title in the public list (no link), and never
                         archived.
                         Accepted "private" values: nei / no / false. Any other value
                         than ja / yes / true is also treated as private, with a
                         warning. Entries without the field are public.
        arkiv: skip      archive never looks up or captures the url (e.g. paywalled
                         pages, where a Wayback capture could republish the full text),
                         upload never sends the PDF, and export leaves arkiv out.
        hentet: <date>   when you retrieved the document/article (exported).

Entries not from Paperpile:
    This script only touches entries with the field `paperpile`. Entries without it
    (written by hand, or left from the old Drive-based kilder.py) are kept as they are,
    exported like the others, and counted in duplicate checks. A citekey already used
    by such an entry gives a warning, and that source is skipped.

Duplicates:
    The same PDF (same sha256) in several entries, across all top folders, is reported
    as DUPLICATE by check, prune and convert. A notice, not an issue (a report can be
    filed under two topics on purpose); nothing is merged or removed. To get rid of a
    copy, remove the bomfast-kilder label from it in Paperpile (or delete the paper),
    so it leaves the .bib export, and run prune. Removing only the top folder label is
    not enough: the entry is then unusable but still in the .bib file, and prune keeps
    it.

Public export (export):
    Writes <out>/<folder>.yaml (default <bomfastinfo>/data/kilder) with only these
    fields per entry: id, tittel, dokument, url, arkiv, lenker, hentet. Technical
    fields, merknad, file paths and your own extra fields are never exported. Every
    entry is exported, so articles can cite any source with the kilde shortcode:
      - offentlig: nei (_PRIVAT, _INNSYN): only id, tittel and dokument. The title is
        public, but never a url, arkiv or lenker. The shortcode shows it as plain text.
      - no url, arkiv or lenker (e.g. _NO_URL): exported as usual, and the shortcode
        shows the title as plain text.
    The file is only rewritten when its content changes, and not created at all if the
    kilder.yaml is empty (an existing file is then emptied, so no stale entries are left
    behind). The public file is generated: correct things in the private kilder.yaml or
    in Paperpile. Run convert first, so new control labels have been applied.

Archive links (archive):
    Looks up the closest existing Wayback snapshot of each entry's url and writes it to
    `arkiv`, but only if `arkiv` is empty: a value you wrote yourself is never
    overwritten. Entries without a url are skipped, and so are urls that already point
    to web.archive.org. With --save, urls that have no snapshot are captured with Save
    Page Now (about one request per --delay seconds; stops if archive.org answers 429).
    The lookup reuses find_wayback() from check_links_wayback.py, which also tries URL
    variants (http/https, with/without www, ...) and rejects truncated PDF captures.
    kilder.yaml is saved after every filled-in entry, so an interrupted run loses
    nothing. Entries with arkiv: skip or offentlig: nei are skipped. For PDFs that are
    gone from the web, use upload instead.

Uploading to archive.org (upload):
    For PDFs that are gone or may disappear from the publisher. Refused, per source, for:
    offentlig: nei, arkiv: skip, arkiv already set, a control label (_PRIVAT, _ABO, ...)
    in the .bib file even if convert has not run since, and a PDF that changed since the
    last convert. A PDF with the same sha256 as an earlier upload in
    uploads_webarchive/results.jsonl (also uploads made by hand with
    archive_org_upload.py) is not uploaded again: that link is written to arkiv, but only
    if archive.org still has that file with the same md5 (results.jsonl is history; a
    file replaced or removed since is reported STALE and the PDF is uploaded as usual).
    A file with the same name already in the item is only reused if its md5 matches. Each upload
    is appended to results.jsonl, and the url is recorded as original_url on archive.org.
    Commit kilder.yaml and results.jsonl afterwards. Uploads are public and permanent.

Copy of the .bib file:
    convert and prune copy the .bib file to <sources>/paperpile.bib when it has changed, so
    git shows what changed in Paperpile between runs. Only a file that was read without
    errors is copied. Commit it together with kilder.yaml and the text files. The copy is
    never read; to run on it (e.g. without Drive), use --bib <sources>/paperpile.bib.

Moves and renames:
    Change the top folder label and the text file and the entry follow. Change the citekey and the source is recognised by its checksum, so the text and
    your own fields are kept; the script then tells you to update references in articles.

Locations:
    Paperpile mirror: --paperpile or BOMFAST_PAPERPILE (default: ~/GoogleDrive/Paperpile)
    .bib file:        --bib or BOMFAST_BIB             (default: <mirror>/bomfast-kilder.bib)
    Private repo:     --sources or BOMFAST_SOURCES     (default: ~/work/git/bomfast-kilder)
    Public export:    --out (export only)              (default: <bomfastinfo>/data/kilder)
    The script refuses to use a sources folder inside the bomfastinfo repo, so the private
    texts cannot end up in the public repo by mistake.

Mounting the mirror:
    The Paperpile folder is under "Shared with me", so gdrive:bomfast does not include it:
        mkdir -p ~/GoogleDrive/Paperpile
        rclone mount gdrive:Paperpile ~/GoogleDrive/Paperpile --drive-shared-with-me \\
            --read-only --vfs-cache-mode=full --dir-cache-time=1h --poll-interval=15s

Dependencies:
    pip install pymupdf pymupdf4llm pyyaml
    # Only for scanned PDFs without a text layer:
    sudo apt install tesseract-ocr tesseract-ocr-nor
    # upload: python3 -m pip install --user internetarchive; ia configure
    # Tests: pip install pytest; python3 -m pytest scripts
    archive_org_upload.py (upload) and check_links_wayback.py (archive) must be in the
    same folder as this script.

The field names, the folder names (tekst/) and the page markers in the text files are
Norwegian on purpose: they are data that sits next to the Norwegian documents and
articles.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import archive_org_upload as ia
import yaml

REPO = Path(__file__).resolve().parent.parent  # bomfastinfo (public)
DEFAULT_SOURCES = Path(
    os.environ.get("BOMFAST_SOURCES", "~/work/git/bomfast-kilder")
).expanduser()
DEFAULT_EXPORT = REPO / "data" / "kilder"
# The private source repo (kilder.yaml + tekst/ per top folder). Set in main().
SOURCES_DIR = DEFAULT_SOURCES
SAVE_API = "https://web.archive.org/save/"  # Wayback "Save Page Now"
WAYBACK_HOST = "web.archive.org"

# Below this average (characters per page) the PDF is treated as scanned without text.
MIN_CHARS_PER_PAGE = 200

# Order of fields in kilder.yaml. Unknown fields (forfatter, emneord, ...) follow.
FIELD_ORDER = [
    "id",
    "tittel",
    "dokument",
    "url",
    "arkiv",
    "lenker",
    "hentet",
    "offentlig",
    "merknad",
    "sider",
    "bytes",
    "sha256",
    "tekst",
    "konvertert",
    "ocr",
]

# Fields that may go into the public export. Everything else stays private.
EXPORT_FIELDS = ["id", "tittel", "dokument", "url", "arkiv", "lenker", "hentet"]
# For private entries (offentlig: nei): citable by id, with the title as plain text.
PRIVATE_EXPORT_FIELDS = ["id", "tittel", "dokument"]
ARCHIVE_SKIP = "skip"
PRIVATE_VALUES = {"nei", "no", "false"}
PUBLIC_VALUES = {"ja", "yes", "true"}
TECH_FIELDS = {"id", "bytes", "sha256", "sider", "tekst", "konvertert", "ocr"}


# --------------------------------------------------------------------------- helpers


class Log:
    """Console output. detail=True lines only show with -v; a log file gets everything."""

    def __init__(self, verbose: bool = False, path: Path | None = None) -> None:
        self.verbose = verbose
        self.file = path.open("a", encoding="utf-8") if path else None
        self.partial = False  # a line without newline is open

    def say(
        self, msg: str = "", detail: bool = False, end: str = "\n", cont: bool = False
    ) -> None:
        """cont=True continues the open (end="") line instead of starting a new one."""
        shown = not detail or self.verbose
        if self.partial and not cont:  # finish an open progress line first
            if self.file:
                self.file.write("\n")
            print(flush=True)
            self.partial = False
        if self.file:
            self.file.write(msg + end)
            self.file.flush()
        if shown:
            print(msg, end=end, flush=True)
        self.partial = end != "\n"


LOG = Log()


def say(
    msg: str = "", detail: bool = False, end: str = "\n", cont: bool = False
) -> None:
    LOG.say(msg, detail, end, cont)


def disp(path: Path) -> str:
    """Path for log lines: relative to the sources repo or bomfastinfo if possible."""
    for base in (SOURCES_DIR, REPO):
        try:
            return path.relative_to(base).as_posix()
        except ValueError:
            pass
    return str(path)


def public_status(entry: dict) -> tuple[bool, str]:
    """(is public, warning). Missing `offentlig` = public. Unknown values = private."""
    if "offentlig" not in entry:
        return True, ""
    value = entry["offentlig"]
    if value is True:
        return True, ""
    if value is False:
        return False, ""
    text = str(value).strip().lower()
    if text in PUBLIC_VALUES:
        return True, ""
    if text in PRIVATE_VALUES:
        return False, ""
    return False, f"offentlig: {value!r} not understood; treated as private (use ja/nei)"


def archive_skipped(entry: dict) -> bool:
    return str(entry.get("arkiv") or "").strip().lower() == ARCHIVE_SKIP


def human_size(n: int | None) -> str:
    if n is None:
        return "?"
    size = float(n)
    for unit in ("B", "kB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return str(n)


def show(value, limit: int = 70) -> str:
    """Short, readable form of a kilder.yaml value for log lines."""
    if value in (None, "", [], False):
        return "(empty)"
    if isinstance(value, list):
        return f"{len(value)} link{'s' if len(value) != 1 else ''}"
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def changed_fields(before: dict | None, after: dict, ignore=()) -> dict:
    """{field: (old, new)} for fields that differ between two versions of an entry."""
    before = before or {}
    empty = (None, "", [])
    return {
        k: (before.get(k), after.get(k))
        for k in {*before, *after}
        if k not in ignore
        and before.get(k) != after.get(k)
        and not (before.get(k) in empty and after.get(k) in empty)
    }


def describe(changes: dict) -> str:
    parts = []
    for k, (old, new) in sorted(changes.items()):
        parts.append(
            f"{k} = {show(new)}"
            if old in (None, "", [])
            else f"{k}: {show(old)} -> {show(new)}"
        )
    return "; ".join(parts)


@functools.cache
def _sha256_cached(path: Path, size: int, mtime: int) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256(path: Path) -> str:
    """SHA-256 of the file, cached per (path, size, mtime) so mid-run changes miss."""
    st = path.stat()
    return _sha256_cached(path, st.st_size, st.st_mtime_ns)


def in_scope(file: str, sub: str) -> bool:
    return not sub or file == sub or file.startswith(sub.rstrip("/") + "/")


def check_sources_dir(sources: Path) -> None:
    """Refuse a sources folder inside the public repo; it must exist."""
    resolved = sources.resolve()
    if resolved == REPO or REPO in resolved.parents:
        sys.exit(
            f"Refusing to use {sources} as the sources folder: it is inside the public "
            f"repo {REPO}. Set --sources or BOMFAST_SOURCES to the private repo "
            "(e.g. ~/work/git/bomfast-kilder)."
        )
    if not resolved.is_dir():
        sys.exit(
            f"Sources folder not found: {sources}. Clone the private repo there, or set "
            "--sources / BOMFAST_SOURCES."
        )


def print_summary(
    title: str, counts: Counter, rows: list[tuple[str, str]], hint_verbose: str = ""
) -> None:
    """rows = [(key, explanation)]. Rows with a zero count are left out, except the first
    unchanged-like row, which is always shown so you can see that things were checked."""
    say()
    say(f"Summary for {title}:")
    always = rows[0][0] if rows and rows[0][0] in ("UNCHANGED", "IN SYNC") else None
    width = max((len(k) for k, _ in rows), default=0)
    for key, why in rows:
        if counts[key] or key == always:
            say(f"  {key:<{width}}  {counts[key]:>4}   {why}")
    if hint_verbose and not LOG.verbose and counts[hint_verbose]:
        say(
            f"  (use -v to list the {counts[hint_verbose]} {hint_verbose.lower()} entries one by one)"
        )


# --------------------------------------------------------------------------- conversion


def clean_text(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = s.replace("­", "")  # soft hyphens
    s = s.replace(" ", " ")  # non-breaking spaces
    s = "\n".join(line.rstrip() for line in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip() + "\n"


def printed_page_numbers(doc) -> list[str]:
    """Find the page number printed on each page (header/footer).

    PDF page index and printed page number are often offset (cover, table of contents),
    and articles should cite the printed page number. Numbers at the top/bottom of each
    page are collected as candidates, and the most common offset (printed - pdf) in the
    document decides which candidates are accepted. This avoids picking up numbers from
    tables of contents and tables. Uses the PDF's own page labels if present.
    """
    n = len(doc)
    if any(doc[i].get_label() for i in range(n)):
        return [doc[i].get_label() for i in range(n)]

    candidates: list[set[int]] = []
    for i in range(n):
        lines = [
            line.strip() for line in doc[i].get_text().splitlines() if line.strip()
        ]
        candidates.append(
            {int(x) for x in lines[:5] + lines[-5:] if re.fullmatch(r"\d{1,4}", x)}
        )

    offsets = Counter(c - (i + 1) for i, cs in enumerate(candidates) for c in cs)
    if not offsets:
        return [""] * n
    best, count = offsets.most_common(1)[0]
    if count < max(2, n // 3):  # no clear page numbering
        return [""] * n
    return [
        str(i + 1 + best) if (i + 1 + best) in cs else ""
        for i, cs in enumerate(candidates)
    ]


def has_norwegian_tesseract() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=False
    )
    return "nor" in out.stdout.split()


def convert_pdf(pdf: Path, out: Path, checksum: str, rel: Path) -> dict:
    """Convert pdf to Markdown in out, with a page marker per page. The header written
    here is replaced by render_header() right after (sync_header)."""
    import pymupdf
    import pymupdf4llm

    with pymupdf.open(pdf) as doc:
        n_pages = len(doc)
        n_chars = sum(len(page.get_text()) for page in doc)
        scanned = n_pages > 0 and n_chars / n_pages < MIN_CHARS_PER_PAGE

        ocr = False
        kw = {"page_chunks": True, "header": False, "footer": False, "use_ocr": False}
        if scanned:
            if has_norwegian_tesseract():
                kw.update(
                    use_ocr=True, force_ocr=True, ocr_language="nor+eng", ocr_dpi=300
                )
                ocr = True
            else:
                say(
                    f"WARNING    {rel}: looks scanned, but tesseract with the Norwegian language "
                    "pack is missing (apt install tesseract-ocr-nor). The text will be incomplete."
                )

        tool = f"pymupdf4llm {pymupdf4llm.__version__}"
        try:
            pages = [c["text"] for c in pymupdf4llm.to_markdown(doc, **kw)]
            if len(pages) != n_pages:
                raise RuntimeError(f"got {len(pages)} pages, expected {n_pages}")
        except Exception as e:  # noqa: BLE001 – fall back to plain text extraction
            say(
                f"WARNING    {rel}: pymupdf4llm failed ({e}); using plain text extraction."
            )
            pages = [page.get_text(sort=True) for page in doc]
            tool = f"pymupdf {pymupdf.__version__} (get_text)"

        printed = printed_page_numbers(doc)
        meta = doc.metadata or {}

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    # The header and page markers are data read alongside Norwegian documents, so they
    # stay in Norwegian.
    parts = [
        (
            "<!--\n"
            f"kilde: {rel.as_posix()}\n"
            f"sha256: {checksum}\n"
            f"sider: {n_pages}\n"
            f"konvertert: {tool}{' + OCR (tesseract nor+eng)' if ocr else ''}, {today}\n"
            "Generert av scripts/ppkilder.py. Ikke rediger for hånd; endringer overskrives.\n"
            "Sidemarkører: pdf = sidenummer i PDF-fila, trykt = sidetallet som står på siden.\n"
            "-->\n"
        )
    ]
    for i, text in enumerate(pages):
        marker = (
            f"<!-- side pdf={i + 1}"
            + (f" trykt={printed[i]}" if printed[i] else "")
            + " -->"
        )
        parts.append(f"\n{marker}\n\n{clean_text(text)}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts), encoding="utf-8")

    return {
        "pages": n_pages,
        "converted": f"{tool}{' + OCR' if ocr else ''}, {today}",
        "ocr": ocr,
        "pdf_title": (meta.get("title") or "").strip(),
        "pdf_subject": (meta.get("subject") or "").strip(),
    }


def move_text(target: Path, old: str, new: Path, new_file: str) -> None:
    """Move a text file (the source moved or was renamed), and fix its source line."""
    src = target / old
    if not src.exists():
        return
    new.parent.mkdir(parents=True, exist_ok=True)
    content = re.sub(
        r"^kilde: .*$",
        f"kilde: {new_file}",
        src.read_text(encoding="utf-8"),
        count=1,
        flags=re.MULTILINE,
    )
    new.write_text(content, encoding="utf-8")
    if src != new:
        remove_text(target, src)


def remove_text(target: Path, text: Path) -> None:
    """Delete a text file, and the folders under tekst/ that it leaves empty."""
    text.unlink()
    for d in text.parents:
        if d == target / "tekst" or d == target or any(d.iterdir()):
            break
        d.rmdir()


# --------------------------------------------------------------------------- kilder.yaml I/O


def read_yaml(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return {e["id"]: e for e in data if isinstance(e, dict) and "id" in e}


def render_yaml(entries: dict[str, dict]) -> str:
    def ordered(e: dict) -> dict:
        known = {k: e[k] for k in FIELD_ORDER if k in e}
        rest = {k: v for k, v in e.items() if k not in FIELD_ORDER}
        return {**known, **rest}

    items = [ordered(entries[k]) for k in sorted(entries)]
    header = (
        "# cspell:disable\n"
        "# Kildeliste, vedlikeholdt av scripts/ppkilder.py fra Paperpile. tittel, forfatter,\n"
        "# aar, url og emneord kommer fra Paperpile; rett dem der. Tekniske felt (paperpile,\n"
        "# mappe, vedlegg, sider, bytes, sha256, tekst, konvertert, ocr) oppdateres av\n"
        "# skriptet. Øvrige felt (dokument, arkiv, lenker, hentet, merknad, ...) redigeres\n"
        "# her og beholdes.\n"
        "# offentlig: nei = aldri med i den offentlige lista (export).\n"
        "# arkiv: skip = archive slår aldri opp eller arkiverer url-en.\n\n"
    )
    return header + yaml.safe_dump(
        items, sort_keys=False, allow_unicode=True, width=100
    )


def write_yaml(path: Path, entries: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_yaml(entries), encoding="utf-8")


def save_yaml(
    path: Path, entries: dict[str, dict], original: dict[str, dict], dry_run: bool
) -> None:
    """Write kilder.yaml only if its content changes, and say what happened."""
    new_text = render_yaml(entries)
    old_text = path.read_text(encoding="utf-8") if path.exists() else None
    rel = disp(path)
    if new_text == old_text:
        say(f"kilder.yaml: no changes, file not rewritten ({rel})")
        return
    if old_text is None and not entries:
        # Nothing to record should not leave an empty kilder.yaml (and folder) behind.
        say(f"kilder.yaml: nothing to record, file not created ({rel})")
        return
    added = len(set(entries) - set(original))
    removed = len(set(original) - set(entries))
    changed = sum(1 for k in set(entries) & set(original) if entries[k] != original[k])
    what = ", ".join(
        f"{n} {label}"
        for n, label in (
            (added, "entries added"),
            (changed, "changed"),
            (removed, "removed"),
        )
        if n
    )
    if dry_run:
        say(f"kilder.yaml: would be written ({what or 'formatting only'}) ({rel})")
    else:
        write_yaml(path, entries)
        say(f"kilder.yaml: written ({what or 'formatting only'}) ({rel})")


def yaml_tops() -> list[str]:
    """The top folders in the sources repo that have a kilder.yaml."""
    return sorted(p.parent.name for p in SOURCES_DIR.glob("*/kilder.yaml"))


def top_only(folder: str, command: str) -> str:
    """archive and export work on whole top folders (one kilder.yaml each)."""
    top = folder.strip("/")
    if not top or "/" in top:
        sys.exit(f"{command} works on top folders only (got {folder})")
    return top


# --------------------------------------------------------------------------- duplicates

Member = tuple[str, dict]  # (top folder, entry)


def checksum_index(
    current: dict[str, dict[str, dict]] | None = None,
) -> dict[str, list[Member]]:
    """{sha256: [(top folder, entry), ...]} over every kilder.yaml in the sources repo.
    `current` ({top: entries}) replaces what is on disk for those top folders, e.g. the
    entries a command is working on."""
    lists = {p.parent.name: read_yaml(p) for p in SOURCES_DIR.glob("*/kilder.yaml")}
    lists.update(current or {})
    index: dict[str, list[Member]] = {}
    for top in sorted(lists):
        for eid in sorted(lists[top]):
            entry = lists[top][eid]
            if entry.get("sha256"):
                index.setdefault(entry["sha256"], []).append((top, entry))
    return index


def duplicate_groups(index: dict[str, list[Member]]) -> list[list[Member]]:
    """The groups of entries that have the same PDF (two or more per group)."""
    return [group for _sha, group in sorted(index.items()) if len(group) > 1]


def other_copies(
    index: dict[str, list[Member]], checksum: str, top: str, entry: dict
) -> list[Member]:
    """The entries other than `entry` that currently have this checksum."""
    return [
        (t, e)
        for t, e in index.get(checksum, [])
        if e is not entry
        and (t, e.get("id")) != (top, entry.get("id"))
        and e.get("sha256") == checksum  # the index may hold entries updated since
    ]


def dup_label(member: Member) -> str:
    top, entry = member
    origin = "" if MARKER in entry else ", not from Paperpile"
    return f"{entry.get('id')} ({top}{origin})"


def same_pdf_as(members: list[Member]) -> str:
    return "same PDF as " + ", ".join(dup_label(m) for m in members)


DEFAULT_PAPERPILE = Path(
    os.environ.get("BOMFAST_PAPERPILE", "~/GoogleDrive/Paperpile")
).expanduser()
BIB_NAME = (
    "bomfast-kilder.bib"  # in the mirror, unless --bib or BOMFAST_BIB says otherwise
)


def default_bib(paperpile: Path) -> Path:
    """BOMFAST_BIB, else the export in the mirror actually used (--paperpile)."""
    env = os.environ.get("BOMFAST_BIB")
    return Path(env).expanduser() if env else paperpile / BIB_NAME


BIB_COPY = "paperpile.bib"  # in the root of the sources repo, tracked by git
TOP_LABEL = re.compile(r"\d{3}_[^\s/\\]+")  # e.g. 005_statsbudsjett_samferdsel
# Looks like a top folder label: caught so that a bad one (e.g. 001_transport/reports,
# which would write a nested kilder.yaml no later run finds) is skipped, not a topic.
TOP_LABEL_LIKE = re.compile(r"\d{3}_\S+")
COLLECTION_LABEL = "bomfast-kilder"
# Control labels start with "_" and are never topics. Every one of them except _NO_URL
# keeps the source away from archive.org (arkiv: skip); _PRIVAT also keeps it out of the
# public list (offentlig: nei). Matched without regard to case. Removing a label never undoes what it
# set (that takes an edit in kilder.yaml), so a lost label cannot publish anything.
CONTROL_PREFIX = "_"
PRIVATE_LABEL = "_PRIVAT"  # private: not in the public list, not archived
INNSYN_LABEL = "_INNSYN"  # obtained via innsyn: treated exactly like _PRIVAT
PRIVATE_LABELS = (PRIVATE_LABEL, INNSYN_LABEL)
SUBSCRIPTION_LABEL = "_ABO"  # paywalled: in the public list, but never archived
# No url on purpose (e.g. a report that is not online): check does not report NO URL.
# It does not keep the source from archive.org: an upload may be the only public copy.
NO_URL_LABEL = "_NO_URL"
KNOWN_CONTROL_LABELS = (*PRIVATE_LABELS, SUBSCRIPTION_LABEL, NO_URL_LABEL)
MIRROR_CHECK = "All Papers"  # always in the mirror; missing = the mount is not up
MARKER = "paperpile"  # the kilder.yaml field that marks an entry as ours
PP_TECH_FIELDS = TECH_FIELDS | {MARKER, "vedlegg", "mappe"}


# --------------------------------------------------------------------------- BibTeX

BIB_ENTRY = re.compile(r"^[ \t]*@\w+[ \t]*\{[ \t]*([^\s,{}]+)[ \t]*,", re.MULTILINE)
BIB_SEPARATOR = re.compile(r"[\s,]*")
BIB_FIELD = re.compile(r"([\w:-]+)\s*=\s*")
BIB_BARE = re.compile(r"\w+")  # number or month macro
BIB_CONCAT = re.compile(r"\s*#\s*")


class BibError(ValueError):
    pass


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def read_delimited(text: str, pos: int) -> tuple[str, int]:
    """Read a "..." or {...} value starting at pos: (content, position after the end)."""
    quoted = text[pos] == '"'
    depth = 0
    i = pos + 1 if quoted else pos
    while i < len(text):
        c = text[i]
        if c == "\\":  # Paperpile escapes literal braces and quotes
            i += 2
            continue
        if c == '"' and quoted and depth == 0:
            return text[pos + 1 : i], i + 1
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and not quoted:
                return text[pos + 1 : i], i + 1
        i += 1
    raise BibError(f"line {line_of(text, pos)}: value is never closed")


def parse_fields(text: str, pos: int) -> tuple[dict[str, str], int]:
    """Read `name = value, ...}` from pos. A value can be "..." # {...} # bareword."""
    fields: dict[str, str] = {}
    while True:
        pos = BIB_SEPARATOR.match(text, pos).end()
        if text[pos : pos + 1] == "}":
            return fields, pos + 1
        name = BIB_FIELD.match(text, pos)
        if not name:
            raise BibError(f"line {line_of(text, pos)}: expected a field")
        pos = name.end()
        parts = []
        while True:
            if text[pos : pos + 1] in ('"', "{"):
                value, pos = read_delimited(text, pos)
            else:
                bare = BIB_BARE.match(text, pos)
                if not bare:
                    raise BibError(f"line {line_of(text, pos)}: expected a value")
                value, pos = bare.group(0), bare.end()
            parts.append(value)
            more = BIB_CONCAT.match(text, pos)
            if not more:
                break
            pos = more.end()
        # Paperpile wraps long values over several lines.
        fields[name.group(1).lower()] = " ".join("".join(parts).split())


def parse_bib(text: str) -> list[tuple[str, dict[str, str]]]:
    """All entries as (citekey, fields), in file order.

    Paperpile writes nothing but entries, so any other text (such as a truncated
    `@article{key` header) means the export is broken. It must be rejected rather than
    skipped: a lost entry would otherwise look gone, and prune would remove its source.
    """
    entries = []
    pos = 0
    while True:
        m = BIB_ENTRY.search(text, pos)
        gap_end = m.start() if m else len(text)
        stray = re.search(r"\S", text[pos:gap_end])
        if stray:
            at = pos + stray.start()
            snippet = text[at:].split("\n", 1)[0][:60]
            raise BibError(
                f"line {line_of(text, at)}: not a complete entry: {snippet!r}"
            )
        if not m:
            return entries
        fields, pos = parse_fields(text, m.end())
        entries.append((m.group(1), fields))


LATEX_ACCENTS = {  # accent command -> combining character
    '"': "\u0308", "'": "\u0301", "`": "\u0300", "^": "\u0302", "~": "\u0303",
    "=": "\u0304", ".": "\u0307", "u": "\u0306", "v": "\u030c", "H": "\u030b",
    "c": "\u0327", "k": "\u0328", "r": "\u030a", "d": "\u0323", "b": "\u0331",
}  # fmt: skip
LATEX_LETTERS = {
    "aa": "å", "AA": "Å", "ae": "æ", "AE": "Æ", "o": "ø", "O": "Ø", "oe": "œ",
    "OE": "Œ", "ss": "ß", "l": "ł", "L": "Ł", "i": "ı", "j": "ȷ",
}  # fmt: skip
_BASE = r"(\\[ij](?![a-zA-Z])|[a-zA-Z])"  # the accented letter; \i, \j are dotless i, j
# An accent takes {x}, or a bare x: right after a symbol accent (\'e), after whitespace
# for a letter accent (\c c). A bare \"x only inside braces, {\"o}: elsewhere \" is an
# escaped quote.
LATEX_ACCENT = re.compile(
    rf"""(?<=\{{)\\(")\s*{_BASE}(?=\s*\}})"""  # {\"o}
    rf"""|\\(?:([uvHckrdb"'`^~=.])\s*\{{\s*{_BASE}\s*\}}"""  # \v{c}, \'{e}, \"{o}
    rf"""|(['`^~=.]){_BASE}"""  # \'e
    rf"""|([uvHckrdb])\s+{_BASE})"""  # \c c
)
LATEX_LETTER = re.compile(
    r"\\("
    + "|".join(sorted(LATEX_LETTERS, key=len, reverse=True))
    + r")(?![a-zA-Z])\s*"
)


def _accent(m: re.Match) -> str:
    groups = [g for g in m.groups() if g is not None]  # exactly (command, letter)
    command, base = groups
    base = base.lstrip("\\")
    return unicodedata.normalize("NFC", base + LATEX_ACCENTS[command])


def unlatex(s: str) -> str:
    """Decode the LaTeX Paperpile writes: \\_ and friends, letters (\\o, {\\AA}),
    accents (\\'e, {\\"o}, \\v{c}), {protected} words; drop formatting like \\textit{x}."""
    s = re.sub(r"\\url\{([^{}]*)\}", r"\1", s)
    s = LATEX_ACCENT.sub(_accent, s)
    s = LATEX_LETTER.sub(lambda m: LATEX_LETTERS[m.group(1)], s)
    s = re.sub(r"\\[a-zA-Z]+\s*", "", s)
    return re.sub(r"\\([_%&#$\"{}])|[{}]", lambda m: m.group(1) or "", s)


def safe_parts(path: str) -> bool:
    """Is this path free of .. and the like? It decides where files are written."""
    parts = path.split("/")
    return all(p and p not in (".", "..") for p in parts)


@dataclass
class Source:
    """One entry in the .bib file that belongs in the repo."""

    id: str
    top: str
    pdf: str  # path in the mirror, "" if the entry has no file
    attachments: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    private: bool = False  # has the _PRIVAT label
    no_archive: bool = False  # has a control label other than _NO_URL (_PRIVAT, _ABO, ...)
    no_url: bool = False  # has the _NO_URL label: no url on purpose

    @property
    def folder(self) -> str:
        return self.top

    @property
    def tekst(self) -> str:
        return f"tekst/{self.id}.md"


@dataclass
class Held:
    """The control labels of a citekey that gave no source (used twice, a bad label or
    file path, ...): they still apply to its entries in kilder.yaml."""

    private: bool = False  # some copy has _PRIVAT
    no_archive: bool = False  # some copy has a control label other than _NO_URL


def bib_metadata(fields: dict[str, str]) -> dict:
    def text(name: str) -> str:
        return unicodedata.normalize("NFC", unlatex(fields.get(name, ""))).strip()

    url = text("url")
    if not url:
        m = re.search(r"\\url\{([^{}]+)\}", fields.get("howpublished", ""))
        url = unlatex(m.group(1)) if m else ""
    year = text("year")
    return {
        "tittel": text("title"),
        "forfatter": text("author").replace(" and ", "; "),
        "aar": int(year) if year.isdigit() else year,
        "url": url if url.startswith("http") else "",  # Paperpile can write "undefined"
    }


def is_label(label: str, wanted: str) -> bool:
    return label.casefold() == wanted.casefold()


def is_control_label(label: str) -> bool:
    return label.startswith(CONTROL_PREFIX)


def is_private_label(label: str) -> bool:
    """_PRIVAT or _INNSYN: offentlig: nei and arkiv: skip."""
    return any(is_label(label, known) for known in PRIVATE_LABELS)


def keeps_from_archive(label: str) -> bool:
    """A control label that means arkiv: skip: all of them (also unknown ones, to be on
    the safe side) except _NO_URL."""
    return is_control_label(label) and not is_label(label, NO_URL_LABEL)


def resembles_control_label(label: str) -> str | None:
    """The known control label this is a near miss of (PRIVAT, privat, _PRIVATE, ABO),
    or None. A near miss would silently leave the source public or archivable."""
    if any(is_label(label, known) for known in KNOWN_CONTROL_LABELS):
        return None
    base = label.casefold().lstrip(CONTROL_PREFIX)
    for known in KNOWN_CONTROL_LABELS:
        name = known.casefold().lstrip(CONTROL_PREFIX)
        if difflib.SequenceMatcher(None, base, name).ratio() >= 0.8:
            return known
    return None


# Paperpile separates several files with ";", but a file name can contain ";" too
# ("Transport Scotland (j1072c-11; queensferry).pdf"). Every path in the mirror starts
# with "All Papers/", so only a ";" followed by a new such path separates files.
FILE_SEPARATOR = re.compile(rf";\s*(?={re.escape(MIRROR_CHECK)}/)")


def split_files(field: str) -> list[str]:
    """The file paths in a .bib `file` field, in order."""
    return [f.strip() for f in FILE_SEPARATOR.split(field) if f.strip()]


# The house style for citekeys: <who>_<year>--<what>, e.g. regjeringen_2017--ntp_2018_2029
# or riches_etal_2019--queensferry_crossing_maintenance. Lowercase a-z and 0-9, words
# joined by _, the year right before --. Only a notice: the id is used in articles.
CITEKEY_WORDS = r"[a-z0-9]+(?:_[a-z0-9]+)*"
CITEKEY_STYLE = re.compile(rf"{CITEKEY_WORDS}_\d{{4}}--{CITEKEY_WORDS}")
CITEKEY_EXAMPLE = "name_2023--short_title"


def citekey_problem(key: str) -> str | None:
    """What is wrong with the citekey's form, or None if it follows the house style."""
    if CITEKEY_STYLE.fullmatch(key):
        return None
    who, sep, what = key.partition("--")
    if key != key.lower():
        why = "has capital letters"
    elif not sep:
        why = "has no -- between name_year and title"
    elif "--" in what:
        why = "has -- more than once"
    elif not re.search(r"_\d{4}$", who):
        why = "has no _<year> (four digits) right before --"
    elif not re.fullmatch(CITEKEY_WORDS, what) or not re.fullmatch(
        rf"{CITEKEY_WORDS}_\d{{4}}", who
    ):
        bad = sorted(set(re.sub(r"[a-z0-9_-]", "", key)))
        why = (
            f"has characters other than a-z, 0-9 and _ ({' '.join(map(repr, bad))})"
            if bad
            else "has - or empty words where only _ between words is allowed"
        )
    else:
        why = "is not on the form"
    return f"{why}; expected {CITEKEY_EXAMPLE} (rename it in Paperpile)"


def bib_keywords(fields: dict[str, str]) -> list[str]:
    """The Paperpile labels of a .bib entry."""
    keywords = [k.strip() for k in unlatex(fields.get("keywords", "")).split(";")]
    return [k for k in keywords if k]


def read_sources(
    bib: Path, need_sources: bool = True
) -> tuple[list[Source], set[str], Counter, bytes, dict[str, Held]]:
    """The usable sources in the .bib file, every citekey that must not count as gone,
    counts of what was left out, the file as read, and the control labels of the
    citekeys that gave no source (see Held). Warns on the way. Exits if there are no
    usable sources, unless need_sources is False (convert still applies Held then)."""
    if not bib.is_file():
        sys.exit(
            f"BibTeX file not found: {bib}. Set up the Paperpile workflow, or use --bib "
            "/ BOMFAST_BIB."
        )
    raw = bib.read_bytes()
    try:
        entries = parse_bib(raw.decode("utf-8"))
    except (BibError, UnicodeDecodeError) as e:
        sys.exit(f"Cannot read {bib}: {e}")

    sources: dict[str, Source] = {}
    skipped: Counter = Counter()
    unusable: set[str] = set()  # still in the .bib file: prune must not remove these

    def skip(key: str, why: str) -> None:
        skipped["WARNING"] += 1
        unusable.add(key)
        say(f"WARNING    {key}: {why}; skipped")

    # A citekey used twice is rejected in every occurrence: keeping one of them would
    # let entry order decide whether _PRIVAT/_ABO on the other one counts.
    key_count = Counter(key for key, _fields in entries)
    duplicates = {key for key, n in key_count.items() if n > 1}
    for key in sorted(duplicates):
        skip(
            key,
            f"the citekey is used {key_count[key]} times in the .bib file (give each "
            "entry its own citekey in Paperpile)",
        )

    for key, fields in entries:
        if key in duplicates:
            continue
        keywords = bib_keywords(fields)
        tops = [k for k in keywords if TOP_LABEL_LIKE.fullmatch(k)]
        if not tops and COLLECTION_LABEL not in keywords:
            skipped["IGNORED"] += 1
            say(f"IGNORED    {key}: no top folder label", detail=True)
            continue
        files = split_files(unlatex(fields.get("file", "")))
        if not tops:
            skip(key, "no top folder label (e.g. 005_statsbudsjett_samferdsel)")
        elif len(tops) > 1:
            skip(key, f"several top folder labels: {', '.join(tops)}")
        elif not TOP_LABEL.fullmatch(tops[0]) or not safe_parts(tops[0]):
            skip(key, f"bad top folder label {tops[0]!r}")
        elif "/" in key or key.startswith("."):
            skip(key, "the citekey cannot be used as a file name")
        elif not all(safe_parts(f) for f in files):
            skip(key, f"bad file path in {fields['file']!r}")
        elif files and not files[0].lower().endswith(".pdf"):
            skip(key, f"the first file is not a PDF: {files[0]}")
        else:
            controls = [k for k in keywords if is_control_label(k)]
            topics = [
                k
                for k in keywords
                if k not in (tops[0], COLLECTION_LABEL) and not is_control_label(k)
            ]
            for k in controls:
                if not any(is_label(k, known) for known in KNOWN_CONTROL_LABELS):
                    hint = resembles_control_label(k)
                    say(
                        f"WARNING    {key}: unknown label {k!r}"
                        + (f" (did you mean {hint}?)" if hint else "")
                        + f"; like every label starting with {CONTROL_PREFIX} it keeps "
                        "the source from archive.org, but it does nothing else"
                    )
            for k in topics:
                if hint := resembles_control_label(k):
                    say(
                        f"WARNING    {key}: the label {k!r} looks like {hint}, but is "
                        f"not; treated as a topic, so it has no effect"
                    )
            sources[key] = Source(
                key,
                tops[0],
                files[0] if files else "",
                files[1:],
                list(dict.fromkeys(topics)),
                bib_metadata(fields),
                private=any(is_private_label(k) for k in controls),
                no_archive=any(keeps_from_archive(k) for k in controls),
                no_url=any(is_label(k, NO_URL_LABEL) for k in controls),
            )
    # Citekeys that gave no source (used twice, a bad label or path, ...): their control
    # labels still count for an entry already in kilder.yaml. With several copies, the
    # strictest wins.
    held: dict[str, Held] = {}
    for key, fields in entries:
        if key in sources:
            continue
        controls = [k for k in bib_keywords(fields) if keeps_from_archive(k)]
        if controls:
            h = held.setdefault(key, Held())
            h.private |= any(is_private_label(k) for k in controls)
            h.no_archive = True
    if not sources and need_sources:
        sys.exit(no_sources_message(bib))
    return list(sources.values()), set(sources) | unusable, skipped, raw, held


def no_sources_message(bib: Path) -> str:
    # A broken or empty export must never look like "all sources were removed".
    return f"No sources with a top folder label in {bib}; nothing done."


def copy_bib(bib: Path, raw: bytes, write: bool) -> None:
    """Keep <sources>/paperpile.bib equal to the .bib file this run was based on.

    raw is the content read_sources() parsed, so a file Paperpile rewrites in the
    meantime cannot slip in unchecked.
    """
    target = SOURCES_DIR / BIB_COPY
    if bib.resolve() == target.resolve():
        return
    if target.exists() and target.read_bytes() == raw:
        say(f"{BIB_COPY}: same as {bib}", detail=True)
    elif not write:
        say(f"{BIB_COPY}: differs from {bib}; would be updated by convert/prune")
    else:
        what = "updated" if target.exists() else "created"
        target.write_bytes(raw)
        say(f"{BIB_COPY}: {what} from {bib}")


# --------------------------------------------------------------------------- kilder.yaml


class Lists:
    """Every <sources>/<top>/kilder.yaml in the repo, since sources can move between them."""

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, dict]] = {}
        self.original: dict[str, dict[str, dict]] = {}
        for path in sorted(SOURCES_DIR.glob("*/kilder.yaml")):
            self.top(path.parent.name)

    def top(self, name: str) -> dict[str, dict]:
        if name not in self.entries:
            path = SOURCES_DIR / name / "kilder.yaml"
            self.entries[name] = read_yaml(path)
            self.original[name] = copy.deepcopy(self.entries[name])
        return self.entries[name]

    def owned(self) -> dict[str, tuple[str, dict]]:
        """{id: (top folder, entry)} for the entries from this script."""
        found: dict[str, tuple[str, dict]] = {}
        for top, entries in self.entries.items():
            for eid, entry in entries.items():
                if MARKER not in entry:
                    continue
                if eid in found:
                    say(
                        f"WARNING    {eid}: in both {found[eid][0]} and {top}; using the first"
                    )
                else:
                    found[eid] = (top, entry)
        return found

    def copies(self, eid: str) -> list[tuple[str, dict]]:
        """Every entry from this script with this id, in all lists: an id in several
        kilder.yaml files is a mistake, but a restriction must reach every copy."""
        return [
            (top, entries[eid])
            for top, entries in self.entries.items()
            if eid in entries and MARKER in entries[eid]
        ]

    def foreign(self) -> dict[str, str]:
        """{id: top folder} for the entries that are not ours (no `paperpile` field)."""
        return {
            eid: top
            for top, entries in self.entries.items()
            for eid, entry in entries.items()
            if MARKER not in entry
        }

    def save(self, dry_run: bool) -> None:
        for top, entries in self.entries.items():
            if entries != self.original[top]:
                path = SOURCES_DIR / top / "kilder.yaml"
                save_yaml(path, entries, self.original[top], dry_run)


def apply_metadata(entry: dict, src: Source) -> None:
    """Paperpile wins for the fields it has a value for.

    A new PDF path drops the cached byte count: bytes, sha256 and the text still describe
    the old PDF, and the next run must compare checksums rather than trust a size and
    mtime match (the new PDF may be missing now and later synced with an old mtime).
    """
    if entry.get(MARKER) != src.pdf:
        entry.pop("bytes", None)
    entry[MARKER] = src.pdf
    entry["mappe"] = src.folder
    for key, value in src.meta.items():
        if value:
            entry[key] = value
    for key, value in (("emneord", src.topics), ("vedlegg", src.attachments)):
        if value:
            entry[key] = value
        else:
            entry.pop(key, None)
    apply_controls(entry, src.private, src.no_archive)


def apply_controls(entry: dict, private: bool, no_archive: bool) -> None:
    """The effect of the control labels. Without them, offentlig and arkiv are left as
    they are: removing a label never makes a source public again."""
    if private:
        entry["offentlig"] = "nei"
    if no_archive:
        entry["arkiv"] = ARCHIVE_SKIP


def restrict_all(
    lists: Lists,
    held: dict[str, Held],
    sources: list[Source] | dict,
    counts: Counter,
    dry_run: bool,
) -> None:
    """Apply the control labels in the .bib file to every Paperpile entry with that id,
    in every list and whatever folders convert runs on: privacy must not depend on
    entry order, folder selection, or an entry that could not be used."""
    labels = dict(held)
    for src in sources:
        if src.no_archive:
            labels[src.id] = Held(src.private, src.no_archive)
    for eid in sorted(labels):
        copies = lists.copies(eid)
        for top, entry in copies:
            before = copy.deepcopy(entry)
            apply_controls(entry, labels[eid].private, labels[eid].no_archive)
            if meta := changed_fields(before, entry):
                counts["METADATA"] += 1
                where = f" ({top})" if len(copies) > 1 else ""
                why = (
                    "skipped in the .bib file, but its control labels still count"
                    if eid in held
                    else "control labels in the .bib file"
                )
                say(f"{'METADATA':<10} {eid}{where}: {why}; kilder.yaml: {describe_meta(meta)}")


def describe_meta(changes: dict) -> str:
    """describe(), but with emneord/vedlegg as text instead of "N links"."""

    def plain(value):
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return "; ".join(value)
        return value

    return describe({k: (plain(old), plain(new)) for k, (old, new) in changes.items()})


def render_header(entry: dict) -> str:
    """The comment at the top of the text file (in Norwegian: it is data, like the text)."""
    lines = ["<!--", f"kilde: Paperpile, {entry[MARKER]}", f"id: {entry['id']}"]
    for key in ("tittel", "forfatter", "aar", "url", "emneord"):
        value = entry.get(key)
        if isinstance(value, list):
            value = "; ".join(value)
        if value:
            lines.append(f"{key}: {str(value).replace('-->', '->')}")
    lines += [
        f"sha256: {entry.get('sha256', '')}",
        f"sider: {entry.get('sider', '')}",
        f"konvertert: {entry.get('konvertert', '')}",
        "Generert av scripts/ppkilder.py. Ikke rediger for hånd; endringer overskrives.",
        "Sidemarkører: pdf = sidenummer i PDF-fila, trykt = sidetallet som står på siden.",
        "-->",
    ]
    return "\n".join(lines) + "\n"


def sync_header(text: Path, entry: dict) -> None:
    """Keep the text file's header in step with the entry, without touching the body."""
    if not text.exists():
        return
    old = text.read_text(encoding="utf-8")
    new = re.sub(
        r"\A<!--\n.*?\n-->\n",
        lambda _m: render_header(entry),
        old,
        count=1,
        flags=re.DOTALL,
    )
    if new != old:
        text.write_text(new, encoding="utf-8")


def selected(folder: str, folders: list[str]) -> bool:
    return not folders or any(in_scope(folder, f.strip("/")) for f in folders)


def entry_folder(top: str, entry: dict) -> str:
    """The folder of an existing entry, comparable with Source.folder."""
    if entry.get("mappe"):
        return entry["mappe"]
    sub = (
        Path(entry["tekst"]).parent.as_posix().removeprefix("tekst")
        if entry.get("tekst")
        else ""
    )
    return top + sub


def find_renames(
    sources: list[Source],
    owned: dict[str, tuple[str, dict]],
    in_bib: set[str],
    foreign: dict[str, str],
    paperpile: Path,
) -> dict[str, str]:
    """{new id: old id} for changed citekeys.

    An entry that has left the .bib file is matched against sources that are not in
    kilder.yaml yet: first by path in the mirror, then by checksum. Both convert and prune
    use this, so prune never removes an entry that convert would carry over.
    """
    retired = {eid: e for eid, (_top, e) in owned.items() if eid not in in_bib}
    by_path = {e[MARKER]: eid for eid, e in retired.items() if e.get(MARKER)}
    by_sha = {e["sha256"]: eid for eid, e in retired.items() if e.get("sha256")}
    renames: dict[str, str] = {}
    for src in sources:
        if src.id in owned or src.id in foreign or not src.pdf:
            continue
        old = by_path.get(src.pdf)
        pdf = paperpile / src.pdf
        if old is None and by_sha and pdf.is_file():
            old = by_sha.get(sha256(pdf))
        if old is not None and old not in renames.values():
            renames[src.id] = old
    return renames


def check_mirror(paperpile: Path) -> None:
    """An rclone mount that is down looks like an empty folder, not like an error."""
    if not (paperpile / MIRROR_CHECK).is_dir():
        sys.exit(
            f"Paperpile mirror not found: no {MIRROR_CHECK!r} in {paperpile}. Is it mounted? "
            "See `Mounting the mirror` in --help, or use --paperpile / BOMFAST_PAPERPILE."
        )


# --------------------------------------------------------------------------- commands


def cmd_convert(
    paperpile: Path, bib: Path, folders: list[str], force: set[str], dry_run: bool
) -> int:
    check_mirror(paperpile)
    say(f"{disp(bib)}{'   [DRY RUN: nothing will be written]' if dry_run else ''}")
    sources, in_bib, counts, raw, held = read_sources(bib, need_sources=False)
    lists = Lists()
    if not sources:
        # Nothing to convert, and the export may be broken: do not touch the copy of
        # the .bib file. But restrictions only ever make entries more private, so
        # apply them first (e.g. a _PRIVAT copy of the only citekey).
        restrict_all(lists, held, {}, counts, dry_run)
        lists.save(dry_run)
        sys.exit(no_sources_message(bib))
    copy_bib(bib, raw, write=not dry_run)
    owned = lists.owned()
    foreign = lists.foreign()
    scope = [s for s in sources if selected(s.folder, folders)]
    renames = find_renames(scope, owned, in_bib, foreign, paperpile)
    unknown = force - {s.id for s in scope}
    if unknown:
        say(f"WARNING    --force: no such id in scope: {', '.join(sorted(unknown))}")
    index = checksum_index(lists.entries)

    def outcome(kind: str, eid: str, msg: str = "", detail: bool = False) -> None:
        counts[kind] += 1
        say(f"{kind:<10} {eid}" + (f": {msg}" if msg else ""), detail=detail)

    def relocate(old_top: str, old_id: str, entry: dict, src: Source) -> None:
        """Move the entry and its text file to where src says they belong."""
        new_text = SOURCES_DIR / src.top / src.tekst
        old_text = entry.get("tekst")
        if old_text and not dry_run:
            move_text(SOURCES_DIR / old_top, old_text, new_text, src.pdf)
        lists.top(old_top).pop(old_id)
        lists.top(src.top)[src.id] = entry
        entry["id"] = src.id
        if old_text:
            entry["tekst"] = src.tekst

    def handle(src: Source) -> None:
        text = SOURCES_DIR / src.top / src.tekst
        if src.id in foreign:
            outcome(
                "WARNING",
                src.id,
                f"id already used in {foreign[src.id]} by an entry not from Paperpile; skipped",
            )
            return

        entry = None
        moved = False  # moved or renamed: the checksum is always recomputed
        have_text = text.exists()
        old_id = src.id if src.id in owned else renames.get(src.id)
        if old_id:
            old_top, entry = owned[old_id]
            old_text = entry.get("tekst")
            if old_id != src.id:
                outcome(
                    "RENAMED", src.id, f"was {old_id}: update references in articles!"
                )
                moved = True
            elif entry_folder(old_top, entry) != src.folder or (
                old_text and old_text != src.tekst
            ):
                outcome(
                    "MOVED", src.id, f"{entry_folder(old_top, entry)} -> {src.folder}"
                )
                moved = True
            if moved:
                have_text = (
                    bool(old_text)
                    and (SOURCES_DIR / old_top / old_text).exists()
                )
                relocate(old_top, old_id, entry, src)

        pdf = paperpile / src.pdf
        if src.pdf and not pdf.is_file():
            kind, why = "MISSING", f"{src.pdf} is not in the mirror (still syncing?)"
        elif not src.pdf:
            kind, why = "NO PDF", "no file in the .bib entry; metadata only"
        else:
            kind = ""
        if kind:
            entry = entry or lists.top(src.top).setdefault(src.id, {"id": src.id})
            apply_metadata(entry, src)
            outcome(kind, src.id, why)
            return

        size = pdf.stat().st_size
        before = copy.deepcopy(entry)
        unchanged_msg = "same path and size, PDF not newer than the text file (checksum not recomputed)"
        same = (
            not moved
            and entry is not None
            and have_text
            and entry.get(MARKER) == src.pdf
            and entry.get("bytes") == size
            and pdf.stat().st_mtime <= text.stat().st_mtime
        )
        checksum = None
        if not same:
            checksum = sha256(pdf)
            if entry is not None and entry.get("sha256") == checksum and have_text:
                same = True
                unchanged_msg = "checksum identical, text file present"

        if same and src.id not in force:
            apply_metadata(entry, src)
            entry["bytes"] = size  # after: the checksum matched, so the size is current
            meta = changed_fields(before, entry, ignore=PP_TECH_FIELDS - {MARKER})
            if meta:
                outcome(
                    "METADATA",
                    src.id,
                    "text untouched; kilder.yaml: " + describe_meta(meta),
                )
            elif not moved:
                outcome("UNCHANGED", src.id, unchanged_msg, detail=True)
            if not dry_run:
                sync_header(text, entry)
            return

        # The PDF has to be (re)converted. Work out why, for the log.
        old_sha = (entry or {}).get("sha256")
        checksum = checksum or sha256(pdf)
        if not old_sha:
            kind, why = "NEW", "not converted before"
        elif old_sha != checksum:
            kind = "UPDATED"
            why = (
                f"PDF changed (sha256 {old_sha[:8]}… -> {checksum[:8]}…, "
                f"{human_size(before.get('bytes'))} -> {human_size(size)})"
            )
        elif src.id in force:
            kind, why = "REBUILT", "text regenerated because of --force (PDF unchanged)"
        else:
            kind, why = "REBUILT", "text file was missing (PDF unchanged)"

        entry = entry or lists.top(src.top).setdefault(src.id, {"id": src.id})
        if kind in ("NEW", "UPDATED"):
            if dups := other_copies(index, checksum, src.top, entry):
                outcome(
                    "DUPLICATE",
                    src.id,
                    same_pdf_as(dups) + "; kept as its own entry",
                )
            # so that a second copy converted later in this run is noticed too
            index.setdefault(checksum, []).append(
                (src.top, {"id": src.id, "sha256": checksum, MARKER: src.pdf})
            )
        if dry_run:
            apply_metadata(entry, src)
            outcome(kind, src.id, why + "; text would be (re)written")
            return

        # Before converting: a failed conversion must not leave an entry without the marker.
        apply_metadata(entry, src)
        started = time.monotonic()
        say(f"{kind:<10} {src.id}: converting ...", end="")
        try:
            info = convert_pdf(pdf, text, checksum, Path(src.pdf))
        except Exception as e:  # noqa: BLE001 – a bad PDF should not stop the rest
            say(f" failed: {type(e).__name__}: {e}", cont=True)
            counts["WARNING"] += 1
            return
        entry.update(
            bytes=size,
            sha256=checksum,
            sider=info["pages"],
            tekst=src.tekst,
            konvertert=info["converted"],
            ocr=info["ocr"],
        )
        sync_header(text, entry)
        counts[kind] += 1
        meta = changed_fields(before, entry, ignore=PP_TECH_FIELDS)
        say(
            f" done in {time.monotonic() - started:.1f} s. {why}. "
            f"{info['pages']} page{'s' if info['pages'] != 1 else ''}, text {src.tekst}"
            + (", OCR" if info["ocr"] else "")
            + (f". kilder.yaml: {describe_meta(meta)}" if meta else ""),
            cont=True,
        )

    try:
        restrict_all(lists, held, sources, counts, dry_run)
        for src in scope:
            if why := citekey_problem(src.id):
                outcome("CITEKEY", src.id, why + "; converted anyway")
            handle(src)
    finally:  # also on Ctrl-C: keep what was converted, conversions are slow
        counts["GONE"] = sum(
            1
            for eid, (top, entry) in lists.owned().items()
            if eid not in in_bib and selected(entry_folder(top, entry), folders)
        )
        print_summary(
            f"{disp(bib)} ({len(scope)} sources checked)",
            counts,
            [
                ("UNCHANGED", "PDF and text untouched, nothing to do"),
                ("NEW", "converted for the first time"),
                ("UPDATED", "the PDF changed, text regenerated"),
                ("REBUILT", "text regenerated, PDF unchanged"),
                ("MOVED", "the top folder label changed, entry and text file followed"),
                ("RENAMED", "the citekey changed, entry and text file followed"),
                ("METADATA", "only kilder.yaml fields changed"),
                ("NO PDF", "no file in the .bib entry, metadata only"),
                ("MISSING", "the PDF is not in the mirror, metadata only"),
                ("WARNING", "skipped, see the lines above"),
                ("CITEKEY", f"citekey not on the form {CITEKEY_EXAMPLE} (converted)"),
                ("IGNORED", "neither a top folder label nor bomfast-kilder"),
                (
                    "DUPLICATE",
                    "converted, but the same PDF is already in another entry",
                ),
                (
                    "GONE",
                    "in kilder.yaml, but no longer in the .bib file (prune removes it)",
                ),
            ],
            hint_verbose="UNCHANGED",
        )
        lists.save(dry_run)
    return 1 if counts["WARNING"] or counts["MISSING"] else 0


def looks_unchanged(entry: dict, rel: str, pdf: Path, top: str) -> bool:
    """Same path and size as in kilder.yaml, and not newer than the text file: taken as
    unchanged without hashing (on the rclone mount, hashing downloads the PDF)."""
    text = SOURCES_DIR / top / entry["tekst"] if entry.get("tekst") else None
    return bool(
        text
        and entry.get(MARKER) == rel
        and entry.get("bytes") == pdf.stat().st_size
        and text.exists()
        and pdf.stat().st_mtime <= text.stat().st_mtime
    )


def cmd_check(
    paperpile: Path,
    bib: Path,
    folders: list[str],
    prune: bool = False,
    dry_run: bool = False,
    checksum: bool = False,
) -> int:
    """checksum: hash every PDF, also those with the same path, size and date as in
    kilder.yaml (slow: the mirror is an rclone mount, hashing downloads the PDF)."""
    check_mirror(paperpile)
    say(
        f"{disp(bib)}: {'prune' if prune else 'check'}"
        + ("   [DRY RUN: nothing will be written]" if dry_run and prune else "")
    )
    sources, in_bib, counts, raw, _held = read_sources(bib)
    copy_bib(bib, raw, write=prune and not dry_run)
    issues = counts["WARNING"]
    lists = Lists()
    owned = lists.owned()
    foreign = lists.foreign()
    scope = [s for s in sources if selected(s.folder, folders)]
    renames = find_renames(sources, owned, in_bib, foreign, paperpile)
    renamed = set(renames.values())

    def report(
        kind: str, ref: str, msg: str, issue: bool = True, detail: bool = False
    ) -> None:
        nonlocal issues
        counts[kind] += 1
        issues += issue
        say(f"{kind:<14} {ref}: {msg}", detail=detail)

    for src in scope:
        if why := citekey_problem(src.id):
            report("CITEKEY", src.id, why, issue=False)
        if src.id in foreign:
            report(
                "ID CONFLICT",
                src.id,
                f"id already used in {foreign[src.id]} by an entry not from Paperpile",
            )
            continue
        if src.id in renames:
            old_id = renames[src.id]
            old_top, old_entry = owned[old_id]
            old_folder = entry_folder(old_top, old_entry)
            # Reported with the old id below, unless the old entry is out of scope.
            if not selected(old_folder, folders):
                report(
                    "RENAMED",
                    old_id,
                    f"citekey changed to {src.id}, {old_folder} -> {src.folder} "
                    "(run convert; prune keeps the entry)",
                )
            continue
        if src.id not in owned:
            report("NEW", src.id, "in the .bib file, not in kilder.yaml (run convert)")
            continue
        top, entry = owned[src.id]
        problems = 0
        if entry_folder(top, entry) != src.folder or (
            entry.get("tekst") and entry["tekst"] != src.tekst
        ):
            report(
                "MOVED",
                src.id,
                f"{entry_folder(top, entry)} -> {src.folder} (run convert)",
            )
            problems += 1
        pdf = paperpile / src.pdf
        if src.pdf and not pdf.is_file():
            report("MISSING", src.id, f"{src.pdf} is not in the mirror")
            problems += 1
        elif (
            src.pdf
            and (checksum or not looks_unchanged(entry, src.pdf, pdf, top))
            and entry.get("sha256") != sha256(pdf)
        ):
            report(
                "CHANGED",
                src.id,
                "checksum in the mirror does not match kilder.yaml (run convert)",
            )
            problems += 1
        if src.pdf and pdf.is_file() and not entry.get("tekst"):
            report(
                "TEXT MISSING", src.id, "the PDF has not been converted (run convert)"
            )
            problems += 1
        elif (
            entry.get("tekst")
            and not (SOURCES_DIR / top / entry["tekst"]).exists()
        ):
            report(
                "TEXT MISSING",
                src.id,
                f"{entry['tekst']} not found in the repo (run convert)",
            )
            problems += 1
        wanted = copy.deepcopy(entry)
        apply_metadata(wanted, src)
        if meta := changed_fields(entry, wanted, ignore=TECH_FIELDS | {"mappe"}):
            report("METADATA", src.id, describe_meta(meta) + " (run convert)")
            problems += 1
        if not wanted.get("url") and src.no_url:
            report(
                "NO URL OK",
                src.id,
                f"no url, as marked with {NO_URL_LABEL}",
                issue=False,
                detail=True,
            )
        elif not wanted.get("url"):
            report(
                "NO URL",
                src.id,
                f"no url (add it in Paperpile, or the label {NO_URL_LABEL} if there "
                "is none)",
                issue=False,
            )
        if not src.private and not public_status(wanted)[0]:
            report(
                "NO LABEL",
                src.id,
                f"offentlig: {wanted.get('offentlig')} in kilder.yaml, but no "
                f"{'/'.join(PRIVATE_LABELS)} label in Paperpile; stays private (add the "
                "label, or "
                "set offentlig: ja in kilder.yaml to make it public)",
                issue=False,
            )
        elif not src.no_archive and archive_skipped(wanted):
            report(
                "NO LABEL",
                src.id,
                f"arkiv: skip in kilder.yaml, but no {SUBSCRIPTION_LABEL} (or other "
                f"{CONTROL_PREFIX}) label in Paperpile; stays skip (add the label, or "
                "remove arkiv: skip from kilder.yaml to allow archiving)",
                issue=False,
            )
        if not problems:
            report(
                "IN SYNC",
                src.id,
                "matches the .bib file and the mirror",
                issue=False,
                detail=True,
            )

    gone = [
        (eid, top, entry)
        for eid, (top, entry) in owned.items()
        if eid not in in_bib and selected(entry_folder(top, entry), folders)
    ]
    for eid, top, entry in gone:
        if eid in renamed:
            new_id = next(k for k, v in renames.items() if v == eid)
            old_folder = entry_folder(top, entry)
            new_folder = next(s.folder for s in sources if s.id == new_id)
            move = f", {old_folder} -> {new_folder}" if old_folder != new_folder else ""
            report(
                "RENAMED",
                eid,
                f"citekey changed to {new_id}{move} (run convert; prune keeps the entry)",
            )
            continue
        report(
            "GONE",
            eid,
            f"in {top}/kilder.yaml, not in the .bib file (prune removes it)",
        )
        if prune:
            text = (
                SOURCES_DIR / top / entry["tekst"]
                if entry.get("tekst")
                else None
            )
            has_text = text is not None and text.exists()
            say(
                f"{'WOULD REMOVE' if dry_run else 'REMOVED':<14} {eid}: from kilder.yaml"
                + (" and its text file" if has_text else "")
                + " (the PDF is untouched)"
            )
            counts["WOULD REMOVE" if dry_run else "REMOVED"] += 1
            issues -= 1
            lists.top(top).pop(eid)
            if has_text and not dry_run:
                text.unlink()

    # The same PDF in several entries, in any kilder.yaml (also entries not from
    # Paperpile). A notice, not an issue. Entries that are gone from the .bib file are
    # left out: prune removes them, so they are not copies anyone has to deal with.
    current = {
        top: {
            eid: e
            for eid, e in entries.items()
            if MARKER not in e or eid in in_bib or eid in renamed
        }
        for top, entries in lists.entries.items()
    }
    for group in duplicate_groups(checksum_index(current)):
        mine = [
            (t, e)
            for t, e in group
            if MARKER in e and selected(entry_folder(t, e), folders)
        ]
        if mine:
            others = [m for m in group if m[1] is not mine[0][1]]
            report(
                "DUPLICATE", mine[0][1]["id"], same_pdf_as(others), issue=False
            )

    print_summary(
        f"{disp(bib)} ({len(scope)} sources)",
        counts,
        [
            ("IN SYNC", "matches the .bib file and the mirror"),
            ("NEW", "in the .bib file, not in kilder.yaml"),
            ("CHANGED", "PDF differs from the checksum in kilder.yaml"),
            ("MOVED", "the top folder label differs from where the entry is"),
            ("METADATA", "kilder.yaml differs from the .bib file"),
            ("MISSING", "the PDF is not in the mirror"),
            ("TEXT MISSING", "text file missing in the repo"),
            ("ID CONFLICT", "the citekey is used by an entry not from Paperpile"),
            ("RENAMED", "the citekey changed, convert carries the entry over"),
            ("GONE", "in kilder.yaml, not in the .bib file"),
            ("NO URL", "entries without url (not counted as issues)"),
            ("NO URL OK", f"entries without url, marked with {NO_URL_LABEL}"),
            ("CITEKEY", f"citekey not on the form {CITEKEY_EXAMPLE} (not issues)"),
            (
                "NO LABEL",
                "private or arkiv: skip, but no label in Paperpile (not issues)",
            ),
            ("DUPLICATE", "same PDF as another entry (not counted as issues)"),
            ("WARNING", "entries in the .bib file that cannot be used"),
            ("IGNORED", "neither a top folder label nor bomfast-kilder"),
            ("REMOVED", "entries (and their text files) removed from kilder.yaml"),
            ("WOULD REMOVE", "entries prune would remove (dry run)"),
        ],
        hint_verbose="IN SYNC",
    )
    if prune:
        lists.save(dry_run)
    say("OK" if issues == 0 else f"{issues} issue{'s' if issues != 1 else ''}")
    return 1 if issues else 0


# --------------------------------------------------------------------------- upload

UPLOAD_RESULTS = (
    REPO / ia.DEFAULT_RESULTS_PATH
)  # also written by archive_org_upload.py


def uploaded_by_sha(results: Path) -> dict[str, list[str]]:
    """{sha256: [file_url, ...]} of earlier uploads in results.jsonl, also the manual
    ones, oldest first. The log is append-only history: a file may have been replaced
    or removed on archive.org since, so check with remote_matches() before linking."""
    found: dict[str, list[str]] = {}
    if results.is_file():
        for line in results.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("sha256") and rec.get("file_url"):
                urls = found.setdefault(rec["sha256"], [])
                if rec["file_url"] not in urls:
                    urls.append(rec["file_url"])
    return found


ARCHIVE_DOWNLOAD = "https://archive.org/download/"


def remote_matches(file_url: str, pdf: Path) -> str | None:
    """None if file_url is on archive.org now with the content of pdf, otherwise why
    not. Raises OSError/ValueError when archive.org cannot be asked."""
    if not file_url.startswith(ARCHIVE_DOWNLOAD):
        return "not an archive.org download link, cannot be checked"
    item, _, remote = file_url.removeprefix(ARCHIVE_DOWNLOAD).partition("/")
    if not item or not remote:
        return "not a link to a file in an item, cannot be checked"
    info = remote_file(item, urllib.parse.unquote(remote))
    if info is None:
        return "no longer on archive.org"
    if info.get("md5") != md5(pdf):
        return "has other content on archive.org now (replaced?)"
    return None


def upload_refusal(
    entry: dict | None, src: Source | None, in_bib: bool = False
) -> str | None:
    """Why this source must not go to archive.org, or None. Both kilder.yaml and the
    .bib file must allow it, so a label added after the last convert still counts.
    in_bib: the citekey is in the .bib file, but unusable (e.g. used twice)."""
    if entry is None:
        return "not in kilder.yaml (run convert first)" if src else "no such id"
    if "paperpile" not in entry:
        return "not from Paperpile (no paperpile field); upload only handles Paperpile"
    public, _warning = public_status(entry)
    if not public:
        return (
            f"offentlig: {entry.get('offentlig')}; private sources are never uploaded"
        )
    if archive_skipped(entry):
        return "arkiv: skip in kilder.yaml; never uploaded"
    if entry.get("arkiv"):
        return f"arkiv already set ({entry['arkiv']}); never overwritten"
    if src is None:
        if in_bib:
            return "unusable in the .bib file (see the WARNING above); never uploaded"
        return "not in the .bib file any more"
    if src.no_archive:
        what = "/".join(PRIVATE_LABELS) if src.private else "a label starting with _"
        return f"has {what} in Paperpile; never uploaded (run convert)"
    if not src.pdf:
        return "no PDF in Paperpile"
    if src.pdf != entry["paperpile"]:
        return "the .bib file and kilder.yaml disagree about the PDF; run convert first"
    return None


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_file(item: str, remote: str) -> dict | None:
    for info in ia.item_metadata(item).get("files", []):
        if info.get("name") == remote:
            return info
    return None


def upload_pdf(pdf: Path, remote: str, item: str, entry: dict, checksum: str) -> dict:
    """Upload one PDF with the ia CLI, or find it already there. Returns the record for
    results.jsonl. Raises SystemExit when it cannot be done (yet), and OSError or
    ValueError when archive.org cannot be reached or answers with something unreadable."""
    ia.validate_pdf(pdf)
    file_url = f"https://archive.org/download/{item}/{urllib.parse.quote(remote)}"
    existing = remote_file(item, remote)
    # ia runs for the upload, and for original_url also when the file is already there.
    if (existing is None or entry.get("url")) and not shutil.which("ia"):
        raise SystemExit(
            "ia CLI not found. Install it with: python3 -m pip install --user "
            "internetarchive, then run: ia configure"
        )
    if existing is not None:
        # E.g. a run that timed out while archive.org was still processing the upload.
        if existing.get("md5") != md5(pdf):
            raise SystemExit(
                f"{remote} is already in {item}, with other content; not replaced "
                "(write arkiv by hand, or remove it there first)"
            )
        say(f"           {remote} is already in {item} with the same content")
    else:
        opts = argparse.Namespace(
            item=item,
            retries=10,
            metadata=[],
            file_metadata=[],
            no_backup_on_replace=False,
        )
        subprocess.run(ia.build_ia_command(opts, pdf, remote), check=True)
        if not ia.wait_for_uploaded_file(item, remote, timeout=120):
            raise SystemExit(
                "uploaded, but not visible in the item yet; run the same command again "
                "later to write arkiv"
            )
    if entry.get("url") and not ia.record_original_url_metadata(
        item, remote, entry["url"]
    ):
        # Not logged and no arkiv yet: the next run finds the file by its md5, reuses
        # it, and tries the metadata again.
        raise SystemExit(
            f"{remote} is in {item}, but recording original_url failed; run the same "
            "command again later"
        )
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "item": item,
        "document_id": entry["id"],
        "title": entry.get("tittel", ""),
        "source_name": entry.get("forfatter", ""),
        "source": f"paperpile:{entry['paperpile']}",
        "original_url": entry.get("url", ""),
        "remote_name": remote,
        "file_url": file_url,
        "size_bytes": pdf.stat().st_size,
        "sha256": checksum,
        "checked": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "notes": "uploaded by ppkilder.py upload",
        "tags": [],
    }


def cmd_upload(
    paperpile: Path,
    bib: Path,
    ids: list[str],
    upload: bool,
    item: str = ia.DEFAULT_ITEM,
    results: Path = UPLOAD_RESULTS,
) -> int:
    """Send the PDFs of these Paperpile sources to archive.org and write the link to
    `arkiv`. Without upload=True, only shows what would be done."""
    check_mirror(paperpile)
    found, in_bib, _counts, _raw, _held = read_sources(bib)
    sources = {s.id: s for s in found}
    lists = {
        p.parent.name: (p, read_yaml(p))
        for p in sorted(SOURCES_DIR.glob("*/kilder.yaml"))
    }
    # Every top folder that has the id: an id in several kilder.yaml files is
    # ambiguous, and picking one by folder order could judge or update the wrong entry.
    where: dict[str, list[str]] = {}
    for top, (_p, entries) in lists.items():
        for eid in entries:
            where.setdefault(eid, []).append(top)
    done = uploaded_by_sha(results)
    counts: Counter = Counter()

    def record_arkiv(top: str, eid: str, url: str) -> None:
        path, entries = lists[top]
        entries[eid]["arkiv"] = url
        write_yaml(path, entries)  # after every source: safe to interrupt

    for eid in dict.fromkeys(ids):
        tops = where.get(eid, [])
        if len(tops) > 1:
            counts["REFUSED"] += 1
            say(
                f"REFUSED    {eid}: in several kilder.yaml files ({', '.join(tops)}); "
                "keep it in one of them (or give the sources different ids) first"
            )
            continue
        top = tops[0] if tops else None
        entry = lists[top][1][eid] if top else None
        reason = upload_refusal(entry, sources.get(eid), eid in in_bib)
        pdf = paperpile / entry["paperpile"] if reason is None else None
        if pdf is not None and not pdf.is_file():
            reason = f"the PDF is not in the mirror: {entry['paperpile']}"
        checksum = sha256(pdf) if reason is None else ""
        if reason is None and checksum != entry.get("sha256"):
            reason = "the PDF changed since the last convert; run convert first"
        if reason is not None:
            counts["REFUSED"] += 1
            say(f"REFUSED    {eid}: {reason}")
            continue

        # Uploaded before, e.g. by hand with archive_org_upload.py: link the newest
        # earlier upload that archive.org still has with this content.
        url = None
        try:
            for old in reversed(done.get(checksum, [])):
                if (why := remote_matches(old, pdf)) is None:
                    url = old
                    break
                counts["STALE"] += 1
                say(f"STALE      {eid}: {old} in {results.name} {why}; not linked")
        except (OSError, ValueError) as err:
            counts["FAILED"] += 1
            say(
                f"FAILED     {eid}: cannot check the earlier upload on archive.org: {err}"
            )
            continue
        if url:
            if upload:
                record_arkiv(top, eid, url)
                counts["LINKED"] += 1
                say(f"LINKED     {eid}: already uploaded, {url}; written to arkiv")
            else:
                counts["WOULD LINK"] += 1
                say(f"WOULD LINK {eid}: already uploaded, {url}")
            continue

        remote = f"{eid}.pdf"
        if not upload:
            counts["WOULD UPLOAD"] += 1
            size = human_size(pdf.stat().st_size)
            say(f"WOULD UPLOAD {eid}: {entry['paperpile']} ({size}) -> {item}/{remote}")
            continue
        try:
            record = upload_pdf(pdf, remote, item, entry, checksum)
        except (SystemExit, subprocess.CalledProcessError) as err:
            counts["FAILED"] += 1
            say(f"FAILED     {eid}: {err}")
            continue
        except (OSError, ValueError) as err:
            # Network errors, timeouts, unreadable metadata (JSONDecodeError), ia that
            # cannot be started: this source failed, the others still get their turn.
            # Nothing is recorded, so the same command retries it; a file that did
            # reach archive.org is then found by its md5 and not uploaded again.
            counts["FAILED"] += 1
            say(f"FAILED     {eid}: {type(err).__name__}: {err} (run again to retry)")
            continue
        ia.append_result(results, record)
        record_arkiv(top, eid, record["file_url"])
        done.setdefault(checksum, []).append(record["file_url"])
        counts["UPLOADED"] += 1
        say(f"UPLOADED   {eid}: {record['file_url']}; written to arkiv")

    print_summary(
        f"upload to {item} ({len(set(ids))} sources)",
        counts,
        [
            ("UPLOADED", "uploaded, link written to arkiv"),
            ("LINKED", "uploaded before (results.jsonl), link written to arkiv"),
            ("WOULD UPLOAD", "would be uploaded (dry run, add --upload)"),
            ("WOULD LINK", "uploaded before, link would be written to arkiv"),
            ("STALE", "earlier upload in results.jsonl no longer matches, not linked"),
            ("REFUSED", "not allowed or not ready, see above"),
            ("FAILED", "upload failed, see above"),
        ],
    )
    if not upload and (counts["WOULD UPLOAD"] or counts["WOULD LINK"]):
        say("Dry run: nothing uploaded or written. Add --upload to do it.")
    bad = counts["REFUSED"] + counts["FAILED"]
    say("OK" if bad == 0 else f"{bad} not done")
    return 1 if bad else 0


# --------------------------------------------------------------------------- archive


def load_wayback_helpers():
    """Import check_links_wayback.py from the same folder (find_wayback etc.)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import check_links_wayback as helpers
    except ImportError as e:
        sys.exit(f"Cannot import scripts/check_links_wayback.py: {e}")
    return helpers


def request_capture(url: str, timeout: int, user_agent: str, context) -> str:
    """Ask Wayback to capture `url` (Save Page Now) and return the snapshot URL.

    Raises urllib.error.HTTPError (e.g. 429 when rate-limited) or RuntimeError.
    """
    import urllib.request

    req = urllib.request.Request(SAVE_API + url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
        location = resp.headers.get("Content-Location") or ""
        final = resp.geturl()
    if location.startswith("/web/"):
        snapshot = "https://" + WAYBACK_HOST + location
    elif "/web/" in final and "/save/" not in final:
        snapshot = final
    else:
        raise RuntimeError("archive.org did not return a snapshot location")
    m = re.search(r"/web/(\d{14})", snapshot)
    if m and url.lower().split("?")[0].endswith(".pdf"):
        snapshot = snapshot.replace(f"/web/{m.group(1)}/", f"/web/{m.group(1)}id_/", 1)
    return snapshot


def cmd_archive(
    folder: str, save: bool, dry_run: bool, delay: float, timeout: int
) -> int:
    """Fill empty `arkiv` fields from Wayback. Reads/writes kilder.yaml only."""
    import ssl
    import urllib.error

    top = top_only(folder, "archive")
    helpers = load_wayback_helpers()
    yaml_file = SOURCES_DIR / top / "kilder.yaml"
    entries = read_yaml(yaml_file)
    if not entries:
        sys.exit(f"No entries: {yaml_file} is missing or empty (run convert first)")
    original = copy.deepcopy(entries)
    context = ssl.create_default_context()
    ua = helpers.DEFAULT_USER_AGENT

    counts: Counter = Counter()
    todo = []
    skipped_lines = []
    for e in entries.values():
        label = e["id"]
        public, _warning = public_status(e)
        if archive_skipped(e):
            counts["SKIP"] += 1
            skipped_lines.append(f"SKIP       {label}: arkiv: skip in kilder.yaml")
        elif not public:
            counts["PRIVATE"] += 1
            skipped_lines.append(
                f"PRIVATE    {label}: offentlig: {e.get('offentlig')} (never archived)"
            )
        elif e.get("arkiv"):
            counts["KEPT"] += 1
            skipped_lines.append(
                f"KEPT       {label}: arkiv already set "
                f"({show(e['arkiv'])}); never overwritten"
            )
        elif not e.get("url"):
            counts["NO URL"] += 1
            skipped_lines.append(
                f"NO URL     {label}: nothing to archive (no url in kilder.yaml)"
            )
        elif WAYBACK_HOST in e["url"]:
            counts["SKIPPED"] += 1
            skipped_lines.append(
                f"SKIPPED    {label}: url already points to {WAYBACK_HOST}"
            )
        else:
            todo.append(e)

    say(
        f"{top}: {len(entries)} entries, {len(todo)} to look up"
        + ("   [DRY RUN: nothing will be written]" if dry_run else "")
    )
    for line in skipped_lines:
        say(line, detail=True)

    last_save = 0.0
    for i, e in enumerate(todo):
        eid, url = e["id"], e["url"]
        archive_url, _timestamp, _status, source = helpers.find_wayback(
            url, timeout, ua, context
        )
        if archive_url:
            counts["FOUND"] += 1
            say(f"FOUND      {eid}: {archive_url}  [{source}]")
        elif save:
            if dry_run:
                counts["WOULD CAPTURE"] += 1
                say(
                    f"WOULD CAPTURE {eid}: no snapshot yet; would request one for {url}"
                )
                continue
            wait = delay - (time.monotonic() - last_save)
            if last_save and wait > 0:
                time.sleep(wait)
            last_save = time.monotonic()
            try:
                archive_url = request_capture(url, max(timeout, 120), ua, context)
            except urllib.error.HTTPError as err:
                counts["FAILED"] += 1
                say(
                    f"FAILED     {eid}: HTTP {err.code} from archive.org"
                    + (
                        " (rate-limited; stopping, try again later)"
                        if err.code == 429
                        else ""
                    )
                )
                if err.code == 429:
                    counts["NOT TRIED"] += len(todo) - i - 1
                    break
                continue
            except Exception as err:  # noqa: BLE001
                counts["FAILED"] += 1
                say(f"FAILED     {eid}: {type(err).__name__}: {err}")
                continue
            counts["CAPTURED"] += 1
            say(f"CAPTURED   {eid}: {archive_url}")
        else:
            counts["NO SNAPSHOT"] += 1
            say(f"NO SNAPSHOT {eid}: none found for {url} (use --save to capture it)")
            continue
        if not dry_run:
            entries[eid]["arkiv"] = archive_url
            write_yaml(yaml_file, entries)  # after every entry: safe to interrupt

    left = (
        counts["NO SNAPSHOT"]
        + counts["FAILED"]
        + counts["NOT TRIED"]
        + counts["WOULD CAPTURE"]
    )
    print_summary(
        f"{top} ({len(entries)} entries)",
        counts,
        [
            ("KEPT", "arkiv already set, left alone"),
            (
                "FOUND",
                "existing Wayback snapshot "
                + ("would be " if dry_run else "")
                + "written to arkiv",
            ),
            ("CAPTURED", "new capture requested and written to arkiv"),
            ("WOULD CAPTURE", "no snapshot; --save would request a capture"),
            ("NO SNAPSHOT", "no snapshot found (use --save)"),
            ("FAILED", "capture request failed"),
            ("NOT TRIED", "not tried because archive.org rate-limited the run"),
            ("SKIPPED", f"url already points to {WAYBACK_HOST}"),
            ("SKIP", "arkiv: skip, never archived"),
            ("PRIVATE", "offentlig: nei, never archived"),
            ("NO URL", "no url in kilder.yaml"),
        ],
        hint_verbose="KEPT",
    )
    if dry_run:
        say("kilder.yaml: not written (dry run)")
    elif entries == original:
        say(f"kilder.yaml: no changes, file not rewritten ({disp(yaml_file)})")
    else:
        n = sum(
            1 for k in entries if entries[k].get("arkiv") != original[k].get("arkiv")
        )
        say(
            f"kilder.yaml: written, {n} arkiv field{'s' if n != 1 else ''} filled in "
            f"({disp(yaml_file)})"
        )
    return 1 if left else 0


# --------------------------------------------------------------------------- export


def private_entry(e: dict) -> dict:
    """What a private entry (offentlig: nei) shows in the public list: id and title,
    so articles can cite it, but no url, arkiv, lenker or anything else."""
    return {k: e[k] for k in PRIVATE_EXPORT_FIELDS if e.get(k) not in (None, "", [])}


def export_entry(e: dict) -> dict:
    """The public part of one entry: only EXPORT_FIELDS, never arkiv: skip."""
    out = {}
    for k in EXPORT_FIELDS:
        v = e.get(k)
        if v in (None, "", []) or (k == "arkiv" and archive_skipped(e)):
            continue
        if k == "hentet" and isinstance(v, (dt.date, dt.datetime)):
            v = v.isoformat()
        out[k] = v
    return out


def cmd_export(folder: str, out_dir: Path, dry_run: bool) -> int:
    """Write the public source list <out_dir>/<top folder>.yaml from the private kilder.yaml."""
    top = top_only(folder, "export")
    yaml_file = SOURCES_DIR / top / "kilder.yaml"
    if not yaml_file.exists():
        sys.exit(f"Source list not found: {yaml_file} (run convert first)")
    entries = read_yaml(yaml_file)
    out_file = out_dir / f"{top}.yaml"
    counts: Counter = Counter()
    public: dict[str, dict] = {}
    warnings = 0
    say(
        f"{top}: export {len(entries)} entries -> {disp(out_file)}"
        + ("   [DRY RUN: nothing will be written]" if dry_run else "")
    )
    for eid in sorted(entries):
        e = entries[eid]
        is_public, warning = public_status(e)
        if warning:
            warnings += 1
            say(f"WARNING    {eid}: {warning}")
        if not is_public:
            # Citable by id, but only the title: never a link or anything else.
            public[eid] = private_entry(e)
            counts["PRIVATE"] += 1
            say(
                f"PRIVATE    {eid}: offentlig: {e.get('offentlig')}; title only",
                detail=True,
            )
            continue
        item = export_entry(e)
        public[eid] = item
        if not ({"url", "arkiv", "lenker"} & set(item)):
            counts["NO LINK"] += 1
            say(f"NO LINK    {eid}: no url, arkiv or lenker; without a link", detail=True)
            continue
        counts["EXPORTED"] += 1
        if archive_skipped(e):
            counts["ARKIV SKIP"] += 1
        say(f"EXPORTED   {eid}", detail=True)

    header = (
        "# cspell:disable\n"
        "# Offentlig kildeliste, generert av scripts/ppkilder.py export fra den private\n"
        f"# {top}/kilder.yaml. Ikke rediger her; endringer overskrives.\n\n"
    )
    text = header + yaml.safe_dump(
        [public[k] for k in sorted(public)],
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    old = out_file.read_text(encoding="utf-8") if out_file.exists() else None

    print_summary(
        f"{top} ({len(entries)} entries in kilder.yaml)",
        counts,
        [
            (
                "EXPORTED",
                "public entries "
                + ("that would be written" if dry_run else "written")
                + " to the public list",
            ),
            ("PRIVATE", "offentlig: nei, exported with the title only (no link)"),
            ("NO LINK", "no url, arkiv or lenker, exported without a link"),
            ("ARKIV SKIP", "exported, but arkiv left out (arkiv: skip)"),
        ],
        hint_verbose="EXPORTED",
    )
    if not public and old is None:
        say(f"{disp(out_file)}: nothing to export, file not created")
    elif text == old:
        say(f"{disp(out_file)}: no changes, file not rewritten")
    elif dry_run:
        say(f"{disp(out_file)}: would be {'written' if old is None else 'updated'}")
    else:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(text, encoding="utf-8")
        say(f"{disp(out_file)}: {'written' if old is None else 'updated'}")
    return 1 if warnings else 0


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--paperpile",
        type=Path,
        default=DEFAULT_PAPERPILE,
        help=f"local mount of the Paperpile mirror (default: {DEFAULT_PAPERPILE})",
    )
    ap.add_argument(
        "--bib",
        type=Path,
        default=None,  # resolved after parsing, from the chosen --paperpile
        help=f"BibTeX export from Paperpile (default: env BOMFAST_BIB, else "
        f"<mirror>/{BIB_NAME})",
    )
    ap.add_argument(
        "--sources",
        type=Path,
        default=DEFAULT_SOURCES,
        help="private repo with kilder.yaml and tekst/ per folder "
        f"(default: {DEFAULT_SOURCES}; env BOMFAST_SOURCES)",
    )
    commands = ap.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also list every unchanged/ignored source, with the reason",
    )
    common.add_argument(
        "--log",
        type=Path,
        metavar="FILE",
        help="append the full (verbose) output, with a timestamp, to FILE",
    )
    common.add_argument(
        "folders",
        nargs="*",
        help="only these top folders, e.g. 001_nasjonal_transportplan_ntp "
        "(default: all)",
    )

    c = commands.add_parser(
        "convert",
        parents=[common],
        help="convert new/changed PDFs and update kilder.yaml",
    )
    c.add_argument(
        "--force", nargs="+", default=[], metavar="ID", help="re-convert these ids"
    )
    c.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be done, without writing anything",
    )

    checksum_help = (
        "hash every PDF, also those with the same path, size and date as in "
        "kilder.yaml (slow: on the rclone mount it downloads them all)"
    )
    k = commands.add_parser(
        "check",
        parents=[common],
        help="compare the .bib file and the mirror with kilder.yaml (never writes)",
    )
    k.add_argument("--checksum", action="store_true", help=checksum_help)

    p = commands.add_parser(
        "prune",
        parents=[common],
        help="like check, but removes entries and text files for sources that are no "
        "longer in the .bib file",
    )
    p.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be removed, without writing anything",
    )
    p.add_argument("--checksum", action="store_true", help=checksum_help)

    u = commands.add_parser(
        "upload",
        help="send the PDFs of these sources to archive.org and write arkiv "
        "(dry run unless --upload)",
    )
    u.add_argument("ids", nargs="+", metavar="ID", help="citekeys to upload")
    u.add_argument(
        "--upload",
        action="store_true",
        help="really upload and write arkiv; without it, only show what would be done",
    )
    u.add_argument(
        "--item",
        default=ia.DEFAULT_ITEM,
        help=f"archive.org item (default: {ia.DEFAULT_ITEM})",
    )
    u.add_argument("-v", "--verbose", action="store_true", help=argparse.SUPPRESS)
    u.add_argument("--log", type=Path, metavar="FILE", help="append the output to FILE")

    a = commands.add_parser(
        "archive",
        parents=[common],
        help="fill empty `arkiv` fields with Wayback snapshots of each url "
        "(reads kilder.yaml only)",
    )
    a.add_argument(
        "--save",
        action="store_true",
        help="request a new capture (Save Page Now) when no snapshot exists",
    )
    a.add_argument(
        "--delay",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="minimum seconds between capture requests (default: 15)",
    )
    a.add_argument(
        "--timeout",
        type=int,
        default=15,
        metavar="SECONDS",
        help="timeout for lookups (default: 15; captures wait at least 120)",
    )
    a.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="look up snapshots and show what would be filled in, without "
        "writing anything or requesting captures",
    )

    e = commands.add_parser(
        "export",
        parents=[common],
        help="write the public source list (public entries, open fields only) "
        "into bomfastinfo",
    )
    e.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_EXPORT,
        metavar="DIR",
        help=f"folder for <folder>.yaml (default: {DEFAULT_EXPORT})",
    )
    e.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be exported, without writing anything",
    )

    args = ap.parse_args()
    global LOG, SOURCES_DIR
    SOURCES_DIR = args.sources.expanduser().resolve()
    check_sources_dir(SOURCES_DIR)
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
    LOG = Log(verbose=args.verbose, path=args.log)
    if args.log:
        LOG.file.write(
            f"\n=== {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC  ppkilder.py "
            f"{' '.join(sys.argv[1:])} ===\n"
        )

    if args.command in ("archive", "export"):
        # kilder.yaml only: neither the mirror nor the .bib file is needed.
        folders = args.folders or yaml_tops()
        if not folders:
            sys.exit(f"No kilder.yaml in {SOURCES_DIR} (run convert first)")
        rc = 0
        for folder in folders:
            if args.command == "export":
                rc |= cmd_export(folder, args.out.expanduser(), args.dry_run)
            else:
                rc |= cmd_archive(
                    folder, args.save, args.dry_run, args.delay, args.timeout
                )
        return rc

    paperpile = args.paperpile.expanduser()
    bib = args.bib.expanduser() if args.bib else default_bib(paperpile)

    if args.command == "upload":
        return cmd_upload(paperpile, bib, args.ids, args.upload, args.item)
    if args.command == "convert":
        return cmd_convert(paperpile, bib, args.folders, set(args.force), args.dry_run)
    return cmd_check(
        paperpile,
        bib,
        args.folders,
        prune=(args.command == "prune"),
        dry_run=getattr(args, "dry_run", False),
        checksum=args.checksum,
    )


if __name__ == "__main__":
    sys.exit(main())
