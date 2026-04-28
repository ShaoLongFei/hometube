from pathlib import Path


class TestVideoFileOps:
    def test_find_final_video_file_prefers_base_output_name(self, tmp_path: Path):
        from app.video_file_ops import find_final_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        titled_file = workspace / "Demo Video.mkv"
        titled_file.write_bytes(b"title-based")
        (workspace / "final.mp4").write_bytes(b"generic-final")

        found = find_final_video_file(workspace, "Demo Video")

        assert found == titled_file

    def test_organize_downloaded_video_file_renames_to_generic_and_final(
        self, tmp_path: Path
    ):
        from app.video_file_ops import organize_downloaded_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        downloaded_file = workspace / "Demo Video.mkv"
        downloaded_file.write_bytes(b"video-bytes")
        subtitle_file = workspace / "Demo Video.en.srt"
        subtitle_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")

        final_path = organize_downloaded_video_file(
            workspace,
            downloaded_file,
            base_output="Demo Video",
            downloaded_format_id="399+251",
            subs_selected=["en"],
        )

        generic_video = workspace / "video-399+251.mkv"
        generic_subtitle = workspace / "subtitles.en.srt"

        assert final_path == workspace / "final.mkv"
        assert generic_video.exists()
        assert generic_video.read_bytes() == b"video-bytes"
        assert final_path.exists()
        assert final_path.read_bytes() == b"video-bytes"
        assert generic_subtitle.exists()
        assert "Hello" in generic_subtitle.read_text(encoding="utf-8")
        assert not downloaded_file.exists()
        assert not subtitle_file.exists()

    def test_organize_downloaded_video_file_returns_existing_final_name(
        self, tmp_path: Path
    ):
        from app.video_file_ops import organize_downloaded_video_file

        workspace = tmp_path / "video"
        workspace.mkdir()
        final_file = workspace / "final.mp4"
        final_file.write_bytes(b"ready")

        result = organize_downloaded_video_file(
            workspace,
            final_file,
            base_output="Ignored",
            downloaded_format_id="18",
            subs_selected=[],
        )

        assert result == final_file
        assert final_file.read_bytes() == b"ready"
