#!/usr/bin/env python3
"""One-off migration: convert the BomfastMedielogg "rapporter" spreadsheet export
(CSV) into native Hugo content files under
content/mer-lesestoff/rapporter/<year>-<month>-01-<slug>/index.md.

Usage:
    python3 scripts/migrate_rapporter_csv.py <path-to-csv>

CSV columns (header row): ID,Institusjon,Forfatter,Tittel,Kommentar,Lenke,LenkeAlt,LENKE1,LENKE2
- ID: YYYYMMNNN (year+month only, no day). NNN is an unused same-month counter.
  Year-only rows (e.g. "2020,,,,,,,,") are section headers and are skipped.
  Since no day is available, the front matter `date` is set to the 1st of the
  month (YYYY-MM-01) and directory names/permalinks inherit that same date -
  the list template displays year-month only, hiding the synthetic day.
- Kommentar: becomes the page body. May contain {LENKE1: text} / {LENKE2: text}
  placeholders that are replaced with markdown links using the LENKE1/LENKE2 columns.
- Lenke: the external report/publication URL.
- LenkeAlt: an occasional extra/archive link, stored as `alt_url` front matter.
"""

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

if len(sys.argv) < 2:
    print(
        "Usage: python3 scripts/migrate_rapporter_csv.py <path-to-csv>", file=sys.stderr
    )
    sys.exit(1)

CSV_PATH = sys.argv[1]
OUT_DIR = Path("content/mer-lesestoff/rapporter")

LENKE_PATTERN = re.compile(r"\{LENKE(1|2):\s*(.*?)\}")


def slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("æ", "ae").replace("ø", "o").replace("å", "aa")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "rapport"


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_year_month(id_value: str):
    if re.fullmatch(r"\d{9}", id_value or ""):
        return f"{id_value[0:4]}-{id_value[4:6]}-01"
    return None


def substitute_links(text: str, lenke1: str, lenke2: str) -> str:
    def repl(match):
        which, label = match.group(1), match.group(2).strip()
        url = lenke1 if which == "1" else lenke2
        return f"[{label}]({url})" if url else label

    return LENKE_PATTERN.sub(repl, text)


def main():
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    rows = rows[1:]  # drop header

    last_date = None
    skipped = 0
    collisions = []
    entries = []  # (rel_path, content) - staged, not yet written
    seen_paths = {}

    for row in rows:
        row = (row + [""] * 9)[:9]
        (
            id_,
            institusjon,
            forfatter,
            tittel,
            kommentar,
            lenke,
            lenke_alt,
            lenke1,
            lenke2,
        ) = (v.strip() for v in row)

        # Year header row, e.g. "2020,,,,,,,,"
        if re.fullmatch(r"\d{4}", id_) and not any(
            [institusjon, forfatter, tittel, kommentar, lenke]
        ):
            continue
        # Fully blank separator row
        if not any([id_, institusjon, forfatter, tittel, kommentar, lenke]):
            continue
        if not tittel:
            print(f"SKIP (no title): {row}")
            skipped += 1
            continue

        date = parse_year_month(id_) or last_date
        if date is None:
            print(f"SKIP (no date context): {tittel!r}")
            skipped += 1
            continue
        last_date = date

        body = substitute_links(kommentar, lenke1, lenke2)

        slug = slugify(tittel)
        rel_dir = OUT_DIR / f"{date}-{slug}"
        rel_path = rel_dir / "index.md"

        if str(rel_path) in seen_paths:
            collisions.append((str(rel_path), seen_paths[str(rel_path)], tittel))
        seen_paths[str(rel_path)] = tittel

        front_matter = [
            "---",
            f"title: {yaml_str(tittel)}",
            f"date: {date}",
            'type: "rapporter"',
        ]
        if institusjon:
            front_matter.append(f"institusjon: {yaml_str(institusjon)}")
        if forfatter:
            front_matter.append(f"forfatter: {yaml_str(forfatter)}")
        if lenke:
            front_matter.append(f"external_url: {yaml_str(lenke)}")
        if lenke_alt:
            front_matter.append(f"alt_url: {yaml_str(lenke_alt)}")
        front_matter.append("---")

        content = "\n".join(front_matter) + "\n\n" + body.strip() + "\n"
        entries.append((rel_path, content))

    if collisions:
        print(
            "ERROR: path collisions found (same year-month+slug) - aborting, nothing written:",
            file=sys.stderr,
        )
        for path, first_title, dup_title in collisions:
            print(
                f" - {path}\n     row 1: {first_title!r}\n     row 2: {dup_title!r}",
                file=sys.stderr,
            )
        print(
            "Resolve by editing the CSV (e.g. tweak one of the titles) and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    for rel_path, content in entries:
        rel_path.parent.mkdir(parents=True, exist_ok=True)
        rel_path.write_text(content, encoding="utf-8")

    print(f"Created/updated: {len(entries)}, skipped: {skipped}")


if __name__ == "__main__":
    main()
