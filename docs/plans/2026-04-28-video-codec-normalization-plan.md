# Video Codec Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add final-stage codec inspection and quality-first normalization so delivered videos target `mp4 + h264 + aac`, while falling back to original delivery with warning if normalization fails.

**Architecture:** Build small backend helpers for `ffprobe` inspection and ffmpeg normalization, then integrate them into the detached worker post-processing chain after optional clip cutting. Keep the implementation incremental, test-first, and avoid mixing normalization policy into yt-dlp download selection logic.

**Tech Stack:** Python 3.11+, ffprobe, ffmpeg, pytest, existing detached worker pipeline

---

### Task 1: Add failing tests for codec inspection and normalization decision

**Files:**
- Create: `tests/test_video_codec_inspection.py`
- Create: `app/video_codec_inspection.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_probe_video_codecs_parses_video_audio_and_container():
    ...
```

```python
def test_normalization_required_only_when_not_mp4_h264_aac():
    ...
```

```python
def test_normalization_summary_formats_user_visible_codec_info():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_codec_inspection.py -q`

Expected: FAIL because `app.video_codec_inspection` does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- a small inspection dataclass for container/video/audio summary
- `probe_video_codecs(...)`
- `needs_codec_normalization(...)`
- `format_codec_summary(...)`

Use injectable subprocess helpers so tests do not require real ffprobe binaries.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_codec_inspection.py -q`

Expected: PASS

### Task 2: Add failing tests for final-stage ffmpeg normalization

**Files:**
- Create: `tests/test_video_codec_normalization.py`
- Create: `app/video_codec_normalization.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_build_normalization_command_targets_mp4_h264_aac():
    ...
```

```python
def test_normalize_video_file_runs_ffmpeg_and_returns_mp4_path():
    ...
```

```python
def test_normalize_video_file_reports_failure_without_hiding_original():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_codec_normalization.py -q`

Expected: FAIL because the module does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- ffmpeg command builder for quality-first normalization
- `normalize_video_file(...)`
- sensible defaults for `libx264`, `aac`, `aac_low`, `preset=slower`

Keep command construction backend-only and side-effect injection friendly.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_codec_normalization.py -q`

Expected: PASS

### Task 3: Extend detached post-processing with inspection and fallback warning flow

**Files:**
- Modify: `app/video_postprocess_backend.py`
- Modify: `tests/test_video_postprocess_backend.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_postprocess_video_file_skips_normalization_for_mp4_h264_aac():
    ...
```

```python
def test_postprocess_video_file_normalizes_non_compliant_output():
    ...
```

```python
def test_postprocess_video_file_returns_original_with_warning_on_normalization_failure():
    ...
```

```python
def test_postprocess_video_file_removes_obsolete_intermediate_after_success():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_video_postprocess_backend.py -q`

Expected: FAIL because the normalization branch does not exist yet.

**Step 3: Write minimal implementation**

Integrate:

- codec inspection after cut/subtitle/metadata steps
- conditional normalization
- warning-bearing fallback when normalization fails
- single-final-file retention

Prefer returning a richer result object if the current path tuple becomes too lossy.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_video_postprocess_backend.py -q`

Expected: PASS

### Task 4: Persist normalization results into detached worker state

**Files:**
- Modify: `app/job_video_handler.py`
- Modify: `app/job_store.py`
- Modify: `tests/test_job_video_handler.py`
- Modify: `tests/test_job_store.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_handle_video_job_item_records_normalized_delivery_summary():
    ...
```

```python
def test_handle_video_job_item_records_warning_when_original_file_is_delivered():
    ...
```

```python
def test_job_store_persists_item_warning_and_codec_summary_fields():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_video_handler.py tests/test_job_store.py -q`

Expected: FAIL because normalization result metadata is not persisted yet.

**Step 3: Write minimal implementation**

Persist enough state for the UI to explain final delivery outcome:

- normalization required
- normalization succeeded
- delivered codec summary
- warning message if fallback occurred

Use either explicit columns or a constrained metadata field, but keep the shape stable and queryable.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_job_video_handler.py tests/test_job_store.py -q`

Expected: PASS

### Task 5: Surface codec-normalization outcome in the background jobs UI

**Files:**
- Modify: `app/main.py`
- Modify: `app/translations/en.py`
- Modify: `app/translations/zh.py`
- Modify: `app/translations/fr.py`
- Modify: `tests/test_translations.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_translation_keys_exist_for_codec_normalization_status():
    ...
```

If there is no UI snapshot harness, at minimum test the translation contract and keep the rendering logic straightforward.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_translations.py -q`

Expected: FAIL because new translation keys do not exist yet.

**Step 3: Write minimal implementation**

Show concise delivery status such as:

- normalized to MP4 / H.264 / AAC
- delivered original file with warning

Avoid adding a full new dashboard section unless necessary.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_translations.py -q`

Expected: PASS

### Task 6: Verify playlist shared-cut normalization flow end to end at the unit/integration seam

**Files:**
- Modify: `tests/test_job_download_config.py`
- Modify: `tests/test_job_worker_entry.py`
- Modify: `tests/test_job_video_handler.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_playlist_job_item_uses_shared_cut_times_then_normalizes():
    ...
```

```python
def test_playlist_job_item_falls_back_to_original_with_warning_when_normalization_fails():
    ...
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_download_config.py tests/test_job_video_handler.py tests/test_job_worker_entry.py -q`

Expected: FAIL because the playlist path does not yet persist the normalization outcome semantics.

**Step 3: Write minimal implementation**

Ensure playlist items:

- inherit shared clip settings from job config
- run the same normalization stage as single videos
- report per-item warnings cleanly

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_job_download_config.py tests/test_job_video_handler.py tests/test_job_worker_entry.py -q`

Expected: PASS

### Task 7: Run focused regression and compile verification

**Files:**
- Test: `tests/test_video_codec_inspection.py`
- Test: `tests/test_video_codec_normalization.py`
- Test: `tests/test_video_postprocess_backend.py`
- Test: `tests/test_job_video_handler.py`
- Test: `tests/test_job_store.py`
- Test: `tests/test_translations.py`

**Step 1: Run focused tests**

Run:

```bash
uv run pytest \
  tests/test_video_codec_inspection.py \
  tests/test_video_codec_normalization.py \
  tests/test_video_postprocess_backend.py \
  tests/test_job_video_handler.py \
  tests/test_job_store.py \
  tests/test_translations.py -q
```

Expected: PASS

**Step 2: Run broader regression checks**

Run:

```bash
uv run pytest \
  tests/test_download_auth.py \
  tests/test_download_runtime_state.py \
  tests/test_logs_runtime_state.py \
  tests/test_video_workspace_backend.py \
  tests/test_video_download_backend.py \
  tests/test_video_file_ops.py \
  tests/test_video_download_service.py \
  tests/test_job_runtime.py \
  tests/test_job_worker.py \
  tests/test_job_worker_entry.py \
  tests/test_job_scheduler.py \
  tests/test_job_submission.py \
  tests/test_download_execution_plan.py \
  tests/test_job_download_config.py \
  tests/test_video_cache_backend.py -q
```

Expected: PASS

**Step 3: Run compile verification**

Run:

```bash
uv run python -m py_compile app/main.py app/job_video_handler.py app/video_postprocess_backend.py app/video_codec_inspection.py app/video_codec_normalization.py
uv run python -m compileall app
```

Expected: exit 0

### Task 8: Commit the codec-normalization phase

**Files:**
- Add: `app/video_codec_inspection.py`
- Add: `app/video_codec_normalization.py`
- Modify: `app/video_postprocess_backend.py`
- Modify: `app/job_video_handler.py`
- Modify: `app/job_store.py`
- Modify: `app/main.py`
- Modify: `app/translations/en.py`
- Modify: `app/translations/zh.py`
- Modify: `app/translations/fr.py`
- Add/Modify: related tests above

**Step 1: Review diff**

Run:

```bash
git diff -- \
  app/video_codec_inspection.py \
  app/video_codec_normalization.py \
  app/video_postprocess_backend.py \
  app/job_video_handler.py \
  app/job_store.py \
  app/main.py \
  app/translations/en.py \
  app/translations/zh.py \
  app/translations/fr.py \
  tests/test_video_codec_inspection.py \
  tests/test_video_codec_normalization.py \
  tests/test_video_postprocess_backend.py
```

Expected: only codec-normalization phase changes

**Step 2: Commit**

Run:

```bash
git add \
  app/video_codec_inspection.py \
  app/video_codec_normalization.py \
  app/video_postprocess_backend.py \
  app/job_video_handler.py \
  app/job_store.py \
  app/main.py \
  app/translations/en.py \
  app/translations/zh.py \
  app/translations/fr.py \
  tests/test_video_codec_inspection.py \
  tests/test_video_codec_normalization.py \
  tests/test_video_postprocess_backend.py
git commit -m "Add final video codec normalization"
```

Expected: clean commit containing only this phase
