from pathlib import Path


class TestVideoPostprocessBackend:
    def test_postprocess_video_file_runs_cut_pipeline_when_requested(self, tmp_path: Path):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        source_file = workspace / "final.webm"
        source_file.write_bytes(b"video")
        cut_output = workspace / "final.mkv"

        commands: list[list[str]] = []

        request = SingleVideoDownloadRequest(
            video_url="https://example.com/watch?v=abc123",
            video_id="abc123",
            video_title="Episode 03",
            video_workspace=workspace,
            base_output="Episode 03",
            embed_chapters=False,
            embed_subs=True,
            force_mp4=False,
            ytdlp_custom_args="",
            do_cut=True,
            subs_selected=["en"],
            sb_choice="disabled",
            start_sec=10,
            end_sec=40,
            cutting_mode="keyframes",
        )

        def fake_run_command(cmd, runtime_state=None):
            commands.append(cmd)
            cut_output.write_bytes(b"cut")
            return 0

        result = postprocess_video_file(
            request,
            MemoryRuntimeState(),
            source_file,
            run_command_fn=fake_run_command,
            process_subtitles_fn=lambda base_output, tmp_video_dir, subtitle_languages, start_time, duration: [("en", workspace / "subtitles-cut.en.srt")],
            build_cut_command_fn=lambda final_tmp, actual_start, duration, processed_subtitle_files, cut_output, cut_ext: [
                "ffmpeg",
                str(actual_start),
                str(duration),
                str(cut_output),
            ],
            get_keyframes_fn=lambda _path: [0.0, 12.0, 42.0],
            find_nearest_keyframes_fn=lambda keyframes, start_sec, end_sec: (12.0, 42.0),
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
        )

        assert result == cut_output
        assert commands == [["ffmpeg", "12.0", "30.0", str(cut_output)]]

    def test_postprocess_video_file_applies_metadata_and_manual_subtitle_embedding(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.mkv"
        final_file.write_bytes(b"video")
        subtitle_file = workspace / "subtitles.en.srt"
        subtitle_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

        metadata_calls: list[tuple[Path, str, dict]] = []
        embed_calls: list[list[Path]] = []

        request = SingleVideoDownloadRequest(
            video_url="https://www.youtube.com/watch?v=abc123",
            video_id="abc123",
            video_title="Episode 03",
            video_workspace=workspace,
            base_output="Episode 03",
            embed_chapters=False,
            embed_subs=True,
            force_mp4=False,
            ytdlp_custom_args="",
            do_cut=False,
            subs_selected=["en"],
            sb_choice="disabled",
        )

        result = postprocess_video_file(
            request,
            MemoryRuntimeState(),
            final_file,
            metadata_title="Episode 03",
            metadata_context={
                "original_title": "Original Episode 03",
                "uploader": "Demo Channel",
                "source": "youtube",
                "webpage_url": request.video_url,
            },
            check_required_subtitles_embedded_fn=lambda video_path, langs: False,
            find_subtitle_files_fn=lambda base_output, tmp_video_dir, subtitle_languages, is_cut=False: [subtitle_file],
            embed_subtitles_fn=lambda video_path, subtitle_files: embed_calls.append(subtitle_files) or True,
            customize_metadata_fn=lambda video_path, title, **kwargs: metadata_calls.append((video_path, title, kwargs)) or True,
        )

        assert result == final_file
        assert metadata_calls == [
            (
                final_file,
                "Episode 03",
                {
                    "original_title": "Original Episode 03",
                    "video_id": "abc123",
                    "source": "youtube",
                    "playlist_id": None,
                    "webpage_url": request.video_url,
                    "duration": None,
                    "uploader": "Demo Channel",
                },
            )
        ]
        assert embed_calls == [[subtitle_file]]

    def test_postprocess_video_file_copies_cached_track_to_final_before_move(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        cached_track = workspace / "video-399+251.webm"
        cached_track.write_bytes(b"cached")

        request = SingleVideoDownloadRequest(
            video_url="https://example.com/watch?v=abc123",
            video_id="abc123",
            video_title="Episode 03",
            video_workspace=workspace,
            base_output="Episode 03",
            embed_chapters=False,
            embed_subs=False,
            force_mp4=False,
            ytdlp_custom_args="",
            do_cut=False,
            subs_selected=[],
            sb_choice="disabled",
        )

        result = postprocess_video_file(
            request,
            MemoryRuntimeState(),
            cached_track,
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
        )

        assert result == workspace / "final.webm"
        assert result.read_bytes() == b"cached"
        assert cached_track.exists()
