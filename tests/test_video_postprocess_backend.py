from pathlib import Path


class TestVideoPostprocessBackend:
    def test_postprocess_video_file_runs_cut_pipeline_when_requested(self, tmp_path: Path):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
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
            probe_video_codecs_fn=lambda path: CodecInspectionResult(
                container="mkv",
                video_codec="h264",
                audio_codecs=["aac"],
                audio_profiles=["lc"],
            ),
            needs_codec_normalization_fn=lambda inspection: False,
        )

        assert result.final_path == cut_output
        assert commands == [["ffmpeg", "12.0", "30.0", str(cut_output)]]

    def test_postprocess_video_file_applies_metadata_and_manual_subtitle_embedding(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
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
            probe_video_codecs_fn=lambda path: CodecInspectionResult(
                container="mkv",
                video_codec="h264",
                audio_codecs=["aac"],
                audio_profiles=["lc"],
            ),
            needs_codec_normalization_fn=lambda inspection: False,
        )

        assert result.final_path == final_file
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
        from app.video_codec_inspection import CodecInspectionResult
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
            probe_video_codecs_fn=lambda path: CodecInspectionResult(
                container="webm",
                video_codec="vp9",
                audio_codecs=["opus"],
                audio_profiles=[None],
            ),
            needs_codec_normalization_fn=lambda inspection: False,
        )

        assert result.final_path == workspace / "final.webm"
        assert result.final_path.read_bytes() == b"cached"
        assert cached_track.exists()

    def test_postprocess_video_file_skips_normalization_for_mp4_h264_aac(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.mp4"
        final_file.write_bytes(b"video")
        inspections: list[Path] = []

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
            final_file,
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
            probe_video_codecs_fn=lambda path: inspections.append(path)
            or CodecInspectionResult(
                container="mp4",
                video_codec="h264",
                audio_codecs=["aac"],
                audio_profiles=["lc"],
            ),
        )

        assert inspections == [final_file]
        assert result.final_path == final_file
        assert result.normalization_required is False
        assert result.normalization_succeeded is None
        assert result.codec_summary == "MP4 / H.264 / AAC-LC"
        assert result.warning_message is None

    def test_postprocess_video_file_normalizes_non_compliant_output(self, tmp_path: Path):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_codec_normalization import CodecNormalizationResult
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.mkv"
        final_file.write_bytes(b"video")
        normalized_file = workspace / "final.mp4"
        inspected_paths: list[Path] = []

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

        def fake_probe(path: Path):
            inspected_paths.append(path)
            if path == final_file:
                return CodecInspectionResult(
                    container="mkv",
                    video_codec="vp9",
                    audio_codecs=["opus"],
                    audio_profiles=[None],
                )
            return CodecInspectionResult(
                container="mp4",
                video_codec="h264",
                audio_codecs=["aac"],
                audio_profiles=["lc"],
            )

        def fake_normalize(source_path: Path, output_path: Path, **kwargs):
            normalized_file.write_bytes(b"normalized")
            return CodecNormalizationResult(True, normalized_file, None)

        result = postprocess_video_file(
            request,
            MemoryRuntimeState(),
            final_file,
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
            probe_video_codecs_fn=fake_probe,
            normalize_video_file_fn=fake_normalize,
        )

        assert inspected_paths == [final_file, normalized_file]
        assert result.final_path == normalized_file
        assert result.normalization_required is True
        assert result.normalization_succeeded is True
        assert result.codec_summary == "MP4 / H.264 / AAC-LC"
        assert result.warning_message is None

    def test_postprocess_video_file_returns_original_with_warning_on_normalization_failure(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_codec_normalization import CodecNormalizationResult
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.webm"
        final_file.write_bytes(b"video")

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
            final_file,
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
            probe_video_codecs_fn=lambda path: CodecInspectionResult(
                container="webm",
                video_codec="vp9",
                audio_codecs=["opus"],
                audio_profiles=[None],
            ),
            normalize_video_file_fn=lambda source_path, output_path, **kwargs: CodecNormalizationResult(
                False,
                final_file,
                "Codec normalization failed",
            ),
        )

        assert result.final_path == final_file
        assert result.normalization_required is True
        assert result.normalization_succeeded is False
        assert result.codec_summary == "WEBM / VP9 / OPUS"
        assert result.warning_message == "Codec normalization failed"

    def test_postprocess_video_file_removes_obsolete_intermediate_after_success(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_codec_normalization import CodecNormalizationResult
        from app.video_download_backend import SingleVideoDownloadRequest
        from app.video_postprocess_backend import postprocess_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.mkv"
        final_file.write_bytes(b"video")
        normalized_file = workspace / "final.mp4"
        removed_paths: list[Path] = []

        def fake_normalize(source_path: Path, output_path: Path, **kwargs):
            normalized_file.write_bytes(b"normalized")
            return CodecNormalizationResult(True, normalized_file, None)

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
            final_file,
            check_required_subtitles_embedded_fn=lambda video_path, langs: True,
            customize_metadata_fn=lambda *args, **kwargs: True,
            probe_video_codecs_fn=lambda path: CodecInspectionResult(
                container="mkv" if path == final_file else "mp4",
                video_codec="vp9" if path == final_file else "h264",
                audio_codecs=["opus"] if path == final_file else ["aac"],
                audio_profiles=[None] if path == final_file else ["lc"],
            ),
            normalize_video_file_fn=fake_normalize,
            cleanup_file_fn=lambda path: removed_paths.append(path),
        )

        assert result.final_path == normalized_file
        assert removed_paths == [final_file]
