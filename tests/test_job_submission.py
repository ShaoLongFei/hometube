from pathlib import Path


class TestJobSubmission:
    def test_enqueue_video_job_uses_video_workspace_and_destination(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_submission import enqueue_video_job

        store = JobStore(tmp_path / "jobs.db")
        tmp_root = tmp_path / "tmp"
        videos_root = tmp_path / "videos"

        job_id = enqueue_video_job(
            store,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            title="Never Gonna Give You Up",
            site="youtube.com",
            destination_dir=videos_root / "music",
            tmp_download_folder=tmp_root,
            base_output="Never Gonna Give You Up",
            config={"embed_subs": True},
        )

        job = store.get_job(job_id)
        items = store.get_job_items(job_id)

        assert job is not None
        assert job["kind"] == "video"
        assert str(job["destination_dir"]) == str(videos_root / "music")
        assert len(items) == 1
        assert items[0]["video_id"] == "dQw4w9WgXcQ"
        assert items[0]["workspace_path"].endswith(
            "videos/youtube/dQw4w9WgXcQ"
        )

    def test_enqueue_playlist_job_creates_one_item_per_entry(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_submission import enqueue_playlist_job

        store = JobStore(tmp_path / "jobs.db")
        tmp_root = tmp_path / "tmp"
        videos_root = tmp_path / "videos"

        job_id = enqueue_playlist_job(
            store,
            url="https://www.youtube.com/playlist?list=PL123",
            playlist_id="PL123",
            playlist_title="Synthwave Mix",
            site="youtube.com",
            destination_dir=videos_root / "mixes",
            tmp_download_folder=tmp_root,
            playlist_entries=[
                {
                    "id": "vid1",
                    "title": "Track 1",
                    "url": "https://www.youtube.com/watch?v=vid1",
                    "playlist_index": 1,
                },
                {
                    "id": "vid2",
                    "title": "Track 2",
                    "url": "https://www.youtube.com/watch?v=vid2",
                    "playlist_index": 2,
                },
            ],
            config={"playlist_title_pattern": "{idx} - {title}"},
            max_parallelism=4,
        )

        job = store.get_job(job_id)
        items = store.get_job_items(job_id)

        assert job is not None
        assert job["kind"] == "playlist"
        assert job["max_parallelism"] == 4
        assert len(items) == 2
        assert [item["item_index"] for item in items] == [1, 2]
        assert items[0]["workspace_path"].endswith("videos/youtube/vid1")
        assert items[1]["workspace_path"].endswith("videos/youtube/vid2")

    def test_default_jobs_db_path_lives_under_tmp_jobs(self, tmp_path: Path):
        from app.job_submission import get_jobs_db_path

        db_path = get_jobs_db_path(tmp_path / "tmp")

        assert db_path == tmp_path / "tmp" / "jobs" / "jobs.db"
