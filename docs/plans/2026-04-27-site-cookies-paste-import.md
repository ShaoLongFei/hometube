# Site Cookies Paste Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Chromium-extension-assisted cookies import flow that pastes Netscape cookies text into HomeTube, automatically splits it by primary domain, stores per-site cookies on the server, and automatically selects the matching cookies file for downloads by URL domain.

**Architecture:** Introduce a new backend module dedicated to managed site cookies. It will parse Netscape cookies text, derive a primary domain grouping key, persist one cookies file per site, and resolve the correct cookies file at download time. Streamlit UI will be simplified to an extension-status block plus a paste/import manager. A lightweight unpacked Chromium extension will provide install detection and manual cookie export for the active site.

**Tech Stack:** Python 3.11, Streamlit, yt-dlp, pytest, Chromium Manifest V3 extension

---

### Task 1: Backend Site Cookies Module

**Files:**
- Create: `app/site_cookies.py`
- Modify: `app/config.py`
- Test: `tests/test_site_cookies.py`

**Step 1: Write the failing test**

Add tests that:
- parse Netscape cookies text into site groups
- save one cookies file per primary domain
- resolve the matching cookies file for a URL

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_site_cookies.py -v --tb=short`
Expected: FAIL because module/functions do not exist yet

**Step 3: Write minimal implementation**

Implement:
- primary-domain extraction
- Netscape cookies parsing/grouping
- managed cookies directory resolution
- file persistence and listing helpers
- URL-to-cookies-file resolution

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_site_cookies.py -v --tb=short`
Expected: PASS

### Task 2: Download Path Integration

**Files:**
- Modify: `app/main.py`
- Modify: `app/playlist_sync.py`
- Test: `tests/test_site_cookies.py`

**Step 1: Write the failing test**

Add tests that verify a download URL resolves to the right managed cookies file path and returns yt-dlp `--cookies` args.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_site_cookies.py -k resolve -v --tb=short`
Expected: FAIL because download integration doesn’t use managed site cookies yet

**Step 3: Write minimal implementation**

Update the cookie-parameter builders to:
- prefer managed per-site cookies when a URL is known
- fall back to legacy config only when no managed cookies match

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_site_cookies.py -v --tb=short`
Expected: PASS

### Task 3: Streamlit Cookies UI

**Files:**
- Modify: `app/main.py`
- Modify: `app/translations/en.py`
- Modify: `app/translations/fr.py`
- Test: `tests/test_site_cookies.py`

**Step 1: Write the failing test**

Add tests for:
- rejecting invalid pasted cookies
- deleting a saved site cookies file
- listing saved site cookies metadata

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_site_cookies.py -k 'save or delete or list' -v --tb=short`
Expected: FAIL until UI/backend paths are wired

**Step 3: Write minimal implementation**

Replace the existing cookies UI block with:
- embedded extension status detector
- paste textarea
- parse/save action
- saved-site status list with delete action

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_site_cookies.py -v --tb=short`
Expected: PASS

### Task 4: Chromium Extension

**Files:**
- Create: `browser-extension/hometube-cookie-export/manifest.json`
- Create: `browser-extension/hometube-cookie-export/background.js`
- Create: `browser-extension/hometube-cookie-export/content.js`
- Create: `browser-extension/hometube-cookie-export/popup.html`
- Create: `browser-extension/hometube-cookie-export/popup.js`
- Create: `browser-extension/hometube-cookie-export/README.md`

**Step 1: Write the failing test**

No automated browser-extension test in repo for first version. Validate by loading unpacked extension manually after implementation.

**Step 2: Write minimal implementation**

Implement:
- content-script bridge for install detection on HomeTube pages
- popup action for current-site cookie export
- clipboard copy flow for exported Netscape text
- minimal install/readme guidance

**Step 3: Manual verification**

Load unpacked extension in Chromium and confirm:
- HomeTube page shows “installed”
- popup exports current-site cookies
- pasted cookies import successfully into HomeTube

### Task 5: Verification

**Files:**
- Modify: none
- Test: `tests/test_config.py`, `tests/test_site_cookies.py`, `tests/test_ytdlp_version_detection.py`

**Step 1: Run verification suite**

Run: `uv run pytest tests/test_config.py tests/test_site_cookies.py tests/test_ytdlp_version_detection.py -m 'not network' -v --tb=short`

**Step 2: Restart app**

Run the local Streamlit app on port `8510` and verify health.

**Step 3: Commit**

```bash
git add app browser-extension docs/plans tests
git commit -m "feat: add managed site cookies import flow"
```
