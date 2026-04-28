from pathlib import Path


class TestVideoCacheBackend:
    def test_check_existing_video_file_returns_completed_cached_track(self, tmp_path: Path):
        from app.status_utils import create_initial_status, add_selected_format, update_format_status
        from app.video_cache_backend import check_existing_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        create_initial_status(
            url="https://example.com/watch?v=abc123",
            video_id="abc123",
            title="Demo",
            content_type="video",
            tmp_url_workspace=workspace,
        )
        add_selected_format(workspace, "399+251", [], 4)
        cached_file = workspace / "video-399+251.mkv"
        cached_file.write_bytes(b"demo")
        update_format_status(workspace, "399+251", cached_file)

        found, format_id = check_existing_video_file(workspace, requested_format_id=None)

        assert found == cached_file
        assert format_id == "399+251"

    def test_check_existing_video_file_respects_requested_format_id(self, tmp_path: Path):
        from app.status_utils import create_initial_status, add_selected_format, update_format_status
        from app.video_cache_backend import check_existing_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        create_initial_status(
            url="https://example.com/watch?v=abc123",
            video_id="abc123",
            title="Demo",
            content_type="video",
            tmp_url_workspace=workspace,
        )
        add_selected_format(workspace, "399+251", [], 4)
        cached_file = workspace / "video-399+251.mkv"
        cached_file.write_bytes(b"demo")
        update_format_status(workspace, "399+251", cached_file)

        found, format_id = check_existing_video_file(workspace, requested_format_id="18")

        assert found is None
        assert format_id is None

    def test_check_existing_video_file_falls_back_to_legacy_track_detection(self, tmp_path: Path):
        from app.video_cache_backend import check_existing_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        legacy_file = workspace / "video-18.mp4"
        legacy_file.write_bytes(b"legacy")

        found, format_id = check_existing_video_file(workspace)

        assert found == legacy_file
        assert format_id is None
