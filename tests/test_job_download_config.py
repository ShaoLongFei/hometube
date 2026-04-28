from pathlib import Path


class TestJobDownloadConfig:
    def test_build_single_video_request_from_job_uses_item_and_config_fields(self):
        from app.job_download_config import build_single_video_request_from_job

        job = {
            "id": "job-1",
            "destination_dir": "/data/videos/anime",
            "config": {
                "base_output": "Episode 01",
                "embed_chapters": True,
                "embed_subs": True,
                "force_mp4": False,
                "ytdlp_custom_args": "--sleep-interval 1",
                "do_cut": False,
                "subs_selected": ["zh-Hans", "en"],
                "sb_choice": "remove",
                "requested_format_id": "399+251",
            },
        }
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 01",
            "workspace_path": "/tmp/hometube/videos/youtube/abc123",
        }

        request = build_single_video_request_from_job(job, item)

        assert request.video_url == item["video_url"]
        assert request.video_id == "abc123"
        assert request.video_title == "Episode 01"
        assert request.video_workspace == Path(item["workspace_path"])
        assert request.base_output == "Episode 01"
        assert request.embed_chapters is True
        assert request.embed_subs is True
        assert request.ytdlp_custom_args == "--sleep-interval 1"
        assert request.subs_selected == ["zh-Hans", "en"]
        assert request.sb_choice == "remove"
        assert request.requested_format_id == "399+251"
        assert request.start_sec is None
        assert request.end_sec is None
        assert request.cutting_mode == "keyframes"

    def test_build_runtime_state_from_job_uses_download_preferences(self):
        from app.job_download_config import build_runtime_state_from_job

        job = {
            "config": {
                "cookies_method": "browser",
                "browser_select": "chrome",
                "browser_profile": "Profile 2",
                "chosen_profiles": [{"format_id": "399+251"}],
                "download_quality_strategy": "choose_profile",
                "refuse_quality_downgrade_best": True,
            }
        }

        state = build_runtime_state_from_job(job)

        assert state.get("cookies_method") == "browser"
        assert state.get("browser_select") == "chrome"
        assert state.get("browser_profile") == "Profile 2"
        assert state.get("chosen_format_profiles") == [{"format_id": "399+251"}]
        assert state.get("download_quality_strategy") == "choose_profile"
        assert state.get("refuse_quality_downgrade_best") is True
        assert state.get("download_cancelled") is False

    def test_build_runtime_state_from_job_defaults_to_no_cookies(self):
        from app.job_download_config import build_runtime_state_from_job

        state = build_runtime_state_from_job({"config": {}})

        assert state.get("cookies_method") == "none"
        assert state.get("chosen_format_profiles") == []
        assert state.get("download_quality_strategy") == "auto_best"

    def test_build_single_video_request_from_playlist_job_prefers_item_title(self):
        from app.job_download_config import build_single_video_request_from_job

        job = {
            "id": "job-1",
            "kind": "playlist",
            "config": {
                "base_output": "Playlist Folder",
            },
        }
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 03",
            "workspace_path": "/tmp/hometube/videos/youtube/abc123",
        }

        request = build_single_video_request_from_job(job, item)

        assert request.base_output == "Episode 03"

    def test_build_single_video_request_from_job_preserves_cutting_fields(self):
        from app.job_download_config import build_single_video_request_from_job

        job = {
            "id": "job-1",
            "kind": "video",
            "config": {
                "base_output": "Episode 03",
                "do_cut": True,
                "start_sec": 12,
                "end_sec": 84,
                "cutting_mode": "precise",
            },
        }
        item = {
            "id": "item-1",
            "video_url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Episode 03",
            "workspace_path": "/tmp/hometube/videos/youtube/abc123",
        }

        request = build_single_video_request_from_job(job, item)

        assert request.do_cut is True
        assert request.start_sec == 12
        assert request.end_sec == 84
        assert request.cutting_mode == "precise"
