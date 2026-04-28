# Background Jobs Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first production-safe background jobs foundation for HomeTube: persistent job/item storage, consistent state aggregation, and scheduler selection logic that no longer depends on Streamlit session state.

**Architecture:** Add a SQLite-backed task store plus pure-Python job models and scheduler helpers. Keep the first implementation slice focused on durable state and dispatch decisions, so later download-worker integration can reuse the same backend contract without reworking persistence again.

**Tech Stack:** Python 3.11+, SQLite (`sqlite3`), pytest, existing HomeTube app modules

---

### Task 1: Add failing tests for persistent job storage

**Files:**
- Create: `tests/test_job_store.py`
- Create: `app/job_store.py`
- Create: `app/job_models.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_create_video_job_persists_items(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(...)
    job = store.get_job(job_id)
    items = store.get_job_items(job_id)
    assert job["kind"] == "video"
    assert len(items) == 1
```

```python
def test_create_playlist_job_persists_multiple_items(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(...)
    items = store.get_job_items(job_id)
    assert len(items) == 3
    assert [item["item_index"] for item in items] == [1, 2, 3]
```

```python
def test_refresh_job_status_marks_completed_when_all_items_done(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    ...
    assert store.get_job(job_id)["status"] == "completed"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_store.py -v --tb=short`

Expected: FAIL because `app.job_store` and related APIs do not exist yet.

**Step 3: Write minimal implementation**

Implement:

- `JobStatus` / `JobItemStatus` enums in `app/job_models.py`
- `JobStore` with schema bootstrap in `app/job_store.py`
- job creation, item creation, retrieval, log insert, item status update, aggregate refresh

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_job_store.py -v --tb=short`

Expected: PASS

### Task 2: Add failing tests for scheduler dispatch fairness and concurrency

**Files:**
- Create: `tests/test_job_scheduler.py`
- Create: `app/job_scheduler.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_select_dispatch_batch_respects_global_limit():
    batch = select_dispatch_batch(...)
    assert len(batch) == 2
```

```python
def test_select_dispatch_batch_respects_per_job_limit():
    batch = select_dispatch_batch(...)
    assert sum(1 for item in batch if item["job_id"] == first_job_id) == 1
```

```python
def test_select_dispatch_batch_spreads_first_slots_across_jobs():
    batch = select_dispatch_batch(...)
    assert {item["job_id"] for item in batch[:2]} == {job_a, job_b}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_scheduler.py -v --tb=short`

Expected: FAIL because `app.job_scheduler` does not exist yet.

**Step 3: Write minimal implementation**

Implement a pure selection helper that:

- accepts runnable items plus active counts
- enforces global active limit
- enforces per-job active limit
- gives each eligible job one slot before filling extra capacity

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_job_scheduler.py -v --tb=short`

Expected: PASS

### Task 3: Integrate job store queries needed by scheduler

**Files:**
- Modify: `app/job_store.py`
- Modify: `tests/test_job_store.py`

**Step 1: Write the failing test**

Add tests covering:

```python
def test_list_runnable_items_excludes_running_and_terminal_states(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    ...
    assert [item["id"] for item in runnable] == [queued_item_id]
```

```python
def test_get_active_counts_reports_global_and_per_job_usage(tmp_path):
    counts = store.get_active_counts()
    assert counts["global"] == 2
    assert counts["per_job"][job_id] == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_store.py -v --tb=short`

Expected: FAIL because runnable-item and active-count APIs are missing.

**Step 3: Write minimal implementation**

Implement:

- `list_runnable_items()`
- `get_active_counts()`
- `list_jobs()`
- deterministic ordering by priority and creation time

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_job_store.py -v --tb=short`

Expected: PASS

### Task 4: Verify the new background-jobs foundation against the existing suite

**Files:**
- Test: `tests/test_job_store.py`
- Test: `tests/test_job_scheduler.py`
- Verify existing modules still import cleanly

**Step 1: Run focused tests**

Run: `uv run pytest tests/test_job_store.py tests/test_job_scheduler.py -v --tb=short`

Expected: PASS

**Step 2: Run broader regression checks**

Run: `uv run pytest tests/test_status_utils.py tests/test_playlist_utils.py tests/test_workspace.py tests/test_file_operations.py -v --tb=short`

Expected: PASS

**Step 3: Run compile verification**

Run: `uv run python -m compileall app`

Expected: exit 0

### Task 5: Commit the phase-1 foundation

**Files:**
- Add: `app/job_models.py`
- Add: `app/job_store.py`
- Add: `app/job_scheduler.py`
- Add: `tests/test_job_store.py`
- Add: `tests/test_job_scheduler.py`
- Add: `docs/plans/2026-04-27-background-jobs-phase-1-plan.md`

**Step 1: Review diff**

Run: `git diff -- app/job_models.py app/job_store.py app/job_scheduler.py tests/test_job_store.py tests/test_job_scheduler.py docs/plans/2026-04-27-background-jobs-phase-1-plan.md`

Expected: only background-jobs foundation changes

**Step 2: Commit**

Run:

```bash
git add app/job_models.py app/job_store.py app/job_scheduler.py tests/test_job_store.py tests/test_job_scheduler.py docs/plans/2026-04-27-background-jobs-phase-1-plan.md
git commit -m "Add background job persistence foundation"
```

Expected: clean commit containing only the new foundation slice
