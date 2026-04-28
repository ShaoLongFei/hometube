"""
Pure helpers for resolving download execution plans outside Streamlit session state.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileDownloadPlan:
    """Resolved execution settings for one profile-based download."""

    profiles_to_try: list[dict]
    quality_strategy: str
    download_mode: str
    refuse_quality_downgrade: bool


def resolve_profile_download_plan(
    *,
    requested_profiles: list[dict] | None,
    requested_quality_strategy: str | None,
    fallback_profiles: list[dict],
    fallback_quality_strategy: str,
    refuse_quality_downgrade_best: bool | None,
    quality_downgrade_enabled: bool,
) -> ProfileDownloadPlan:
    """Resolve the effective profile list and fallback policy for a download."""
    profiles_to_try = (
        requested_profiles if requested_profiles is not None else fallback_profiles
    )
    quality_strategy = requested_quality_strategy or fallback_quality_strategy

    if not profiles_to_try:
        raise ValueError("No profiles available for download")

    refuse_best = (
        refuse_quality_downgrade_best
        if refuse_quality_downgrade_best is not None
        else (not quality_downgrade_enabled)
    )

    if quality_strategy == "auto_best":
        download_mode = "auto"
        refuse_quality_downgrade = False
    elif quality_strategy == "best_no_fallback":
        download_mode = "forced"
        refuse_quality_downgrade = refuse_best
    elif quality_strategy in {"choose_profile", "choose_available"}:
        download_mode = "forced"
        refuse_quality_downgrade = False
    else:
        download_mode = "auto"
        refuse_quality_downgrade = False

    return ProfileDownloadPlan(
        profiles_to_try=profiles_to_try,
        quality_strategy=quality_strategy,
        download_mode=download_mode,
        refuse_quality_downgrade=refuse_quality_downgrade,
    )
