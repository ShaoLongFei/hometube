from pathlib import Path


def _video_item(video_id: str, title: str, item_index: int = 1) -> dict:
    return {
        "item_index": item_index,
        "video_id": video_id,
        "video_url": f"https://example.com/watch?v={video_id}",
        "title": title,
        "workspace_path": f"/tmp/{video_id}",
    }


class TestJobStore:
    def test_create_video_job_persists_items(self, tmp_path: Path):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")

        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=abc123",
            title="Example Video",
            site="example.com",
            destination_dir="/data/videos",
            config={"embed_subs": True},
            items=[_video_item("abc123", "Example Video")],
        )

        job = store.get_job(job_id)
        items = store.get_job_items(job_id)

        assert job["kind"] == "video"
        assert job["status"] == "queued"
        assert job["total_items"] == 1
        assert len(items) == 1
        assert items[0]["video_id"] == "abc123"
        assert items[0]["status"] == "queued"

    def test_create_playlist_job_persists_multiple_items(self, tmp_path: Path):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")

        job_id = store.create_job(
            kind="playlist",
            url="https://example.com/playlist?id=pl-1",
            title="Example Playlist",
            site="example.com",
            destination_dir="/data/videos",
            config={"playlist_title_pattern": "{idx}-{title}"},
            items=[
                _video_item("a1", "First", 1),
                _video_item("a2", "Second", 2),
                _video_item("a3", "Third", 3),
            ],
        )

        items = store.get_job_items(job_id)

        assert len(items) == 3
        assert [item["item_index"] for item in items] == [1, 2, 3]
        assert all(item["job_id"] == job_id for item in items)

    def test_refresh_job_status_marks_completed_when_all_items_done(
        self, tmp_path: Path
    ):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="playlist",
            url="https://example.com/playlist?id=pl-2",
            title="Done Playlist",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[
                _video_item("c1", "One", 1),
                _video_item("c2", "Two", 2),
            ],
        )

        items = store.get_job_items(job_id)
        store.update_job_item_status(items[0]["id"], "completed")
        store.update_job_item_status(items[1]["id"], "skipped")
        store.refresh_job_status(job_id)

        job = store.get_job(job_id)

        assert job["status"] == "completed"
        assert job["completed_items"] == 2
        assert job["failed_items"] == 0

    def test_list_runnable_items_excludes_running_and_terminal_states(
        self, tmp_path: Path
    ):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="playlist",
            url="https://example.com/playlist?id=pl-3",
            title="Runnable Playlist",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[
                _video_item("r1", "Queued", 1),
                _video_item("r2", "Running", 2),
                _video_item("r3", "Done", 3),
            ],
        )

        items = store.get_job_items(job_id)
        store.update_job_item_status(items[1]["id"], "running")
        store.update_job_item_status(items[2]["id"], "completed")

        runnable = store.list_runnable_items()

        assert [item["id"] for item in runnable] == [items[0]["id"]]

    def test_get_active_counts_reports_global_and_per_job_usage(self, tmp_path: Path):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")

        job_a = store.create_job(
            kind="playlist",
            url="https://example.com/playlist?id=active-a",
            title="Active A",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_video_item("a1", "A1", 1), _video_item("a2", "A2", 2)],
        )
        job_b = store.create_job(
            kind="video",
            url="https://example.com/watch?v=active-b",
            title="Active B",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_video_item("b1", "B1", 1)],
        )

        items_a = store.get_job_items(job_a)
        items_b = store.get_job_items(job_b)
        store.update_job_item_status(items_a[0]["id"], "running")
        store.update_job_item_status(items_b[0]["id"], "running")

        counts = store.get_active_counts()

        assert counts["global"] == 2
        assert counts["per_job"][job_a] == 1
        assert counts["per_job"][job_b] == 1

    def test_update_job_item_progress_persists_runtime_metrics(self, tmp_path: Path):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=abc123",
            title="Progress Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_video_item("abc123", "Progress Video")],
        )
        item = store.get_job_items(job_id)[0]

        store.update_job_item_progress(
            item["id"],
            progress_percent=42.5,
            downloaded_bytes=123456,
            total_bytes=234567,
            speed_bps=98765.0,
            eta_seconds=12,
            status_message="Downloading",
        )

        refreshed = store.get_job_item(item["id"])

        assert refreshed is not None
        assert refreshed["progress_percent"] == 42.5
        assert refreshed["downloaded_bytes"] == 123456
        assert refreshed["total_bytes"] == 234567
        assert refreshed["speed_bps"] == 98765.0
        assert refreshed["eta_seconds"] == 12
        assert refreshed["status_message"] == "Downloading"

    def test_list_job_logs_returns_recent_entries_first(self, tmp_path: Path):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=abc123",
            title="Logged Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_video_item("abc123", "Logged Video")],
        )

        store.record_job_log(job_id=job_id, level="info", message="First")
        store.record_job_log(job_id=job_id, level="warning", message="Second")

        logs = store.list_job_logs(job_id, limit=1)

        assert len(logs) == 1
        assert logs[0]["message"] == "Second"

    def test_update_job_item_delivery_persists_codec_normalization_fields(
        self, tmp_path: Path
    ):
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=abc123",
            title="Codec Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_video_item("abc123", "Codec Video")],
        )
        item = store.get_job_items(job_id)[0]

        store.update_job_item_delivery(
            item["id"],
            normalization_required=True,
            normalization_succeeded=False,
            final_container="webm",
            final_video_codec="vp9",
            final_audio_summary="OPUS",
            final_codec_summary="WEBM / VP9 / OPUS",
            delivery_warning="Codec normalization failed",
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
