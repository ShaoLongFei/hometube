class TestJobWorkerEntry:
    def test_dispatch_job_item_routes_video_jobs_to_video_handler(self):
        from app.job_worker_entry import dispatch_job_item

        calls: list[tuple[dict, dict]] = []

        dispatch_job_item(
            {"kind": "video", "id": "job-1"},
            {"id": "item-1"},
            video_handler=lambda job, item: calls.append((job, item)),
        )

        assert calls == [({"kind": "video", "id": "job-1"}, {"id": "item-1"})]

    def test_dispatch_job_item_routes_playlist_jobs_to_playlist_handler(self):
        from app.job_worker_entry import dispatch_job_item

        calls: list[tuple[dict, dict, object]] = []
        marker = object()

        dispatch_job_item(
            {"kind": "playlist", "id": "job-1"},
            {"id": "item-1"},
            store=marker,
            playlist_handler=lambda job, item, store: calls.append((job, item, store)),
        )

        assert calls == [
            ({"kind": "playlist", "id": "job-1"}, {"id": "item-1"}, marker)
        ]

    def test_dispatch_job_item_rejects_unsupported_job_kind(self):
        import pytest

        from app.job_worker_entry import dispatch_job_item

        with pytest.raises(RuntimeError, match="Unsupported job kind"):
            dispatch_job_item(
                {"kind": "audio", "id": "job-1"},
                {"id": "item-1"},
            )
