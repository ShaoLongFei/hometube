class TestDownloadExecutionPlan:
    def test_explicit_profiles_override_session_fallbacks(self):
        from app.download_execution_plan import resolve_profile_download_plan

        explicit_profiles = [{"label": "AV1 1080p", "format_id": "399+251"}]
        fallback_profiles = [{"label": "VP9 720p", "format_id": "247+251"}]

        plan = resolve_profile_download_plan(
            requested_profiles=explicit_profiles,
            requested_quality_strategy="auto_best",
            fallback_profiles=fallback_profiles,
            fallback_quality_strategy="choose_profile",
            refuse_quality_downgrade_best=None,
            quality_downgrade_enabled=True,
        )

        assert plan.profiles_to_try == explicit_profiles
        assert plan.quality_strategy == "auto_best"
        assert plan.download_mode == "auto"
        assert plan.refuse_quality_downgrade is False

    def test_best_no_fallback_uses_quality_downgrade_setting_by_default(self):
        from app.download_execution_plan import resolve_profile_download_plan

        plan = resolve_profile_download_plan(
            requested_profiles=None,
            requested_quality_strategy=None,
            fallback_profiles=[{"label": "AV1 4K", "format_id": "401+251"}],
            fallback_quality_strategy="best_no_fallback",
            refuse_quality_downgrade_best=None,
            quality_downgrade_enabled=False,
        )

        assert plan.quality_strategy == "best_no_fallback"
        assert plan.download_mode == "forced"
        assert plan.refuse_quality_downgrade is True

    def test_choose_available_forces_single_profile_without_refuse_flag(self):
        from app.download_execution_plan import resolve_profile_download_plan

        plan = resolve_profile_download_plan(
            requested_profiles=None,
            requested_quality_strategy="choose_available",
            fallback_profiles=[{"label": "H264 480p", "format_id": "135+140"}],
            fallback_quality_strategy="auto_best",
            refuse_quality_downgrade_best=True,
            quality_downgrade_enabled=False,
        )

        assert plan.quality_strategy == "choose_available"
        assert plan.download_mode == "forced"
        assert plan.refuse_quality_downgrade is False

    def test_raises_when_no_profiles_are_available(self):
        import pytest

        from app.download_execution_plan import resolve_profile_download_plan

        with pytest.raises(ValueError, match="No profiles available for download"):
            resolve_profile_download_plan(
                requested_profiles=None,
                requested_quality_strategy=None,
                fallback_profiles=[],
                fallback_quality_strategy="auto_best",
                refuse_quality_downgrade_best=None,
                quality_downgrade_enabled=True,
            )
