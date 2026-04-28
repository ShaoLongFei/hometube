# HomeTube Video Codec Normalization Design

**Date:** 2026-04-28

**Status:** Approved design

## Goal

Add a final delivery normalization step so that downloaded videos are checked with `ffprobe` and, when needed, normalized toward:

- container: `mp4`
- video codec: `h264`
- audio codec: `aac` / `aac-lc`

This must work for both:

- single-video downloads
- playlist downloads
- playlist-wide shared clipping, where the same time range applies to every item

## User Decisions

The following product decisions are fixed:

1. Only normalize when the final delivery file does not already satisfy the target codecs.
2. Quality is more important than speed or CPU cost.
3. Prefer `mp4` as the final delivery container.
4. Keep only one final delivered file on disk.
5. If normalization fails, still deliver the original file and clearly report a warning.

## Current Problem

HomeTube currently prefers preserving downloaded streams and often keeps:

- AV1 / VP9 video
- Opus or other non-AAC audio
- MKV outputs for modern codec compatibility

That is good for download efficiency and fidelity, but it does not guarantee the final file is widely compatible across playback environments.

The current detached worker flow also still treats post-processing primarily as:

- clip cutting
- subtitle embedding
- metadata customization

There is no final codec compliance check before delivery.

## Design Principles

- Normalize only at the final delivery boundary
- Do not re-encode files that already satisfy the target
- Reuse the detached worker post-processing chain
- Keep failure semantics simple and explicit
- Prefer predictable user-facing outcomes over internal cleverness

## Target Output Contract

The final desired delivery format is:

- **Container:** `mp4`
- **Video:** `h264`
- **Audio:** `aac`

`AAC-LC` is the preferred audio profile when re-encoding.

For files that already satisfy this contract, no codec normalization step should run.

## Scope

### In Scope

- Check the final candidate file with `ffprobe`
- Detect whether codec/container normalization is required
- Re-encode to `mp4 + h264 + aac`
- Apply this after any cut/clip stage
- Support single videos and playlist items
- Persist warning state when normalization fails but fallback delivery succeeds

### Out of Scope

- User-configurable codec presets
- Preserving original downloaded cache tracks
- Multiple retained output variants
- Per-playlist-item custom time ranges

## High-Level Pipeline

The detached worker pipeline becomes:

1. Download or reuse a workspace file
2. Apply optional clip/cut processing
3. Apply subtitle processing and metadata steps as needed
4. Inspect the resulting candidate with `ffprobe`
5. If already `mp4 + h264 + aac`, deliver it directly
6. Otherwise normalize to `mp4 + h264 + aac`
7. If normalization succeeds, deliver the normalized file and delete obsolete intermediates
8. If normalization fails, deliver the pre-normalization candidate and mark the task with a warning

This keeps normalization as a final compliance stage rather than mixing it into download selection logic.

## Why Final-Stage Normalization

This is the recommended approach because:

- yt-dlp format selection should continue optimizing acquisition reliability
- clip/cut logic should operate on the best available downloaded source
- normalization should reflect the actual final delivered file, not an earlier intermediate

If normalization happened earlier, clip/cut and subtitle steps could still produce outputs that drift away from the desired final contract.

## Detection Model

Introduce a small backend inspection helper built around `ffprobe`.

It should extract at minimum:

- container / format name
- first video stream codec
- all audio stream codecs
- whether a video stream exists
- whether any audio stream exists

The normalization decision is:

- no normalization needed only if:
  - container is compatible with final `mp4`
  - video codec is `h264`
  - all retained audio streams are `aac`

Otherwise normalization is required.

## Normalization Strategy

When normalization is needed:

- output path becomes the final `*.mp4`
- video is re-encoded using `libx264`
- audio is re-encoded using `aac`
- audio profile targets AAC-LC
- subtitles for MP4 continue using `mov_text` when embedded

Suggested defaults:

- `-c:v libx264`
- `-preset slower`
- `-crf 14` or nearby quality-first default
- `-c:a aac`
- `-profile:a aac_low`

The exact command can be tuned during implementation, but the design intent is clear: quality-first H.264/AAC normalization.

## Multi-Audio Behavior

If the final candidate contains multiple audio streams:

- preserve them
- normalize each retained audio stream to AAC

This avoids surprising data loss while still satisfying the compatibility goal.

## File Retention Policy

The user explicitly prefers a single final file only.

Therefore:

- do not keep the original downloaded cache track after successful delivery
- do not keep a second normalized copy alongside the original
- after delivery, only the final delivered file should remain as the stable output artifact

Temporary workspace intermediates may exist during processing, but they should not remain as durable final artifacts.

## Failure Policy

If normalization fails:

- do **not** fail the whole task if a valid pre-normalization output exists
- deliver the original candidate file
- record a warning that codec normalization failed
- surface that warning in logs and UI

This means delivery semantics become:

- `completed`: delivered and satisfies normalization target
- `completed_with_warning`: delivered, but codec normalization failed or final output does not satisfy target
- `failed`: no deliverable file exists

If the existing store keeps only top-level `completed` states, the warning can first live in item/job log metadata plus a dedicated warning field, then optionally evolve into a richer status later.

## UI / Status Behavior

The background jobs panel should eventually show codec-normalization outcomes in human terms, for example:

- `Normalized to MP4 / H.264 / AAC`
- `Delivered original file; normalization failed`

For this phase, the minimum acceptable surface is:

- structured warning log entry
- visible latest warning in the background job panel

## Playlist + Shared Clip Semantics

Playlist clipping remains:

- one shared `start_sec` / `end_sec`
- applied independently to each item

Codec normalization happens after each item’s cut result is produced. There is no playlist-level combined media operation.

## Required Data Model Additions

Persist enough job/item metadata to explain delivery state:

- whether normalization was required
- whether normalization succeeded
- final delivered container
- final delivered video codec
- final delivered audio codec summary
- warning message if fallback delivery occurred

These can begin as additions inside item runtime metadata or structured logs if a schema expansion is not yet necessary.

## Backend Modules Impacted

Primary code areas expected to change:

- `app/video_postprocess_backend.py`
- `app/job_video_handler.py`
- `app/job_progress.py`
- `app/job_store.py`
- `app/main.py`

Likely new helper module:

- `app/video_codec_inspection.py`
  - `ffprobe` helpers
  - normalization decision logic
  - normalized codec summary

Possibly another helper:

- `app/video_codec_normalization.py`
  - ffmpeg command builder for quality-first normalization

## Risks

### 1. Subtitle / MP4 compatibility

`mp4` is the chosen final container, but embedded subtitle behavior is stricter than `mkv`.

Mitigation:

- keep using `mov_text` for embedded MP4 subtitles
- if subtitle embedding fails during normalization fallback, still deliver with warning

### 2. Re-encoding cost

Quality-first H.264 normalization is expensive.

Accepted tradeoff:

- the user explicitly prefers quality over speed/CPU

### 3. Warning-state semantics

Current job status model is mostly success/failure oriented.

Mitigation:

- start with explicit warning logs and final item warning fields
- only add a new visible warning status if needed by UI

## Testing Strategy

Add tests for:

- `ffprobe` parsing for compliant vs non-compliant files
- normalization decision helper
- no-op path when file is already `mp4 + h264 + aac`
- normalization path when codec mismatch exists
- fallback delivery when normalization fails
- playlist item behavior with shared clip config
- final single-file retention behavior

## Recommended Rollout

1. Add codec inspection helpers and tests
2. Add normalization decision layer and tests
3. Integrate normalization into detached post-processing
4. Add fallback warning semantics
5. Update background jobs UI/log messaging

## Acceptance Criteria

This design is successful when:

- single-video background downloads can deliver `mp4 + h264 + aac`
- playlist item background downloads can do the same
- already compliant outputs skip unnecessary re-encoding
- normalization failure still yields a delivered file plus warning
- only one final delivered file remains as the durable output artifact
