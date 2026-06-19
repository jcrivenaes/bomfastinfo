#!/usr/bin/env python3
"""Prepare and optionally upload source PDFs to an Internet Archive item.

The script never stores archive.org credentials. Configure the official `ia` CLI
outside the repo first:

    python3 -m pip install --user internetarchive
    ia configure

Dry-run from a URL:

    python3 scripts/archive_org_upload.py \
        --item bomfast-kildedokumenter \
        --source-url "https://www.vegvesen.no/.../rapport.pdf" \
        --remote-name rapport.pdf

Actually upload after checking the output:

    python3 scripts/archive_org_upload.py --item bomfast-kildedokumenter \
        --source-url "https://www.vegvesen.no/.../rapport.pdf" \
        --remote-name rapport.pdf --upload

More complete example with metadata and notes:
    python3 scripts/archive_org_upload.py \
        --item bomfast-kildedokumenter \
        --source-url "https://www.regjeringen.no/globalassets/upload/sd/vedlegg/kvu-rapporter/tilleggsutgr2012.pdf" \
        --remote-name e39-aksdal-bergen-kvu-tilleggsutgreing-2012.pdf \
        --title "E39 Aksdal-Bergen KVU tilleggsutgreiing 2012" \
        --source-name "Samferdselsdepartementet" \
        --notes "Lastet ned fra regjeringen.no og arkivert som kildedokument."

Upload local file:
    python3 scripts/archive_org_upload.py \
        --item bomfast-kildedokumenter \
        --file /path/to/local/rapport.pdf \
        --original-url "https://www.vegvesen.no/.../rapport.pdf" \
        --remote-name rapport.pdf \
        --upload

Checks locally:
    ia tasks bomfast-kildedokumenter | grep -E 'queued|running|failed|error'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path


DEFAULT_ITEM = "bomfast-kildedokumenter"
DEFAULT_USER_AGENT = "Mozilla/5.0 bomfast-source-archive"


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def remote_name_from_source(source: str) -> str:
    if is_url(source):
        parsed = urllib.parse.urlparse(source)
        name = Path(parsed.path).name
    else:
        name = Path(source).name
    if not name:
        raise SystemExit("Could not infer --remote-name; please provide it explicitly.")
    return name


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pdf(path: Path) -> None:
    with path.open("rb") as source:
        header = source.read(5)
    if header != b"%PDF-":
        raise SystemExit(f"Not a PDF file: {path}")

    pdfinfo = shutil.which("pdfinfo")
    if not pdfinfo:
        print(
            "warning: pdfinfo not found; only PDF header was checked", file=sys.stderr
        )
        return

    result = subprocess.run(
        [pdfinfo, str(path)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        raise SystemExit(f"pdfinfo failed for {path}")

    for line in result.stdout.splitlines():
        if line.startswith(("Title:", "Pages:", "File size:", "PDF version:")):
            print(line)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def document_id_from_remote_name(remote_name: str) -> str:
    suffix = Path(remote_name).suffix
    if suffix:
        return remote_name[: -len(suffix)]
    return remote_name


def print_manifest_snippet(
    args: argparse.Namespace,
    source: str,
    remote_name: str,
    file_url: str,
    checksum: str,
    size: int,
) -> None:
    title = args.title or document_id_from_remote_name(remote_name).replace("-", " ")
    archive_item = f"https://archive.org/details/{args.item}"
    checked = args.checked or date.today().isoformat()
    notes = args.notes or ""

    print("\nManifest YAML:")
    print(
        f"- id: {yaml_quote(args.document_id or document_id_from_remote_name(remote_name))}"
    )
    print(f"  title: {yaml_quote(title)}")
    print(f"  source: {yaml_quote(args.source_name)}")
    if is_url(source):
        print(f"  original_url: {yaml_quote(source)}")
    else:
        print(f"  original_url: {yaml_quote(args.original_url or '')}")
    print(f"  archive_item: {yaml_quote(archive_item)}")
    print(f"  file_url: {yaml_quote(file_url)}")
    print(f"  file_name: {yaml_quote(remote_name)}")
    print(f"  size_bytes: {size}")
    print(f"  sha256: {yaml_quote(checksum)}")
    print(f"  checked: {yaml_quote(checked)}")
    print(f"  notes: {yaml_quote(notes)}")


def build_ia_command(
    args: argparse.Namespace, local_file: Path, remote_name: str
) -> list[str]:
    command = [
        "ia",
        "upload",
        args.item,
        str(local_file),
        "--remote-name",
        remote_name,
        "--retries",
        str(args.retries),
    ]

    for metadata in args.metadata:
        command.extend(["--metadata", metadata])

    for file_metadata in args.file_metadata:
        command.extend(["--file-metadata", file_metadata])

    if args.no_backup_on_replace:
        command.extend(["-H", "x-archive-keep-old-version:0"])

    return command


def item_metadata(item: str) -> dict:
    url = f"https://archive.org/metadata/{urllib.parse.quote(item)}"
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def metadata_contains_file(item: str, remote_name: str) -> tuple[bool, dict]:
    metadata = item_metadata(item)
    for file_info in metadata.get("files", []):
        if file_info.get("name") == remote_name:
            return True, metadata
    return False, metadata


def wait_for_uploaded_file(item: str, remote_name: str, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    last_metadata: dict = {}

    while True:
        found, last_metadata = metadata_contains_file(item, remote_name)
        if found:
            return True
        if time.monotonic() >= deadline:
            pending = last_metadata.get("pending_tasks")
            tasks = last_metadata.get("tasks", [])
            print(
                f"warning: {remote_name} is not visible in item metadata yet. pending_tasks={pending}",
                file=sys.stderr,
            )
            for task in tasks[:5]:
                print(
                    "warning: task "
                    f"{task.get('task_id')} {task.get('cmd')} {task.get('status')}",
                    file=sys.stderr,
                )
            return False
        time.sleep(5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a source PDF and optionally upload it to an Internet Archive item."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-url", help="URL to download before upload")
    source.add_argument("--file", type=Path, help="Existing local PDF to upload")
    parser.add_argument(
        "--item", default=DEFAULT_ITEM, help="Internet Archive item identifier"
    )
    parser.add_argument(
        "--remote-name", help="Filename to use inside the archive.org item"
    )
    parser.add_argument("--document-id", help="ID to use in the manifest snippet")
    parser.add_argument("--title", help="Title to use in the manifest snippet")
    parser.add_argument(
        "--source-name",
        default="Statens vegvesen",
        help="Source/publisher to use in the manifest snippet",
    )
    parser.add_argument(
        "--original-url",
        help="Original URL to use in manifest when uploading from --file",
    )
    parser.add_argument(
        "--checked", help="Checked date for manifest, defaults to today"
    )
    parser.add_argument(
        "--notes", default="", help="Notes to use in the manifest snippet"
    )
    parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Item metadata, e.g. subject:Statens vegvesen",
    )
    parser.add_argument(
        "--file-metadata",
        action="append",
        default=[],
        help="Path to IA file metadata JSON/JSONL",
    )
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Run ia upload. Without this, only print the command.",
    )
    parser.add_argument(
        "--verify-timeout",
        type=int,
        default=120,
        help="Seconds to wait for uploaded file to appear in archive.org metadata.",
    )
    parser.add_argument(
        "--no-backup-on-replace",
        action="store_true",
        help="Ask archive.org not to keep old versions if the remote filename already exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source_url or str(args.file)
    remote_name = args.remote_name or remote_name_from_source(source)

    with tempfile.TemporaryDirectory(prefix="bomfast-archive-upload-") as temp_dir:
        if args.source_url:
            local_file = Path(temp_dir) / remote_name
            print(f"Downloading: {args.source_url}")
            download(args.source_url, local_file)
        else:
            local_file = args.file.resolve()

        validate_pdf(local_file)
        checksum = sha256(local_file)
        size = local_file.stat().st_size
        file_url = f"https://archive.org/download/{args.item}/{urllib.parse.quote(remote_name)}"

        print(f"File: {local_file}")
        print(f"Remote name: {remote_name}")
        print(f"Size: {size} bytes")
        print(f"SHA256: {checksum}")
        print(f"Expected file URL: {file_url}")
        print_manifest_snippet(args, source, remote_name, file_url, checksum, size)

        command = build_ia_command(args, local_file, remote_name)
        printable = " ".join(shell_quote(part) for part in command)
        print(f"IA command: {printable}")

        if not args.upload:
            print("Dry run only. Add --upload to run ia upload.")
            return 0

        if not shutil.which("ia"):
            raise SystemExit(
                "ia CLI not found. Install with: python3 -m pip install --user internetarchive"
            )

        subprocess.run(command, check=True)
        if wait_for_uploaded_file(args.item, remote_name, args.verify_timeout):
            print(f"Upload visible in metadata: {file_url}")
        else:
            print(
                "Upload command completed, but the file is not visible yet. "
                "Try checking item tasks or rerun the upload after archive.org finishes processing.",
                file=sys.stderr,
            )
            return 1
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
