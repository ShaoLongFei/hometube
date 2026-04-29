from pathlib import Path


class TestVideoCodecNormalization:
    def test_build_normalization_command_preserves_all_streams_and_overrides_media(
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
        assert "-map" in cmd and cmd[cmd.index("-map") + 1] == "0"
        assert "-c" in cmd and cmd[cmd.index("-c") + 1] == "copy"
        assert "-c:v:0" in cmd and cmd[cmd.index("-c:v:0") + 1] == "libx264"
        assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
        assert "-profile:a" in cmd and cmd[cmd.index("-profile:a") + 1] == "aac_low"
        assert "-progress" in cmd and cmd[cmd.index("-progress") + 1] == "pipe:1"
        assert "-nostats" in cmd
        assert "-movflags" not in cmd
        assert cmd[-1] == str(target)

    def test_build_subtitle_preserving_fallback_maps_media_and_subtitles_only(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import (
            build_subtitle_preserving_normalization_command,
        )

        source = tmp_path / "source-with-cover.mkv"
        target = tmp_path / "final.mp4"

        cmd = build_subtitle_preserving_normalization_command(source, target)

        map_args = [cmd[index + 1] for index, arg in enumerate(cmd) if arg == "-map"]
        assert "0" not in map_args
        assert map_args == ["0:v:0", "0:a?", "0:s?"]
        assert "-c:s" in cmd and cmd[cmd.index("-c:s") + 1] == "copy"

    def test_build_minimal_fallback_maps_only_primary_video_and_audio(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import build_minimal_normalization_command

        source = tmp_path / "source-with-cover.mkv"
        target = tmp_path / "final.mp4"

        cmd = build_minimal_normalization_command(source, target)

        map_args = [cmd[index + 1] for index, arg in enumerate(cmd) if arg == "-map"]
        assert map_args == ["0:v:0", "0:a?"]
        assert "-c:s" not in cmd

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

    def test_normalize_video_file_falls_back_when_preserve_all_fails(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import normalize_video_file

        source = tmp_path / "source.mkv"
        source.write_bytes(b"video")
        target = tmp_path / "normalized.mkv"
        calls: list[list[str]] = []

        def fake_run_command(cmd, runtime_state=None):
            calls.append(cmd)
            if len(calls) == 1:
                target.write_bytes(b"partial")
                return 1
            assert not target.exists()
            target.write_bytes(b"normalized")
            return 0

        result = normalize_video_file(
            source,
            target,
            run_command_fn=fake_run_command,
        )

        assert result.succeeded is True
        assert result.output_path == target
        assert len(calls) == 2
        assert [calls[0][i + 1] for i, arg in enumerate(calls[0]) if arg == "-map"] == [
            "0"
        ]
        assert [calls[1][i + 1] for i, arg in enumerate(calls[1]) if arg == "-map"] == [
            "0:v:0",
            "0:a?",
            "0:s?",
        ]

    def test_normalize_video_file_reports_failure_without_hiding_original(
        self, tmp_path: Path
    ):
        from app.video_codec_normalization import normalize_video_file

        source = tmp_path / "source.webm"
        source.write_bytes(b"video")
        target = tmp_path / "normalized.mp4"
        calls: list[list[str]] = []

        def fake_run_command(cmd, runtime_state=None):
            calls.append(cmd)
            return 1

        result = normalize_video_file(
            source,
            target,
            run_command_fn=fake_run_command,
            subtitle_codec="mov_text",
        )

        assert result.succeeded is False
        assert result.output_path == source
        assert result.warning_message == "Codec normalization failed"
        assert len(calls) == 3
