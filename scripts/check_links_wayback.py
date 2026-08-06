#!/usr/bin/env python3
"""Check external links and find Wayback Machine replacements.

Default usage:
    python3 scripts/check_links_wayback.py

Useful variants:
    python3 scripts/check_links_wayback.py --host vegvesen.no
    python3 scripts/check_links_wayback.py --output reports/innsikt-links.md
    python3 scripts/check_links_wayback.py --format csv --output reports/innsikt-links.csv
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import http.cookiejar
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# A generic "...link-check-wayback" UA (and minimal headers) gets 403'd by bot/WAF
# protection on several real, working sites (e.g. Cloudflare-style checks for
# Sec-Fetch-*/Sec-Ch-Ua headers), even though the pages load fine in a browser.
# Mimicking a real browser's request headers avoids those false positives.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "nb-NO,nb;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Ch-Ua": '"Chromium";v="126", "Not.A/Brand";v="24", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

LINK_PATTERNS = [
    # Markdown links: [text](https://example.com) but not images.
    re.compile(
        r"(?<![!])\[[^\]]*\]\((<https?://[^>]+>|https?://[^\s)]+)(?:\s+\"[^\"]*\")?\)"
    ),
    # HTML attrs in rawhtml shortcodes, iframes, etc.
    re.compile(r"(?i)\b(?:href|src)=[\"'](https?://[^\"']+)[\"']"),
    # Bare URLs.
    re.compile(r"(?<![\w=\"'])(https?://[^\s)\"'<>]+)"),
]


@dataclass(frozen=True)
class Reference:
    path: Path
    line: int


@dataclass
class LinkResult:
    url: str
    status: int | None
    reason: str = ""
    final_url: str = ""
    refs: list[Reference] = field(default_factory=list)
    wayback_url: str = ""
    wayback_timestamp: str = ""
    wayback_status: str = ""
    wayback_source: str = ""

    @property
    def broken(self) -> bool:
        return self.status is None or self.status >= 400

    @property
    def likely_blocked(self) -> bool:
        # 403/406/429 are the classic bot/WAF-blocking responses; these links may
        # actually work fine in a real browser and should be verified manually
        # rather than treated as confirmed-dead.
        return self.status in {403, 406, 429}


def clean_url(raw_url: str) -> str:
    return raw_url.strip("<>").rstrip(".,;")


def is_pdf_url(url: str) -> bool:
    return urllib.parse.urlparse(url).path.lower().endswith(".pdf")


def normalize_wayback_url(archive_url: str, timestamp: str, original_url: str) -> str:
    if archive_url.startswith("http://web.archive.org/"):
        archive_url = "https://" + archive_url[len("http://") :]

    if is_pdf_url(original_url):
        marker = f"/web/{timestamp}/"
        if marker in archive_url:
            archive_url = archive_url.replace(marker, f"/web/{timestamp}id_/", 1)

    return archive_url


def extract_links(
    content_dir: Path, host_filter: str | None
) -> dict[str, list[Reference]]:
    refs: dict[str, list[Reference]] = {}
    seen: set[tuple[Path, int, str]] = set()

    for path in sorted(content_dir.glob("**/*.md")):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            for pattern in LINK_PATTERNS:
                for match in pattern.finditer(line):
                    url = clean_url(match.group(1))
                    if not url.startswith(("http://", "https://")):
                        continue
                    if (
                        host_filter
                        and host_filter not in urllib.parse.urlparse(url).netloc
                    ):
                        continue
                    key = (path, line_no, url)
                    if key in seen:
                        continue
                    seen.add(key)
                    refs.setdefault(url, []).append(Reference(path, line_no))

    return refs


def build_opener(context: ssl.SSLContext) -> urllib.request.OpenerDirector:
    # Cookies matter for sites that gate content behind a consent-cookie redirect.
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )


def open_url(
    url: str,
    method: str,
    timeout: int,
    user_agent: str,
    opener: urllib.request.OpenerDirector,
) -> tuple[int, str, str]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": user_agent, **BROWSER_HEADERS},
    )
    with opener.open(request, timeout=timeout) as response:
        if method == "GET":
            response.read(256)
        return response.status, "", response.geturl()


def parse_content_length(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def wayback_capture_looks_complete(
    archive_url: str,
    original_url: str,
    timeout: int,
    user_agent: str,
    context: ssl.SSLContext,
) -> bool:
    if not is_pdf_url(original_url):
        return True

    request = urllib.request.Request(
        archive_url,
        method="HEAD",
        headers={"User-Agent": user_agent, "Accept": "application/pdf,*/*"},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=context
        ) as response:
            archive_size = parse_content_length(response.headers.get("Content-Length"))
            crawler_size = parse_content_length(
                response.headers.get("X-Archive-Orig-X-Crawler-Content-Length")
            )
            original_size = parse_content_length(
                response.headers.get("X-Archive-Orig-Content-Length")
            )
    except Exception:
        return True

    expected_size = crawler_size or original_size
    if archive_size and expected_size and archive_size < expected_size * 0.95:
        return False

    return True


def check_http_status(
    url: str, timeout: int, user_agent: str, opener: urllib.request.OpenerDirector
) -> tuple[int | None, str, str]:
    for method in ("HEAD", "GET"):
        try:
            return open_url(url, method, timeout, user_agent, opener)
        except urllib.error.HTTPError as error:
            if method == "HEAD" and error.code in {403, 405, 406, 429, 500, 501}:
                continue
            return error.code, str(error.reason), getattr(error, "url", url)
        except Exception as error:  # noqa: BLE001 - report network failures as link results.
            if method == "HEAD":
                continue
            return None, f"{type(error).__name__}: {error}", url

    return None, "unknown error", url


def url_variants(url: str) -> list[tuple[str, str]]:
    parsed = urllib.parse.urlparse(url)
    variants: list[tuple[str, str]] = [("exact", url)]

    if parsed.query:
        variants.append(
            ("without-query", urllib.parse.urlunparse(parsed._replace(query="")))
        )

    if parsed.scheme == "https":
        variants.append(
            ("http", urllib.parse.urlunparse(parsed._replace(scheme="http")))
        )
    elif parsed.scheme == "http":
        variants.append(
            ("https", urllib.parse.urlunparse(parsed._replace(scheme="https")))
        )

    # Some old Vegvesen URLs moved between www and bare host before being archived.
    if parsed.netloc.startswith("www."):
        variants.append(
            (
                "without-www",
                urllib.parse.urlunparse(parsed._replace(netloc=parsed.netloc[4:])),
            )
        )
    else:
        variants.append(
            (
                "with-www",
                urllib.parse.urlunparse(parsed._replace(netloc="www." + parsed.netloc)),
            )
        )

    filename = Path(parsed.path).name
    if filename:
        variants.append(("filename-wildcard", f"*.{parsed.netloc}/*/{filename}"))
        if parsed.netloc.startswith("www."):
            variants.append(
                ("filename-wildcard-without-www", f"*.{parsed.netloc[4:]}/*/{filename}")
            )

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, variant in variants:
        if variant not in seen:
            seen.add(variant)
            unique.append((label, variant))
    return unique


def wayback_available(
    url: str, timeout: int, user_agent: str, context: ssl.SSLContext
) -> tuple[str, str, str] | None:
    api = "https://archive.org/wayback/available?" + urllib.parse.urlencode(
        {"url": url}
    )
    request = urllib.request.Request(api, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        data = json.loads(response.read().decode("utf-8"))
    closest = data.get("archived_snapshots", {}).get("closest")
    if not closest or closest.get("status") != "200":
        return None
    timestamp = closest.get("timestamp", "")
    archive_url = normalize_wayback_url(closest.get("url", ""), timestamp, url)
    return archive_url, timestamp, closest.get("status", "")


def wayback_cdx(
    url: str, timeout: int, user_agent: str, context: ssl.SSLContext
) -> tuple[str, str, str] | None:
    params = urllib.parse.urlencode(
        {
            "url": url,
            "output": "json",
            "fl": "timestamp,original,statuscode,mimetype",
            "filter": "statuscode:200",
            "collapse": "digest",
            "limit": "1",
            "sort": "reverse",
        }
    )
    api = "https://web.archive.org/cdx?" + params
    request = urllib.request.Request(api, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        data = json.loads(response.read().decode("utf-8"))
    rows = data[1:] if data and data[0][0] == "timestamp" else data
    if not rows:
        return None

    for timestamp, original, status, mimetype in rows:
        if (
            "*" in url
            and Path(urllib.parse.urlparse(original).path).name != Path(url).name
        ):
            continue

        archive_mode = (
            "id_"
            if "pdf" in mimetype.lower() or original.lower().endswith(".pdf")
            else ""
        )
        return (
            f"https://web.archive.org/web/{timestamp}{archive_mode}/{original}",
            timestamp,
            status,
        )

    return None


def find_wayback(
    url: str, timeout: int, user_agent: str, context: ssl.SSLContext
) -> tuple[str, str, str, str]:
    for source, variant in url_variants(url):
        try:
            if source in {
                "exact",
                "without-query",
                "http",
                "https",
                "without-www",
                "with-www",
            }:
                available = wayback_available(variant, timeout, user_agent, context)
                if available:
                    archive_url, timestamp, status = available
                    if wayback_capture_looks_complete(
                        archive_url, variant, timeout, user_agent, context
                    ):
                        return archive_url, timestamp, status, f"available:{source}"

            cdx = wayback_cdx(variant, timeout, user_agent, context)
            if cdx:
                archive_url, timestamp, status = cdx
                if wayback_capture_looks_complete(
                    archive_url, variant, timeout, user_agent, context
                ):
                    return archive_url, timestamp, status, f"cdx:{source}"
        except Exception:
            continue

    return "", "", "", ""


def check_link(
    url: str,
    refs: list[Reference],
    args: argparse.Namespace,
    context: ssl.SSLContext,
    opener: urllib.request.OpenerDirector,
) -> LinkResult:
    status, reason, final_url = check_http_status(
        url, args.timeout, args.user_agent, opener
    )
    result = LinkResult(
        url=url, status=status, reason=reason, final_url=final_url, refs=refs
    )
    if result.broken:
        archive_url, timestamp, archive_status, source = find_wayback(
            url, args.timeout, args.user_agent, context
        )
        result.wayback_url = archive_url
        result.wayback_timestamp = timestamp
        result.wayback_status = archive_status
        result.wayback_source = source
    return result


def format_refs(refs: Iterable[Reference]) -> str:
    return ", ".join(f"{ref.path}:{ref.line}" for ref in refs)


def write_markdown(results: list[LinkResult], output: Path | None) -> None:
    lines = ["# Link Check With Wayback", ""]
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %z')}")
    lines.append("")
    lines.append(f"Checked URLs: {len(results)}")
    lines.append(f"Broken URLs: {sum(result.broken for result in results)}")
    lines.append(
        f"Wayback matches: {sum(bool(result.wayback_url) for result in results)}"
    )
    lines.append("")

    broken = [
        result for result in results if result.broken and not result.likely_blocked
    ]
    blocked = [result for result in results if result.broken and result.likely_blocked]

    lines.append("## Broken Links")
    lines.append("")
    if not broken:
        lines.append("No broken links found.")
    for result in broken:
        status = result.status if result.status is not None else "ERR"
        lines.append(f"- `{status}` {result.url}")
        if result.reason:
            lines.append(f"  - Reason: {result.reason}")
        lines.append(f"  - References: {format_refs(result.refs)}")
        if result.wayback_url:
            lines.append(f"  - Wayback: {result.wayback_url}")
            lines.append(
                f"  - Wayback timestamp: `{result.wayback_timestamp}` ({result.wayback_source})"
            )
        else:
            lines.append("  - Wayback: no 200 snapshot found")

    if blocked:
        lines.append("")
        lines.append("## Possibly Blocked by Bot Protection (verify manually)")
        lines.append("")
        lines.append(
            "These returned 403/406/429, which is often a WAF/anti-bot response "
            "rather than a truly dead link. Open them in a browser before assuming "
            "they are broken."
        )
        lines.append("")
        for result in blocked:
            lines.append(f"- `{result.status}` {result.url}")
            if result.reason:
                lines.append(f"  - Reason: {result.reason}")
            lines.append(f"  - References: {format_refs(result.refs)}")

    text = "\n".join(lines) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def write_csv(results: list[LinkResult], output: Path | None) -> None:
    fieldnames = [
        "status",
        "reason",
        "url",
        "final_url",
        "references",
        "likely_blocked",
        "wayback_url",
        "wayback_timestamp",
        "wayback_status",
        "wayback_source",
    ]
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
    stream = output.open("w", newline="", encoding="utf-8") if output else sys.stdout
    try:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            if not result.broken:
                continue
            writer.writerow(
                {
                    "status": result.status if result.status is not None else "ERR",
                    "reason": result.reason,
                    "url": result.url,
                    "final_url": result.final_url,
                    "references": format_refs(result.refs),
                    "likely_blocked": result.likely_blocked,
                    "wayback_url": result.wayback_url,
                    "wayback_timestamp": result.wayback_timestamp,
                    "wayback_status": result.wayback_status,
                    "wayback_source": result.wayback_source,
                }
            )
    finally:
        if output:
            stream.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check external Markdown links and find Wayback replacements."
    )
    parser.add_argument("--content-dir", default="content/innsikt", type=Path)
    parser.add_argument(
        "--host",
        help="Only check URLs whose host contains this string, e.g. vegvesen.no",
    )
    parser.add_argument("--format", choices=("markdown", "csv"), default="markdown")
    parser.add_argument(
        "--output", type=Path, help="Write report to this path instead of stdout"
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.content_dir.exists():
        print(f"Content directory does not exist: {args.content_dir}", file=sys.stderr)
        return 2

    refs_by_url = extract_links(args.content_dir, args.host)
    context = ssl.create_default_context()
    opener = build_opener(context)
    results: list[LinkResult] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(check_link, url, refs, args, context, opener)
            for url, refs in sorted(refs_by_url.items())
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda result: (not result.broken, result.url))
    if args.format == "csv":
        write_csv(results, args.output)
    else:
        write_markdown(results, args.output)

    return 1 if any(result.broken for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
