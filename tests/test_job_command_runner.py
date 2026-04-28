import sys


class TestJobCommandRunner:
    def test_run_monitored_command_emits_ffmpeg_progress_without_log_spam(self):
        from app.job_command_runner import run_monitored_command

        updates = []
        logs = []

        return_code = run_monitored_command(
            [
                sys.executable,
                "-c",
                "print('out_time_ms=5000000'); print('progress=end')",
            ],
            log_fn=logs.append,
            progress_callback=updates.append,
            command_duration_seconds=20.0,
        )

        assert return_code == 0
        assert [update.progress_percent for update in updates] == [25.0, 100.0]
        assert logs == []
