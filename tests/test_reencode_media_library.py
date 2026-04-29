import sqlite3
from pathlib import Path

from scripts import reencode_media_library as reencode


def test_reencode_defaults_do_not_embed_machine_specific_paths():
    expected_state_root = Path.home() / ".local" / "state" / "hometube"

    assert reencode.DEFAULT_ROOT is None
    assert reencode.DEFAULT_STATE.is_relative_to(expected_state_root)
    assert reencode.DEFAULT_LOG.is_relative_to(expected_state_root)


def test_estimate_progress_uses_output_size_when_ffmpeg_time_is_missing(tmp_path):
    source = tmp_path / "source.mkv"
    output = tmp_path / ".hometube-reencode.tmp.mkv"
    source.write_bytes(b"x" * 1000)
    output.write_bytes(b"y" * 250)

    percent, bytes_written = reencode.estimate_progress_percent(
        duration_seconds=120.0,
        last_out_time_us=0,
        source_size=source.stat().st_size,
        output_path=output,
    )

    assert percent == 25.0
    assert bytes_written == 250


def test_estimate_progress_caps_output_size_fallback_below_complete(tmp_path):
    source = tmp_path / "source.mkv"
    output = tmp_path / ".hometube-reencode.tmp.mkv"
    source.write_bytes(b"x" * 1000)
    output.write_bytes(b"y" * 2000)

    percent, bytes_written = reencode.estimate_progress_percent(
        duration_seconds=None,
        last_out_time_us=0,
        source_size=source.stat().st_size,
        output_path=output,
    )

    assert percent == 99.0
    assert bytes_written == 2000


def test_state_db_resets_interrupted_running_rows(tmp_path):
    db_path = tmp_path / "state.sqlite3"
    video_path = tmp_path / "video.mkv"
    output_path = tmp_path / ".hometube-reencode.tmp.mkv"
    video_path.write_bytes(b"x" * 100)
    output_path.write_bytes(b"y" * 10)

    state = reencode.StateDB(db_path)
    state.mark_scanned(
        video_path, video_path.stat().st_size, video_path.stat().st_mtime_ns
    )
    state.mark_status(
        video_path,
        "running",
        phase="preserve-all",
        output_path=output_path,
        progress_percent=12.5,
        speed="0.5x",
    )

    reset_count = state.reset_interrupted_runs()
    state.close()

    assert reset_count == 1
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        select status, progress_percent, speed, phase, output_path, error
        from files
        where path=?
        """,
        (str(video_path),),
    ).fetchone()
    conn.close()
    assert row == (
        "planned",
        0.0,
        None,
        "interrupted",
        None,
        "Reset stale running state from a previous interrupted run",
    )
