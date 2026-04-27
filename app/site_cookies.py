"""
Managed site cookies utilities for HomeTube.

This module stores Netscape cookies text as one file per primary domain and
resolves the matching file for a download URL.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings


NETSCAPE_HEADER = "# Netscape HTTP Cookie File"
COMMON_SECOND_LEVEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.cn",
    "net.cn",
    "org.cn",
    "com.hk",
    "com.tw",
    "co.jp",
    "co.kr",
    "co.in",
    "com.au",
    "com.br",
    "com.mx",
    "com.tr",
    "com.sg",
}


def get_managed_cookies_dir(base_dir: Path | None = None) -> Path:
    """Get the managed cookies directory and ensure it exists."""
    directory = base_dir if base_dir is not None else get_settings().MANAGED_COOKIES_FOLDER
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_primary_domain(host_or_domain: str) -> str:
    """Reduce a host/domain to its primary domain grouping key."""
    value = (host_or_domain or "").strip().lower().lstrip(".")
    if not value:
        return ""

    labels = [label for label in value.split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)

    last_two = ".".join(labels[-2:])
    last_three = ".".join(labels[-3:])

    if last_two in COMMON_SECOND_LEVEL_SUFFIXES and len(labels) >= 3:
        return last_three

    if ".".join(labels[-2:]) in COMMON_SECOND_LEVEL_SUFFIXES and len(labels) >= 3:
        return last_three

    return last_two


def _iter_cookie_entries(cookies_text: str) -> list[str]:
    """Extract valid Netscape cookie lines."""
    entries: list[str] = []
    for raw_line in cookies_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = raw_line.split("\t")
        if len(parts) < 7:
            continue
        domain = parts[0].strip()
        if not domain:
            continue
        entries.append(raw_line.rstrip())
    return entries


def parse_cookies_text_by_site(cookies_text: str) -> dict[str, list[str]]:
    """Parse Netscape cookies text and group entries by primary domain."""
    grouped: dict[str, list[str]] = {}
    for entry in _iter_cookie_entries(cookies_text):
        domain = entry.split("\t", 1)[0].strip()
        site = get_primary_domain(domain)
        if not site:
            continue
        grouped.setdefault(site, []).append(entry)

    if not grouped:
        raise ValueError("No valid cookie entries found in pasted text")

    return grouped


def save_cookies_text_by_site(
    cookies_text: str,
    base_dir: Path | None = None,
) -> dict[str, Path]:
    """Split cookies text by primary domain and save one file per site."""
    grouped = parse_cookies_text_by_site(cookies_text)
    directory = get_managed_cookies_dir(base_dir)

    saved: dict[str, Path] = {}
    for site, entries in grouped.items():
        target = directory / f"{site}.txt"
        content = NETSCAPE_HEADER + "\n" + "\n".join(entries) + "\n"
        target.write_text(content, encoding="utf-8")
        saved[site] = target

    return saved


def list_saved_site_cookies(base_dir: Path | None = None) -> list[dict]:
    """List saved managed site cookies files and basic metadata."""
    directory = get_managed_cookies_dir(base_dir)
    items: list[dict] = []

    for file_path in sorted(directory.glob("*.txt")):
        lines = file_path.read_text(encoding="utf-8").splitlines()
        cookie_count = len(_iter_cookie_entries("\n".join(lines)))
        items.append(
            {
                "site": file_path.stem,
                "path": str(file_path),
                "cookie_count": cookie_count,
                "modified_at": file_path.stat().st_mtime,
            }
        )

    return items


def delete_site_cookies_file(site: str, base_dir: Path | None = None) -> bool:
    """Delete a managed site cookies file if it exists."""
    normalized_site = get_primary_domain(site)
    if not normalized_site:
        return False

    target = get_managed_cookies_dir(base_dir) / f"{normalized_site}.txt"
    if not target.exists():
        return False

    target.unlink()
    return True


def resolve_site_cookies_file_for_url(
    url: str,
    base_dir: Path | None = None,
) -> Path | None:
    """Resolve the managed cookies file for a given URL."""
    host = urlparse(url).hostname or ""
    site = get_primary_domain(host)
    if not site:
        return None

    target = get_managed_cookies_dir(base_dir) / f"{site}.txt"
    return target if target.exists() else None


def build_site_cookies_params(
    url: str,
    base_dir: Path | None = None,
) -> list[str]:
    """Build yt-dlp --cookies args for a URL if managed site cookies exist."""
    path = resolve_site_cookies_file_for_url(url, base_dir)
    if path is None:
        return []
    return ["--cookies", str(path)]
