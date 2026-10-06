#!/usr/bin/env python3
# cspell:disable
"""Convert source documents (PDF) from the Drive folder to text and maintain kilder.yaml.

The originals live on Google Drive (local copy, e.g. ~/GoogleDrive/bomfast). The text
versions and kilder.yaml go into the repo under kilder/<folder>/. Hugo does not publish
kilder/, so this is working material, not part of the website.

Usage:
    # Convert one folder (only new or changed PDFs):
    python3 scripts/kilder.py convert 001_nasjonal_transportplan_ntp

    # Dry run: show what would be converted, moved or removed, without writing anything
    # (works for both convert and prune; check never writes anything):
    python3 scripts/kilder.py convert 101_hordfast --dry-run
    python3 scripts/kilder.py prune 101_hordfast -n

    # Only one subfolder (useful while tidying up a large folder):
    python3 scripts/kilder.py convert 101_hordfast/hordfast_regplan/02_plankart

    # All folders:
    python3 scripts/kilder.py convert --all

    # Force re-conversion of one file:
    python3 scripts/kilder.py convert 001_nasjonal_transportplan_ntp --force ntp_2018_2029

    # Check that Drive and repo agree (missing files, changed checksums, empty URLs):
    python3 scripts/kilder.py check 001_nasjonal_transportplan_ntp

    # Remove entries and text files for PDFs deleted from Drive
    # (or later added to EXCLUDE.txt):
    python3 scripts/kilder.py prune 101_hordfast

    # Fill in empty `arkiv` fields with Wayback Machine snapshots of each `url`
    # (reads kilder.yaml only, does not need the Drive folder):
    python3 scripts/kilder.py archive 001_nasjonal_transportplan_ntp
    python3 scripts/kilder.py archive 101_hordfast --dry-run
    # Also ask Wayback to capture URLs that have no snapshot yet (slow, rate-limited):
    python3 scripts/kilder.py archive 101_hordfast --save

Output (what the script tells you):
    Every changed file gets one line with a status tag (`archive` and `check` use similar
    tags for entries): NEW, UPDATED (the PDF changed),
    REBUILT (same PDF, text file regenerated), MOVED (moved/renamed on Drive), METADATA
    (PDF and text untouched, but kilder.yaml fields changed, e.g. url filled in) or
    WARNING. Unchanged files are counted in the summary at the end, together with files
    skipped by EXCLUDE.txt, and the script says whether kilder.yaml was rewritten.
        -v, --verbose   also list every unchanged/skipped file, with the reason
        --log FILE      append the full (verbose) output, with a timestamp, to FILE
    With --dry-run the same lines describe what *would* happen; nothing is written.

Excluding folders:
    Put patterns in kilder/<top folder>/EXCLUDE.txt, one per line, e.g.
        utkast                               # every folder named utkast
        hordfast_regplan/90_Arbeidsmateriale # one specific folder
    Backup folders, trash folders and files ending in ~ are always skipped.

Structure and ids:
    There is one kilder.yaml per top folder (kilder/101_hordfast/kilder.yaml), also when
    you run on a subfolder. Subfolders on Drive are mirrored under tekst/.
    id = file name without extension, independent of subfolder. If you move a PDF to
    another subfolder it keeps its id, and the script moves the text file along. If you
    rename it, it is recognised by its checksum; the id then changes and the script tells
    you, so you can update references in articles. File names must therefore be unique
    within a top folder.

The Drive folder can be set with --drive or the environment variable BOMFAST_DRIVE
(default: ~/GoogleDrive/bomfast).

Dependencies:
    pip install pymupdf pymupdf4llm pyyaml
    # Only for scanned PDFs without a text layer:
    sudo apt install tesseract-ocr tesseract-ocr-nor

kilder.yaml:
    The script fills in the technical fields (fil, sha256, sider, tekst, konvertert, ocr).
    Fields you fill in yourself (tittel, dokument, url, arkiv, lenker, merknad, ...) are
    kept on every run. Comments in the YAML file are not kept.

Archive links (arkiv):
    `archive` looks up the closest existing Wayback snapshot of each entry's url and writes
    it to `arkiv`, but only if `arkiv` is empty: a value you wrote yourself is never
    overwritten. Entries without a url are skipped, and so are urls that already point to
    web.archive.org. With --save, urls that have no snapshot are captured with Save Page
    Now (about one request per --delay seconds; stops if archive.org answers 429). The
    snapshot lookup reuses find_wayback() from check_links_wayback.py, which also tries
    URL variants (http/https, with/without www, ...) and rejects truncated PDF captures.
    kilder.yaml is saved after every filled-in entry, so an interrupted run loses nothing.
    To use your own archive.org upload as `arkiv` instead, write that link by hand.

URLs:
    kilder.yaml is the source of truth. A <name>.url file next to the PDF on Drive (and
    <name>_annet.txt for extra links) is only used to fill in url/lenker when the field
    in kilder.yaml is empty, typically the first time a document is converted. To add or
    correct a URL, edit kilder.yaml. `check` reports URL MISMATCH if a .url file on Drive
    disagrees with kilder.yaml; kilder.yaml wins.
    The field names, the folder names (kilder/, tekst/) and the page markers in the text
    files are Norwegian on purpose: they are data that sits next to the Norwegian
    documents and articles.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import fnmatch
import functools
import hashlib
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO / "kilder"
DEFAULT_DRIVE = Path(
    os.environ.get("BOMFAST_DRIVE", "~/GoogleDrive/bomfast")
).expanduser()
EXCLUDE_FILE = "EXCLUDE.txt"
SAVE_API = "https://web.archive.org/save/"  # Wayback "Save Page Now"
WAYBACK_HOST = "web.archive.org"

# Folders/files on Drive that are never converted (matched against path components).
ALWAYS_EXCLUDE = ["*backup*", ".Trash*", ".trash*", "*~"]

# Below this average (characters per page) the PDF is treated as scanned without text.
MIN_CHARS_PER_PAGE = 200

# Order of fields in kilder.yaml. Unknown fields (your own) are appended at the end.
FIELD_ORDER = [
    "id",
    "fil",
    "tittel",
    "dokument",
    "url",
    "arkiv",
    "lenker",
    "merknad",
    "sider",
    "bytes",
    "sha256",
    "tekst",
    "konvertert",
    "ocr",
]


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


TECH_FIELDS = {"id", "fil", "bytes", "sha256", "sider", "tekst", "konvertert", "ocr"}


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


def read_exclude(top_name: str) -> list[str]:
    """Read kilder/<top folder>/EXCLUDE.txt: one pattern per line, # for comments."""
    path = SOURCES_DIR / top_name / EXCLUDE_FILE
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def exclusion_reason(rel: Path, extra: list[str] = ()) -> str | None:
    """The pattern that excludes this path (None if it is not excluded).

    Patterns without / (e.g. "utkast", "*backup*") match a folder or file name anywhere
    in the path. Patterns with / (e.g. "hordfast_regplan/90_Arbeidsmateriale") match the
    path from the top folder and everything below it. * may span several folder levels.
    """
    path_str = rel.as_posix()
    for source, patterns in (("built-in", ALWAYS_EXCLUDE), (EXCLUDE_FILE, extra)):
        for pattern in patterns:
            pat = pattern.strip("/")
            if "/" not in pat:
                hit = any(fnmatch.fnmatch(part, pat) for part in rel.parts)
            else:
                hit = fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(
                    path_str, pat + "/*"
                )
            if hit:
                return f"{source}: {pattern}"
    return None


def is_excluded(rel: Path, extra: list[str] = ()) -> bool:
    return exclusion_reason(rel, extra) is not None


def find_excluded(top: Path, sub: str = "") -> list[tuple[str, str]]:
    """PDFs under top/sub that are skipped, with the pattern that skipped them."""
    root = top / sub if sub else top
    extra = read_exclude(top.name)
    found = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() == ".pdf":
            rel = p.relative_to(top)
            if reason := exclusion_reason(rel, extra):
                found.append((rel.as_posix(), reason))
    return found


def read_url(path: Path) -> str:
    """Read both plain URL files and Windows shortcuts ([InternetShortcut] URL=...)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^URL=(\S+)", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    m = re.search(r"https?://\S+", text)
    return m.group(0).strip() if m else ""


def read_extra_links(path: Path) -> list[dict]:
    """Read <id>_annet.txt with lines like: "Description": https://..."""
    links = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r'\s*"?([^":]+?)"?\s*:\s*(https?://\S+)', line)
        if m:
            links.append({"tittel": m.group(1).strip(), "url": m.group(2).strip()})
        elif u := re.search(r"https?://\S+", line):
            links.append({"tittel": "", "url": u.group(0)})
    return links


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
    import subprocess

    out = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=False
    )
    return "nor" in out.stdout.split()


# --------------------------------------------------------------------------- conversion


def convert_pdf(pdf: Path, out: Path, checksum: str, rel: Path) -> dict:
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
            "Generert av scripts/kilder.py. Ikke rediger for hånd; endringer overskrives.\n"
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


# --------------------------------------------------------------------------- kilder.yaml


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
        "# Kildeliste. Tekniske felt (fil, sider, bytes, sha256, tekst, konvertert, ocr)\n"
        "# oppdateres av scripts/kilder.py. Øvrige felt (tittel, dokument, url, arkiv,\n"
        "# lenker, merknad, ...) redigeres her og beholdes. url/lenker hentes fra .url- og\n"
        "# _annet.txt-filer på Drive bare når feltet er tomt; rett URL-er i denne fila.\n\n"
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
    rel = path.relative_to(REPO)
    if new_text == old_text:
        say(f"kilder.yaml: no changes, file not rewritten ({rel})")
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


def find_pdfs(top: Path, sub: str = "") -> list[Path]:
    """All PDFs under top/sub, except ALWAYS_EXCLUDE and kilder/<top>/EXCLUDE.txt."""
    root = top / sub if sub else top
    extra = read_exclude(top.name)
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() == ".pdf"
        and not is_excluded(p.relative_to(top), extra)
    )


def assign_ids(
    pdfs: list[Path], top: Path, entries: dict[str, dict]
) -> dict[Path, str]:
    """id = file name without extension.

    The id does not depend on the subfolder, so files can be moved around on Drive
    without changing ids (and references in articles). A file already in kilder.yaml
    always keeps its id. Only if a new file has the same name as another file in the top
    folder does it get the subfolders as a prefix, and the script warns about it.
    """
    file_to_id = {e["fil"]: eid for eid, e in entries.items() if e.get("fil")}
    rel = {p: p.relative_to(top) for p in pdfs}
    stem_count = Counter(r.stem for r in rel.values())
    ids: dict[Path, str] = {}
    on_disk = {r.as_posix() for r in rel.values()}
    # Ids of entries whose file has disappeared from Drive may be reused (typically:
    # the same file moved to another subfolder).
    taken = {
        eid for eid, e in entries.items() if not e.get("fil") or e["fil"] in on_disk
    }
    for p, r in rel.items():  # existing files first
        if r.as_posix() in file_to_id:
            ids[p] = file_to_id[r.as_posix()]
    for p, r in rel.items():  # then new files
        if p in ids:
            continue
        if r.stem in taken or stem_count[r.stem] > 1:
            ids[p] = "__".join(r.with_suffix("").parts)
            say(
                f"WARNING    {r.as_posix()}: the name {r.stem} is already in use; "
                f"using id {ids[p]}. Give the file a unique name."
            )
        else:
            ids[p] = r.stem
        taken.add(ids[p])
    return ids


def in_scope(file: str, sub: str) -> bool:
    return not sub or file == sub or file.startswith(sub.rstrip("/") + "/")


def move_text(target: Path, old: str, new: Path, new_file: str) -> None:
    """Move the text file after the PDF was moved/renamed on Drive, and fix the source line."""
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
        src.unlink()
        # Remove empty folders left behind by the move.
        for d in src.parents:
            if d == target / "tekst" or any(d.iterdir()):
                break
            d.rmdir()


def drive_url(pdf: Path) -> str | None:
    """URL from <name>.url next to the PDF on Drive, or None if there is no such file."""
    url_file = pdf.with_suffix(".url")
    return read_url(url_file) if url_file.exists() else None


def drive_links(pdf: Path) -> list[dict] | None:
    """Links from <name>_annet.txt next to the PDF on Drive, or None if there is none."""
    extra = pdf.with_name(pdf.stem + "_annet.txt")
    return read_extra_links(extra) if extra.exists() else None


def update_links(entry: dict, pdf: Path) -> None:
    """Seed url/lenker from Drive, but only when the field in kilder.yaml is empty.

    kilder.yaml is the source of truth once a value is there: correct URLs in
    kilder.yaml, not on Drive. `check` reports a mismatch if the Drive files differ.
    """
    if not entry.get("url"):
        entry["url"] = drive_url(pdf) or ""
    if not entry.get("lenker") and (links := drive_links(pdf)):
        entry["lenker"] = links


def detect_moves(on_drive: dict[str, Path], entries: dict[str, dict]) -> dict[str, str]:
    """Find PDFs that were moved or renamed on Drive: {new relative path: old id}.

    An entry whose file is gone from Drive is matched by checksum against PDFs that are
    not in kilder.yaml (anywhere in the top folder). If several files have the same
    content (e.g. a moved file plus a copy), the one with the old file name wins.
    """
    known = {e.get("fil") for e in entries.values()}
    unknown: dict[str, list[str]] = {}
    for rel, pdf in on_drive.items():
        if rel not in known:
            unknown.setdefault(sha256(pdf), []).append(rel)
    moves: dict[str, str] = {}
    for eid, e in entries.items():
        if not e.get("fil") or e["fil"] in on_drive or e.get("sha256") not in unknown:
            continue
        candidates = [r for r in unknown[e["sha256"]] if r not in moves]
        same_name = [r for r in candidates if Path(r).stem == Path(e["fil"]).stem]
        if candidates:
            moves[(same_name or candidates)[0]] = eid
    return moves


def split_folder(folder: str) -> tuple[str, str]:
    """'101_hordfast/a/b' -> ('101_hordfast', 'a/b')."""
    top_name, _, sub = folder.strip("/").partition("/")
    return top_name, sub


# --------------------------------------------------------------------------- commands


def cmd_convert(drive: Path, folder: str, force: set[str], dry_run: bool) -> None:
    top_name, sub = split_folder(folder)
    top = drive / top_name
    if not (top / sub).is_dir():
        sys.exit(f"Not found: {top / sub}")
    target = SOURCES_DIR / top_name
    yaml_file = target / "kilder.yaml"
    entries = read_yaml(yaml_file)
    original = copy.deepcopy(entries)

    # Ids are computed from the whole top folder, so they are the same regardless of
    # which subfolder you run on.
    all_pdfs = find_pdfs(top)
    ids = assign_ids(all_pdfs, top, entries)
    on_drive = {p.relative_to(top).as_posix(): p for p in all_pdfs}
    present = set(on_drive)
    moves = detect_moves(on_drive, entries)

    pdfs = find_pdfs(top, sub)
    say(
        f"{folder}: {len(pdfs)} PDFs"
        + ("   [DRY RUN: nothing will be written]" if dry_run else "")
    )
    force = force - set(ids.values())
    if (
        force
    ):  # leftover after discarding matched ids below would go unnoticed otherwise
        say(f"WARNING    --force: no such id in {folder}: {', '.join(sorted(force))}")
        force = set()
    counts: Counter = Counter()

    def outcome(kind: str, rel: str, msg: str = "", detail: bool = False) -> None:
        counts[kind] += 1
        say(f"{kind:<10} {rel}" + (f": {msg}" if msg else ""), detail=detail)

    for pdf in pdfs:
        rel = pdf.relative_to(top)
        rels = rel.as_posix()
        eid = ids[pdf]
        text = target / "tekst" / rel.with_suffix(".md")
        entry = entries.get(eid)
        before = copy.deepcopy(entry)
        force.discard(eid)

        # Fast path: same path, same size, and the PDF is not newer than the text
        # file -> don't hash the PDF.
        if (
            entry
            and entry.get("fil") == rels
            and entry.get("bytes") == pdf.stat().st_size
            and text.exists()
            and pdf.stat().st_mtime <= text.stat().st_mtime
            and eid not in force
        ):
            update_links(entry, pdf)
            meta = changed_fields(before, entry)
            if meta:
                outcome(
                    "METADATA",
                    rels,
                    "PDF and text untouched; kilder.yaml: " + describe(meta),
                )
            else:
                outcome(
                    "UNCHANGED",
                    rels,
                    "same path and size, PDF not newer than the text file "
                    "(checksum not recomputed)",
                    detail=True,
                )
            continue

        checksum = sha256(pdf)

        # Moved or renamed on Drive? (recognised by checksum in detect_moves)
        if rels in moves:
            old_id = moves[rels]
            old = entries[old_id]
            id_note = (
                f"id {old_id} -> {eid}: update references in articles!"
                if old_id != eid
                else f"id {eid} kept"
            )
            if old.get("tekst") and (target / old["tekst"]).exists():
                text_note = "text file moved"
            else:
                text_note = "text file was missing, will be rebuilt on the next run"
            outcome(
                "MOVED",
                rels,
                f"was {old['fil']} ({id_note}; {text_note}; checksum identical)",
            )
            if not dry_run:
                if old.get("tekst"):
                    move_text(target, old["tekst"], text, rels)
                entry = entries.pop(old_id)
                entry.update(
                    id=eid, fil=rels, tekst=text.relative_to(target).as_posix()
                )
                entries[eid] = entry
                update_links(entry, pdf)
            continue

        if entry is None:
            entry = entries.setdefault(eid, {"id": eid})
        elif entry.get("fil") and entry["fil"] != rels and entry["fil"] in present:
            outcome(
                "WARNING", rels, f"id {eid} is already used by {entry['fil']}; skipped"
            )
            continue
        if entry.get("fil") and entry["fil"] != rels and entry.get("tekst"):
            # Same name, but a new file elsewhere (the old one is gone): drop the old text.
            old_text = target / entry["tekst"]
            if old_text.exists() and old_text != text and not dry_run:
                old_text.unlink()
        entry["fil"] = rels
        update_links(entry, pdf)

        if entry.get("sha256") == checksum and text.exists() and eid not in force:
            entry["bytes"] = pdf.stat().st_size
            meta = changed_fields(before, entry)
            if meta:
                outcome(
                    "METADATA",
                    rels,
                    "PDF unchanged (checksum identical); kilder.yaml: "
                    + describe(meta),
                )
            else:
                outcome(
                    "UNCHANGED",
                    rels,
                    "checksum identical, text file present",
                    detail=True,
                )
            continue

        # The PDF has to be (re)converted. Work out why, for the log.
        old_sha = (before or {}).get("sha256")
        if not old_sha:
            kind, why = "NEW", "not in kilder.yaml before"
        elif old_sha != checksum:
            kind = "UPDATED"
            why = (
                f"PDF changed (sha256 {old_sha[:8]}… -> {checksum[:8]}…, "
                f"{human_size(before.get('bytes'))} -> {human_size(pdf.stat().st_size)})"
            )
        elif eid in force:
            kind, why = "REBUILT", "text regenerated because of --force (PDF unchanged)"
        else:
            kind, why = "REBUILT", "text file was missing (PDF unchanged)"

        if dry_run:
            outcome(kind, rels, why + "; text would be (re)written")
            continue

        started = time.monotonic()
        say(f"{kind:<10} {rels}: converting ...", end="")
        info = convert_pdf(pdf, text, checksum, rel)
        entry.update(
            bytes=pdf.stat().st_size,
            sha256=checksum,
            sider=info["pages"],
            tekst=text.relative_to(target).as_posix(),
            konvertert=info["converted"],
            ocr=info["ocr"],
        )
        # Suggest title/document from PDF metadata, only if the field is empty.
        if not entry.get("tittel") and info["pdf_subject"]:
            entry["tittel"] = info["pdf_subject"]
        if not entry.get("dokument") and " " in info["pdf_title"]:  # skips "Stm46" etc.
            entry["dokument"] = info["pdf_title"]
        meta = changed_fields(before, entry, ignore=TECH_FIELDS)
        counts[kind] += 1
        pages = (
            f"pages {before['sider']} -> {info['pages']}"
            if kind == "UPDATED" and before.get("sider")
            else f"{info['pages']} page{'s' if info['pages'] != 1 else ''}"
        )
        say(
            f" done in {time.monotonic() - started:.1f} s. {why}. "
            f"{pages}, text {entry['tekst']}"
            + (", OCR" if info["ocr"] else "")
            + (f". kilder.yaml: {describe(meta)}" if meta else ""),
            cont=True,
        )

    # Entries for _annet.txt without a matching PDF (e.g. links only).
    for extra in (top / sub).rglob("*_annet.txt"):
        rel = extra.relative_to(top)
        if is_excluded(rel, read_exclude(top_name)):
            continue
        eid = extra.stem.removesuffix("_annet")
        if eid not in entries:
            links = read_extra_links(extra)
            entries[eid] = {"id": eid, "lenker": links}
            outcome(
                "NEW", rel.as_posix(), f"links-only entry {eid} ({show(links)}; no PDF)"
            )

    excluded = find_excluded(top, sub)
    counts["EXCLUDED"] = len(excluded)
    for rel, reason in excluded:
        say(f"EXCLUDED   {rel}  [{reason}]", detail=True)
    gone = [
        eid
        for eid, e in entries.items()
        if e.get("fil")
        and e["fil"] not in present
        and eid not in moves.values()
        and in_scope(e["fil"], sub)
    ]
    counts["GONE"] = len(gone)
    for eid in gone:
        say(
            f"GONE       {eid}: {entries[eid]['fil']} is in kilder.yaml but not on Drive "
            "(see `check`; `prune` removes it)",
            detail=True,
        )

    print_summary(
        f"{folder} ({len(pdfs)} PDFs checked)",
        counts,
        [
            ("UNCHANGED", "PDF and text untouched, nothing to do"),
            ("NEW", "converted for the first time"),
            ("UPDATED", "the PDF changed on Drive, text regenerated"),
            ("REBUILT", "text regenerated, PDF unchanged"),
            ("MOVED", "moved/renamed on Drive, kilder.yaml and text file followed"),
            ("METADATA", "only kilder.yaml fields changed (url/lenker filled in etc.)"),
            ("WARNING", "skipped, see the lines above"),
            ("EXCLUDED", "skipped because of EXCLUDE.txt / backup / trash folders"),
            ("GONE", "in kilder.yaml, but no longer on Drive"),
        ],
        hint_verbose="UNCHANGED",
    )
    if counts["EXCLUDED"] and not LOG.verbose:
        say("  (use -v to list the excluded files and which pattern matched)")
    save_yaml(yaml_file, entries, original, dry_run)


def cmd_check(
    drive: Path, folder: str, prune: bool = False, dry_run: bool = False
) -> int:
    top_name, sub = split_folder(folder)
    top = drive / top_name
    target = SOURCES_DIR / top_name
    yaml_file = target / "kilder.yaml"
    entries = read_yaml(yaml_file)
    original = copy.deepcopy(entries)
    issues = 0
    all_pdfs = find_pdfs(top)
    on_drive = {p.relative_to(top).as_posix(): p for p in all_pdfs}
    ids = assign_ids(all_pdfs, top, entries)
    known_files = {e.get("fil") for e in entries.values()}
    # Moved/renamed files are recognised by checksum and not treated as deleted.
    moved_to = {eid: rel for rel, eid in detect_moves(on_drive, entries).items()}
    counts: Counter = Counter()
    say(
        f"{folder}: {'prune' if prune else 'check'}"
        + ("   [DRY RUN: nothing will be written]" if dry_run and prune else "")
    )

    def report(
        kind: str, ref: str, msg: str, issue: bool = True, detail: bool = False
    ) -> None:
        nonlocal issues
        counts[kind] += 1
        issues += issue
        say(f"{kind:<14} {ref}: {msg}", detail=detail)

    for rel, pdf in on_drive.items():
        if not in_scope(rel, sub):
            continue
        entry = entries.get(ids[pdf])
        counts["PDFS"] += 1
        if rel in moved_to.values():
            continue  # reported as MOVED below
        if rel not in known_files:
            report("NEW", rel, "on Drive, not in kilder.yaml (run convert)")
        elif entry and entry.get("sha256") != sha256(pdf):
            report(
                "CHANGED",
                rel,
                "checksum on Drive does not match kilder.yaml (run convert)",
            )
        else:
            report(
                "IN SYNC", rel, "checksum matches kilder.yaml", issue=False, detail=True
            )

    to_remove = []
    removal_issues: dict[str, int] = {}
    for eid, entry in entries.items():
        if not entry.get("fil") or not in_scope(entry["fil"], sub):
            continue
        if eid in moved_to:
            report(
                "MOVED",
                eid,
                f"{entry['fil']} -> {moved_to[eid]} "
                "(run convert to update; prune leaves it alone)",
            )
        elif entry["fil"] not in on_drive:
            if (top / entry["fil"]).exists():
                report(
                    "EXCLUDED",
                    eid,
                    f"{entry['fil']} matches {EXCLUDE_FILE} (prune removes it)",
                )
            else:
                report(
                    "GONE",
                    eid,
                    f"{entry['fil']} not found on Drive (moved? run convert)",
                )
            to_remove.append(eid)
            # Prune removes these entries, so their remaining checks should not be
            # counted as issues left after pruning. Remember how many issues this
            # entry has produced, and keep checking (for the report).
            issues_before = issues
            if entry.get("tekst") and not (target / entry["tekst"]).exists():
                report("TEXT MISSING", eid, f"{entry['tekst']} not found in the repo")
            if not entry.get("url"):
                report("NO URL", eid, "no url (add it in kilder.yaml)", issue=False)
            removal_issues[eid] = issues - issues_before
            continue
        if entry.get("tekst") and not (target / entry["tekst"]).exists():
            report("TEXT MISSING", eid, f"{entry['tekst']} not found in the repo")
        if not entry.get("url"):
            report("NO URL", eid, "no url (add it in kilder.yaml)", issue=False)
        elif entry["fil"] in on_drive:
            on_disk = drive_url(on_drive[entry["fil"]])
            if on_disk is not None and on_disk != entry["url"]:
                report(
                    "URL MISMATCH",
                    eid,
                    f"kilder.yaml has {entry['url']}\n"
                    f"{'':15}{Path(entry['fil']).stem}.url on Drive has {on_disk}\n"
                    f"{'':15}(kilder.yaml wins; fix or delete the .url file to silence this)",
                )
        if entry.get("fil") in on_drive and entry.get("lenker"):
            links = drive_links(on_drive[entry["fil"]])
            if links is not None and {x["url"] for x in links} != {
                x["url"] for x in entry["lenker"]
            }:
                report(
                    "LINKS MISMATCH",
                    eid,
                    "lenker in kilder.yaml differ from "
                    f"{Path(entry['fil']).stem}_annet.txt on Drive (kilder.yaml wins)",
                )

    # Text files on disk that no entry points to (e.g. left behind by older
    # versions of this script, or by entries that were removed by hand).
    referenced = {e.get("tekst") for e in entries.values()}
    orphans = []
    tekst_dir = target / "tekst"
    if tekst_dir.is_dir():
        for md in sorted(tekst_dir.rglob("*.md")):
            rel_md = md.relative_to(target).as_posix()
            if rel_md not in referenced and in_scope(rel_md, sub):
                orphans.append(md)
                report(
                    "ORPHAN",
                    rel_md,
                    "text file not referenced by any kilder.yaml entry "
                    "(prune deletes it)",
                )

    removed = 0
    if prune and to_remove:
        for eid in to_remove:
            entry = entries.pop(eid)
            has_text = entry.get("tekst") and (target / entry["tekst"]).exists()
            say(
                f"{'WOULD REMOVE' if dry_run else 'REMOVED':<14} {eid}: from kilder.yaml"
                + (" and its text file" if has_text else "")
                + " (the PDF on Drive is untouched)"
            )
            if has_text and not dry_run:
                (target / entry["tekst"]).unlink()
            removed += 1
            counts["WOULD REMOVE" if dry_run else "REMOVED"] += 1
        # Removing the entries resolves exactly the issues that belonged to them
        # (GONE/EXCLUDED/TEXT MISSING); each removal counted as one issue, and any
        # extra issues reported for the entry while checking are discounted too.
        issues -= len(to_remove) + sum(removal_issues.values())
        save_yaml(yaml_file, entries, original, dry_run)
    if prune and orphans:
        for md in orphans:
            say(
                f"{'WOULD DELETE' if dry_run else 'DELETED':<14} "
                f"{md.relative_to(target).as_posix()}: orphaned text file"
            )
            if not dry_run:
                md.unlink()
            counts["WOULD DELETE" if dry_run else "DELETED"] += 1
        issues -= len(orphans)
    if moved_to and prune:
        say(
            "Tip: run `convert` first, so moved files are registered at their new location."
        )

    print_summary(
        f"{folder} ({counts['PDFS']} PDFs on Drive; kilder.yaml had "
        f"{len(original)} entries)",
        counts,
        [
            ("IN SYNC", "PDF on Drive matches kilder.yaml"),
            ("NEW", "on Drive, not in kilder.yaml"),
            ("CHANGED", "PDF differs from the checksum in kilder.yaml"),
            ("MOVED", "moved/renamed on Drive"),
            ("GONE", "in kilder.yaml, not on Drive"),
            ("EXCLUDED", "in kilder.yaml, but excluded by EXCLUDE.txt"),
            ("TEXT MISSING", "text file missing in the repo"),
            ("URL MISMATCH", ".url on Drive differs from kilder.yaml"),
            ("LINKS MISMATCH", "_annet.txt on Drive differs from kilder.yaml"),
            ("NO URL", "entries without url (not counted as issues)"),
            ("ORPHAN", "text files not referenced by any entry"),
            ("REMOVED", "entries (and their text files) removed from kilder.yaml"),
            ("WOULD REMOVE", "entries prune would remove (dry run)"),
            ("DELETED", "orphaned text files deleted"),
            ("WOULD DELETE", "orphaned text files prune would delete (dry run)"),
        ],
        hint_verbose="IN SYNC",
    )
    say("OK" if issues == 0 else f"{issues} issue{'s' if issues != 1 else ''}")
    return 1 if issues else 0


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

    helpers = load_wayback_helpers()
    top_name, sub = split_folder(folder)
    yaml_file = SOURCES_DIR / top_name / "kilder.yaml"
    entries = read_yaml(yaml_file)
    if not entries:
        sys.exit(f"No entries: {yaml_file} is missing or empty (run convert first)")
    original = copy.deepcopy(entries)
    context = ssl.create_default_context()
    ua = helpers.DEFAULT_USER_AGENT

    scope = [e for e in entries.values() if not sub or in_scope(e.get("fil", ""), sub)]
    counts: Counter = Counter()
    todo = []
    skipped_lines = []
    for e in scope:
        label = e["id"]
        if e.get("arkiv"):
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
        f"{folder}: {len(scope)} entries, {len(todo)} to look up"
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
        f"{folder} ({len(scope)} entries)",
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
            ("NO URL", "no url in kilder.yaml"),
        ],
        hint_verbose="KEPT",
    )
    if dry_run:
        say("kilder.yaml: not written (dry run)")
    elif entries == original:
        say(
            f"kilder.yaml: no changes, file not rewritten ({yaml_file.relative_to(REPO)})"
        )
    else:
        n = sum(
            1 for k in entries if entries[k].get("arkiv") != original[k].get("arkiv")
        )
        say(
            f"kilder.yaml: written, {n} arkiv field{'s' if n != 1 else ''} filled in "
            f"({yaml_file.relative_to(REPO)})"
        )
    return 1 if left else 0


# --------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--drive",
        type=Path,
        default=DEFAULT_DRIVE,
        help=f"local copy of the Drive folder (default: {DEFAULT_DRIVE})",
    )
    commands = ap.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also list every unchanged/skipped file, with the reason",
    )
    common.add_argument(
        "--log",
        type=Path,
        metavar="FILE",
        help="append the full (verbose) output, with a timestamp, to FILE",
    )

    folder_help = (
        "folder on Drive, e.g. 001_nasjonal_transportplan_ntp or "
        "101_hordfast/hordfast_regplan/02_plankart"
    )

    c = commands.add_parser(
        "convert",
        parents=[common],
        help="convert new/changed PDFs and update kilder.yaml",
    )
    c.add_argument("folders", nargs="*", help=folder_help)
    c.add_argument("--all", action="store_true", help="all folders on Drive")
    c.add_argument(
        "--force", nargs="*", default=[], metavar="ID", help="re-convert these ids"
    )
    c.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be done, without writing anything",
    )

    k = commands.add_parser(
        "check", parents=[common], help="compare Drive with kilder.yaml (never writes)"
    )
    k.add_argument("folders", nargs="*", help=folder_help)
    k.add_argument("--all", action="store_true", help="all folders on Drive")

    p = commands.add_parser(
        "prune",
        parents=[common],
        help="like check, but removes entries and text files "
        "for PDFs deleted from Drive or excluded",
    )
    p.add_argument("folders", nargs="*", help=folder_help)
    p.add_argument("--all", action="store_true", help="all folders on Drive")
    p.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="show what would be removed, without writing anything",
    )

    a = commands.add_parser(
        "archive",
        parents=[common],
        help="fill empty `arkiv` fields with Wayback snapshots "
        "of each url (reads kilder.yaml only)",
    )
    a.add_argument("folders", nargs="*", help=folder_help)
    a.add_argument(
        "--all", action="store_true", help="all folders that have a kilder.yaml"
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

    args = ap.parse_args()
    global LOG
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
    LOG = Log(verbose=args.verbose, path=args.log)
    if args.log:
        LOG.file.write(
            f"\n=== {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} UTC  kilder.py "
            f"{' '.join(sys.argv[1:])} ===\n"
        )
    drive = args.drive.expanduser()
    if args.all and args.command == "archive":
        folders = sorted(
            d.name for d in SOURCES_DIR.iterdir() if (d / "kilder.yaml").exists()
        )
    elif args.all:
        folders = sorted(
            d.name
            for d in drive.iterdir()
            if d.is_dir() and re.match(r"\d{3}_", d.name)
        )
    else:
        folders = args.folders
    if not folders:
        ap.error("give at least one folder, or --all")

    rc = 0
    for folder in folders:
        if args.command == "archive":
            rc |= cmd_archive(folder, args.save, args.dry_run, args.delay, args.timeout)
        elif args.command == "convert":
            cmd_convert(drive, folder, set(args.force), args.dry_run)
        else:
            rc |= cmd_check(
                drive,
                folder,
                prune=(args.command == "prune"),
                dry_run=getattr(args, "dry_run", False),
            )
    return rc


if __name__ == "__main__":
    sys.exit(main())
