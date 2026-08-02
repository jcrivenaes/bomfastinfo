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

Upload one or more jobs from a config file instead of (or in addition to) the
command line. The config is a JSON file holding either a single job object, a
bare array of job objects, or {"uploads": [...]}. Keys match the CLI options
(source_url, file, item, remote_name, document_id, title, source_name,
original_url, checked, notes, metadata, file_metadata, retries, upload,
verify_timeout, no_backup_on_replace). Any field missing from a job falls back
to the corresponding CLI option, so shared settings like --item or --upload can
be passed once on the command line. Config and results files default to the
uploads_webarchive/ folder:

    python3 scripts/archive_org_upload.py --config --upload
    python3 scripts/archive_org_upload.py --config uploads_webarchive/my-batch.json --upload

Each successful, verified upload is appended as one JSON line to the results
file (default uploads_webarchive/results.jsonl) with the manifest metadata and
file URL. It is also recorded on archive.org itself as file-level metadata
(`original_url`) via `ia metadata --target=files/<remote-name>`, unless
--skip-original-url-metadata is set.

Backfill metadata/results for files uploaded before this script tracked them,
without deleting or re-uploading anything:

    python3 scripts/archive_org_upload.py --backfill \
        --remote-name hb-v712-konsekvensanalyser_2018.pdf \
        --original-url "https://www.vegvesen.no/.../v712.pdf" \
        --title "V712 - Konsekvensanalyser"

Or via a config file with several {"backfill": true, "remote_name": ...} jobs,
see uploads_webarchive/backfill.example.json.

View a file's metadata (e.g. to confirm original_url was attached):

    curl -s https://archive.org/metadata/bomfast-kildedokumenter | \
        jq '.files[] | select(.name=="rapport.pdf")'

Also:
    curl -s https://archive.org/metadata/bomfast-kildedokumenter | python3 -m json.tool

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
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ITEM = "bomfast-kildedokumenter"
DEFAULT_USER_AGENT = "Mozilla/5.0 bomfast-source-archive"
DEFAULT_UPLOADS_DIR = Path("uploads_webarchive")
DEFAULT_CONFIG_PATH = DEFAULT_UPLOADS_DIR / "config.json"
DEFAULT_RESULTS_PATH = DEFAULT_UPLOADS_DIR / "results.jsonl"

# Job fields that a config entry may override; CLI options are the fallback.
JOB_FIELDS = {
    "source_url": None,
    "file": Path,
    "item": None,
    "remote_name": None,
    "document_id": None,
    "title": None,
    "source_name": None,
    "original_url": None,
    "checked": None,
    "notes": None,
    "metadata": None,
    "file_metadata": None,
    "retries": None,
    "upload": None,
    "verify_timeout": None,
    "no_backup_on_replace": None,
    "results_file": Path,
    "skip_original_url_metadata": None,
    "backfill": None,
}


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
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        destination.open("wb") as output,
    ):
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
    checked = args.checked or datetime.now(tz=timezone.utc).date().isoformat()
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


def build_ia_metadata_command(
    item: str, remote_name: str, key: str, value: str
) -> list[str]:
    return [
        "ia",
        "metadata",
        item,
        "--target",
        f"files/{remote_name}",
        "--modify",
        f"{key}:{value}",
    ]


def record_original_url_metadata(
    item: str, remote_name: str, original_url: str
) -> bool:
    """Attach original_url as archive.org file-level metadata via the Metadata
    Write API (not `ia upload --file-metadata`, which is for bulk uploads)."""
    command = build_ia_metadata_command(item, remote_name, "original_url", original_url)
    printable = " ".join(shell_quote(part) for part in command)
    print(f"IA metadata command: {printable}")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(
            f"warning: failed to attach original_url metadata to {remote_name}",
            file=sys.stderr,
        )
        return False
    return True


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
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--source-url", help="URL to download before upload")
    source.add_argument("--file", type=Path, help="Existing local PDF to upload")
    parser.add_argument(
        "--config",
        nargs="?",
        const=str(DEFAULT_CONFIG_PATH),
        type=Path,
        help=(
            "JSON config file with one job (object) or several (array, or "
            f"{{'uploads': [...]}}). Defaults to {DEFAULT_CONFIG_PATH} when given "
            "without a path. Missing fields in a job fall back to the matching CLI "
            "option, e.g. --item or --upload."
        ),
    )
    parser.add_argument(
        "--results-file",
        type=Path,
        default=DEFAULT_RESULTS_PATH,
        help="JSONL file to append successful, verified upload records to.",
    )
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
    parser.add_argument(
        "--skip-original-url-metadata",
        action="store_true",
        help=(
            "Do not attach the source/original URL as archive.org file-level "
            "metadata (via `ia metadata --target=files/<name>`) after a verified upload."
        ),
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Do not download/upload anything. Instead, verify --remote-name already "
            "exists in --item, attach --original-url as file metadata, and log it to "
            "the results file. Use this for files uploaded before this script tracked "
            "metadata/results."
        ),
    )
    args = parser.parse_args()
    if args.backfill:
        if not args.config and not args.remote_name:
            parser.error("--backfill requires --remote-name (or use --config)")
    elif not args.config and not (args.source_url or args.file):
        parser.error("one of --source-url, --file or --config is required")
    return args


def load_config_jobs(config_path: Path) -> list[dict]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {config_path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {config_path}: {exc}")

    if isinstance(data, dict) and isinstance(data.get("uploads"), list):
        jobs = data["uploads"]
    elif isinstance(data, list):
        jobs = data
    elif isinstance(data, dict):
        jobs = [data]
    else:
        raise SystemExit(f"Invalid config format in {config_path}")

    if not jobs:
        raise SystemExit(f"No upload entries found in {config_path}")
    return jobs


def build_job_args(job: dict, defaults: argparse.Namespace) -> argparse.Namespace:
    ns = argparse.Namespace(**vars(defaults))
    for key, caster in JOB_FIELDS.items():
        if key in job and job[key] is not None:
            value = job[key]
            setattr(ns, key, caster(value) if caster else value)

    if ns.backfill:
        if not ns.remote_name:
            raise SystemExit("Config entry with 'backfill' needs 'remote_name'")
    else:
        if not ns.source_url and not ns.file:
            raise SystemExit("Config entry needs 'source_url' or 'file'")
        if ns.source_url and ns.file:
            raise SystemExit("Config entry cannot have both 'source_url' and 'file'")
    return ns


def append_result(results_file: Path, record: dict) -> None:
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with results_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def process_backfill_job(args: argparse.Namespace) -> dict | None:
    """Attach metadata/log an entry for a file already uploaded to archive.org,
    without downloading a source or running `ia upload` again."""
    found, _ = metadata_contains_file(args.item, args.remote_name)
    if not found:
        raise SystemExit(
            f"{args.remote_name} not found in item {args.item}; nothing to backfill"
        )

    file_url = f"https://archive.org/download/{args.item}/{urllib.parse.quote(args.remote_name)}"

    with tempfile.TemporaryDirectory(prefix="bomfast-archive-backfill-") as temp_dir:
        local_file = Path(temp_dir) / args.remote_name
        print(f"Downloading existing file to compute checksum: {file_url}")
        download(file_url, local_file)
        checksum = sha256(local_file)
        size = local_file.stat().st_size

    print(f"Remote name: {args.remote_name}")
    print(f"Size: {size} bytes")
    print(f"SHA256: {checksum}")
    print(f"File URL: {file_url}")

    if args.original_url and not args.skip_original_url_metadata:
        record_original_url_metadata(args.item, args.remote_name, args.original_url)

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "item": args.item,
        "document_id": args.document_id
        or document_id_from_remote_name(args.remote_name),
        "title": args.title
        or document_id_from_remote_name(args.remote_name).replace("-", " "),
        "source_name": args.source_name,
        "source": args.original_url or "",
        "original_url": args.original_url or "",
        "remote_name": args.remote_name,
        "file_url": file_url,
        "size_bytes": size,
        "sha256": checksum,
        "checked": args.checked or datetime.now(tz=timezone.utc).date().isoformat(),
        "notes": args.notes,
        "backfilled": True,
    }


def process_job(args: argparse.Namespace) -> dict | None:
    """Validate and optionally upload one job. Returns a result record on a
    verified successful upload, or None for a dry run or unverified upload."""
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
            return None

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
            return None

        original_url_value = args.source_url or args.original_url
        if original_url_value and not args.skip_original_url_metadata:
            record_original_url_metadata(args.item, remote_name, original_url_value)

        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "item": args.item,
            "document_id": args.document_id
            or document_id_from_remote_name(remote_name),
            "title": args.title
            or document_id_from_remote_name(remote_name).replace("-", " "),
            "source_name": args.source_name,
            "source": source,
            "original_url": args.original_url if not is_url(source) else source,
            "remote_name": remote_name,
            "file_url": file_url,
            "size_bytes": size,
            "sha256": checksum,
            "checked": args.checked or datetime.now(tz=timezone.utc).date().isoformat(),
            "notes": args.notes,
        }


def main() -> int:
    args = parse_args()

    if args.config:
        raw_jobs = load_config_jobs(args.config)
    else:
        raw_jobs = [None]

    failures = 0
    for index, raw_job in enumerate(raw_jobs, start=1):
        try:
            job_args = args if raw_job is None else build_job_args(raw_job, args)
        except SystemExit as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue

        if len(raw_jobs) > 1:
            source = job_args.source_url or job_args.file or job_args.remote_name
            print(f"\n=== Job {index}/{len(raw_jobs)}: {source} ===")
        try:
            if job_args.backfill:
                record = process_backfill_job(job_args)
            else:
                record = process_job(job_args)
        except (SystemExit, subprocess.CalledProcessError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures += 1
            continue

        if record is not None:
            append_result(job_args.results_file, record)
            print(f"Recorded result in {job_args.results_file}")
        elif job_args.backfill or job_args.upload:
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
