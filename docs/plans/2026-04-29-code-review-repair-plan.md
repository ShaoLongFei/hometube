# Code Review Repair Plan

Date: 2026-04-29

## Goal

Fix the confirmed code review issues while keeping the implementation simple: one shared domain resolver, one workspace routing rule, one progress scaling rule, and minimal browser-extension messaging changes.

## Approach

1. Centralize domain logic in `app/domain_utils.py`.
   - Use bundled public suffix rules through `tldextract` without runtime network fetching.
   - Reuse the same primary-domain logic for managed cookies and generic workspace platform keys.

2. Route workspaces by real platform/site.
   - Parse Bilibili video/list URLs explicitly.
   - Keep YouTube/known-platform behavior stable.
   - For unknown sites, use the primary domain as the platform key instead of a global `generic` bucket.

3. Make Bilibili multipart entries executable and uniquely trackable.
   - Always create `{parent_id}_p{part_number}` IDs for multipart entries.
   - Preserve extractor-provided IDs separately as `source_video_id`.

4. Harden managed cookies storage.
   - Managed cookies directories are `0700`.
   - Cookie files are atomically written as `0600`.

5. Keep background jobs recoverable and UI progress monotonic.
   - Run orphan recovery before every scheduler iteration.
   - Scale download progress to `0-80%` and transcoding progress to `80-99%`; completion still sets `100%`.

6. Simplify extension and reencode script behavior.
   - Extension content script responds to Streamlit iframe pings.
   - Extension no longer duplicates primary-domain logic; the server performs final grouping.
   - Media-library reencode defaults no longer contain deployment-specific paths.

## Verification

- Targeted regression tests cover each confirmed issue.
- Changed Python files pass `ruff check`.
- Full test suite should pass before considering the repair complete.
