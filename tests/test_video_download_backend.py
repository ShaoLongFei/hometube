from pathlib import Path


class TestVideoDownloadBackend:
    def test_execute_video_download_reuses_cached_file_without_downloading(
        self, tmp_path: Path
    ):
        from app.video_download_backend import (
            DownloadAttemptResult,
            SingleVideoDownloadRequest,
            execute_video_download,
        )

        workspace = tmp_path / "video"
        workspace.mkdir()
        cached_file = workspace / "video-18.mp4"
        cached_file.write_bytes(b"cached")

        request = SingleVideoDownloadRequest(
            video_url="https://example.com/watch?v=abc123",
            video_id="abc123",
            video_title="Cached Video",
            video_workspace=workspace,
            base_output="Cached Video",
            embed_chapters=False,
            embed_subs=False,
            force_mp4=False,
            ytdlp_custom_args="",
            do_cut=False,
            subs_selected=[],
            sb_choice="disabled",
            requested_format_id="18",
        )

        download_called = False

        def initialize_workspace(req):
            return {"id": req.video_id}, True

        def check_existing_file(video_workspace, requested_format_id):
            return cached_file, "18"

        def perform_download(req):
            nonlocal download_called
            download_called = True
            return DownloadAttemptResult(return_code=0, downloaded_format_id="18")

        updated_formats: list[tuple[str, Path]] = []

        result = execute_video_download(
            request,
            initialize_workspace=initialize_workspace,
            check_existing_file=check_existing_file,
            perform_download=perform_download,
            locate_final_file=lambda *_args, **_kwargs: None,
            finalize_downloaded_file=lambda *_args, **_kwargs: None,
            update_cached_format_status=lambda workspace, format_id, final_file: updated_formats.append((format_id, final_file)),
        )

        assert result.return_code == 0
        assert result.final_file == cached_file
        assert result.error_message is None
        assert result.used_cached_file is True
        assert download_called is False
        assert updated_formats == [("18", cached_file)]

    def test_execute_video_download_finalizes_new_download(self, tmp_path: Path):
        from app.video_download_backend import (
            DownloadAttemptResult,
            SingleVideoDownloadRequest,
            execute_video_download,
        )

        workspace = tmp_path / "video"
        workspace.mkdir()
        downloaded_file = workspace / "Fresh Video.mkv"
        downloaded_file.write_bytes(b"fresh")

        request = SingleVideoDownloadRequest(
            video_url="https://example.com/watch?v=fresh123",
            video_id="fresh123",
            video_title="Fresh Video",
            video_workspace=workspace,
            base_output="Fresh Video",
            embed_chapters=True,
            embed_subs=True,
            force_mp4=False,
            ytdlp_custom_args="--sleep-interval 1",
            do_cut=False,
            subs_selected=["en"],
            sb_choice="disabled",
        )

        finalized_paths: list[tuple[Path, str]] = []
        final_output = workspace / "final.mkv"

        result = execute_video_download(
            request,
            initialize_workspace=lambda req: ({"id": req.video_id}, True),
            check_existing_file=lambda *_args, **_kwargs: (None, None),
            perform_download=lambda req: DownloadAttemptResult(
                return_code=0,
                downloaded_format_id="399+251",
            ),
            locate_final_file=lambda video_workspace, base_output: downloaded_file,
            finalize_downloaded_file=lambda video_workspace, file_path, base_output, downloaded_format_id, subs_selected: finalized_paths.append((file_path, downloaded_format_id)) or final_output,
        )

        assert result.return_code == 0
        assert result.final_file == final_output
        assert result.error_message is None
        assert result.used_cached_file is False
        assert finalized_paths == [(downloaded_file, "399+251")]

    def test_execute_video_download_returns_error_when_workspace_init_fails(
        self, tmp_path: Path
    ):
        from app.video_download_backend import (
            DownloadAttemptResult,
            SingleVideoDownloadRequest,
            execute_video_download,
        )

        workspace = tmp_path / "video"
        workspace.mkdir()
        request = SingleVideoDownloadRequest(
            video_url="https://example.com/watch?v=bad123",
            video_id="bad123",
            video_title="Bad Video",
            video_workspace=workspace,
            base_output="Bad Video",
            embed_chapters=False,
            embed_subs=False,
            force_mp4=False,
            ytdlp_custom_args="",
            do_cut=False,
            subs_selected=[],
            sb_choice="disabled",
        )

        def perform_download(req):
            return DownloadAttemptResult(return_code=0, downloaded_format_id="18")

        result = execute_video_download(
            request,
            initialize_workspace=lambda req: ({"error": "boom"}, False),
            check_existing_file=lambda *_args, **_kwargs: (None, None),
            perform_download=perform_download,
            locate_final_file=lambda *_args, **_kwargs: None,
            finalize_downloaded_file=lambda *_args, **_kwargs: None,
        )

        assert result.return_code == 1
        assert result.final_file is None
        assert result.error_message == "boom"
