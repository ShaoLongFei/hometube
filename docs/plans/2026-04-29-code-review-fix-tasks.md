# HomeTube Code Review Fix Tasks

Date: 2026-04-29

This document records the confirmed issues from the code review pass. Each item includes the verification status, evidence, and the recommended fix direction. No code changes are included here.

## Task List

| ID | Priority | Status | Issue | Evidence | Recommended Fix |
| --- | --- | --- | --- | --- | --- |
| CR-001 | High | Fixed | Chromium extension installation detection can falsely report "not installed". | `app/main.py` posts `HOMETUBE_EXTENSION_PING` from a Streamlit component iframe to `window.parent`; `browser-extension/hometube-cookie-export/content.js` only accepts messages where `event.source === window`. Messages from the iframe are rejected. | Content script now replies to the ping source, including the Streamlit iframe. |
| CR-002 | High | Fixed | Playlist workspaces are hardcoded to `youtube`, so Bilibili and other sites are cached under the wrong platform. | `app/job_submission.py` uses `ensure_video_workspace(tmp_download_folder, "youtube", video_id)`. `app/main.py` also creates playlist workspaces with `"youtube"`. `app.workspace.parse_url()` currently parses Bilibili URLs as `generic`, so a naive `parse_url()` replacement is not enough. | Workspace routing now uses explicit Bilibili parsing and primary-domain fallback keys. |
| CR-003 | High | Fixed | Bilibili multipart expansion can generate duplicate item IDs when nested entries already contain the parent BV ID. | `app/playlist_entry_expansion.py` keeps `nested_entry["id"]` if present. A reproduced case returns `[("BV1abc", "...?p=1"), ("BV1abc", "...?p=2")]`. `app/playlist_utils.py` stores status in a dict keyed by `video_id`, so duplicate IDs overwrite each other. | Multipart IDs are now always `{parent_id}_p{part_number}`, with extractor IDs preserved as `source_video_id`. |
| CR-004 | High | Fixed | Managed cookies are written with default file permissions. | `app/site_cookies.py` writes cookie files with `Path.write_text()`. On a normal umask, a newly created managed cookies directory is `0755` and files are `0644`. | Cookie directories are `0700`; cookie files are atomically written as `0600`. |
| CR-005 | Medium | Fixed | Orphaned running jobs are only recovered when the scheduler starts. | `app/job_runtime.py` calls `recover()` once before entering the loop. If a worker dies after that, the item can stay `running` until the web process restarts. | Scheduler recovery now runs before each dispatch iteration. |
| CR-006 | Medium | Fixed | Download and transcode progress share one raw percentage field, so progress can move backward or misrepresent total work. | `app/job_command_runner.py` writes ffmpeg progress percentages into the same `progress_percent` field used by yt-dlp. `app/main.py` aggregates this raw field directly. After download reaches 100%, transcoding can report a lower percentage. | Job item progress now scales download to `0-80%` and transcoding to `80-99%`; completion remains `100%`. |
| CR-007 | Medium | Fixed | Primary-domain matching relies on hand-maintained suffix lists in both Python and the extension. | `app/site_cookies.py` and `browser-extension/.../background.js` duplicate small suffix lists. `www.example.co.nz` currently resolves to `co.nz`, which is wrong. | Server-side primary-domain parsing now uses bundled public suffix rules through `tldextract`; the extension no longer duplicates this logic. |
| CR-008 | Low | Fixed | The media-library reencode script contains deployment-specific defaults. | `scripts/reencode_media_library.py` previously embedded machine-specific media and service data paths. | Reencode root now comes from `--root` or `HOMETUBE_REENCODE_ROOT`; state/log defaults use generic local state paths. |

## Notes

- The full test suite currently passes: `458 passed, 9 skipped`.
- Targeted regression tests were added for the confirmed failure modes.
- Implementation details are summarized in `docs/plans/2026-04-29-code-review-repair-plan.md`.
