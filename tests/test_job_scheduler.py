class TestJobScheduler:
    def test_select_dispatch_batch_respects_global_limit(self):
        from app.job_scheduler import select_dispatch_batch

        runnable_items = [
            {"id": "i1", "job_id": "job-a", "priority": 0},
            {"id": "i2", "job_id": "job-b", "priority": 0},
            {"id": "i3", "job_id": "job-c", "priority": 0},
        ]

        batch = select_dispatch_batch(
            runnable_items=runnable_items,
            active_per_job={},
            global_active_count=0,
            global_limit=2,
            default_per_job_limit=4,
            job_parallelism={},
        )

        assert [item["id"] for item in batch] == ["i1", "i2"]

    def test_select_dispatch_batch_respects_per_job_limit(self):
        from app.job_scheduler import select_dispatch_batch

        runnable_items = [
            {"id": "i1", "job_id": "job-a", "priority": 0},
            {"id": "i2", "job_id": "job-a", "priority": 0},
            {"id": "i3", "job_id": "job-b", "priority": 0},
        ]

        batch = select_dispatch_batch(
            runnable_items=runnable_items,
            active_per_job={"job-a": 1},
            global_active_count=1,
            global_limit=4,
            default_per_job_limit=2,
            job_parallelism={},
        )

        assert sum(1 for item in batch if item["job_id"] == "job-a") == 1
        assert sum(1 for item in batch if item["job_id"] == "job-b") == 1

    def test_select_dispatch_batch_spreads_first_slots_across_jobs(self):
        from app.job_scheduler import select_dispatch_batch

        runnable_items = [
            {"id": "i1", "job_id": "job-a", "priority": 10},
            {"id": "i2", "job_id": "job-a", "priority": 10},
            {"id": "i3", "job_id": "job-b", "priority": 5},
            {"id": "i4", "job_id": "job-b", "priority": 5},
        ]

        batch = select_dispatch_batch(
            runnable_items=runnable_items,
            active_per_job={},
            global_active_count=0,
            global_limit=3,
            default_per_job_limit=2,
            job_parallelism={},
        )

        assert {item["job_id"] for item in batch[:2]} == {"job-a", "job-b"}
        assert len(batch) == 3
