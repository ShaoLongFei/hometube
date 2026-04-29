# Code Review Fixes Design

## Goal

Close the real risks found in the architecture review without broad rewrites.

## Scope

- Keep background downloads as the only active download path.
- Remove the unreachable foreground download block from `app/main.py`.
- Resolve playlist entry platform/workspace details from the entry URL when present, and from the playlist platform when an entry URL is missing.
- Make playlist synchronization look for cached tmp videos under the playlist platform, not always `youtube`.
- Make media-library reencode return a non-zero exit code when any file fails.
- Make background progress text distinguish completed and actively running items.
- Remove machine-specific sample paths from scripts.

## Design

Playlist entry routing gets a small shared helper that returns `video_url`, `video_id`, `platform`, and `workspace_id`. YouTube can still synthesize a watch URL from a bare ID. Other sites keep the original playlist URL as a last-resort executable URL but use the entry ID and playlist platform for the workspace, avoiding cross-site cache pollution.

Playlist synchronization infers the playlist platform from `tmp/playlists/{platform}/{playlist_id}` first, then from playlist metadata. That keeps the public sync API mostly unchanged and fixes cached tmp lookup for Bilibili and future sites.

The reencode CLI remains simple: it still processes all files and writes the summary, but returns `1` when any item failed. This makes cron/systemd/CI monitoring accurate without changing retry or state behavior.

The Streamlit background panel keeps the existing progress calculation. Only the displayed label changes when items are running, so users can see both settled completion and in-flight activity.

## Test Plan

- Add regression tests before implementation for the playlist routing and sync bugs.
- Add a reencode CLI test that simulates one failed worker result and expects non-zero exit.
- Add lightweight source/translation tests for the progress label and repo-hygiene cleanup.
- Run focused tests, then the full suite.
