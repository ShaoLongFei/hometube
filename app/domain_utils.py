"""Domain and site-key helpers shared by cookies and workspace routing."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

import tldextract

_EXTRACTOR = tldextract.TLDExtract(
    suffix_list_urls=(),
    cache_dir=False,
    include_psl_private_domains=True,
)
_SAFE_SITE_KEY_RE = re.compile(r"[^a-z0-9._-]+")


def get_primary_domain(host_or_domain: str) -> str:
    """Return the registrable domain for a host using bundled PSL rules."""
    value = (host_or_domain or "").strip().lower().lstrip(".")
    if not value:
        return ""

    extracted = _EXTRACTOR(value)
    primary = extracted.top_domain_under_public_suffix
    if primary:
        return primary

    labels = [label for label in value.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) > 1 else value


def site_key_from_url(url: str, *, fallback: str = "generic") -> str:
    """Return a stable, filesystem-safe platform key for a URL."""
    hostname = urlparse(url or "").hostname or ""
    primary_domain = get_primary_domain(hostname)
    if not primary_domain:
        return fallback
    return sanitize_site_key(primary_domain)


def sanitize_site_key(value: str) -> str:
    """Normalize arbitrary site names for use as a workspace path segment."""
    normalized = _SAFE_SITE_KEY_RE.sub("-", (value or "").strip().lower())
    normalized = normalized.strip(".-_")
    return normalized or "generic"


def stable_url_hash(url: str, *, length: int = 12) -> str:
    """Return a short deterministic hash for URLs without a better ID."""
    return hashlib.md5((url or "").encode("utf-8")).hexdigest()[:length]
