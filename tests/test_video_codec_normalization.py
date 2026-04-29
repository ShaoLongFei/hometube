from pathlib import Path


class TestVideoCodecNormalization:
    def test_build_normalization_command_targets_h264_aac_and_copies_subtitles(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import build_normalization_command

        source = tmp_path / "source.mkv"
        target = tmp_path / "final.mkv"

        cmd = build_normalization_command(
            source,
            target,
            subtitle_codec="mov_text",
        )

        assert cmd[:4] == ["ffmpeg", "-y", "-loglevel", "warning"]
        assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
        assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
        assert "-profile:a" in cmd and cmd[cmd.index("-profile:a") + 1] == "aac_low"
        assert "-c:s" in cmd and cmd[cmd.index("-c:s") + 1] == "copy"
        assert "-progress" in cmd and cmd[cmd.index("-progress") + 1] == "pipe:1"
        assert "-nostats" in cmd
        assert "-movflags" not in cmd
        assert cmd[-1] == str(target)

    def test_build_normalization_command_maps_media_and_subtitle_streams_only(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import build_normalization_command

        source = tmp_path / "source-with-cover.mkv"
        target = tmp_path / "final.mp4"

        cmd = build_normalization_command(source, target)

        map_args = [cmd[index + 1] for index, arg in enumerate(cmd) if arg == "-map"]
        assert "0" not in map_args
        assert map_args == ["0:v:0", "0:a?", "0:s?"]

    def test_build_normalization_command_adds_faststart_for_mp4(self, tmp_path: Path):
        from app.video_codec_normalization import build_normalization_command

        source = tmp_path / "source.mkv"
        target = tmp_path / "final.mp4"

        cmd = build_normalization_command(source, target)

        assert "-movflags" in cmd and cmd[cmd.index("-movflags") + 1] == "+faststart"

    def test_normalize_video_file_runs_ffmpeg_and_returns_mp4_path(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import normalize_video_file

        source = tmp_path / "source.webm"
        source.write_bytes(b"video")
        target = tmp_path / "normalized.mp4"
        calls: list[list[str]] = []

        def fake_run_command(cmd, runtime_state=None):
            calls.append(cmd)
            target.write_bytes(b"normalized")
            return 0

        result = normalize_video_file(
            source,
            target,
            run_command_fn=fake_run_command,
            subtitle_codec="mov_text",
        )

        assert result.succeeded is True
        assert result.output_path == target
        assert calls and calls[0][-1] == str(target)

    def test_normalize_video_file_forwards_duration_for_progress(self, tmp_path: Path):
        from app.video_codec_normalization import normalize_video_file

        source = tmp_path / "source.webm"
        source.write_bytes(b"video")
        target = tmp_path / "normalized.mp4"
        durations: list[float | None] = []

        def fake_run_command(cmd, runtime_state=None, command_duration_seconds=None):
            durations.append(command_duration_seconds)
            target.write_bytes(b"normalized")
            return 0

        normalize_video_file(
            source,
            target,
            run_command_fn=fake_run_command,
            duration_seconds=42.5,
        )

        assert durations == [42.5]

    def test_normalize_video_file_reports_failure_without_hiding_original(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import normalize_video_file

        source = tmp_path / "source.webm"
        source.write_bytes(b"video")
        target = tmp_path / "normalized.mp4"

        result = normalize_video_file(
            source,
            target,
            run_command_fn=lambda cmd, runtime_state=None: 1,
            subtitle_codec="mov_text",
        )

        assert result.succeeded is False
        assert result.output_path == source
        assert result.warning_message == "Codec normalization failed"
