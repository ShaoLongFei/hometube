"""
Backend-friendly cookies resolution helpers for downloads and URL analysis.
"""

from __future__ import annotations

from pathlib import Path

from app.core import build_cookies_params as core_build_cookies_params
from app.download_runtime_state import adapt_runtime_state
from app.file_system_utils import is_valid_browser
from app.site_cookies import build_site_cookies_params


def _noop_log(message: str) -> None:
    """Default no-op logger."""


def resolve_cookies_params(
    *,
    url: str,
    runtime_state,
    cookies_file_path: str,
    managed_cookies_params_fn=build_site_cookies_params,
    core_build_cookies_params_fn=core_build_cookies_params,
    log_fn=None,
) -> list[str]:
    """Resolve yt-dlp cookie arguments using runtime state plus managed cookies."""
    log = log_fn or _noop_log
    state = adapt_runtime_state(runtime_state)

    managed_result = managed_cookies_params_fn(url or "")
    if "--cookies" in managed_result:
        log(f"🍪 Using managed site cookies for URL: {url}")
        return managed_result

    cookies_method = state.get("cookies_method", "none")
    if cookies_method == "file":
        result = core_build_cookies_params_fn(
            cookies_method="file",
            cookies_file_path=cookies_file_path,
        )
        if "--cookies" in result:
            log(f"🍪 Using cookies from file: {cookies_file_path}")
        else:
            log(
                f"⚠️ Cookies file not found, falling back to no cookies: {cookies_file_path}"
            )
        return result

    if cookies_method == "browser":
        browser = state.get("browser_select", "chrome")
        profile = state.get("browser_profile", "").strip()
        result = core_build_cookies_params_fn(
            cookies_method="browser",
            browser_select=browser,
            browser_profile=profile,
        )
        browser_config = f"{browser}:{profile}" if profile else browser
        log(f"🍪 Using cookies from browser: {browser_config}")
        return result

    log("🍪 No cookies authentication")
    return core_build_cookies_params_fn(cookies_method="none")


def resolve_cookies_params_from_config(
    *,
    url: str,
    cookies_file_path: str,
    cookies_from_browser: str,
    managed_cookies_params_fn=build_site_cookies_params,
    core_build_cookies_params_fn=core_build_cookies_params,
    is_valid_browser_fn=is_valid_browser,
) -> list[str]:
    """Resolve yt-dlp cookie arguments using server-side config defaults."""
    managed_result = managed_cookies_params_fn(url or "")
    if "--cookies" in managed_result:
        return managed_result

    if cookies_file_path and Path(cookies_file_path).exists():
        return core_build_cookies_params_fn(
            cookies_method="file",
            cookies_file_path=cookies_file_path,
        )

    if cookies_from_browser and is_valid_browser_fn(cookies_from_browser):
        return core_build_cookies_params_fn(
            cookies_method="browser",
            browser_select=cookies_from_browser,
            browser_profile="",
        )

    return []
