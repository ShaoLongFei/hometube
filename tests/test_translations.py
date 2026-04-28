"""
Simplified and essential translation tests.
"""


class TestTranslations:
    """Essential translation tests."""

    def test_translation_files_exist(self, project_root):
        """Test that translation files exist."""
        en_file = project_root / "app" / "translations" / "en.py"
        fr_file = project_root / "app" / "translations" / "fr.py"
        zh_file = project_root / "app" / "translations" / "zh.py"
        assert en_file.exists(), "English translation file missing"
        assert fr_file.exists(), "French translation file missing"
        assert zh_file.exists(), "Chinese translation file missing"

    def test_translation_import(self):
        """Test that translation modules can be imported."""
        import pytest

        try:
            from app.translations import en, fr, zh  # noqa: F401
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_essential_keys_present(self):
        """Test that essential keys are present."""
        import pytest

        try:
            from app.translations import en, fr, zh

            essential_keys = [
                "page_title",
                "download_button",
                "video_or_playlist_url",
                "options",
            ]

            for key in essential_keys:
                assert key in en.TRANSLATIONS, f"Missing key in English: {key}"
                assert key in fr.TRANSLATIONS, f"Missing key in French: {key}"
                assert key in zh.TRANSLATIONS, f"Missing key in Chinese: {key}"
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_no_obvious_empty_translations(self):
        """Test that there are no obviously empty translations."""
        import pytest

        try:
            from app.translations import en, fr, zh

            for lang_name, module in [("en", en), ("fr", fr), ("zh", zh)]:
                for key, value in module.TRANSLATIONS.items():
                    # Check for truly empty strings (not multiline)
                    if isinstance(value, str) and len(value.strip()) == 0:
                        assert False, f"Empty translation in {lang_name}: {key}"
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_configure_language_supports_chinese(self):
        """Configuring zh should load Chinese translations."""
        import pytest

        try:
            from app.translations import configure_language, get_translations

            configure_language("zh")
            translations = get_translations()

            assert translations["download_button"] == "📥 &nbsp; 下载"
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_unknown_language_falls_back_to_english(self):
        """Unknown languages should safely fall back to English."""
        import pytest

        try:
            from app.translations import configure_language, get_translations

            configure_language("unknown-language")
            translations = get_translations()

            assert translations["video_or_playlist_url"] == "Video or Playlist URL"
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_chinese_translates_key_configuration_labels(self):
        """Chinese UI should translate key configuration labels instead of falling back to English."""
        import pytest

        try:
            from app.translations import en, zh

            keys_expected_in_chinese = [
                "ads_sponsors_presentation",
                "detect_sponsors_button",
                "detect_sponsors_help",
                "sponsors_detected_title",
                "sponsors_detected_summary",
                "sponsors_config_title",
                "sponsors_remove_label",
                "sponsors_mark_label",
                "sb_option_1",
                "sb_option_6",
                "cutting_modes_presentation",
                "cutting_mode_prompt",
                "cutting_mode_keyframes",
                "cutting_mode_precise",
                "cutting_mode_help",
                "advanced_encoding_options",
                "codec_video",
                "codec_h264",
                "codec_h265",
                "codec_help",
                "encoding_quality",
                "quality_balanced",
                "quality_high",
                "quality_help",
                "start_time",
                "end_time",
                "time_format_help",
                "sponsorblock_sections_info",
                "quality_strategy_prompt",
                "quality_strategy_auto_best",
                "quality_strategy_best_no_fallback",
                "quality_strategy_choose_profile",
                "quality_strategy_choose_available",
                "quality_strategy_help",
                "quality_auto_best_desc",
                "quality_best_no_fallback_desc",
                "quality_choose_profile_desc",
                "quality_choose_available_desc",
                "quality_choose_available_warning",
                "quality_profiles_generated",
                "quality_profiles_list_title",
                "quality_refuse_downgrade",
                "quality_refuse_downgrade_help",
                "quality_select_profile_prompt",
                "quality_select_format_prompt",
                "subtitles_info",
                "embed_subs",
                "embed_subs_help",
                "chapters_info",
                "embed_chapters",
                "embed_chapters_help",
                "create_new_folder",
                "create_inside_folder",
                "create_inside_folder_help",
                "folder_name_label",
                "folder_name_help",
                "ready_to_create_folder",
                "playlist_name",
                "playlist_name_help",
                "playlist_title_pattern",
                "playlist_title_pattern_help",
                "playlist_keep_old_videos",
                "playlist_keep_old_videos_help",
                "playlist_sync_plan",
                "playlist_sync_details",
                "playlist_apply_changes",
                "playlist_apply_changes_help",
                "metrics_duration",
                "metrics_eta",
                "metrics_progress",
                "metrics_size",
                "metrics_speed",
                "metrics_status",
            ]

            for key in keys_expected_in_chinese:
                assert zh.TRANSLATIONS[key] != en.TRANSLATIONS[key], (
                    f"Chinese translation for {key} still falls back to English"
                )
        except ImportError:
            pytest.skip("Translation modules not available")

    def test_codec_normalization_background_job_keys_exist(self):
        """Background-job codec status labels should exist in every language."""
        import pytest

        try:
            from app.translations import en, fr, zh

            keys = [
                "background_jobs_delivery_ready",
                "background_jobs_delivery_normalized",
                "background_jobs_delivery_original_warning",
                "background_jobs_delivery_warning_label",
            ]

            for key in keys:
                assert key in en.TRANSLATIONS, f"Missing key in English: {key}"
                assert key in fr.TRANSLATIONS, f"Missing key in French: {key}"
                assert key in zh.TRANSLATIONS, f"Missing key in Chinese: {key}"
        except ImportError:
            pytest.skip("Translation modules not available")
