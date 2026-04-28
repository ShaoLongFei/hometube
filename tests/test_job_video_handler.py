from pathlib import Path


class TestJobVideoHandler:
    def test_handle_video_job_item_builds_request_and_runtime_state(self, tmp_path: Path):
        from app.job_video_handler import handle_video_job_item

        job = {
            "id": "job-1",
            "kind": "video",
            "destination_dir": str(tmp_path / "library"),
            "config": {
                "base_output": "Episode 01",
                "cookies_method": "browser",
                "browser_select": "chrome",
                "chosen_profiles": [{"format_id": "399+251"}],
            },
        }
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 01",
            "workspace_path": str(tmp_path / "video"),
        }

        captured: dict[str, object] = {}

        def fake_download_executor(request, runtime_state):
            captured["request"] = request
            captured["runtime_state"] = runtime_state.snapshot()
            return 0, Path(item["workspace_path"]) / "final.mkv", None

        handle_video_job_item(
            job,
            item,
            download_executor=fake_download_executor,
            move_to_destination=lambda source, destination: destination,
        )

        request = captured["request"]
        assert request.video_url == item["video_url"]
        assert request.video_workspace == Path(item["workspace_path"])
        assert captured["runtime_state"]["cookies_method"] == "browser"
        assert captured["runtime_state"]["chosen_format_profiles"] == [{"format_id": "399+251"}]

    def test_handle_video_job_item_raises_on_failed_download(self, tmp_path: Path):
        import pytest

        from app.job_video_handler import handle_video_job_item

        job = {"id": "job-1", "config": {}}
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 01",
            "workspace_path": str(tmp_path / "video"),
        }

        with pytest.raises(RuntimeError, match="download failed"):
            handle_video_job_item(
                job,
                item,
                download_executor=lambda request, runtime_state: (1, None, "download failed"),
            )

    def test_handle_video_job_item_moves_final_file_to_job_destination(self, tmp_path: Path):
        from app.job_video_handler import handle_video_job_item

        job = {
            "id": "job-1",
            "kind": "video",
            "destination_dir": str(tmp_path / "library"),
            "config": {
                "base_output": "Episode 01",
            },
        }
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 01",
            "workspace_path": str(tmp_path / "video"),
        }

        moves: list[tuple[Path, Path]] = []

        handle_video_job_item(
            job,
            item,
            download_executor=lambda request, runtime_state: (
                0,
                Path(item["workspace_path"]) / "final.mkv",
                None,
            ),
            move_to_destination=lambda source, destination: moves.append(
                (source, destination)
            )
            or destination,
        )

        assert moves == [
            (
                Path(item["workspace_path"]) / "final.mkv",
                tmp_path / "library" / "Episode 01.mkv",
            )
        ]

    def test_handle_playlist_job_item_renders_output_name_and_updates_playlist_status(
        self, tmp_path: Path
    ):
        from app.job_video_handler import handle_playlist_job_item

        playlist_workspace = tmp_path / "playlist"
        playlist_dest = tmp_path / "library" / "My Playlist"
        job = {
            "id": "job-1",
            "kind": "playlist",
            "destination_dir": str(playlist_dest),
            "config": {
                "playlist_workspace": str(playlist_workspace),
                "playlist_title_pattern": "{idx} - {pretty(title)}.{ext}",
                "playlist_total_count": 12,
                "playlist_channel": "Demo Channel",
            },
        }
        item = {
            "id": "item-1",
            "item_index": 3,
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "third episode",
            "workspace_path": str(tmp_path / "video"),
        }

        updates: list[tuple[str, str, str | None, dict | None]] = []
        moves: list[tuple[Path, Path]] = []

        handle_playlist_job_item(
            job,
            item,
            store=None,
            download_executor=lambda request, runtime_state: (
                0,
                Path(item["workspace_path"]) / "final.webm",
                None,
            ),
            update_playlist_status=lambda workspace, video_id, status, error=None, extra_data=None: updates.append(
                (str(workspace), video_id, status, extra_data)
            )
            or True,
            move_to_destination=lambda source, destination: moves.append(
                (source, destination)
            )
            or destination,
        )

        assert updates[0][:3] == (str(playlist_workspace), "abc123", "downloading")
        assert updates[1][:3] == (str(playlist_workspace), "abc123", "completed")
        assert updates[1][3]["resolved_title"] == "03 - Third Episode.webm"
        assert moves == [
            (
                Path(item["workspace_path"]) / "final.webm",
                playlist_dest / "03 - Third Episode.webm",
            )
        ]
