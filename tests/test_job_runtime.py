from pathlib import Path
import sqlite3


def _item(video_id: str, index: int = 1) -> dict:
    return {
        "item_index": index,
        "video_id": video_id,
        "video_url": f"https://example.com/watch?v={video_id}",
        "title": f"Video {video_id}",
        "workspace_path": f"/tmp/{video_id}",
    }


class TestSchedulerLock:
    def test_scheduler_lock_allows_single_owner(self, tmp_path: Path):
        from app.job_runtime import SchedulerLock

        lock_path = tmp_path / "scheduler.lock"

        first = SchedulerLock(lock_path)
        second = SchedulerLock(lock_path)

        assert first.acquire() is True
        assert second.acquire() is False

        first.release()

        assert second.acquire() is True
        second.release()

    def test_scheduler_lock_reclaims_stale_owner_pid_file(self, tmp_path: Path):
        from app.job_runtime import SchedulerLock

        lock_path = tmp_path / "scheduler.lock"
        lock_path.write_text("999999", encoding="utf-8")

        lock = SchedulerLock(lock_path)

        assert lock.acquire() is True
        lock.release()


class TestJobRecovery:
    def test_recover_orphaned_running_item_requeues_it(self, tmp_path: Path):
        from app.job_runtime import recover_orphaned_running_items
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=abc123",
            title="Recoverable Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("abc123")],
        )

        item = store.get_job_items(job_id)[0]
        store.update_job_item_status(item["id"], "running")
        store.set_job_item_runtime(item["id"], worker_pid=424242)

        recovered = recover_orphaned_running_items(
            store,
            pid_exists=lambda pid: False,
            max_retries=2,
        )

        refreshed_item = store.get_job_items(job_id)[0]
        refreshed_job = store.get_job(job_id)

        assert recovered == 1
        assert refreshed_item["status"] == "queued"
        assert refreshed_item["retry_count"] == 1
        assert refreshed_item["worker_pid"] is None
        assert refreshed_job["status"] == "queued"

    def test_recover_orphaned_running_item_marks_failed_after_retry_budget(
        self, tmp_path: Path
    ):
        from app.job_runtime import recover_orphaned_running_items
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=def456",
            title="Failing Recovery Video",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("def456")],
        )

        item = store.get_job_items(job_id)[0]
        store.update_job_item_status(item["id"], "running")
        store.set_job_item_runtime(item["id"], worker_pid=515151, retry_count=2)

        recovered = recover_orphaned_running_items(
            store,
            pid_exists=lambda pid: False,
            max_retries=2,
        )

        refreshed_item = store.get_job_items(job_id)[0]
        refreshed_job = store.get_job(job_id)

        assert recovered == 1
        assert refreshed_item["status"] == "failed"
        assert refreshed_item["retry_count"] == 3
        assert refreshed_job["status"] == "failed"


class TestSchedulerIteration:
    def test_run_scheduler_iteration_dispatches_items_and_marks_them_running(
        self, tmp_path: Path
    ):
        from app.job_runtime import run_scheduler_iteration
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        first_job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=one123",
            title="One",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("one123")],
        )
        second_job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=two123",
            title="Two",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("two123")],
        )

        spawned: list[str] = []

        def spawn_worker(item: dict) -> int:
            spawned.append(item["id"])
            return 7000 + len(spawned)

        dispatched = run_scheduler_iteration(
            store,
            spawn_worker=spawn_worker,
            global_limit=2,
            default_per_job_limit=4,
        )

        first_item = store.get_job_items(first_job_id)[0]
        second_item = store.get_job_items(second_job_id)[0]
        first_job = store.get_job(first_job_id)
        second_job = store.get_job(second_job_id)

        assert dispatched == spawned
        assert len(dispatched) == 2
        assert first_item["status"] == "running"
        assert second_item["status"] == "running"
        assert first_item["worker_pid"] == 7001
        assert second_item["worker_pid"] == 7002
        assert first_job["status"] == "running"
        assert second_job["status"] == "running"

    def test_run_scheduler_iteration_respects_existing_global_capacity(
        self, tmp_path: Path
    ):
        from app.job_runtime import run_scheduler_iteration
        from app.job_store import JobStore

        store = JobStore(tmp_path / "jobs.db")
        first_job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=busy123",
            title="Busy",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("busy123")],
        )
        second_job_id = store.create_job(
            kind="video",
            url="https://example.com/watch?v=wait123",
            title="Waiting",
            site="example.com",
            destination_dir="/data/videos",
            config={},
            items=[_item("wait123")],
        )

        busy_item = store.get_job_items(first_job_id)[0]
        waiting_item = store.get_job_items(second_job_id)[0]
        store.claim_job_item(busy_item["id"], worker_pid=8123)
        store.refresh_job_status(first_job_id)

        spawned: list[str] = []

        def spawn_worker(item: dict) -> int:
            spawned.append(item["id"])
            return 9001

        dispatched = run_scheduler_iteration(
            store,
            spawn_worker=spawn_worker,
            global_limit=1,
            default_per_job_limit=4,
        )

        refreshed_waiting_item = store.get_job_item(waiting_item["id"])

        assert dispatched == []
        assert spawned == []
        assert refreshed_waiting_item is not None
        assert refreshed_waiting_item["status"] == "queued"

    def test_spawn_worker_subprocess_builds_detached_module_command(
        self, tmp_path: Path
    ):
        from app.job_runtime import spawn_worker_subprocess

        calls: dict[str, object] = {}

        class FakeProcess:
            pid = 54321

        def fake_popen(cmd, **kwargs):
            calls["cmd"] = cmd
            calls["kwargs"] = kwargs
            return FakeProcess()

        db_path = tmp_path / "jobs.db"
        pid = spawn_worker_subprocess(
            "item-123",
            db_path,
            popen=fake_popen,
            python_executable="/usr/bin/python3",
        )

        assert pid == 54321
        assert calls["cmd"] == [
            "/usr/bin/python3",
            "-m",
            "app.job_worker_entry",
            "--db-path",
            str(db_path),
            "--item-id",
            "item-123",
        ]
        assert calls["kwargs"] == {
            "stdout": -3,
            "stderr": -3,
            "stdin": -3,
            "start_new_session": True,
        }


class TestSchedulerLoop:
    def test_run_scheduler_loop_recovers_dispatches_and_releases_lock(
        self, tmp_path: Path
    ):
        from app.job_runtime import run_scheduler_loop

        events: list[tuple[str, object]] = []

        class FakeLock:
            def acquire(self) -> bool:
                events.append(("acquire", None))
                return True

            def release(self) -> None:
                events.append(("release", None))

        class FakeStore:
            db_path = tmp_path / "jobs.db"

        stop_state = {"calls": 0}

        def should_stop() -> bool:
            stop_state["calls"] += 1
            return stop_state["calls"] >= 2

        run_scheduler_loop(
            FakeStore(),
            lock=FakeLock(),
            sleep_fn=lambda _seconds: events.append(("sleep", None)),
            should_stop=should_stop,
            recover_fn=lambda store: events.append(("recover", store.db_path)) or 1,
            iteration_fn=lambda store: events.append(("iterate", store.db_path))
            or ["item-1"],
        )

        assert events == [
            ("acquire", None),
            ("recover", tmp_path / "jobs.db"),
            ("iterate", tmp_path / "jobs.db"),
            ("release", None),
        ]

    def test_run_scheduler_loop_continues_after_transient_sqlite_lock(
        self, tmp_path: Path
    ):
        from app.job_runtime import run_scheduler_loop

        events: list[tuple[str, object]] = []

        class FakeLock:
            def acquire(self) -> bool:
                events.append(("acquire", None))
                return True

            def release(self) -> None:
                events.append(("release", None))

        class FakeStore:
            db_path = tmp_path / "jobs.db"

        attempts = {"count": 0}

        def should_stop() -> bool:
            return attempts["count"] >= 2

        def iterate(store):
            attempts["count"] += 1
            events.append(("iterate", attempts["count"]))
            if attempts["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return ["item-1"]

        run_scheduler_loop(
            FakeStore(),
            lock=FakeLock(),
            sleep_fn=lambda _seconds: events.append(("sleep", None)),
            should_stop=should_stop,
            recover_fn=lambda store: events.append(("recover", store.db_path)) or 0,
            iteration_fn=iterate,
        )

        assert events == [
            ("acquire", None),
            ("recover", tmp_path / "jobs.db"),
            ("iterate", 1),
            ("sleep", None),
            ("recover", tmp_path / "jobs.db"),
            ("iterate", 2),
            ("release", None),
        ]

    def test_run_scheduler_loop_recovers_again_after_worker_disappears(
        self, tmp_path: Path
    ):
        from app.job_runtime import run_scheduler_loop

        events: list[tuple[str, object]] = []

        class FakeLock:
            def acquire(self) -> bool:
                events.append(("acquire", None))
                return True

            def release(self) -> None:
                events.append(("release", None))

        class FakeStore:
            db_path = tmp_path / "jobs.db"

        attempts = {"count": 0}

        def should_stop() -> bool:
            return attempts["count"] >= 2

        def iterate(_store):
            attempts["count"] += 1
            events.append(("iterate", attempts["count"]))
            return []

        run_scheduler_loop(
            FakeStore(),
            lock=FakeLock(),
            sleep_fn=lambda _seconds: events.append(("sleep", None)),
            should_stop=should_stop,
            recover_fn=lambda store: events.append(("recover", attempts["count"])) or 0,
            iteration_fn=iterate,
        )

        assert events == [
            ("acquire", None),
            ("recover", 0),
            ("iterate", 1),
            ("sleep", None),
            ("recover", 1),
            ("iterate", 2),
            ("release", None),
        ]

    def test_ensure_scheduler_thread_started_only_starts_once_per_db_path(
        self, tmp_path: Path
    ):
        from app.job_runtime import ensure_scheduler_thread_started

        starts: list[str] = []

        class FakeThread:
            def __init__(self, *, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon

            def start(self) -> None:
                starts.append(self.name)

        class FakeStore:
            db_path = tmp_path / "jobs.db"

        ensure_scheduler_thread_started(
            FakeStore(),
            thread_factory=lambda **kwargs: FakeThread(**kwargs),
        )
        ensure_scheduler_thread_started(
            FakeStore(),
            thread_factory=lambda **kwargs: FakeThread(**kwargs),
        )

        assert starts == [f"hometube-scheduler-{(tmp_path / 'jobs.db').name}"]

    def test_ensure_scheduler_thread_started_restarts_dead_thread(self, tmp_path: Path):
        from app.job_runtime import ensure_scheduler_thread_started

        starts: list[str] = []

        class FakeThread:
            def __init__(self, *, target, name, daemon, alive=False):
                self.target = target
                self.name = name
                self.daemon = daemon
                self._alive = alive

            def start(self) -> None:
                starts.append(self.name)

            def is_alive(self) -> bool:
                return self._alive

        class FakeStore:
            db_path = tmp_path / "jobs-restart.db"

        dead_thread = FakeThread(
            target=lambda: None,
            name="dead-thread",
            daemon=True,
            alive=False,
        )

        ensure_scheduler_thread_started(
            FakeStore(),
            thread_factory=lambda **kwargs: dead_thread,
        )
        restarted = ensure_scheduler_thread_started(
            FakeStore(),
            thread_factory=lambda **kwargs: FakeThread(**kwargs, alive=False),
        )

        assert starts == [
            "dead-thread",
            f"hometube-scheduler-{(tmp_path / 'jobs-restart.db').name}",
        ]
        assert (
            restarted.name
            == f"hometube-scheduler-{(tmp_path / 'jobs-restart.db').name}"
        )
