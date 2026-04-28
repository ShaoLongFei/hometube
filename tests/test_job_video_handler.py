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

    def test_handle_video_job_item_records_normalized_delivery_summary(
        self, tmp_path: Path
    ):
        from app.job_store import JobStore
        from app.job_video_handler import DetachedVideoJobResult, handle_video_job_item
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_postprocess_backend import VideoPostprocessResult

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://www.youtube.com/watch?v=abc123",
            title="Episode 01",
            site="youtube.com",
            destination_dir=str(tmp_path / "library"),
            config={"base_output": "Episode 01"},
            items=[
                {
                    "item_index": 1,
                    "video_id": "abc123",
                    "video_url": "https://www.youtube.com/watch?v=abc123",
                    "title": "Episode 01",
                    "workspace_path": str(tmp_path / "video"),
                }
            ],
        )
        job = store.get_job(job_id)
        item = store.get_job_items(job_id)[0]

        handle_video_job_item(
            job,
            item,
            store=store,
            download_executor=lambda request, runtime_state: DetachedVideoJobResult(
                return_code=0,
                final_file=Path(item["workspace_path"]) / "final.mp4",
                error_message=None,
                postprocess_result=VideoPostprocessResult(
                    final_path=Path(item["workspace_path"]) / "final.mp4",
                    inspection=CodecInspectionResult(
                        container="mp4",
                        video_codec="h264",
                        audio_codecs=["aac"],
                        audio_profiles=["lc"],
                    ),
                    codec_summary="MP4 / H.264 / AAC-LC",
                    normalization_required=True,
                    normalization_succeeded=True,
                    warning_message=None,
                ),
            ),
            move_to_destination=lambda source, destination: destination,
        )

        refreshed = store.get_job_item(item["id"])

        assert refreshed is not None
        assert refreshed["normalization_required"] == 1
        assert refreshed["normalization_succeeded"] == 1
        assert refreshed["final_container"] == "mp4"
        assert refreshed["final_video_codec"] == "h264"
        assert refreshed["final_audio_summary"] == "AAC-LC"
        assert refreshed["final_codec_summary"] == "MP4 / H.264 / AAC-LC"
        assert refreshed["delivery_warning"] is None

    def test_handle_playlist_job_item_records_warning_when_original_file_is_delivered(
        self, tmp_path: Path
    ):
        from app.job_store import JobStore
        from app.job_video_handler import DetachedVideoJobResult, handle_playlist_job_item
        from app.video_codec_inspection import CodecInspectionResult
        from app.video_postprocess_backend import VideoPostprocessResult

        playlist_workspace = tmp_path / "playlist"
        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="playlist",
            url="https://www.youtube.com/playlist?list=pl123",
            title="Playlist",
            site="youtube.com",
            destination_dir=str(tmp_path / "library" / "Playlist"),
            config={
                "playlist_workspace": str(playlist_workspace),
                "playlist_title_pattern": "{idx} - {pretty(title)}.{ext}",
                "playlist_total_count": 1,
            },
            items=[
                {
                    "item_index": 1,
                    "video_id": "abc123",
                    "video_url": "https://www.youtube.com/watch?v=abc123",
                    "title": "Episode 01",
                    "workspace_path": str(tmp_path / "video"),
                }
            ],
        )
        job = store.get_job(job_id)
        item = store.get_job_items(job_id)[0]
        updates: list[tuple[str, str, str, dict | None]] = []

        handle_playlist_job_item(
            job,
            item,
            store=store,
            download_executor=lambda request, runtime_state: DetachedVideoJobResult(
                return_code=0,
                final_file=Path(item["workspace_path"]) / "final.webm",
                error_message=None,
                postprocess_result=VideoPostprocessResult(
                    final_path=Path(item["workspace_path"]) / "final.webm",
                    inspection=CodecInspectionResult(
                        container="webm",
                        video_codec="vp9",
                        audio_codecs=["opus"],
                        audio_profiles=[None],
                    ),
                    codec_summary="WEBM / VP9 / OPUS",
                    normalization_required=True,
                    normalization_succeeded=False,
                    warning_message="Codec normalization failed",
                ),
            ),
            update_playlist_status=lambda workspace, video_id, status, error=None, extra_data=None: updates.append(
                (str(workspace), video_id, status, extra_data)
            )
            or True,
            move_to_destination=lambda source, destination: destination,
        )

        refreshed = store.get_job_item(item["id"])

        assert refreshed is not None
        assert refreshed["normalization_required"] == 1
        assert refreshed["normalization_succeeded"] == 0
        assert refreshed["final_container"] == "webm"
        assert refreshed["final_video_codec"] == "vp9"
        assert refreshed["final_audio_summary"] == "OPUS"
        assert refreshed["final_codec_summary"] == "WEBM / VP9 / OPUS"
        assert refreshed["delivery_warning"] == "Codec normalization failed"
        assert updates[1][2] == "completed"
