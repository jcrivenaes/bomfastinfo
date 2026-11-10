#!/usr/bin/env python3
# cspell:disable
"""Convert the sources in a Paperpile BibTeX export to text and maintain kilder.yaml.

The alternative to kilder.py for sources kept in Paperpile instead of in our own Drive
folder. Paperpile has no API, so two things are read:
  - the .bib file from Paperpile's BibTeX workflow (profile picture -> Workflows and
    Integrations -> BibTeX export), auto-exporting only the bomfast-kilder label to Google
    Drive. Paperpile names it bomfast-kilder.bib and puts it at the top of the account that
    owns Paperpile; move it into the Paperpile folder (allowed, it keeps syncing), so it is
    shared and mounted together with the PDFs
  - the PDFs in Paperpile's mirror on Google Drive, through a local rclone mount

The text versions and kilder.yaml go to the same private repo and the same place as those
from kilder.py: <sources>/<top folder>/kilder.yaml and tekst/. The PDF conversion is the
one in kilder.py, so text files look the same.

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

    # archive and export read kilder.yaml only, so use kilder.py for those:
    python3 scripts/kilder.py archive 001_nasjonal_transportplan_ntp
    python3 scripts/kilder.py export --all

Output:
    Same style as kilder.py: one line with a status tag per changed source, and a summary.
    -v/--verbose also lists unchanged sources, --log FILE appends the full output to FILE.

How a .bib entry is read:
    citekey   the id, and the name of the text file: <citekey>.md. Used in the kilde
              shortcode, so it must be unique across all folders. A citekey used by
              several .bib entries is skipped in all of them, with a warning. Its
              entry in kilder.yaml is kept, but the control labels of every copy
              still apply to it (_PRIVAT on one copy is enough), and upload
              refuses it.
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
                    _ABO      arkiv: skip: paywalled; in the public list with its
                              url, but never archived (a Wayback capture could
                              republish the full text)
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
    hentet, offentlig, merknad, ...) are yours and are kept, see kilder.py for what they
    mean.

Living next to kilder.py:
    Entries from this script have the field `paperpile` and never `fil`. kilder.py leaves
    entries without `fil` alone in convert, check and prune, and this script only touches
    entries with `paperpile`. Both can therefore use the same kilder.yaml. An id already
    used by an entry from kilder.py gives a warning, and that source is skipped.

Duplicates:
    The same PDF (same sha256) in several entries is reported as DUPLICATE by check,
    prune and convert, also against entries from kilder.py, just like in kilder.py (see
    `Duplicates` there). A notice, not an issue; nothing is merged or removed.

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

Mounting the mirror:
    The Paperpile folder is under "Shared with me", so gdrive:bomfast does not include it:
        mkdir -p ~/GoogleDrive/Paperpile
        rclone mount gdrive:Paperpile ~/GoogleDrive/Paperpile --drive-shared-with-me \\
            --read-only --vfs-cache-mode=full --dir-cache-time=1h --poll-interval=15s

Dependencies:
    The same as kilder.py (which is imported, so it must be in the same folder).
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import difflib
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
import kilder
from kilder import (
    TECH_FIELDS,
    changed_fields,
    check_sources_dir,
    convert_pdf,
    describe,
    disp,
    human_size,
    in_scope,
    move_text,
    print_summary,
    read_yaml,
    save_yaml,
    say,
    sha256,
)

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
# Control labels start with "_" and are never topics. Every one of them keeps the source
# away from archive.org (arkiv: skip); _PRIVAT also keeps it out of the public list
# (offentlig: nei). Matched without regard to case. Removing a label never undoes what it
# set (that takes an edit in kilder.yaml), so a lost label cannot publish anything.
CONTROL_PREFIX = "_"
PRIVATE_LABEL = "_PRIVAT"  # private: not in the public list, not archived
SUBSCRIPTION_LABEL = "_ABO"  # paywalled: in the public list, but never archived
KNOWN_CONTROL_LABELS = (PRIVATE_LABEL, SUBSCRIPTION_LABEL)
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
    no_archive: bool = False  # has any control label (_PRIVAT, _ABO, ...)

    @property
    def folder(self) -> str:
        return self.top

    @property
    def tekst(self) -> str:
        return f"tekst/{self.id}.md"


@dataclass
class Held:
    """A citekey used by several .bib entries: no source is made from it, but the
    control labels of every copy still count (the strictest wins)."""

    private: bool = False  # some copy has _PRIVAT
    no_archive: bool = False  # some copy has a control label


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


def bib_keywords(fields: dict[str, str]) -> list[str]:
    """The Paperpile labels of a .bib entry."""
    keywords = [k.strip() for k in unlatex(fields.get("keywords", "")).split(";")]
    return [k for k in keywords if k]


def read_sources(
    bib: Path,
) -> tuple[list[Source], set[str], Counter, bytes, dict[str, Held]]:
    """The usable sources in the .bib file, every citekey that must not count as gone,
    counts of what was left out, the file as read, and the strictest control labels of
    each citekey that is used twice (see Held). Warns on the way."""
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
    held = {key: Held() for key in duplicates}
    for key, fields in entries:
        if key in held:
            controls = [k for k in bib_keywords(fields) if is_control_label(k)]
            held[key].private |= any(is_label(k, PRIVATE_LABEL) for k in controls)
            held[key].no_archive |= bool(controls)
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
        files = [f.strip() for f in unlatex(fields.get("file", "")).split(";")]
        files = [f for f in files if f]
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
                private=any(is_label(k, PRIVATE_LABEL) for k in controls),
                no_archive=bool(controls),
            )
    if not sources:
        # A broken or empty export must never look like "all sources were removed".
        sys.exit(f"No sources with a top folder label in {bib}; nothing done.")
    return list(sources.values()), set(sources) | unusable, skipped, raw, held


def copy_bib(bib: Path, raw: bytes, write: bool) -> None:
    """Keep <sources>/paperpile.bib equal to the .bib file this run was based on.

    raw is the content read_sources() parsed, so a file Paperpile rewrites in the
    meantime cannot slip in unchecked.
    """
    target = kilder.SOURCES_DIR / BIB_COPY
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
        for path in sorted(kilder.SOURCES_DIR.glob("*/kilder.yaml")):
            self.top(path.parent.name)

    def top(self, name: str) -> dict[str, dict]:
        if name not in self.entries:
            path = kilder.SOURCES_DIR / name / "kilder.yaml"
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

    def foreign(self) -> dict[str, str]:
        """{id: top folder} for the entries that are not ours (from kilder.py)."""
        return {
            eid: top
            for top, entries in self.entries.items()
            for eid, entry in entries.items()
            if MARKER not in entry
        }

    def save(self, dry_run: bool) -> None:
        for top, entries in self.entries.items():
            if entries != self.original[top]:
                path = kilder.SOURCES_DIR / top / "kilder.yaml"
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
        entry["arkiv"] = kilder.ARCHIVE_SKIP


def describe_meta(changes: dict) -> str:
    """describe() from kilder.py, but with emneord/vedlegg as text instead of "N links"."""

    def plain(value):
        if isinstance(value, list) and all(isinstance(x, str) for x in value):
            return "; ".join(value)
        return value

    return describe({k: (plain(old), plain(new)) for k, (old, new) in changes.items()})


def render_header(entry: dict) -> str:
    """The comment at the top of the text file, in Norwegian like the one from kilder.py."""
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
    sources, in_bib, counts, raw, held = read_sources(bib)
    copy_bib(bib, raw, write=not dry_run)
    lists = Lists()
    owned = lists.owned()
    foreign = lists.foreign()
    scope = [s for s in sources if selected(s.folder, folders)]
    renames = find_renames(scope, owned, in_bib, foreign, paperpile)
    unknown = force - {s.id for s in scope}
    if unknown:
        say(f"WARNING    --force: no such id in scope: {', '.join(sorted(unknown))}")
    index = kilder.checksum_index(lists.entries)

    def outcome(kind: str, eid: str, msg: str = "", detail: bool = False) -> None:
        counts[kind] += 1
        say(f"{kind:<10} {eid}" + (f": {msg}" if msg else ""), detail=detail)

    def relocate(old_top: str, old_id: str, entry: dict, src: Source) -> None:
        """Move the entry and its text file to where src says they belong."""
        new_text = kilder.SOURCES_DIR / src.top / src.tekst
        old_text = entry.get("tekst")
        if old_text and not dry_run:
            move_text(kilder.SOURCES_DIR / old_top, old_text, new_text, src.pdf)
        lists.top(old_top).pop(old_id)
        lists.top(src.top)[src.id] = entry
        entry["id"] = src.id
        if old_text:
            entry["tekst"] = src.tekst

    def handle(src: Source) -> None:
        text = kilder.SOURCES_DIR / src.top / src.tekst
        if src.id in foreign:
            outcome(
                "WARNING",
                src.id,
                f"id already used in {foreign[src.id]} by kilder.py; skipped",
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
                    and (kilder.SOURCES_DIR / old_top / old_text).exists()
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
            if dups := kilder.other_copies(index, checksum, src.top, entry):
                outcome(
                    "DUPLICATE",
                    src.id,
                    kilder.same_pdf_as(dups) + "; kept as its own entry",
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

    def restrict(eid: str, labels: Held) -> None:
        """Apply the labels of a citekey used twice to its existing entry, in every
        folder: entry order in the .bib file must not leave it public."""
        _top, entry = owned[eid]
        before = copy.deepcopy(entry)
        apply_controls(entry, labels.private, labels.no_archive)
        if meta := changed_fields(before, entry):
            outcome(
                "METADATA",
                eid,
                "citekey used twice, the labels of every copy count; kilder.yaml: "
                + describe_meta(meta),
            )

    try:
        for eid, labels in sorted(held.items()):
            if eid in owned:
                restrict(eid, labels)
        for src in scope:
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


def cmd_check(
    paperpile: Path,
    bib: Path,
    folders: list[str],
    prune: bool = False,
    dry_run: bool = False,
) -> int:
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
        if src.id in foreign:
            report(
                "ID CONFLICT",
                src.id,
                f"id already used in {foreign[src.id]} by kilder.py",
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
        elif src.pdf and entry.get("sha256") != sha256(pdf):
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
            and not (kilder.SOURCES_DIR / top / entry["tekst"]).exists()
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
        if not wanted.get("url"):
            report("NO URL", src.id, "no url (add it in Paperpile)", issue=False)
        if not src.private and not kilder.public_status(wanted)[0]:
            report(
                "NO LABEL",
                src.id,
                f"offentlig: {wanted.get('offentlig')} in kilder.yaml, but no "
                f"{PRIVATE_LABEL} label in Paperpile; stays private (add the label, or "
                "set offentlig: ja in kilder.yaml to make it public)",
                issue=False,
            )
        elif not src.no_archive and kilder.archive_skipped(wanted):
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
                kilder.SOURCES_DIR / top / entry["tekst"]
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

    # The same PDF in several entries, in any kilder.yaml (also from kilder.py). A
    # notice, not an issue. Entries that are gone from the .bib file are left out:
    # prune removes them, so they are not copies anyone has to deal with.
    current = {
        top: {
            eid: e
            for eid, e in entries.items()
            if MARKER not in e or eid in in_bib or eid in renamed
        }
        for top, entries in lists.entries.items()
    }
    for group in kilder.duplicate_groups(kilder.checksum_index(current)):
        mine = [
            (t, e)
            for t, e in group
            if MARKER in e and selected(entry_folder(t, e), folders)
        ]
        if mine:
            others = [m for m in group if m[1] is not mine[0][1]]
            report(
                "DUPLICATE", mine[0][1]["id"], kilder.same_pdf_as(others), issue=False
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
            ("ID CONFLICT", "the citekey is used by an entry from kilder.py"),
            ("RENAMED", "the citekey changed, convert carries the entry over"),
            ("GONE", "in kilder.yaml, not in the .bib file"),
            ("NO URL", "entries without url (not counted as issues)"),
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
    kilder.REPO / ia.DEFAULT_RESULTS_PATH
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
        return "not from Paperpile (a kilder.py entry); upload only handles Paperpile"
    public, _warning = kilder.public_status(entry)
    if not public:
        return (
            f"offentlig: {entry.get('offentlig')}; private sources are never uploaded"
        )
    if kilder.archive_skipped(entry):
        return "arkiv: skip in kilder.yaml; never uploaded"
    if entry.get("arkiv"):
        return f"arkiv already set ({entry['arkiv']}); never overwritten"
    if src is None:
        if in_bib:
            return "unusable in the .bib file (see the WARNING above); never uploaded"
        return "not in the .bib file any more"
    if src.no_archive:
        what = PRIVATE_LABEL if src.private else "a label starting with _"
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
    if entry.get("url"):
        ia.record_original_url_metadata(item, remote, entry["url"])
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
        for p in sorted(kilder.SOURCES_DIR.glob("*/kilder.yaml"))
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
        kilder.write_yaml(path, entries)  # after every source: safe to interrupt

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
        default=kilder.DEFAULT_SOURCES,
        help="private repo with kilder.yaml and tekst/ per folder "
        f"(default: {kilder.DEFAULT_SOURCES}; env BOMFAST_SOURCES)",
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

    commands.add_parser(
        "check",
        parents=[common],
        help="compare the .bib file and the mirror with kilder.yaml (never writes)",
    )

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

    args = ap.parse_args()
    kilder.SOURCES_DIR = args.sources.expanduser().resolve()
    check_sources_dir(kilder.SOURCES_DIR)
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
    kilder.LOG = kilder.Log(verbose=args.verbose, path=args.log)
    if args.log:
        kilder.LOG.file.write(
            f"\n=== {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC  ppkilder.py "
            f"{' '.join(sys.argv[1:])} ===\n"
        )
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
    )


if __name__ == "__main__":
    sys.exit(main())
