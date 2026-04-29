"""
Shared playlist-entry routing helpers.

These helpers keep playlist item URL/platform/workspace decisions consistent
between job submission and playlist synchronization.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.workspace import parse_url


@dataclass(frozen=True)
class PlaylistEntryTarget:
    """Resolved execution and workspace target for one playlist entry."""

    video_id: str
    video_url: str
    platform: str
    workspace_id: str


def resolve_playlist_entry_target(entry: dict, playlist_url: str) -> PlaylistEntryTarget:
    """
    Resolve one playlist entry without inventing cross-site URLs.

    YouTube entries often contain only a bare video ID, so a watch URL is safe to
    synthesize. For other platforms, keep the playlist URL as the last-resort
    executable URL but use the entry ID and playlist platform for workspace
    identity.
    """
    entry_id = str(entry.get("id") or "").strip()
    entry_url = str(entry.get("url") or "").strip()
    playlist_info = parse_url(playlist_url)

    if entry_url:
        parsed = parse_url(entry_url)
        workspace_id = parsed.id if parsed.id != "unknown" else entry_id
        return PlaylistEntryTarget(
            video_id=entry_id or workspace_id,
            video_url=entry_url,
            platform=parsed.platform,
            workspace_id=workspace_id,
        )

    if playlist_info.platform == "youtube" and entry_id:
        video_url = f"https://www.youtube.com/watch?v={entry_id}"
        parsed = parse_url(video_url)
        return PlaylistEntryTarget(
            video_id=entry_id,
            video_url=video_url,
            platform=parsed.platform,
            workspace_id=parsed.id,
        )

    workspace_id = entry_id or playlist_info.id
    return PlaylistEntryTarget(
        video_id=entry_id or playlist_info.id,
        video_url=playlist_url,
        platform=playlist_info.platform,
        workspace_id=workspace_id,
    )
