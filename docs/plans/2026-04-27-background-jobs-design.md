# HomeTube Background Jobs Design

**Date:** 2026-04-27

**Status:** Approved design

## Goal

Refactor HomeTube from a Streamlit-session-driven downloader into a server-side background job system so that:

- Closing the web page does not interrupt downloads
- Reopening the web UI shows current progress and history
- Multiple jobs can run in parallel
- A single playlist can download multiple videos in parallel
- The design stays simple: single container, no Redis, no extra services

## Current Problems

HomeTube currently executes downloads directly from `app/main.py` inside the active Streamlit request flow. This creates several issues:

- Download execution is tied to the browser session
- `st.session_state` acts as runtime state for active jobs
- Progress comes from multiple sources with inconsistent timing
- There is no global job queue or scheduler
- Playlist progress and active download progress can diverge in the UI
- The app cannot safely support detached execution or multi-job concurrency

## Design Principles

- Keep deployment simple: one container, one app, no external queue service
- Reuse existing download logic, workspaces, and media-processing code
- Move execution authority to the server, not the browser
- Use one durable source of truth for task state
- Prefer small, explicit state machines over clever orchestration
- Keep cancellation, retries, and restart recovery predictable

## Non-Goals

- No Redis, Celery, RabbitMQ, or separate worker containers
- No full distributed scheduling
- No live hot-reload of code into running jobs
- No large rewrite of yt-dlp/ffmpeg command construction

## High-Level Architecture

The new system has three layers inside the same container:

1. **Web UI / Streamlit**
   - Creates jobs
   - Displays jobs, job items, logs, and progress
   - Sends cancel and retry requests
   - Never directly executes yt-dlp or ffmpeg for long-running downloads

2. **Task Store**
   - SQLite-backed persistent store for jobs, items, events, and runtime metadata
   - Becomes the only authoritative source for active download state

3. **Worker Runtime**
   - One scheduler process controls dispatch
   - Multiple worker subprocesses execute actual downloads
   - Workers read configuration from the task store and workspace files, not from `st.session_state`

## Execution Model

### Job Types

- **Video job**
  - One submitted URL
  - One executable item

- **Playlist job**
  - One submitted playlist URL
  - One parent job
  - N executable items, one per playlist video

### Authority Split

- UI is responsible for submission and observation
- Scheduler is responsible for dispatch decisions
- Worker is responsible for one executable unit

This removes the existing coupling between the browser session and the download lifecycle.

## Persistent Data Model

Use SQLite with four core tables.

### `jobs`

One row per user-submitted task.

Suggested fields:

- `id`
- `kind` (`video`, `playlist`)
- `url`
- `title`
- `site`
- `destination_dir`
- `status`
- `priority`
- `max_parallelism`
- `total_items`
- `completed_items`
- `failed_items`
- `cancel_requested`
- `last_error`
- `config_json`
- `created_at`
- `started_at`
- `finished_at`
- `updated_at`

`config_json` stores a frozen snapshot of the user-selected options for this job, including:

- cookies resolution result
- subtitle settings
- SponsorBlock settings
- naming pattern
- overwrite rules
- custom yt-dlp args
- clip settings
- output location

### `job_items`

One row per executable download unit.

Suggested fields:

- `id`
- `job_id`
- `item_index`
- `video_id`
- `video_url`
- `title`
- `resolved_output_name`
- `workspace_path`
- `status`
- `retry_count`
- `progress_percent`
- `downloaded_bytes`
- `total_bytes`
- `speed_bps`
- `eta_seconds`
- `status_message`
- `worker_pid`
- `started_at`
- `finished_at`
- `last_heartbeat_at`
- `last_error`
- `updated_at`

### `job_logs`

Recent structured job events and UI-visible summaries.

Suggested fields:

- `id`
- `job_id`
- `job_item_id`
- `level`
- `message`
- `created_at`

This table should only keep structured summaries and recent user-facing events. Full raw logs should live on disk.

### `runtime_state`

Minimal global coordination state.

Suggested fields:

- `key`
- `value`
- `updated_at`

Use it for scheduler heartbeat, runtime versioning, and coarse global coordination only.

## State Machines

### Job States

- `queued`
- `running`
- `partially_failed`
- `completed`
- `failed`
- `cancelling`
- `cancelled`

### Job Item States

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`
- `skipped`

### Transition Rules

Job items:

- `queued -> running`
- `running -> completed | failed | cancelled`
- `queued -> skipped`

Jobs:

- Start as `queued`
- Move to `running` when at least one item starts
- Move to `completed` when all items are `completed` or `skipped`
- Move to `partially_failed` when some items succeed and some fail
- Move to `failed` when all executable items fail or startup fails
- Move to `cancelling` when the user requests cancel
- Move to `cancelled` after active items are stopped and no further dispatch is allowed

## Scheduler Design

Only one scheduler instance may dispatch tasks.

### Responsibilities

- Poll for dispatchable items
- Enforce concurrency limits
- Start worker subprocesses
- Track worker exit and heartbeats
- Stop dispatch for cancelling jobs
- Recover orphaned running items after restart

### Concurrency Model

The design supports both required levels of concurrency:

- Multiple jobs in parallel
- Playlist-internal parallel downloads

Use dual throttling:

- **Global active item limit:** `6`
- **Per-job active item limit:** default `4` for playlists
- **Single video jobs:** fixed effective limit `1`

These are aggressive defaults, matching the user's stated preference for throughput on a strong server, while still imposing a hard global ceiling.

### Fair Dispatch

Avoid allowing one large playlist to occupy every execution slot.

Recommended policy:

- Primary order: `priority DESC`, then `created_at ASC`
- Fairness pass: give each eligible job one slot before filling extra capacity
- Second pass: continue assigning until per-job and global limits are reached

This keeps new single-video jobs responsive even when large playlists are active.

## Worker Design

Each worker subprocess receives:

- `job_id`
- `job_item_id`

The worker then:

1. Loads job and item records from SQLite
2. Loads workspace metadata (`url_info.json`, existing `status.json`)
3. Executes the existing per-video download flow
4. Periodically writes progress and heartbeat updates
5. Writes structured events and raw logs
6. Marks the item as completed, failed, cancelled, or skipped

Workers must not depend on:

- `st.session_state`
- Streamlit placeholders
- active browser connections

## Progress and UI Consistency

### Single Source of Truth

All runtime progress displayed in the UI must come from:

- `jobs`
- `job_items`

Not from:

- active Streamlit in-memory counters
- destination directory scans during execution
- ad hoc playlist counters inside the current page run

### Runtime Progress Fields

Each running item should update:

- `progress_percent`
- `downloaded_bytes`
- `total_bytes`
- `speed_bps`
- `eta_seconds`
- `status_message`
- `last_heartbeat_at`

Suggested update cadence:

- once every `0.5s` to `1s`, or
- on meaningful value change

This keeps UI responsive without excessive SQLite writes.

### Playlist Aggregation

Playlist progress must be derived exclusively from child items:

- `total_items`
- `completed_items`
- `running_items`
- `queued_items`
- `failed_items`
- `skipped_items`

The old UI pattern of showing one pre-download count and a separate live loop counter must be removed during active job execution.

## Logging Strategy

Use two layers:

1. **SQLite summaries**
   - recent job events
   - status transitions
   - user-visible warnings and errors

2. **Raw log files**
   - `tmp/jobs/<job_id>/job.log`
   - `tmp/jobs/<job_id>/items/<job_item_id>.log`

This avoids bloating SQLite while still supporting live UI inspection and debugging.

## Cancellation and Retry

### Cancellation

Support both:

- cancel entire job
- cancel individual item

Implementation:

- UI sets `cancel_requested`
- Scheduler stops giving new slots to that job
- Scheduler sends `SIGTERM` to active worker PIDs
- If graceful stop times out, scheduler sends `SIGKILL`
- Worker catches termination, stops child tools, and marks item `cancelled`

### Retry

Keep retry logic conservative:

- default automatic retry count per item: `1`
- auto-retry only transient failures
- do not auto-retry deterministic failures such as permission, path, or invalid config errors

UI should allow:

- retry failed job
- retry failed items only

## Restart Recovery

### Browser Disconnect

No special recovery is needed because the browser is no longer the executor. UI simply reloads current state from SQLite.

### Service Restart

On app startup, scheduler should:

1. Find `job_items` marked `running`
2. Check whether their `worker_pid` still exists
3. If not, reclassify them for recovery

Recommended recovery rule:

- if a running item has no live worker, move it back to `queued`
- increment recovery-aware retry count
- log a structured recovery event
- if retry budget is exhausted, mark it `failed`

This approach is simpler and safer than trying to reattach to unknown child processes.

## Reuse of Existing Code

The download core should be reused as much as possible.

Keep and adapt:

- `app/workspace.py`
- `app/status_utils.py`
- `app/playlist_utils.py`
- `app/playlist_sync.py`
- yt-dlp command construction
- ffmpeg processing flow
- subtitle handling
- SponsorBlock logic
- cookie resolution logic
- destination naming and file organization

The main refactor is not "rewrite download logic". The main refactor is "move execution out of Streamlit request flow and make it task-driven".

## New Modules

Recommended new modules:

- `app/job_models.py`
  - enums and helper data structures

- `app/job_store.py`
  - SQLite schema and transactional persistence

- `app/job_scheduler.py`
  - dispatch loop and concurrency control

- `app/job_worker.py`
  - subprocess entrypoint for one executable item

- `app/job_logging.py`
  - structured events and log file helpers

- `app/job_runtime.py`
  - singleton scheduler startup and recovery behavior

## Required Refactor in `app/main.py`

Current behavior:

- user clicks download
- Streamlit immediately performs the download in the page execution flow

Target behavior:

- user clicks download
- UI builds a frozen job config snapshot
- UI persists a job and items
- UI returns immediately
- scheduler starts execution independently

This requires extracting the per-video execution path into backend-callable code with no direct `st.*` dependencies.

## UI Changes

Keep the current form, but change its semantics from "execute now" to "enqueue job".

Add a task center view with:

- active jobs
- queued jobs
- completed jobs
- failed jobs
- per-job expanders showing child items
- structured logs
- cancel action
- retry action

During active playlist execution, progress should be shown from job/item state only.

## Implementation Phases

### Phase 1: Background Job Foundation

- Add SQLite task store
- Add job and item creation flow
- Add detached single-worker execution
- Make page closing safe
- Show persisted job progress after reload

This is the minimum milestone that changes the execution model correctly.

### Phase 2: Multi-Job Concurrency

- Add scheduler
- Add global concurrency cap
- Run multiple jobs in parallel

### Phase 3: Playlist Internal Concurrency

- Allow multiple child items within one playlist job
- Enforce per-job cap
- Aggregate progress from child items

### Phase 4: Operational Hardening

- robust cancel behavior
- restart recovery
- retry controls
- log browser
- richer history filters
- remove remaining UI state-splitting paths

## Testing Strategy

### Unit Tests

- SQLite schema and state transitions
- scheduler dispatch selection
- fairness and concurrency enforcement
- job aggregation logic
- cancellation and retry decisions
- recovery behavior for orphaned running items

### Integration Tests

- enqueue video job and run to completion
- enqueue playlist job and verify item fan-out
- run multiple jobs in parallel
- run playlist with internal parallelism
- close and reopen UI while workers run
- restart service and verify recovery

### Regression Tests

- existing workspace reuse
- existing completed download detection
- playlist sync behavior
- cookies resolution selection
- file-system permission error handling

## Risks and Mitigations

### Risk: `st.session_state` leakage into worker path

Mitigation:

- explicitly extract pure backend execution functions
- forbid worker code from importing Streamlit UI primitives

### Risk: Too many SQLite writes during progress updates

Mitigation:

- throttle progress writes
- keep full logs on disk instead of in DB

### Risk: One large playlist monopolizes execution slots

Mitigation:

- fairness-aware dispatch loop
- global and per-job caps

### Risk: Recovery becomes complex and fragile

Mitigation:

- use a simple requeue model for orphaned running items
- rely on existing workspace reuse instead of complex process reattachment

## Recommended Defaults

- global active item limit: `6`
- default playlist internal parallelism: `4`
- automatic retry count per item: `1`

These defaults should remain configurable, but the initial product behavior should prefer throughput while maintaining explicit global limits.

## Summary

The correct simplification is not to keep downloads inside Streamlit and add more session logic. The correct simplification is to move execution to a built-in background job system while keeping deployment single-container and reusing the existing media-processing code.

This design gives HomeTube:

- detached downloads
- persistent progress
- multiple jobs in parallel
- playlist-internal concurrency
- restart-aware recovery
- one consistent progress model

without adding Redis or separate infrastructure.
