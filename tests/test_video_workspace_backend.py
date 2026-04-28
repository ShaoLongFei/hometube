from pathlib import Path


class TestWorkspaceProfileAnalysis:
    def test_compute_workspace_profiles_for_video_uses_audio_analysis_and_builds_auto_best_plan(
        self, tmp_path: Path
    ):
        from app.video_workspace_backend import compute_workspace_profiles

        json_path = tmp_path / "url_info.json"
        json_path.write_text("{}", encoding="utf-8")

        calls: dict[str, object] = {}

        def fake_analyze_audio_formats(url_info, language_primary, languages_secondaries, vo_first):
            calls["audio_args"] = (
                language_primary,
                languages_secondaries,
                vo_first,
            )
            return "ja", [{"format_id": "251"}], True

        def fake_get_profiles(url_info_path, multiple_langs, audio_formats):
            calls["profiles_args"] = (url_info_path, multiple_langs, audio_formats)
            return [{"label": "AV1", "format_id": "399+251"}]

        def fake_get_available_formats(url_info):
            return [{"format_id": "399"}]

        result = compute_workspace_profiles(
            {"id": "abc123", "formats": [{"format_id": "251"}]},
            json_path,
            language_primary="zh",
            languages_secondaries="en,ja",
            vo_first=False,
            analyze_audio_formats_fn=fake_analyze_audio_formats,
            get_profiles_fn=fake_get_profiles,
            get_available_formats_fn=fake_get_available_formats,
        )

        assert result.optimal_format_profiles == [{"label": "AV1", "format_id": "399+251"}]
        assert result.available_formats_list == [{"format_id": "399"}]
        assert result.chosen_format_profiles == [{"label": "AV1", "format_id": "399+251"}]
        assert result.download_quality_strategy == "auto_best"
        assert calls["audio_args"] == ("zh", "en,ja", False)
        assert calls["profiles_args"] == (str(json_path), True, [{"format_id": "251"}])

    def test_compute_workspace_profiles_skips_playlist(self, tmp_path: Path):
        from app.video_workspace_backend import compute_workspace_profiles

        result = compute_workspace_profiles(
            {"_type": "playlist", "entries": []},
            tmp_path / "playlist.json",
            language_primary="en",
            languages_secondaries="",
            vo_first=True,
        )

        assert result.optimal_format_profiles == []
        assert result.available_formats_list == []
        assert result.chosen_format_profiles == []
        assert result.download_quality_strategy is None


class TestVideoWorkspaceInitialization:
    def test_prepare_video_workspace_loads_existing_info_and_creates_status_when_missing(
        self, tmp_path: Path
    ):
        from app.video_workspace_backend import (
            WorkspaceProfilesResult,
            prepare_video_workspace,
        )

        workspace = tmp_path / "video"
        workspace.mkdir()
        url_info_path = workspace / "url_info.json"
        url_info_path.write_text('{"id":"abc123"}', encoding="utf-8")
        status_calls: list[tuple[str, str, str, str, Path]] = []

        result = prepare_video_workspace(
            video_url="https://example.com/watch?v=abc123",
            video_id="abc123",
            video_title="Existing Video",
            video_workspace=workspace,
            load_existing_url_info=lambda path: {"id": "abc123", "title": "Existing Video"},
            fetch_url_info=lambda *_args, **_kwargs: {"error": "should-not-fetch"},
            create_initial_status_fn=lambda url, video_id, title, content_type, tmp_url_workspace: status_calls.append(
                (url, video_id, title, content_type, tmp_url_workspace)
            ),
            compute_profiles_fn=lambda url_info, json_path: WorkspaceProfilesResult(
                optimal_format_profiles=[{"format_id": "18"}],
                available_formats_list=[{"format_id": "18"}],
                chosen_format_profiles=[{"format_id": "18"}],
                download_quality_strategy="auto_best",
            ),
        )

        assert result.success is True
        assert result.url_info == {"id": "abc123", "title": "Existing Video"}
        assert result.profiles.chosen_format_profiles == [{"format_id": "18"}]
        assert status_calls == [
            (
                "https://example.com/watch?v=abc123",
                "abc123",
                "Existing Video",
                "video",
                workspace,
            )
        ]

    def test_prepare_video_workspace_fetches_when_no_existing_info(self, tmp_path: Path):
        from app.video_workspace_backend import (
            WorkspaceProfilesResult,
            prepare_video_workspace,
        )

        workspace = tmp_path / "video"
        workspace.mkdir()
        fetch_calls: list[tuple[str, Path]] = []

        result = prepare_video_workspace(
            video_url="https://example.com/watch?v=fresh123",
            video_id="fresh123",
            video_title="Fresh Video",
            video_workspace=workspace,
            load_existing_url_info=lambda path: None,
            fetch_url_info=lambda url, json_path: fetch_calls.append((url, json_path)) or {"id": "fresh123"},
            create_initial_status_fn=lambda *args, **kwargs: None,
            compute_profiles_fn=lambda url_info, json_path: WorkspaceProfilesResult(
                optimal_format_profiles=[],
                available_formats_list=[],
                chosen_format_profiles=[],
                download_quality_strategy=None,
            ),
        )

        assert result.success is True
        assert result.url_info == {"id": "fresh123"}
        assert fetch_calls == [("https://example.com/watch?v=fresh123", workspace / "url_info.json")]

    def test_prepare_video_workspace_returns_failure_for_fetch_error(self, tmp_path: Path):
        from app.video_workspace_backend import prepare_video_workspace

        workspace = tmp_path / "video"
        workspace.mkdir()

        result = prepare_video_workspace(
            video_url="https://example.com/watch?v=bad123",
            video_id="bad123",
            video_title="Bad Video",
            video_workspace=workspace,
            load_existing_url_info=lambda path: None,
            fetch_url_info=lambda url, json_path: {"error": "boom"},
            create_initial_status_fn=lambda *args, **kwargs: None,
            compute_profiles_fn=lambda *_args, **_kwargs: None,
        )

        assert result.success is False
        assert result.url_info is None
        assert result.profiles.optimal_format_profiles == []
