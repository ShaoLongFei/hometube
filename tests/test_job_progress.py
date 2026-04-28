class TestJobProgress:
    def test_parse_download_progress_line_extracts_percent_and_metrics(self):
        from app.job_progress import parse_progress_update

        update = parse_progress_update(
            "[download]  42.3% of 100.00MiB at 2.00MiB/s ETA 00:12"
        )

        assert update is not None
        assert update.progress_percent == 42.3
        assert update.downloaded_bytes == 42300000
        assert update.total_bytes == 100000000
        assert update.eta_seconds == 12
        assert update.status_message == "Downloading"

    def test_parse_fragment_progress_line_estimates_progress_without_sizes(self):
        from app.job_progress import parse_progress_update

        update = parse_progress_update("[download] Downloading fragment 3/10")

        assert update is not None
        assert update.progress_percent == 30.0
        assert update.downloaded_bytes is None
        assert update.total_bytes is None
        assert update.status_message == "Downloading fragments"

    def test_parse_ffmpeg_progress_line_estimates_transcoding_percent(self):
        from app.job_progress import parse_progress_update

        update = parse_progress_update(
            "out_time_ms=5000000",
            ffmpeg_duration_seconds=20.0,
        )

        assert update is not None
        assert update.progress_percent == 25.0
        assert update.status_message == "Transcoding 25.0%"

    def test_parse_ffmpeg_progress_end_reports_completion(self):
        from app.job_progress import parse_progress_update

        update = parse_progress_update(
            "progress=end",
            ffmpeg_duration_seconds=20.0,
        )

        assert update is not None
        assert update.progress_percent == 100.0
        assert update.status_message == "Transcoding 100.0%"
