from pathlib import Path


class TestVideoDownloadService:
    def test_smart_download_with_profiles_returns_error_when_no_profiles_available(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_download_service import smart_download_with_profiles

        runtime_state = MemoryRuntimeState(
            {
                "chosen_format_profiles": [],
                "download_quality_strategy": "auto_best",
            }
        )

        result_code, error_message = smart_download_with_profiles(
            base_output="Demo",
            tmp_video_dir=tmp_path,
            embed_chapters=False,
            embed_subs=False,
            force_mp4=False,
            ytdlp_custom_args="",
            url="https://example.com/watch?v=abc123",
            do_cut=False,
            subs_selected=[],
            sb_choice="disabled",
            runtime_state=runtime_state,
            cookies_resolver=lambda _url, _runtime_state: [],
            translations={"error_no_profiles_for_download": "No profiles"},
            settings_quality_downgrade=True,
            youtube_clients=[],
        )

        assert result_code == 1
        assert error_message == "No profiles"

    def test_smart_download_with_profiles_updates_runtime_state_on_success(
        self, tmp_path: Path
    ):
        from app.download_runtime_state import MemoryRuntimeState
        from app.video_download_service import smart_download_with_profiles

        runtime_state = MemoryRuntimeState(
            {
                "chosen_format_profiles": [
                    {
                        "label": "AV1 1080p",
                        "format_id": "399+251",
                        "container": "mkv",
                        "vcodec": "av01",
                        "height": 1080,
                        "filesize_approx": 123,
                        "ext": "webm",
                    }
                ],
                "download_quality_strategy": "auto_best",
            }
        )

        calls: dict[str, object] = {}

        def fake_build_profile_command(*args, **kwargs):
            return ["yt-dlp", "--newline"]

        def fake_try_profile_with_clients(
            cmd_base,
            url,
            cookies_part,
            cookies_available,
            status_placeholder,
            progress_placeholder,
            info_placeholder,
            preferred_client,
            runtime_state,
            run_cmd_fn,
            log_fn,
        ):
            calls["cookies"] = cookies_part
            calls["url"] = url
            return True

        result_code, error_message = smart_download_with_profiles(
            base_output="Demo",
            tmp_video_dir=tmp_path,
            embed_chapters=False,
            embed_subs=False,
            force_mp4=False,
            ytdlp_custom_args="",
            url="https://example.com/watch?v=abc123",
            do_cut=False,
            subs_selected=["en"],
            sb_choice="disabled",
            runtime_state=runtime_state,
            cookies_resolver=lambda _url, _runtime_state: ["--cookies", "/tmp/site.txt"],
            translations={"error_no_profiles_for_download": "No profiles"},
            settings_quality_downgrade=True,
            youtube_clients=[],
            build_profile_command_fn=fake_build_profile_command,
            try_profile_with_clients_fn=fake_try_profile_with_clients,
            add_selected_format_fn=lambda **kwargs: None,
            mark_format_error_fn=lambda **kwargs: None,
            log_fn=lambda _message: None,
            title_log_fn=lambda _message: None,
        )

        assert result_code == 0
        assert error_message == ""
        assert runtime_state.get("downloaded_format_id") == "399+251"
        assert calls["cookies"] == ["--cookies", "/tmp/site.txt"]
        assert calls["url"] == "https://example.com/watch?v=abc123"
