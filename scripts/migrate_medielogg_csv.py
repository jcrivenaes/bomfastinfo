#!/usr/bin/env python3
"""One-off migration: convert the BomfastMedielogg spreadsheet export (CSV) into
native Hugo content files under content/mer-lesestoff/medialogg/<date>-<slug>/index.md.

Usage:
    python3 scripts/migrate_medielogg_csv.py <path-to-csv>

CSV columns (header row): ID,XX,Media,Abo,Tittel,Kommentar,Lenke,Alt,LENKE1,LENKE2
- ID: YYYYMMDDNNN. Date is the first 8 digits; NNN is an unused same-day counter.
  Year-only rows (e.g. "2026,,,,,,,,,,") are section headers and are skipped.
- XX: unused.
- Abo: "Ja"/"Nei" - whether the article is behind a paywall/login.
- Kommentar: becomes the page body. May contain {LENKE1: text} / {LENKE2: text}
  placeholders that are replaced with markdown links using the LENKE1/LENKE2 columns.
- Lenke: the external article URL.
- Alt: an occasional extra/supporting link, appended at the end of the body.
"""

import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

if len(sys.argv) < 2:
    print(
        "Usage: python3 scripts/migrate_medielogg_csv.py <path-to-csv>", file=sys.stderr
    )
    sys.exit(1)

CSV_PATH = sys.argv[1]
OUT_DIR = Path("content/mer-lesestoff/medialogg")

LENKE_PATTERN = re.compile(r"\{LENKE(1|2):\s*(.*?)\}")


def slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("æ", "ae").replace("ø", "o").replace("å", "aa")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "oppforing"


def yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_date(id_value: str):
    if re.fullmatch(r"\d{11}", id_value or ""):
        return f"{id_value[0:4]}-{id_value[4:6]}-{id_value[6:8]}"
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
    created = skipped = 0
    collisions = []
    seen_paths = set()

    for row in rows:
        row = (row + [""] * 10)[:10]
        id_, _xx, media, abo, tittel, kommentar, lenke, alt, lenke1, lenke2 = (
            v.strip() for v in row
        )

        # Year header row, e.g. "2026,,,,,,,,,,"
        if re.fullmatch(r"\d{4}", id_) and not any([media, tittel, kommentar, lenke]):
            continue
        # Fully blank separator row
        if not any([id_, media, tittel, kommentar, lenke]):
            continue
        if not tittel:
            print(f"SKIP (no title): {row}")
            skipped += 1
            continue

        date = parse_date(id_) or last_date
        if date is None:
            print(f"SKIP (no date context): {tittel!r}")
            skipped += 1
            continue
        last_date = date

        body = substitute_links(kommentar, lenke1, lenke2)
        if alt:
            body += f"\n\n[Ekstra lenke]({alt})"

        slug = slugify(tittel)
        rel_dir = OUT_DIR / f"{date}-{slug}"
        rel_path = rel_dir / "index.md"

        if str(rel_path) in seen_paths:
            collisions.append(str(rel_path))
        seen_paths.add(str(rel_path))

        front_matter = [
            "---",
            f"title: {yaml_str(tittel)}",
            f"date: {date}",
            'type: "medialogg"',
        ]
        if media:
            front_matter.append(f"source: {yaml_str(media)}")
        if lenke:
            front_matter.append(f"external_url: {yaml_str(lenke)}")
        if abo.lower() == "ja":
            front_matter.append("abo: true")
        front_matter.append("---")

        content = "\n".join(front_matter) + "\n\n" + body.strip() + "\n"

        rel_dir.mkdir(parents=True, exist_ok=True)
        rel_path.write_text(content, encoding="utf-8")
        created += 1

    print(f"Created/updated: {created}, skipped: {skipped}")
    if collisions:
        print("Path collisions (same date+slug - last row wins):")
        for c in collisions:
            print(" -", c)


if __name__ == "__main__":
    main()
