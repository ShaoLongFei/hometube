#!/usr/bin/env python3
"""Resume-safe media library H.264/AAC normalizer."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Condition, Lock
from typing import Iterable

DEFAULT_ROOT = Path("/mnt/nas/jellyfin/音乐视频")
DEFAULT_STATE = Path("/opt/hometube/data/tmp/reencode/music_videos_h264_aac.sqlite3")
DEFAULT_LOG = Path("/opt/hometube/data/tmp/reencode/music_videos_h264_aac.log")
VIDEO_EXTENSIONS = {
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ts",
    ".webm",
}

LOG_LOCK = Lock()


@dataclass(frozen=True)
class ProbeSummary:
    path: Path
    container: str
    streams: list[dict]
    primary_video: dict | None
    primary_video_position: int | None
    audio_codecs: list[str]
    duration_seconds: float | None


@dataclass
class RunStats:
    planned: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0


class StateDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self._conn.execute("pragma journal_mode=WAL")
        self._conn.execute("pragma busy_timeout=30000")
        self._conn.execute("""
            create table if not exists files (
                path text primary key,
                size integer not null default 0,
                mtime_ns integer not null default 0,
                status text not null,
                container text,
                video_codec text,
                audio_codecs text,
                attempts integer not null default 0,
                progress_percent real not null default 0,
                speed text,
                phase text,
                duration_seconds real,
                output_path text,
                error text,
                started_at text,
                finished_at text,
                updated_at text not null
            )
            """)
        self._conn.execute("""
            create table if not exists events (
                id integer primary key autoincrement,
                path text,
                level text not null,
                message text not null,
                created_at text not null
            )
            """)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def mark_scanned(self, path: Path, size: int, mtime_ns: int) -> None:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                insert into files(path, size, mtime_ns, status, updated_at)
                values(?, ?, ?, 'scanned', ?)
                on conflict(path) do update set
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    updated_at=excluded.updated_at
                """,
                (str(path), size, mtime_ns, now),
            )
            self._conn.commit()

    def mark_status(
        self,
        path: Path,
        status: str,
        *,
        summary: ProbeSummary | None = None,
        phase: str | None = None,
        output_path: Path | None = None,
        error: str | None = None,
        progress_percent: float | None = None,
        speed: str | None = None,
        increment_attempts: bool = False,
        finished: bool = False,
    ) -> None:
        now = utc_now()
        video_codec = (
            normalized_codec(summary.primary_video.get("codec_name"))
            if summary and summary.primary_video
            else None
        )
        audio_codecs = ",".join(summary.audio_codecs) if summary is not None else None
        with self._lock:
            self._conn.execute(
                """
                insert into files(
                    path, status, container, video_codec, audio_codecs,
                    attempts, progress_percent, speed, phase, duration_seconds,
                    output_path, error, started_at, finished_at, updated_at
                )
                values(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                on conflict(path) do update set
                    status=excluded.status,
                    container=coalesce(excluded.container, files.container),
                    video_codec=coalesce(excluded.video_codec, files.video_codec),
                    audio_codecs=coalesce(excluded.audio_codecs, files.audio_codecs),
                    attempts=files.attempts + ?,
                    progress_percent=coalesce(excluded.progress_percent, files.progress_percent),
                    speed=coalesce(excluded.speed, files.speed),
                    phase=coalesce(excluded.phase, files.phase),
                    duration_seconds=coalesce(excluded.duration_seconds, files.duration_seconds),
                    output_path=coalesce(excluded.output_path, files.output_path),
                    error=excluded.error,
                    started_at=coalesce(files.started_at, excluded.started_at),
                    finished_at=excluded.finished_at,
                    updated_at=excluded.updated_at
                """,
                (
                    str(path),
                    status,
                    summary.container if summary else None,
                    video_codec,
                    audio_codecs,
                    1 if increment_attempts else 0,
                    progress_percent if progress_percent is not None else 0,
                    speed,
                    phase,
                    summary.duration_seconds if summary else None,
                    str(output_path) if output_path else None,
                    error,
                    now,
                    now if finished else None,
                    now,
                    1 if increment_attempts else 0,
                ),
            )
            self._conn.commit()

    def progress(
        self,
        path: Path,
        *,
        percent: float,
        speed: str,
        phase: str,
        output_path: Path,
    ) -> None:
        now = utc_now()
        with self._lock:
            self._conn.execute(
                """
                update files set
                    status='running',
                    progress_percent=?,
                    speed=?,
                    phase=?,
                    output_path=?,
                    updated_at=?
                where path=?
                """,
                (percent, speed, phase, str(output_path), now, str(path)),
            )
            self._conn.commit()

    def event(self, path: Path | None, level: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "insert into events(path, level, message, created_at) values(?, ?, ?, ?)",
                (str(path) if path else None, level, message, utc_now()),
            )
            self._conn.commit()


class StorageGate:
    def __init__(
        self,
        min_free_bytes: int,
        reserve_multiplier: float,
        min_reservation_bytes: int,
    ) -> None:
        self.min_free_bytes = min_free_bytes
        self.reserve_multiplier = reserve_multiplier
        self.min_reservation_bytes = min_reservation_bytes
        self._reserved = 0
        self._condition = Condition()

    def acquire(self, source: Path, label: str) -> int:
        source_size = max(source.stat().st_size, 1)
        required = max(
            int(source_size * self.reserve_multiplier),
            self.min_reservation_bytes,
        )
        last_log = 0.0
        with self._condition:
            while True:
                free = shutil.disk_usage(source.parent).free
                available_after_reservations = free - self._reserved
                if available_after_reservations - required >= self.min_free_bytes:
                    self._reserved += required
                    return required
                now = time.monotonic()
                if now - last_log > 60:
                    log(
                        "Waiting for storage headroom "
                        f"{label}: free={format_bytes(free)} "
                        f"reserved={format_bytes(self._reserved)} "
                        f"required={format_bytes(required)} "
                        f"min_free={format_bytes(self.min_free_bytes)}"
                    )
                    last_log = now
                self._condition.wait(timeout=15)

    def release(self, reservation: int) -> None:
        with self._condition:
            self._reserved = max(0, self._reserved - reservation)
            self._condition.notify_all()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str, *, log_file: Path | None = None) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    with LOG_LOCK:
        print(line, flush=True)
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TiB"


def ensure_binary(name: str) -> None:
    if shutil.which(name):
        return
    raise RuntimeError(f"Required binary not found in PATH: {name}")


def normalized_codec(codec: object) -> str:
    return str(codec or "").strip().lower().replace("_", "-")


def is_aac_compatible_codec(codec: object) -> bool:
    normalized = normalized_codec(codec)
    return (
        normalized == "aac"
        or normalized.startswith("aac-")
        or normalized.startswith("mp4a")
    )


def is_attached_picture(stream: dict) -> bool:
    disposition = stream.get("disposition") or {}
    return bool(disposition.get("attached_pic"))


def is_cover_like_video(stream: dict) -> bool:
    tags = {
        str(k).lower(): str(v).lower() for k, v in (stream.get("tags") or {}).items()
    }
    filename = tags.get("filename", "")
    mimetype = tags.get("mimetype", "")
    return (
        is_attached_picture(stream)
        or filename.startswith("cover.")
        or mimetype.startswith("image/")
    )


def select_primary_video_stream(streams: Iterable[dict]) -> dict | None:
    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    for stream in video_streams:
        if not is_cover_like_video(stream):
            return stream
    return video_streams[0] if video_streams else None


def video_position(streams: list[dict], selected: dict | None) -> int | None:
    if selected is None:
        return None
    position = 0
    selected_index = selected.get("index")
    for stream in streams:
        if stream.get("codec_type") != "video":
            continue
        if stream.get("index") == selected_index:
            return position
        position += 1
    return None


def discover_video_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if ".hometube-reencode." in path.name:
            continue
        files.append(path)
    return sorted(files)


def run_json_command(command: list[str]) -> dict:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout or "{}")


def probe_media(path: Path, ffprobe_binary: str) -> ProbeSummary:
    payload = run_json_command(
        [
            ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    streams = payload.get("streams") or []
    format_data = payload.get("format") or {}
    primary = select_primary_video_stream(streams)
    audio_codecs = [
        normalized_codec(stream.get("codec_name"))
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]
    duration_seconds = parse_duration(format_data.get("duration"))
    return ProbeSummary(
        path=path,
        container=str(format_data.get("format_name") or ""),
        streams=streams,
        primary_video=primary,
        primary_video_position=video_position(streams, primary),
        audio_codecs=audio_codecs,
        duration_seconds=duration_seconds,
    )


def parse_duration(value: object) -> float | None:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def is_compliant(summary: ProbeSummary) -> bool:
    if summary.primary_video is None:
        return False
    if normalized_codec(summary.primary_video.get("codec_name")) != "h264":
        return False
    if not summary.audio_codecs:
        return False
    return all(is_aac_compatible_codec(codec) for codec in summary.audio_codecs)


def plan_temp_output(source: Path) -> Path:
    source_hash = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:16]
    suffix = uuid.uuid4().hex[:10]
    return source.with_name(
        f".hometube-reencode-{source_hash}-{suffix}.tmp{source.suffix}"
    )


def cleanup_library_temp_outputs(root: Path) -> int:
    removed = 0
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        if ".hometube-reencode" not in candidate.name:
            continue
        candidate.unlink()
        removed += 1
    return removed


def cleanup_stale_outputs(source: Path) -> None:
    source_hash = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:16]
    patterns = [
        f".hometube-reencode-{source_hash}-*.tmp{source.suffix}",
        f".{source.name}.hometube-reencode.*.tmp{source.suffix}",
    ]
    for pattern in patterns:
        for candidate in source.parent.glob(pattern):
            if candidate.is_file():
                candidate.unlink()
    for candidate in source.parent.iterdir():
        if ".hometube-reencode." not in candidate.name:
            continue
        if source.name not in candidate.name:
            continue
        if candidate.is_file():
            candidate.unlink()


def append_container_options(command: list[str], output_path: Path) -> None:
    if output_path.suffix.lower() in {".m4v", ".mov", ".mp4"}:
        command.extend(["-movflags", "+faststart"])


def add_video_encoder_options(
    command: list[str],
    *,
    output_video_position: int,
    preset: str,
    crf: int,
    ffmpeg_threads: int,
) -> None:
    command.extend(
        [
            f"-c:v:{output_video_position}",
            "libx264",
            f"-preset:v:{output_video_position}",
            preset,
            f"-crf:v:{output_video_position}",
            str(crf),
        ]
    )
    if ffmpeg_threads > 0:
        command.extend([f"-threads:v:{output_video_position}", str(ffmpeg_threads)])


def build_preserve_all_command(
    source: Path,
    output_path: Path,
    summary: ProbeSummary,
    *,
    ffmpeg_binary: str,
    preset: str,
    crf: int,
    ffmpeg_threads: int,
) -> list[str]:
    output_video_position = summary.primary_video_position
    if output_video_position is None:
        output_video_position = 0
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        str(source),
        "-map",
        "0",
        "-c",
        "copy",
    ]
    add_video_encoder_options(
        command,
        output_video_position=output_video_position,
        preset=preset,
        crf=crf,
        ffmpeg_threads=ffmpeg_threads,
    )
    command.extend(["-c:a", "aac", "-profile:a", "aac_low"])
    append_container_options(command, output_path)
    command.append(str(output_path))
    return command


def build_selected_stream_command(
    source: Path,
    output_path: Path,
    summary: ProbeSummary,
    *,
    ffmpeg_binary: str,
    preset: str,
    crf: int,
    ffmpeg_threads: int,
    include_subtitles: bool,
) -> list[str]:
    if summary.primary_video is None:
        raise RuntimeError("No primary video stream found")
    command = [
        ffmpeg_binary,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",
        "-progress",
        "pipe:1",
        "-i",
        str(source),
        "-map",
        f"0:{summary.primary_video.get('index')}",
        "-map",
        "0:a?",
    ]
    if include_subtitles:
        command.extend(["-map", "0:s?"])
    add_video_encoder_options(
        command,
        output_video_position=0,
        preset=preset,
        crf=crf,
        ffmpeg_threads=ffmpeg_threads,
    )
    command.extend(["-c:a", "aac", "-profile:a", "aac_low"])
    if include_subtitles:
        command.extend(["-c:s", "copy"])
    append_container_options(command, output_path)
    command.append(str(output_path))
    return command


def build_attempt_commands(
    source: Path,
    output_path: Path,
    summary: ProbeSummary,
    *,
    ffmpeg_binary: str,
    preset: str,
    crf: int,
    ffmpeg_threads: int,
) -> list[tuple[str, list[str]]]:
    return [
        (
            "preserve-all",
            build_preserve_all_command(
                source,
                output_path,
                summary,
                ffmpeg_binary=ffmpeg_binary,
                preset=preset,
                crf=crf,
                ffmpeg_threads=ffmpeg_threads,
            ),
        ),
        (
            "media-subtitles",
            build_selected_stream_command(
                source,
                output_path,
                summary,
                ffmpeg_binary=ffmpeg_binary,
                preset=preset,
                crf=crf,
                ffmpeg_threads=ffmpeg_threads,
                include_subtitles=True,
            ),
        ),
        (
            "media-only",
            build_selected_stream_command(
                source,
                output_path,
                summary,
                ffmpeg_binary=ffmpeg_binary,
                preset=preset,
                crf=crf,
                ffmpeg_threads=ffmpeg_threads,
                include_subtitles=False,
            ),
        ),
    ]


def remove_partial_output(output_path: Path, source: Path) -> None:
    if output_path != source and output_path.exists():
        output_path.unlink()


def run_ffmpeg_with_progress(
    command: list[str],
    *,
    duration_seconds: float | None,
    state: StateDB,
    source: Path,
    output_path: Path,
    phase: str,
    log_file: Path | None,
) -> int:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    last_out_time_us = 0
    last_update = 0.0
    speed = "?"
    tail: deque[str] = deque(maxlen=12)

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        tail.append(line)
        if "=" not in line:
            log(f"{source.name} {phase}: {line}", log_file=log_file)
            continue
        key, value = line.split("=", 1)
        if key in {"out_time_ms", "out_time_us"}:
            try:
                last_out_time_us = int(value)
            except ValueError:
                last_out_time_us = 0
        elif key == "speed":
            speed = value
        elif key == "progress":
            now = time.monotonic()
            if now - last_update >= 5 or value == "end":
                percent = 0.0
                if duration_seconds and last_out_time_us:
                    seconds_done = last_out_time_us / 1_000_000
                    percent = min(100.0, seconds_done / duration_seconds * 100.0)
                state.progress(
                    source,
                    percent=percent,
                    speed=speed,
                    phase=phase,
                    output_path=output_path,
                )
                log(
                    f"{source.name} {phase}: progress={percent:5.1f}% speed={speed}",
                    log_file=log_file,
                )
                last_update = now

    return_code = process.wait()
    if return_code != 0:
        log(
            f"{source.name} {phase}: ffmpeg exited {return_code}; "
            f"tail={' | '.join(tail)}",
            log_file=log_file,
        )
    return return_code


def verify_output(path: Path, ffprobe_binary: str) -> ProbeSummary:
    summary = probe_media(path, ffprobe_binary)
    if not is_compliant(summary):
        video = (
            normalized_codec(summary.primary_video.get("codec_name"))
            if summary.primary_video
            else "none"
        )
        raise RuntimeError(
            "Output validation failed: "
            f"video={video} audio={','.join(summary.audio_codecs) or 'none'}"
        )
    return summary


def replace_original(source: Path, output_path: Path) -> None:
    output_path.replace(source)


def process_file(
    *,
    source: Path,
    index: int,
    total: int,
    state: StateDB,
    storage_gate: StorageGate,
    args: argparse.Namespace,
) -> str:
    label = f"[{index}/{total}]"
    log(f"{label} Inspecting {source}", log_file=args.log_file)
    cleanup_stale_outputs(source)

    try:
        summary = probe_media(source, args.ffprobe)
        state.mark_status(source, "inspected", summary=summary, phase="inspect")
    except Exception as exc:
        state.mark_status(
            source,
            "failed",
            error=f"ffprobe failed: {exc}",
            finished=True,
        )
        log(f"{label} Failed probe: {source} :: {exc}", log_file=args.log_file)
        return "failed"

    if summary.primary_video is None:
        state.mark_status(source, "skipped_no_video", summary=summary, finished=True)
        log(f"{label} Skip: no video stream", log_file=args.log_file)
        return "skipped"

    if is_compliant(summary):
        state.mark_status(
            source,
            "skipped_compliant",
            summary=summary,
            progress_percent=100.0,
            finished=True,
        )
        log(f"{label} Skip: already H.264/AAC-compatible", log_file=args.log_file)
        return "skipped"

    if not summary.audio_codecs:
        state.mark_status(
            source,
            "failed",
            summary=summary,
            error="No audio stream; cannot produce AAC audio",
            finished=True,
        )
        log(f"{label} Failed: no audio stream", log_file=args.log_file)
        return "failed"

    video_codec = normalized_codec(summary.primary_video.get("codec_name"))
    log(
        f"{label} Needs transcode: video={video_codec} "
        f"audio={','.join(summary.audio_codecs)} size={format_bytes(source.stat().st_size)}",
        log_file=args.log_file,
    )

    if args.dry_run:
        state.mark_status(source, "planned", summary=summary, finished=True)
        return "skipped"

    reservation = storage_gate.acquire(source, label)
    output_path = plan_temp_output(source)
    try:
        state.mark_status(
            source,
            "running",
            summary=summary,
            phase="queued",
            output_path=output_path,
            increment_attempts=True,
        )
        commands = build_attempt_commands(
            source,
            output_path,
            summary,
            ffmpeg_binary=args.ffmpeg,
            preset=args.preset,
            crf=args.crf,
            ffmpeg_threads=args.ffmpeg_threads,
        )
        last_error = "Codec normalization failed"
        for attempt_name, command in commands:
            remove_partial_output(output_path, source)
            log(
                f"{label} Attempt {attempt_name}: {source.name}", log_file=args.log_file
            )
            return_code = run_ffmpeg_with_progress(
                command,
                duration_seconds=summary.duration_seconds,
                state=state,
                source=source,
                output_path=output_path,
                phase=attempt_name,
                log_file=args.log_file,
            )
            if return_code != 0 or not output_path.exists():
                last_error = f"{attempt_name} ffmpeg failed with code {return_code}"
                continue
            try:
                output_summary = verify_output(output_path, args.ffprobe)
            except Exception as exc:
                last_error = f"{attempt_name} validation failed: {exc}"
                log(f"{label} {last_error}", log_file=args.log_file)
                continue
            replace_original(source, output_path)
            state.mark_status(
                source,
                "completed",
                summary=output_summary,
                phase=attempt_name,
                progress_percent=100.0,
                output_path=source,
                finished=True,
            )
            log(
                f"{label} Success: replaced original via {attempt_name}: {source}",
                log_file=args.log_file,
            )
            return "processed"

        raise RuntimeError(last_error)
    except Exception as exc:
        remove_partial_output(output_path, source)
        state.mark_status(
            source,
            "failed",
            summary=summary,
            output_path=output_path,
            error=str(exc),
            finished=True,
        )
        log(f"{label} Failed: {source} :: {exc}", log_file=args.log_file)
        return "failed"
    finally:
        storage_gate.release(reservation)


def normalize_worker_count(requested: int, total: int) -> int:
    if total <= 0:
        return 1
    return max(1, min(requested, total))


def print_status(state_path: Path) -> int:
    if not state_path.exists():
        print(
            json.dumps({"state": str(state_path), "exists": False}, ensure_ascii=False)
        )
        return 0
    conn = sqlite3.connect(str(state_path))
    conn.row_factory = sqlite3.Row
    summary = [
        dict(row)
        for row in conn.execute(
            "select status, count(*) as count from files group by status order by status"
        )
    ]
    active = [dict(row) for row in conn.execute("""
            select path, status, progress_percent, speed, phase, updated_at
            from files
            where status='running'
            order by updated_at desc
            """)]
    recent_failures = [dict(row) for row in conn.execute("""
            select path, error, updated_at
            from files
            where status='failed'
            order by updated_at desc
            limit 20
            """)]
    print(
        json.dumps(
            {
                "state": str(state_path),
                "exists": True,
                "summary": summary,
                "active": active,
                "recent_failures": recent_failures,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Re-encode non-H.264/AAC videos in a media library in place."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--preset", default="slow")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--ffmpeg-threads", type=int, default=4)
    parser.add_argument("--min-free-gib", type=float, default=1024.0)
    parser.add_argument("--min-temp-gib", type=float, default=1.0)
    parser.add_argument("--reserve-multiplier", type=float, default=6.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.status:
        return print_status(args.state)

    args.root = args.root.expanduser()
    args.state = args.state.expanduser()
    args.log_file = args.log_file.expanduser()

    ensure_binary(args.ffprobe)
    ensure_binary(args.ffmpeg)

    if not args.root.exists():
        log(f"Root directory does not exist: {args.root}", log_file=args.log_file)
        return 1

    state = StateDB(args.state)
    storage_gate = StorageGate(
        min_free_bytes=int(args.min_free_gib * 1024**3),
        reserve_multiplier=args.reserve_multiplier,
        min_reservation_bytes=int(args.min_temp_gib * 1024**3),
    )
    try:
        files = discover_video_files(args.root)
        if not args.dry_run:
            removed_temp_count = cleanup_library_temp_outputs(args.root)
            if removed_temp_count:
                log(
                    f"Removed {removed_temp_count} stale reencode temp files under {args.root}",
                    log_file=args.log_file,
                )
        for path in files:
            stat = path.stat()
            state.mark_scanned(path, stat.st_size, stat.st_mtime_ns)

        worker_count = normalize_worker_count(args.jobs, len(files))
        log(
            f"Discovered {len(files)} video files under {args.root}; "
            f"jobs={worker_count} ffmpeg_threads={args.ffmpeg_threads} "
            f"preset={args.preset} crf={args.crf} "
            f"min_free={args.min_free_gib:.1f}GiB reserve_multiplier={args.reserve_multiplier}",
            log_file=args.log_file,
        )

        stats = RunStats(planned=len(files))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    process_file,
                    source=source,
                    index=index,
                    total=len(files),
                    state=state,
                    storage_gate=storage_gate,
                    args=args,
                ): source
                for index, source in enumerate(files, start=1)
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    stats.failed += 1
                    state.mark_status(
                        source,
                        "failed",
                        error=f"Unhandled worker error: {exc}",
                        finished=True,
                    )
                    log(
                        f"Unhandled worker error: {source} :: {exc}",
                        log_file=args.log_file,
                    )
                    continue
                if result == "processed":
                    stats.processed += 1
                elif result == "failed":
                    stats.failed += 1
                else:
                    stats.skipped += 1

        log(
            f"Summary: planned={stats.planned} processed={stats.processed} "
            f"skipped={stats.skipped} failed={stats.failed}",
            log_file=args.log_file,
        )
        return 0
    finally:
        state.close()


if __name__ == "__main__":
    sys.exit(main())
