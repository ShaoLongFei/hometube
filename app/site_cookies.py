"""
Managed site cookies utilities for HomeTube.

This module stores Netscape cookies text as one file per primary domain and
resolves the matching file for a download URL.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings
from app.domain_utils import get_primary_domain


NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


def get_managed_cookies_dir(base_dir: Path | None = None) -> Path:
    """Get the managed cookies directory and ensure it exists."""
    directory = base_dir if base_dir is not None else get_settings().MANAGED_COOKIES_FOLDER
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def _write_private_text(target: Path, content: str) -> None:
    """Atomically write sensitive text with owner-only file permissions."""
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp_path, target)
        target.chmod(0o600)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


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
        _write_private_text(target, content)
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
