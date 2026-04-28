from pathlib import Path


def _item(video_id: str) -> dict:
    return {
        "item_index": 1,
        "video_id": video_id,
        "video_url": f"https://example.com/watch?v={video_id}",
        "title": f"Video {video_id}",
        "workspace_path": f"/tmp/{video_id}",
    }


class TestJobWorker:
    def test_execute_job_item_marks_completed_on_success(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_worker import execute_job_item

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=ok123",
            title="Success Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("ok123")],
        )
        item = store.get_job_items(job_id)[0]

        calls: list[str] = []

        def handler(job, job_item):
            calls.append(job_item["id"])

        assert execute_job_item(store, item["id"], handler, worker_pid=9999) is True

        refreshed_item = store.get_job_items(job_id)[0]
        refreshed_job = store.get_job(job_id)

        assert calls == [item["id"]]
        assert refreshed_item["status"] == "completed"
        assert refreshed_item["worker_pid"] == 9999
        assert refreshed_job["status"] == "completed"

    def test_execute_job_item_marks_failed_on_exception(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_worker import execute_job_item

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=bad123",
            title="Broken Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("bad123")],
        )
        item = store.get_job_items(job_id)[0]

        def handler(job, job_item):
            raise RuntimeError("boom")

        assert execute_job_item(store, item["id"], handler, worker_pid=1111) is False

        refreshed_item = store.get_job_items(job_id)[0]
        refreshed_job = store.get_job(job_id)

        assert refreshed_item["status"] == "failed"
        assert "boom" in refreshed_item["last_error"]
        assert refreshed_job["status"] == "failed"

    def test_execute_job_item_refuses_double_claim(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_worker import execute_job_item

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=dup123",
            title="Claimed Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("dup123")],
        )
        item = store.get_job_items(job_id)[0]
        store.update_job_item_status(item["id"], "running")

        def handler(job, job_item):
            raise AssertionError("handler should not run")

        assert execute_job_item(store, item["id"], handler, worker_pid=2222) is False

    def test_execute_job_item_accepts_scheduler_preclaimed_item(self, tmp_path: Path):
        from app.job_store import JobStore
        from app.job_worker import execute_job_item

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=pre123",
            title="Preclaimed Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("pre123")],
        )
        item = store.get_job_items(job_id)[0]
        assert store.claim_job_item(item["id"], worker_pid=None) is True

        calls: list[str] = []

        def handler(job, job_item):
            calls.append(job_item["id"])

        assert execute_job_item(store, item["id"], handler, worker_pid=3333) is True

        refreshed_item = store.get_job_items(job_id)[0]
        refreshed_job = store.get_job(job_id)

        assert calls == [item["id"]]
        assert refreshed_item["status"] == "completed"
        assert refreshed_item["worker_pid"] == 3333
        assert refreshed_job["status"] == "completed"
